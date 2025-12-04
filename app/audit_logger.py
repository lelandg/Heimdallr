"""Audit logger for comprehensive action tracking.

Provides:
- All automated actions logged
- Before/after state capture
- Compliance reporting
- Searchable audit trail
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.action_recommender import ActionType, ActionPlan
from app.action_executor import ExecutionResult, ExecutionStatus

log = logging.getLogger("monitor.audit")


class AuditEventType(Enum):
    """Types of audit events."""
    ACTION_PLANNED = "action_planned"
    ACTION_APPROVED = "action_approved"
    ACTION_REJECTED = "action_rejected"
    ACTION_EXECUTED = "action_executed"
    ACTION_FAILED = "action_failed"
    ACTION_ROLLED_BACK = "action_rolled_back"
    SAFETY_VIOLATION = "safety_violation"
    CONFIG_CHANGED = "config_changed"
    ALERT_CREATED = "alert_created"
    ALERT_RESOLVED = "alert_resolved"
    ERROR_DETECTED = "error_detected"
    ERROR_ANALYZED = "error_analyzed"


@dataclass
class AuditEvent:
    """A single audit log entry."""
    event_id: str
    event_type: AuditEventType
    timestamp: datetime
    actor: str  # "system", "operator:name", or "llm:model"
    target_service: str
    description: str
    details: Dict[str, Any] = field(default_factory=dict)
    before_state: Optional[Dict[str, Any]] = None
    after_state: Optional[Dict[str, Any]] = None
    correlation_id: Optional[str] = None  # Link related events

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "actor": self.actor,
            "target_service": self.target_service,
            "description": self.description,
            "details": self.details,
            "before_state": self.before_state,
            "after_state": self.after_state,
            "correlation_id": self.correlation_id,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str)


class AuditLogger:
    """Comprehensive audit logging for compliance and debugging.

    Features:
    - Logs all automated actions with context
    - Captures before/after state for changes
    - Provides searchable audit trail
    - Generates compliance reports
    """

    def __init__(
        self,
        log_dir: str = "Logs",
        log_file: str = "audit.log",
        retain_days: int = 90,
    ):
        """Initialize the audit logger.

        Args:
            log_dir: Directory for audit logs
            log_file: Audit log filename
            retain_days: Days to retain logs
        """
        self.log_dir = Path(log_dir)
        self.log_file = self.log_dir / log_file
        self.retain_days = retain_days

        # Ensure log directory exists
        self.log_dir.mkdir(exist_ok=True)

        # In-memory cache for recent events (for quick access)
        self._recent_events: List[AuditEvent] = []
        self._max_cached = 1000

        # Event counter for IDs
        self._event_counter = 0

        # Setup dedicated file handler
        self._setup_file_handler()

    def _setup_file_handler(self) -> None:
        """Setup dedicated file handler for audit logs."""
        from logging.handlers import RotatingFileHandler

        audit_handler = RotatingFileHandler(
            self.log_file,
            maxBytes=50_000_000,  # 50MB
            backupCount=10,
        )
        audit_handler.setLevel(logging.INFO)
        formatter = logging.Formatter("%(message)s")  # JSON-only
        audit_handler.setFormatter(formatter)

        # Create dedicated audit logger
        self._file_logger = logging.getLogger("monitor.audit.file")
        self._file_logger.setLevel(logging.INFO)
        self._file_logger.addHandler(audit_handler)
        self._file_logger.propagate = False  # Don't propagate to root

    def _generate_event_id(self) -> str:
        """Generate unique event ID."""
        self._event_counter += 1
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        return f"AUD-{timestamp}-{self._event_counter:06d}"

    def _log_event(self, event: AuditEvent) -> None:
        """Log an event to file and cache."""
        # Write to file
        self._file_logger.info(event.to_json())

        # Add to cache
        self._recent_events.append(event)
        if len(self._recent_events) > self._max_cached:
            self._recent_events.pop(0)

        # Standard logging
        log.info(f"AUDIT: {event.event_type.value} - {event.description}")

    def log_action_planned(
        self,
        plan: ActionPlan,
        actor: str = "system",
    ) -> str:
        """Log when an action plan is created.

        Returns:
            correlation_id for tracking related events
        """
        correlation_id = plan.plan_id

        for action in plan.actions:
            event = AuditEvent(
                event_id=self._generate_event_id(),
                event_type=AuditEventType.ACTION_PLANNED,
                timestamp=datetime.now(timezone.utc),
                actor=actor,
                target_service=action.target_service,
                description=f"Action planned: {action.action_type.value}",
                details={
                    "action_type": action.action_type.value,
                    "risk_level": action.risk_level.value,
                    "confidence": action.confidence,
                    "rationale": action.rationale,
                    "requires_approval": action.requires_approval,
                },
                correlation_id=correlation_id,
            )
            self._log_event(event)

        return correlation_id

    def log_action_approved(
        self,
        plan_id: str,
        approved_by: str,
        target_service: str,
    ) -> None:
        """Log when an action is approved."""
        event = AuditEvent(
            event_id=self._generate_event_id(),
            event_type=AuditEventType.ACTION_APPROVED,
            timestamp=datetime.now(timezone.utc),
            actor=f"operator:{approved_by}",
            target_service=target_service,
            description=f"Action plan approved by {approved_by}",
            details={"plan_id": plan_id},
            correlation_id=plan_id,
        )
        self._log_event(event)

    def log_action_rejected(
        self,
        plan_id: str,
        rejected_by: str,
        target_service: str,
        reason: str,
    ) -> None:
        """Log when an action is rejected."""
        event = AuditEvent(
            event_id=self._generate_event_id(),
            event_type=AuditEventType.ACTION_REJECTED,
            timestamp=datetime.now(timezone.utc),
            actor=f"operator:{rejected_by}",
            target_service=target_service,
            description=f"Action plan rejected: {reason}",
            details={"plan_id": plan_id, "reason": reason},
            correlation_id=plan_id,
        )
        self._log_event(event)

    def log_action_executed(
        self,
        result: ExecutionResult,
        plan_id: Optional[str] = None,
        before_state: Optional[Dict] = None,
        after_state: Optional[Dict] = None,
    ) -> None:
        """Log action execution with results."""
        event_type = (
            AuditEventType.ACTION_EXECUTED
            if result.status == ExecutionStatus.SUCCESS
            else AuditEventType.ACTION_FAILED
        )

        event = AuditEvent(
            event_id=self._generate_event_id(),
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            actor="system",
            target_service=result.target_service,
            description=f"Action {result.action_type.value}: {result.status.value}",
            details={
                "action_type": result.action_type.value,
                "status": result.status.value,
                "message": result.message,
                "duration_ms": result.duration_ms,
                "execution_details": result.details,
            },
            before_state=before_state,
            after_state=after_state,
            correlation_id=plan_id,
        )
        self._log_event(event)

    def log_safety_violation(
        self,
        action_type: ActionType,
        target_service: str,
        violation_type: str,
        reason: str,
    ) -> None:
        """Log a safety guard violation."""
        event = AuditEvent(
            event_id=self._generate_event_id(),
            event_type=AuditEventType.SAFETY_VIOLATION,
            timestamp=datetime.now(timezone.utc),
            actor="safety_guard",
            target_service=target_service,
            description=f"Safety violation: {violation_type}",
            details={
                "action_type": action_type.value,
                "violation_type": violation_type,
                "reason": reason,
            },
        )
        self._log_event(event)

    def log_error_detected(
        self,
        service: str,
        error_type: str,
        message: str,
        fingerprint: str,
    ) -> str:
        """Log detection of an error.

        Returns:
            correlation_id for tracking
        """
        correlation_id = fingerprint

        event = AuditEvent(
            event_id=self._generate_event_id(),
            event_type=AuditEventType.ERROR_DETECTED,
            timestamp=datetime.now(timezone.utc),
            actor="log_collector",
            target_service=service,
            description=f"Error detected: {error_type}",
            details={
                "error_type": error_type,
                "message": message[:500],
                "fingerprint": fingerprint,
            },
            correlation_id=correlation_id,
        )
        self._log_event(event)
        return correlation_id

    def log_error_analyzed(
        self,
        service: str,
        fingerprint: str,
        analysis_model: str,
        root_cause: str,
        recommended_action: str,
    ) -> None:
        """Log LLM error analysis."""
        event = AuditEvent(
            event_id=self._generate_event_id(),
            event_type=AuditEventType.ERROR_ANALYZED,
            timestamp=datetime.now(timezone.utc),
            actor=f"llm:{analysis_model}",
            target_service=service,
            description=f"Error analyzed: {recommended_action}",
            details={
                "fingerprint": fingerprint,
                "root_cause": root_cause,
                "recommended_action": recommended_action,
                "model": analysis_model,
            },
            correlation_id=fingerprint,
        )
        self._log_event(event)

    def log_alert(
        self,
        alert_id: str,
        service: str,
        resolved: bool = False,
        resolved_by: Optional[str] = None,
    ) -> None:
        """Log alert creation or resolution."""
        event_type = AuditEventType.ALERT_RESOLVED if resolved else AuditEventType.ALERT_CREATED

        event = AuditEvent(
            event_id=self._generate_event_id(),
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            actor=f"operator:{resolved_by}" if resolved_by else "system",
            target_service=service,
            description=f"Alert {'resolved' if resolved else 'created'}: {alert_id}",
            details={"alert_id": alert_id},
            correlation_id=alert_id,
        )
        self._log_event(event)

    def search_events(
        self,
        event_type: Optional[AuditEventType] = None,
        target_service: Optional[str] = None,
        actor: Optional[str] = None,
        correlation_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[AuditEvent]:
        """Search audit events with filters.

        Args:
            event_type: Filter by event type
            target_service: Filter by service
            actor: Filter by actor
            correlation_id: Filter by correlation ID
            start_time: Start of time range
            end_time: End of time range
            limit: Maximum results

        Returns:
            List of matching events
        """
        results = []

        for event in reversed(self._recent_events):
            if len(results) >= limit:
                break

            if event_type and event.event_type != event_type:
                continue
            if target_service and event.target_service != target_service:
                continue
            if actor and event.actor != actor:
                continue
            if correlation_id and event.correlation_id != correlation_id:
                continue
            if start_time and event.timestamp < start_time:
                continue
            if end_time and event.timestamp > end_time:
                continue

            results.append(event)

        return results

    def get_events_by_correlation(self, correlation_id: str) -> List[AuditEvent]:
        """Get all events with a specific correlation ID."""
        return [e for e in self._recent_events if e.correlation_id == correlation_id]

    def generate_compliance_report(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> Dict[str, Any]:
        """Generate compliance report for a time period.

        Args:
            start_date: Report start date
            end_date: Report end date

        Returns:
            Compliance report dictionary
        """
        events = self.search_events(
            start_time=start_date,
            end_time=end_date,
            limit=10000,
        )

        # Aggregate statistics
        by_type = {}
        by_service = {}
        by_actor = {}
        safety_violations = []
        failed_actions = []

        for event in events:
            # Count by type
            type_name = event.event_type.value
            by_type[type_name] = by_type.get(type_name, 0) + 1

            # Count by service
            by_service[event.target_service] = by_service.get(event.target_service, 0) + 1

            # Count by actor
            by_actor[event.actor] = by_actor.get(event.actor, 0) + 1

            # Track violations
            if event.event_type == AuditEventType.SAFETY_VIOLATION:
                safety_violations.append({
                    "timestamp": event.timestamp.isoformat(),
                    "service": event.target_service,
                    "reason": event.details.get("reason", ""),
                })

            # Track failures
            if event.event_type == AuditEventType.ACTION_FAILED:
                failed_actions.append({
                    "timestamp": event.timestamp.isoformat(),
                    "service": event.target_service,
                    "action": event.details.get("action_type", ""),
                    "message": event.details.get("message", ""),
                })

        return {
            "report_period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
            "total_events": len(events),
            "events_by_type": by_type,
            "events_by_service": by_service,
            "events_by_actor": by_actor,
            "safety_violations": safety_violations,
            "failed_actions": failed_actions,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_stats(self) -> Dict:
        """Get audit logger statistics."""
        return {
            "cached_events": len(self._recent_events),
            "log_file": str(self.log_file),
            "retain_days": self.retain_days,
        }
