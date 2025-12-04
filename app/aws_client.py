"""AWS client wrapper for CloudWatch, EC2, and Amplify integration.

Provides async access to AWS services needed for monitoring:
- CloudWatch Logs for log retrieval and filtering
- EC2 for instance health and management
- Amplify for app status and deployment control
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Dict, List, Optional

from app.config import AWSSettings, AmplifyAppConfig, EC2InstanceConfig

log = logging.getLogger("monitor.aws")


class AWSError(Exception):
    """Base exception for AWS errors."""
    pass


class AWSConnectionError(AWSError):
    """Raised when unable to connect to AWS."""
    pass


class AWSResourceNotFoundError(AWSError):
    """Raised when requested AWS resource doesn't exist."""
    pass


@dataclass
class LogEvent:
    """A single log event from CloudWatch."""
    timestamp: datetime
    message: str
    log_stream: str
    ingestion_time: Optional[datetime] = None

    @classmethod
    def from_aws(cls, event: Dict[str, Any], stream_name: str = "") -> "LogEvent":
        """Create LogEvent from AWS API response."""
        return cls(
            timestamp=datetime.fromtimestamp(
                event.get("timestamp", 0) / 1000, tz=timezone.utc
            ),
            message=event.get("message", ""),
            log_stream=stream_name or event.get("logStreamName", ""),
            ingestion_time=datetime.fromtimestamp(
                event.get("ingestionTime", 0) / 1000, tz=timezone.utc
            ) if event.get("ingestionTime") else None,
        )


@dataclass
class EC2Instance:
    """EC2 instance status information."""
    instance_id: str
    name: str
    state: str  # running, stopped, pending, etc.
    status_check: str  # ok, impaired, initializing, etc.
    launch_time: Optional[datetime] = None
    instance_type: str = ""
    availability_zone: str = ""

    @property
    def is_healthy(self) -> bool:
        """Check if instance is running and passing status checks."""
        return self.state == "running" and self.status_check == "ok"


@dataclass
class AmplifyApp:
    """Amplify application status information."""
    app_id: str
    name: str
    status: str  # RUNNING, PENDING, FAILED, etc.
    last_deploy_time: Optional[datetime] = None
    branch: str = ""
    domain: str = ""

    @property
    def is_healthy(self) -> bool:
        """Check if app is in healthy state."""
        return self.status in {"RUNNING", "SUCCEED"}


