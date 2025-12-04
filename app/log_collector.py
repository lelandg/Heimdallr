"""Log collector for CloudWatch log streaming and error detection.

Provides:
- Real-time log polling from CloudWatch
- Error pattern detection and extraction
- Log categorization by severity
- Deduplication of repeated errors
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Callable, Dict, List, Optional, Set

from app.aws_client import AWSClient, LogEvent
from app.config import AmplifyAppConfig, MonitoringSettings

log = logging.getLogger("monitor.log_collector")


class ErrorSeverity(Enum):
    """Severity levels for detected errors."""
    CRITICAL = "critical"  # Service down, data loss risk
    ERROR = "error"        # Failures requiring attention
    WARNING = "warning"    # Potential issues
    INFO = "info"          # Informational messages


@dataclass
class DetectedError:
    """An error detected from log analysis."""
    message: str
    severity: ErrorSeverity
    source_app: str
    log_group: str
    timestamp: datetime
    log_stream: str = ""
    error_type: str = ""  # timeout, exception, connection, etc.
    fingerprint: str = ""  # Hash for deduplication
    context_lines: List[str] = field(default_factory=list)
    count: int = 1  # Number of occurrences

    def __post_init__(self):
        if not self.fingerprint:
            # Create fingerprint from normalized message
            normalized = self._normalize_message(self.message)
            self.fingerprint = hashlib.md5(
                f"{self.source_app}:{self.error_type}:{normalized}".encode()
            ).hexdigest()[:12]

    @staticmethod
    def _normalize_message(message: str) -> str:
        """Normalize message for fingerprinting (remove variable parts)."""
        # Remove timestamps
        normalized = re.sub(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.\d]*Z?', '[TIME]', message)
        # Remove UUIDs
        normalized = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '[UUID]', normalized, flags=re.I)
        # Remove numbers
        normalized = re.sub(r'\d+', '[N]', normalized)
        # Remove long hex strings
        normalized = re.sub(r'[0-9a-f]{16,}', '[HEX]', normalized, flags=re.I)
        return normalized[:200]  # Truncate for consistent hashing


# Error pattern definitions
ERROR_PATTERNS = [
    # Critical patterns
    (r'FATAL|fatal|Fatal', ErrorSeverity.CRITICAL, 'fatal'),
    (r'OutOfMemory|OOM|oom', ErrorSeverity.CRITICAL, 'memory'),
    (r'SIGKILL|SIGTERM|killed', ErrorSeverity.CRITICAL, 'killed'),
    (r'crash(?:ed)?|segfault|core dump', ErrorSeverity.CRITICAL, 'crash'),

    # Error patterns
    (r'ERROR|Error|error', ErrorSeverity.ERROR, 'error'),
    (r'Exception|exception', ErrorSeverity.ERROR, 'exception'),
    (r'Traceback|traceback', ErrorSeverity.ERROR, 'traceback'),
    (r'FAILED|failed|failure', ErrorSeverity.ERROR, 'failure'),
    (r'timeout|timed out|TimeoutError', ErrorSeverity.ERROR, 'timeout'),
    (r'connection refused|ECONNREFUSED', ErrorSeverity.ERROR, 'connection'),
    (r'5\d{2}\s', ErrorSeverity.ERROR, 'http_5xx'),  # 500-599 HTTP errors
    (r'database.*error|DB.*error|sql.*error', ErrorSeverity.ERROR, 'database'),

    # Warning patterns
    (r'WARN|Warning|warn', ErrorSeverity.WARNING, 'warning'),
    (r'deprecated', ErrorSeverity.WARNING, 'deprecated'),
    (r'retry|retrying', ErrorSeverity.WARNING, 'retry'),
    (r'slow|latency|delay', ErrorSeverity.WARNING, 'performance'),
    (r'4\d{2}\s', ErrorSeverity.WARNING, 'http_4xx'),  # 400-499 HTTP errors
]


@dataclass
class LogCollector:
    """Collects and analyzes logs from CloudWatch.

    Features:
    - Periodic polling of configured log groups
    - Error pattern detection and categorization
    - Deduplication to avoid alert fatigue
    - Callback support for real-time error handling
    """

    aws_client: AWSClient
    settings: MonitoringSettings
    error_callback: Optional[Callable[[DetectedError], None]] = None

    # Internal state
    _last_fetch_time: Dict[str, datetime] = field(default_factory=dict)
    _seen_fingerprints: Dict[str, datetime] = field(default_factory=dict)
    _running: bool = False
    _poll_task: Optional[asyncio.Task] = None

    # Configuration
    dedup_window_minutes: int = 30  # Ignore duplicate errors within this window
    max_context_lines: int = 5  # Context lines to capture around errors

    async def start(self) -> None:
        """Start the log collection loop."""
        if self._running:
            log.warning("Log collector already running")
            return

        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        log.info("Log collector started")

    async def stop(self) -> None:
        """Stop the log collection loop."""
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        log.info("Log collector stopped")

    async def _poll_loop(self) -> None:
        """Main polling loop for log collection."""
        while self._running:
            try:
                await self._poll_all_apps()
            except Exception as e:
                log.error(f"Error in poll loop: {e}")

            # Wait for next poll interval
            await asyncio.sleep(self.settings.log_poll_interval)

    async def _poll_all_apps(self) -> None:
        """Poll logs from all configured Amplify apps."""
        for app in self.settings.amplify_apps:
            try:
                errors = await self.collect_errors(app)
                for error in errors:
                    # Check deduplication
                    if self._is_duplicate(error):
                        log.debug(f"Skipping duplicate error: {error.fingerprint}")
                        continue

                    # Mark as seen
                    self._seen_fingerprints[error.fingerprint] = datetime.now(timezone.utc)

                    # Invoke callback
                    if self.error_callback:
                        try:
                            self.error_callback(error)
                        except Exception as e:
                            log.error(f"Error callback failed: {e}")

                    log.info(
                        f"Detected {error.severity.value} in {app.name}: "
                        f"{error.error_type} - {error.message[:80]}..."
                    )

            except Exception as e:
                log.error(f"Failed to collect logs from {app.name}: {e}")

        # Clean up old fingerprints
        self._cleanup_fingerprints()

    async def collect_errors(
        self,
        app: AmplifyAppConfig,
    ) -> List[DetectedError]:
        """Collect and analyze errors from an Amplify app's logs.

        Args:
            app: Amplify app configuration

        Returns:
            List of detected errors
        """
        log_group = app.log_group

        # Determine time window
        last_fetch = self._last_fetch_time.get(log_group)
        if last_fetch:
            start_time = last_fetch
        else:
            start_time = datetime.now(timezone.utc) - timedelta(
                minutes=self.settings.error_lookback_minutes
            )

        # Update last fetch time
        self._last_fetch_time[log_group] = datetime.now(timezone.utc)

        # Fetch error logs
        events = await self.aws_client.fetch_error_logs(
            log_group=log_group,
            lookback_minutes=self.settings.error_lookback_minutes,
        )

        # Filter to events after start_time
        events = [e for e in events if e.timestamp > start_time]

        if not events:
            return []

        log.debug(f"Processing {len(events)} log events from {app.name}")

        # Analyze events for errors
        errors = self._analyze_events(events, app)

        return errors

    def _analyze_events(
        self,
        events: List[LogEvent],
        app: AmplifyAppConfig,
    ) -> List[DetectedError]:
        """Analyze log events and extract errors.

        Args:
            events: Log events to analyze
            app: Source app configuration

        Returns:
            List of detected errors
        """
        errors: List[DetectedError] = []
        error_counts: Dict[str, DetectedError] = {}  # fingerprint -> error

        for event in events:
            detected = self._classify_event(event, app)
            if detected:
                # Aggregate by fingerprint
                if detected.fingerprint in error_counts:
                    error_counts[detected.fingerprint].count += 1
                else:
                    error_counts[detected.fingerprint] = detected

        return list(error_counts.values())

    def _classify_event(
        self,
        event: LogEvent,
        app: AmplifyAppConfig,
    ) -> Optional[DetectedError]:
        """Classify a single log event.

        Args:
            event: Log event to classify
            app: Source app configuration

        Returns:
            DetectedError if error detected, None otherwise
        """
        message = event.message

        # Check against error patterns (highest severity first)
        for pattern, severity, error_type in ERROR_PATTERNS:
            if re.search(pattern, message, re.IGNORECASE):
                return DetectedError(
                    message=message.strip(),
                    severity=severity,
                    source_app=app.name,
                    log_group=app.log_group,
                    timestamp=event.timestamp,
                    log_stream=event.log_stream,
                    error_type=error_type,
                )

        return None

    def _is_duplicate(self, error: DetectedError) -> bool:
        """Check if error is a duplicate within the dedup window.

        Args:
            error: Error to check

        Returns:
            True if this is a duplicate
        """
        if error.fingerprint not in self._seen_fingerprints:
            return False

        last_seen = self._seen_fingerprints[error.fingerprint]
        window = timedelta(minutes=self.dedup_window_minutes)
        return datetime.now(timezone.utc) - last_seen < window

    def _cleanup_fingerprints(self) -> None:
        """Remove old fingerprints from the dedup cache."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=self.dedup_window_minutes * 2)
        expired = [fp for fp, ts in self._seen_fingerprints.items() if ts < cutoff]
        for fp in expired:
            del self._seen_fingerprints[fp]
        if expired:
            log.debug(f"Cleaned up {len(expired)} expired fingerprints")

    async def fetch_recent_errors(
        self,
        app_id: Optional[str] = None,
        minutes: int = 60,
        severity: Optional[ErrorSeverity] = None,
    ) -> List[DetectedError]:
        """Fetch recent errors across all or specific apps.

        Args:
            app_id: Optional app ID to filter
            minutes: How far back to look
            severity: Optional severity filter

        Returns:
            List of detected errors
        """
        all_errors: List[DetectedError] = []

        apps = self.settings.amplify_apps
        if app_id:
            apps = [a for a in apps if a.app_id == app_id]

        for app in apps:
            try:
                events = await self.aws_client.fetch_error_logs(
                    log_group=app.log_group,
                    lookback_minutes=minutes,
                    limit=100,
                )
                errors = self._analyze_events(events, app)
                all_errors.extend(errors)
            except Exception as e:
                log.error(f"Failed to fetch errors for {app.name}: {e}")

        # Filter by severity if specified
        if severity:
            all_errors = [e for e in all_errors if e.severity == severity]

        # Sort by timestamp
        all_errors.sort(key=lambda e: e.timestamp, reverse=True)

        return all_errors

    def get_stats(self) -> Dict:
        """Get collector statistics.

        Returns:
            Dict with collector stats
        """
        return {
            "running": self._running,
            "apps_monitored": len(self.settings.amplify_apps),
            "unique_errors_seen": len(self._seen_fingerprints),
            "poll_interval_s": self.settings.log_poll_interval,
            "dedup_window_m": self.dedup_window_minutes,
        }
