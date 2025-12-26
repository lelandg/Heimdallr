#!/usr/bin/env python3
"""AWS Monitor - Main entry point.

LLM-powered monitoring for AWS Amplify and EC2 services.
Provides real-time error detection, analysis, and automated remediation.
"""
from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.config import AppConfig
from app.aws_client import AWSClient
from app.llm_client import LLMClient
from app.log_collector import LogCollector, DetectedError
from app.service_monitor import ServiceMonitor, HealthChange
from app.alert_manager import AlertManager, Alert
from app.error_analyzer import ErrorAnalyzer
from app.llm_orchestrator import LLMOrchestrator
from app.action_recommender import ActionRecommender
from app.action_executor import ActionExecutor
from app.safety_guard import SafetyGuard, SafetyCheckResult
from app.audit_logger import AuditLogger
from app.notifier import Notifier
from app.api import app as api_app, set_monitor_app


def setup_logging(config: AppConfig) -> None:
    """Configure application logging.

    Args:
        config: Application configuration
    """
    from logging.handlers import RotatingFileHandler

    log_dir = Path(config.logging.log_dir)
    log_dir.mkdir(exist_ok=True)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config.logging.log_level.upper()))

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S"
    )
    console_handler.setFormatter(console_format)
    root_logger.addHandler(console_handler)

    # File handler
    file_handler = RotatingFileHandler(
        log_dir / "monitor.log",
        maxBytes=config.logging.log_max_bytes,
        backupCount=config.logging.log_backup_count,
    )
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s"
    )
    file_handler.setFormatter(file_format)
    root_logger.addHandler(file_handler)

    # LLM interactions log (separate file)
    if config.logging.log_llm_interactions:
        llm_handler = RotatingFileHandler(
            log_dir / "llm_interactions.log",
            maxBytes=config.logging.log_max_bytes,
            backupCount=config.logging.log_backup_count,
        )
        llm_handler.setLevel(logging.INFO)
        llm_handler.setFormatter(file_format)
        logging.getLogger("monitor.llm.interactions").addHandler(llm_handler)