class AWSClient:
    """Async AWS client for monitoring operations.

    Uses aiobotocore for async AWS API calls. Provides methods for:
    - CloudWatch Logs: fetch_logs, filter_errors, tail_logs
    - EC2: get_instance_status, reboot_instance
    - Amplify: get_app_status, start_deployment
    """

    def __init__(self, settings: AWSSettings):
        """Initialize AWS client.

        Args:
            settings: AWS configuration settings
        """
        self.settings = settings
        self._session = None
        self._initialized = False

    async def _get_session(self):
        """Get or create aiobotocore session."""
        if self._session is None:
            try:
                from aiobotocore.session import get_session
                self._session = get_session()
            except ImportError:
                log.error("aiobotocore not installed. Run: pip install aiobotocore")
                raise AWSConnectionError("aiobotocore not installed")
        return self._session

    async def _get_client(self, service: str):
        """Get an AWS service client context manager.

        Args:
            service: AWS service name (logs, ec2, amplify)

        Returns:
            Async context manager for the service client
        """
        session = await self._get_session()
        return session.create_client(
            service,
            region_name=self.settings.region,
        )

    # =========================================================================
    # CloudWatch Logs Operations
    # =========================================================================

    async def fetch_logs(
        self,
        log_group: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        filter_pattern: Optional[str] = None,
        limit: int = 100,
    ) -> List[LogEvent]:
        """Fetch logs from a CloudWatch log group.

        Args:
            log_group: Log group name (e.g., /aws/amplify/app-id)
            start_time: Start of time range (default: 5 minutes ago)
            end_time: End of time range (default: now)
            filter_pattern: CloudWatch filter pattern (e.g., "ERROR" or "?ERROR ?Exception")
            limit: Maximum number of events to return

        Returns:
            List of LogEvent objects, newest first
        """
        if start_time is None:
            start_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        if end_time is None:
            end_time = datetime.now(timezone.utc)

        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)

        events: List[LogEvent] = []

        try:
            async with await self._get_client("logs") as client:
                kwargs: Dict[str, Any] = {
                    "logGroupName": log_group,
                    "startTime": start_ms,
                    "endTime": end_ms,
                    "limit": limit,
                }
                if filter_pattern:
                    kwargs["filterPattern"] = filter_pattern

                paginator = client.get_paginator("filter_log_events")
                async for page in paginator.paginate(**kwargs):
                    for event in page.get("events", []):
                        events.append(LogEvent.from_aws(event))
                        if len(events) >= limit:
                            break
                    if len(events) >= limit:
                        break

        except Exception as e:
            error_msg = str(e)
            if "ResourceNotFoundException" in error_msg:
                raise AWSResourceNotFoundError(f"Log group not found: {log_group}")
            log.error(f"Error fetching logs from {log_group}: {e}")
            raise AWSError(f"Failed to fetch logs: {e}")

        # Sort by timestamp, newest first
        events.sort(key=lambda e: e.timestamp, reverse=True)
        log.debug(f"Fetched {len(events)} log events from {log_group}")
        return events

    async def fetch_error_logs(
        self,
        log_group: str,
        lookback_minutes: int = 5,
        limit: int = 50,
    ) -> List[LogEvent]:
        """Fetch error logs from a CloudWatch log group.

        Uses a filter pattern to find common error indicators.

        Args:
            log_group: Log group name
            lookback_minutes: How many minutes back to search
            limit: Maximum number of events

        Returns:
            List of error LogEvents
        """
        # CloudWatch filter pattern for common errors
        error_pattern = '?ERROR ?Error ?error ?FATAL ?Fatal ?Exception ?exception ?FAILED ?failed ?Traceback'

        return await self.fetch_logs(
            log_group=log_group,
            start_time=datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes),
            filter_pattern=error_pattern,
            limit=limit,
        )

    async def get_log_streams(
        self,
        log_group: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Get recent log streams for a log group.

        Args:
            log_group: Log group name
            limit: Maximum number of streams

        Returns:
            List of log stream info dicts
        """
        try:
            async with await self._get_client("logs") as client:
                response = await client.describe_log_streams(
                    logGroupName=log_group,
                    orderBy="LastEventTime",
                    descending=True,
                    limit=limit,
                )
                return response.get("logStreams", [])

        except Exception as e:
            log.error(f"Error getting log streams for {log_group}: {e}")
            return []

    # =========================================================================
    # EC2 Operations
    # =========================================================================

    async def get_instance_status(
        self,
        instance_id: str,
    ) -> EC2Instance:
        """Get status of an EC2 instance.

        Args:
            instance_id: EC2 instance ID

        Returns:
            EC2Instance with current status
        """
        try:
            async with await self._get_client("ec2") as client:
                # Get instance details
                instances_resp = await client.describe_instances(
                    InstanceIds=[instance_id]
                )

                reservations = instances_resp.get("Reservations", [])
                if not reservations or not reservations[0].get("Instances"):
                    raise AWSResourceNotFoundError(f"Instance not found: {instance_id}")

                instance = reservations[0]["Instances"][0]

                # Get status checks
                status_resp = await client.describe_instance_status(
                    InstanceIds=[instance_id],
                    IncludeAllInstances=True,
                )

                statuses = status_resp.get("InstanceStatuses", [])
                status_check = "unknown"
                if statuses:
                    instance_status = statuses[0].get("InstanceStatus", {}).get("Status", "unknown")
                    system_status = statuses[0].get("SystemStatus", {}).get("Status", "unknown")
                    status_check = "ok" if instance_status == "ok" and system_status == "ok" else "impaired"

                # Extract name from tags
                name = ""
                for tag in instance.get("Tags", []):
                    if tag.get("Key") == "Name":
                        name = tag.get("Value", "")
                        break

                return EC2Instance(
                    instance_id=instance_id,
                    name=name,
                    state=instance.get("State", {}).get("Name", "unknown"),
                    status_check=status_check,
                    launch_time=instance.get("LaunchTime"),
                    instance_type=instance.get("InstanceType", ""),
                    availability_zone=instance.get("Placement", {}).get("AvailabilityZone", ""),
                )

        except AWSResourceNotFoundError:
            raise
        except Exception as e:
            log.error(f"Error getting status for instance {instance_id}: {e}")
            raise AWSError(f"Failed to get instance status: {e}")

    async def get_all_instance_statuses(
        self,
        instances: List[EC2InstanceConfig],
    ) -> Dict[str, EC2Instance]:
        """Get status of multiple EC2 instances.

        Args:
            instances: List of instance configurations

        Returns:
            Dict mapping instance_id to EC2Instance
        """
        results = {}
        for config in instances:
            try:
                status = await self.get_instance_status(config.instance_id)
                status.name = config.name or status.name  # Use config name if provided
                results[config.instance_id] = status
            except Exception as e:
                log.warning(f"Failed to get status for {config.instance_id}: {e}")
                results[config.instance_id] = EC2Instance(
                    instance_id=config.instance_id,
                    name=config.name,
                    state="error",
                    status_check="unknown",
                )
        return results

    async def reboot_instance(
        self,
        instance_id: str,
    ) -> bool:
        """Reboot an EC2 instance.

        Args:
            instance_id: EC2 instance ID

        Returns:
            True if reboot was initiated successfully
        """
        try:
            async with await self._get_client("ec2") as client:
                await client.reboot_instances(InstanceIds=[instance_id])
                log.info(f"Reboot initiated for instance {instance_id}")
                return True

        except Exception as e:
            log.error(f"Failed to reboot instance {instance_id}: {e}")
            return False

    # =========================================================================
    # Amplify Operations
    # =========================================================================

    async def get_amplify_app_status(
        self,
        app_id: str,
    ) -> AmplifyApp:
        """Get status of an Amplify application.

        Args:
            app_id: Amplify app ID

        Returns:
            AmplifyApp with current status
        """
        try:
            async with await self._get_client("amplify") as client:
                # Get app details
                app_resp = await client.get_app(appId=app_id)
                app = app_resp.get("app", {})

                # Get production branch info
                branches_resp = await client.list_branches(appId=app_id)
                branches = branches_resp.get("branches", [])

                # Find production branch or first branch
                branch_name = ""
                last_deploy = None
                deploy_status = "UNKNOWN"

                for branch in branches:
                    if branch.get("stage") == "PRODUCTION" or not branch_name:
                        branch_name = branch.get("branchName", "")
                        last_deploy = branch.get("updateTime")

                        # Get latest job for deployment status
                        try:
                            jobs_resp = await client.list_jobs(
                                appId=app_id,
                                branchName=branch_name,
                                maxResults=1,
                            )
                            jobs = jobs_resp.get("jobSummaries", [])
                            if jobs:
                                deploy_status = jobs[0].get("status", "UNKNOWN")
                        except Exception:
                            pass

                return AmplifyApp(
                    app_id=app_id,
                    name=app.get("name", ""),
                    status=deploy_status,
                    last_deploy_time=last_deploy,
                    branch=branch_name,
                    domain=app.get("defaultDomain", ""),
                )

        except Exception as e:
            error_msg = str(e)
            if "NotFoundException" in error_msg:
                raise AWSResourceNotFoundError(f"Amplify app not found: {app_id}")
            log.error(f"Error getting Amplify app status for {app_id}: {e}")
            raise AWSError(f"Failed to get Amplify app status: {e}")

    async def get_all_amplify_statuses(
        self,
        apps: List[AmplifyAppConfig],
    ) -> Dict[str, AmplifyApp]:
        """Get status of multiple Amplify applications.

        Args:
            apps: List of app configurations

        Returns:
            Dict mapping app_id to AmplifyApp
        """
        results = {}
        for config in apps:
            try:
                status = await self.get_amplify_app_status(config.app_id)
                status.name = config.name or status.name
                results[config.app_id] = status
            except Exception as e:
                log.warning(f"Failed to get status for Amplify app {config.app_id}: {e}")
                results[config.app_id] = AmplifyApp(
                    app_id=config.app_id,
                    name=config.name,
                    status="ERROR",
                )
        return results

    async def start_amplify_deployment(
        self,
        app_id: str,
        branch_name: str,
    ) -> Optional[str]:
        """Start a new deployment for an Amplify app.

        Args:
            app_id: Amplify app ID
            branch_name: Branch to deploy

        Returns:
            Job ID if successful, None otherwise
        """
        try:
            async with await self._get_client("amplify") as client:
                response = await client.start_job(
                    appId=app_id,
                    branchName=branch_name,
                    jobType="RELEASE",
                )
                job_id = response.get("jobSummary", {}).get("jobId")
                log.info(f"Deployment started for {app_id}/{branch_name}: job {job_id}")
                return job_id

        except Exception as e:
            log.error(f"Failed to start deployment for {app_id}/{branch_name}: {e}")
            return None

    # =========================================================================
    # Utility Methods
    # =========================================================================

    async def test_connection(self) -> Dict[str, bool]:
        """Test connections to AWS services.

        Returns:
            Dict mapping service name to connection success
        """
        results = {}

        # Test CloudWatch Logs
        try:
            async with await self._get_client("logs") as client:
                await client.describe_log_groups(limit=1)
                results["cloudwatch_logs"] = True
                log.info("CloudWatch Logs connection: OK")
        except Exception as e:
            results["cloudwatch_logs"] = False
            log.warning(f"CloudWatch Logs connection failed: {e}")

        # Test EC2
        try:
            async with await self._get_client("ec2") as client:
                await client.describe_regions(RegionNames=[self.settings.region])
                results["ec2"] = True
                log.info("EC2 connection: OK")
        except Exception as e:
            results["ec2"] = False
            log.warning(f"EC2 connection failed: {e}")

        # Test Amplify
        try:
            async with await self._get_client("amplify") as client:
                await client.list_apps(maxResults=1)
                results["amplify"] = True
                log.info("Amplify connection: OK")
        except Exception as e:
            results["amplify"] = False
            log.warning(f"Amplify connection failed: {e}")

        return results
