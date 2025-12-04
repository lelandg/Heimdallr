"""Service health monitor for EC2 and Amplify services.

Provides:
- Periodic health checks for EC2 instances
- Amplify deployment status monitoring
- Service dependency tracking
- Health state change detection
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Dict, List, Optional

from app.aws_client import AWSClient, AmplifyApp, EC2Instance
from app.config import MonitoringSettings, AmplifyAppConfig, EC2InstanceConfig

log = logging.getLogger("monitor.service_monitor")


class HealthState(Enum):
    """Overall health state for a service."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ServiceHealth:
    """Health status for a monitored service."""
    service_id: str
    service_name: str
    service_type: str  # "amplify" or "ec2"
    state: HealthState
    message: str = ""
    last_check: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_state_change: Optional[datetime] = None
    details: Dict = field(default_factory=dict)

    @property
    def is_healthy(self) -> bool:
        """Check if service is in healthy state."""
        return self.state == HealthState.HEALTHY


@dataclass
class HealthChange:
    """Represents a change in service health."""
    service_id: str
    service_name: str
    service_type: str
    old_state: HealthState
    new_state: HealthState
    timestamp: datetime
    message: str = ""


class ServiceMonitor:
    """Monitors health of EC2 and Amplify services.

    Features:
    - Periodic health checks
    - State change detection and callbacks
    - Service dependency tracking
    - Health history
    """

    def __init__(
        self,
        aws_client: AWSClient,
        settings: MonitoringSettings,
        health_change_callback: Optional[Callable[[HealthChange], None]] = None,
    ):
        """Initialize the service monitor.

        Args:
            aws_client: AWS client for API calls
            settings: Monitoring configuration
            health_change_callback: Optional callback for health changes
        """
        self.aws_client = aws_client
        self.settings = settings
        self.health_change_callback = health_change_callback

        # Current health state for all services
        self._health_state: Dict[str, ServiceHealth] = {}

        # Health history (recent changes)
        self._health_history: List[HealthChange] = []
        self._max_history = 100

        # Monitoring state
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the health monitoring loop."""
        if self._running:
            log.warning("Service monitor already running")
            return

        self._running = True

        # Initial health check
        await self._check_all_services()

        # Start monitoring loop
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        log.info("Service monitor started")

    async def stop(self) -> None:
        """Stop the health monitoring loop."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        log.info("Service monitor stopped")

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            # Wait for check interval
            await asyncio.sleep(self.settings.health_check_interval)

            try:
                await self._check_all_services()
            except Exception as e:
                log.error(f"Error in monitor loop: {e}")

    async def _check_all_services(self) -> None:
        """Check health of all configured services."""
        # Check Amplify apps
        for app in self.settings.amplify_apps:
            try:
                await self._check_amplify_app(app)
            except Exception as e:
                log.error(f"Failed to check Amplify app {app.name}: {e}")

        # Check EC2 instances
        for instance in self.settings.ec2_instances:
            try:
                await self._check_ec2_instance(instance)
            except Exception as e:
                log.error(f"Failed to check EC2 instance {instance.name}: {e}")

    async def _check_amplify_app(self, app: AmplifyAppConfig) -> ServiceHealth:
        """Check health of an Amplify app.

        Args:
            app: Amplify app configuration

        Returns:
            Updated ServiceHealth
        """
        service_id = f"amplify:{app.app_id}"

        try:
            status = await self.aws_client.get_amplify_app_status(app.app_id)

            # Determine health state from status
            if status.status in {"SUCCEED", "RUNNING"}:
                state = HealthState.HEALTHY
                message = f"Deployment successful on {status.branch}"
            elif status.status == "PENDING":
                state = HealthState.DEGRADED
                message = f"Deployment pending on {status.branch}"
            elif status.status == "FAILED":
                state = HealthState.UNHEALTHY
                message = f"Deployment failed on {status.branch}"
            else:
                state = HealthState.UNKNOWN
                message = f"Unknown status: {status.status}"

            health = ServiceHealth(
                service_id=service_id,
                service_name=app.name,
                service_type="amplify",
                state=state,
                message=message,
                details={
                    "app_id": app.app_id,
                    "status": status.status,
                    "branch": status.branch,
                    "domain": status.domain,
                    "last_deploy": status.last_deploy_time.isoformat() if status.last_deploy_time else None,
                },
            )

        except Exception as e:
            health = ServiceHealth(
                service_id=service_id,
                service_name=app.name,
                service_type="amplify",
                state=HealthState.UNKNOWN,
                message=f"Check failed: {e}",
            )

        # Update state and detect changes
        self._update_health(health)
        return health

    async def _check_ec2_instance(self, instance: EC2InstanceConfig) -> ServiceHealth:
        """Check health of an EC2 instance.

        Args:
            instance: EC2 instance configuration

        Returns:
            Updated ServiceHealth
        """
        service_id = f"ec2:{instance.instance_id}"

        try:
            status = await self.aws_client.get_instance_status(instance.instance_id)

            # Determine health state
            if status.is_healthy:
                state = HealthState.HEALTHY
                message = f"Instance running, status checks passing"
            elif status.state == "running" and status.status_check != "ok":
                state = HealthState.DEGRADED
                message = f"Instance running but status check: {status.status_check}"
            elif status.state in {"stopped", "stopping"}:
                state = HealthState.UNHEALTHY
                message = f"Instance {status.state}"
            elif status.state in {"pending", "shutting-down"}:
                state = HealthState.DEGRADED
                message = f"Instance {status.state}"
            else:
                state = HealthState.UNKNOWN
                message = f"Unknown state: {status.state}"

            health = ServiceHealth(
                service_id=service_id,
                service_name=instance.name,
                service_type="ec2",
                state=state,
                message=message,
                details={
                    "instance_id": instance.instance_id,
                    "state": status.state,
                    "status_check": status.status_check,
                    "instance_type": status.instance_type,
                    "availability_zone": status.availability_zone,
                    "launch_time": status.launch_time.isoformat() if status.launch_time else None,
                },
            )

        except Exception as e:
            health = ServiceHealth(
                service_id=service_id,
                service_name=instance.name,
                service_type="ec2",
                state=HealthState.UNKNOWN,
                message=f"Check failed: {e}",
            )

        # Update state and detect changes
        self._update_health(health)
        return health

    def _update_health(self, health: ServiceHealth) -> None:
        """Update health state and detect changes.

        Args:
            health: New health status
        """
        service_id = health.service_id
        old_health = self._health_state.get(service_id)

        # Check for state change
        if old_health and old_health.state != health.state:
            health.last_state_change = datetime.now(timezone.utc)

            change = HealthChange(
                service_id=service_id,
                service_name=health.service_name,
                service_type=health.service_type,
                old_state=old_health.state,
                new_state=health.state,
                timestamp=health.last_state_change,
                message=health.message,
            )

            # Add to history
            self._health_history.append(change)
            if len(self._health_history) > self._max_history:
                self._health_history.pop(0)

            log.info(
                f"Health change: {health.service_name} "
                f"{old_health.state.value} -> {health.state.value}: {health.message}"
            )

            # Invoke callback
            if self.health_change_callback:
                try:
                    self.health_change_callback(change)
                except Exception as e:
                    log.error(f"Health change callback failed: {e}")

        elif old_health:
            # Preserve last state change time
            health.last_state_change = old_health.last_state_change

        # Update stored state
        self._health_state[service_id] = health

    def get_health(self, service_id: str) -> Optional[ServiceHealth]:
        """Get current health for a service.

        Args:
            service_id: Service identifier (e.g., "amplify:app-id")

        Returns:
            ServiceHealth or None if not found
        """
        return self._health_state.get(service_id)

    def get_all_health(self) -> Dict[str, ServiceHealth]:
        """Get current health for all services.

        Returns:
            Dict mapping service_id to ServiceHealth
        """
        return self._health_state.copy()

    def get_unhealthy_services(self) -> List[ServiceHealth]:
        """Get all services that are not healthy.

        Returns:
            List of unhealthy ServiceHealth entries
        """
        return [
            h for h in self._health_state.values()
            if h.state in {HealthState.UNHEALTHY, HealthState.DEGRADED}
        ]

    def get_recent_changes(self, limit: int = 10) -> List[HealthChange]:
        """Get recent health changes.

        Args:
            limit: Maximum number of changes to return

        Returns:
            List of recent HealthChange entries, newest first
        """
        return list(reversed(self._health_history[-limit:]))

    def get_stats(self) -> Dict:
        """Get monitor statistics.

        Returns:
            Dict with monitor stats
        """
        states = {s.value: 0 for s in HealthState}
        for health in self._health_state.values():
            states[health.state.value] += 1

        return {
            "running": self._running,
            "total_services": len(self._health_state),
            "health_states": states,
            "recent_changes": len(self._health_history),
            "check_interval_s": self.settings.health_check_interval,
        }

    async def force_check(self, service_id: Optional[str] = None) -> List[ServiceHealth]:
        """Force an immediate health check.

        Args:
            service_id: Optional specific service to check, or all if None

        Returns:
            List of updated ServiceHealth entries
        """
        results = []

        if service_id:
            # Check specific service
            if service_id.startswith("amplify:"):
                app_id = service_id.split(":", 1)[1]
                apps = [a for a in self.settings.amplify_apps if a.app_id == app_id]
                for app in apps:
                    health = await self._check_amplify_app(app)
                    results.append(health)
            elif service_id.startswith("ec2:"):
                instance_id = service_id.split(":", 1)[1]
                instances = [i for i in self.settings.ec2_instances if i.instance_id == instance_id]
                for instance in instances:
                    health = await self._check_ec2_instance(instance)
                    results.append(health)
        else:
            # Check all services
            await self._check_all_services()
            results = list(self._health_state.values())

        return results