class MonitorApp:
    """Main monitoring application.

    Coordinates all monitoring components:
    - Log collection and error detection
    - Service health monitoring
    - LLM-powered error analysis
    - Automated remediation
    - Notifications and audit logging
    """

    def __init__(self, config: AppConfig):
        """Initialize the monitor application.

        Args:
            config: Application configuration
        """
        self.config = config
        self.log = logging.getLogger("monitor.app")

        # Shutdown coordination
        self._shutdown_event = asyncio.Event()
        self._running = False

        # Initialize components (will be set up in start())
        self.aws_client: AWSClient = None
        self.llm_client: LLMClient = None
        self.log_collector: LogCollector = None
        self.service_monitor: ServiceMonitor = None
        self.alert_manager: AlertManager = None
        self.error_analyzer: ErrorAnalyzer = None
        self.llm_orchestrator: LLMOrchestrator = None
        self.action_recommender: ActionRecommender = None
        self.action_executor: ActionExecutor = None
        self.safety_guard: SafetyGuard = None
        self.audit_logger: AuditLogger = None
        self.notifier: Notifier = None

    async def start(self) -> None:
        """Start the monitoring application."""
        self.log.info("=" * 60)
        self.log.info("AWS Monitor Starting")
        self.log.info("=" * 60)

        # Initialize AWS client
        self.aws_client = AWSClient(self.config.aws)
        self.log.info(f"Region: {self.config.aws.region}")

        # Test AWS connections
        self.log.info("Testing AWS connections...")
        aws_results = await self.aws_client.test_connection()
        for service, connected in aws_results.items():
            status = "OK" if connected else "FAILED"
            self.log.info(f"  AWS {service}: {status}")

        if not any(aws_results.values()):
            self.log.error("No AWS services available. Check credentials.")
            return

        # Initialize LLM client
        try:
            self.llm_client = LLMClient(self.config.llm)
            self.log.info(f"Primary LLM: {self.config.llm.primary_model}")
            self.log.info(f"Analysis LLM: {self.config.llm.analysis_model}")
        except ImportError as e:
            self.log.error(f"Failed to initialize LLM client: {e}")
            self.log.error("Run: pip install -r requirements.txt")
            return

        # Test LLM connections
        self.log.info("Testing LLM provider connections...")
        llm_results = await self.llm_client.test_connection()
        for provider, connected in llm_results.items():
            status = "OK" if connected else "FAILED"
            self.log.info(f"  {provider}: {status}")

        if not any(llm_results.values()):
            self.log.warning("No LLM providers available. Analysis will use fallbacks.")

        # Initialize remaining components
        self._init_components()

        # Set up API
        set_monitor_app(self)

        # Start monitoring loops
        self._running = True
        await self._run_monitoring_loop()

    def _init_components(self) -> None:
        """Initialize all monitoring components."""
        # Audit logger (needed by other components)
        self.audit_logger = AuditLogger(
            log_dir=self.config.logging.log_dir,
        )

        # Notifier
        self.notifier = Notifier(self.config.notifications)

        # Alert manager with notification callback
        self.alert_manager = AlertManager(
            alert_callback=self._on_alert_created,
            escalation_callback=self._on_alert_escalation,
        )

        # Safety guard
        self.safety_guard = SafetyGuard(
            settings=self.config.actions,
            approval_callback=self._on_approval_needed,
        )

        # Action recommender
        self.action_recommender = ActionRecommender(
            settings=self.config.actions,
            approval_callback=self._on_approval_needed,
        )

        # Action executor
        self.action_executor = ActionExecutor(
            aws_client=self.aws_client,
            pre_execution_callback=self._pre_execution_check,
            post_execution_callback=self._post_execution_log,
        )

        # LLM orchestrator
        self.llm_orchestrator = LLMOrchestrator(
            llm_client=self.llm_client,
            settings=self.config.llm,
            on_model_switch=self._on_model_switch,
        )

        # Error analyzer
        self.error_analyzer = ErrorAnalyzer(self.llm_client)

        # Service monitor
        self.service_monitor = ServiceMonitor(
            aws_client=self.aws_client,
            settings=self.config.monitoring,
            health_change_callback=self._on_health_change,
        )

        # Log collector
        self.log_collector = LogCollector(
            aws_client=self.aws_client,
            settings=self.config.monitoring,
            error_callback=self._on_error_detected,
        )

        self.log.info("All components initialized")

    async def _run_monitoring_loop(self) -> None:
        """Main monitoring loop."""
        import uvicorn

        self.log.info(f"Monitoring {len(self.config.monitoring.amplify_apps)} Amplify apps")
        self.log.info(f"Monitoring {len(self.config.monitoring.ec2_instances)} EC2 instances")
        self.log.info(f"Log poll interval: {self.config.monitoring.log_poll_interval}s")
        self.log.info(f"Health check interval: {self.config.monitoring.health_check_interval}s")

        # Start API server
        api_config = uvicorn.Config(
            api_app,
            host="0.0.0.0",
            port=8000,
            log_level="warning",  # Reduce uvicorn log noise
        )
        api_server = uvicorn.Server(api_config)

        # Start background tasks
        tasks = [
            asyncio.create_task(self.log_collector.start(), name="log_collector"),
            asyncio.create_task(self.service_monitor.start(), name="service_monitor"),
            asyncio.create_task(self.alert_manager.start(), name="alert_manager"),
            asyncio.create_task(api_server.serve(), name="api_server"),
        ]

        self.log.info("Monitor started. Press Ctrl+C to stop.")
        self.log.info("API server running on http://0.0.0.0:8000")

        try:
            # Wait for shutdown signal
            await self._shutdown_event.wait()
        except asyncio.CancelledError:
            pass
        finally:
            # Stop all components
            self.log.info("Stopping monitoring...")
            await self.log_collector.stop()
            await self.service_monitor.stop()
            await self.alert_manager.stop()
            await self.notifier.close()

            # Cancel remaining tasks
            for task in tasks:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

            self.log.info("Monitor stopped")

    def _on_error_detected(self, error: DetectedError) -> None:
        """Handle detected error from log collector."""
        self.log.info(f"Error detected in {error.source_app}: {error.error_type}")

        # Log to audit
        self.audit_logger.log_error_detected(
            service=error.source_app,
            error_type=error.error_type,
            message=error.message,
            fingerprint=error.fingerprint,
        )

        # Create alert
        alert = self.alert_manager.process_error(error)
        if alert:
            # Schedule async analysis
            asyncio.create_task(self._analyze_and_respond(error, alert))

    async def _analyze_and_respond(self, error: DetectedError, alert: Alert) -> None:
        """Analyze error and potentially take action."""
        try:
            # Perform LLM analysis
            analysis = await self.error_analyzer.quick_triage(error)

            self.log.info(
                f"Analysis: {analysis.category.value} - "
                f"{analysis.recommended_action.value} (confidence: {analysis.confidence:.0%})"
            )

            # Log analysis
            self.audit_logger.log_error_analyzed(
                service=error.source_app,
                fingerprint=error.fingerprint,
                analysis_model=analysis.model_used,
                root_cause=analysis.root_cause,
                recommended_action=analysis.recommended_action.value,
            )

            # Get current service health
            service_id = f"amplify:{error.source_app}" if "amplify" in error.log_group else f"ec2:{error.source_app}"
            service_health = self.service_monitor.get_health(service_id)

            # Generate action recommendation
            plan = self.action_recommender.recommend_for_analysis(analysis, service_health)

            if plan.actions:
                # Log plan
                self.audit_logger.log_action_planned(plan)

                # Check safety
                for action in plan.actions:
                    safety_result = self.safety_guard.check_action(
                        action.action_type,
                        action.target_service,
                        action.risk_level,
                    )

                    if safety_result == SafetyCheckResult.ALLOWED:
                        if action.is_safe_to_execute:
                            # Execute automatically
                            result = await self.action_executor.execute_plan(plan)
                            self.action_recommender.record_execution(
                                plan,
                                result.overall_status.value == "success",
                                result.overall_status.value,
                            )
                    elif safety_result == SafetyCheckResult.REQUIRES_APPROVAL:
                        self.log.info(f"Action requires approval: {action.action_type.value}")
                    else:
                        self.log.warning(f"Action blocked: {safety_result.value}")

        except Exception as e:
            self.log.error(f"Error in analysis pipeline: {e}")

    def _on_health_change(self, change: HealthChange) -> None:
        """Handle health state change from service monitor."""
        self.log.info(
            f"Health change: {change.service_name} "
            f"{change.old_state.value} -> {change.new_state.value}"
        )

        # Create/update alert
        self.alert_manager.process_health_change(change)

        # Send notification
        asyncio.create_task(self.notifier.notify_health_change(change))

    def _on_alert_created(self, alert: Alert) -> None:
        """Handle new alert creation."""
        self.log.info(f"Alert created: {alert.alert_id} - {alert.title}")
        self.audit_logger.log_alert(alert.alert_id, alert.source_service, resolved=False)
        asyncio.create_task(self.notifier.notify_alert(alert))

    def _on_alert_escalation(self, alert: Alert, action: str) -> None:
        """Handle alert escalation."""
        self.log.warning(f"Alert escalation: {alert.alert_id} - {action}")
        # Could trigger PagerDuty, on-call rotation, etc.

    def _on_approval_needed(self, plan, reason: str = "") -> None:
        """Handle action requiring approval."""
        self.log.info(f"Approval needed for plan {plan.plan_id}: {reason}")
        # Could send to Slack for approval, etc.

    def _pre_execution_check(self, action) -> bool:
        """Pre-execution safety check."""
        result = self.safety_guard.check_action(
            action.action_type,
            action.target_service,
            action.risk_level,
        )
        return result == SafetyCheckResult.ALLOWED

    def _post_execution_log(self, result) -> None:
        """Log execution result."""
        self.audit_logger.log_action_executed(result)
        self.safety_guard.record_action(
            result.action_type,
            result.target_service,
            result.status.value == "success",
        )

    def _on_model_switch(self, old_model: str, new_model: str, reason: str) -> None:
        """Handle LLM model switch."""
        self.log.info(f"Model switch: {old_model} -> {new_model} ({reason})")

    def shutdown(self) -> None:
        """Trigger graceful shutdown."""
        self.log.info("Shutdown requested")
        self._shutdown_event.set()


async def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success)
    """
    log = logging.getLogger("monitor")

    # Load configuration
    config = AppConfig.load()
    setup_logging(config)

    # Create and start application
    app = MonitorApp(config)

    # Setup signal handlers
    def signal_handler(signum, frame):
        log.info(f"Received signal {signum}")
        app.shutdown()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run
    try:
        await app.start()
        return 0
    except Exception as e:
        log.exception(f"Fatal error: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
