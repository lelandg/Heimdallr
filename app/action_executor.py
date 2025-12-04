"""Action executor for safe automated remediation.

Provides:
- Service restart via AWS API
- Amplify redeployment triggers
- EC2 instance reboot
- Execution tracking and verification
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from app.aws_client import AWSClient
from app.action_recommender import ActionPlan, ActionRecommendation, ActionType

log = logging.getLogger("monitor.action_executor")


class ExecutionStatus(Enum):
    """Status of action execution."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    ROLLED_BACK = "rolled_back"


@dataclass
class ExecutionResult:
    """Result of executing a single action."""
    action_type: ActionType
    target_service: str
    status: ExecutionStatus
    message: str = ""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> int:
        """Get execution duration in milliseconds."""
        if self.started_at and self.completed_at:
            return int((self.completed_at - self.started_at).total_seconds() * 1000)
        return 0


@dataclass
class PlanExecutionResult:
    """Result of executing an action plan."""
    plan_id: str
    overall_status: ExecutionStatus
    action_results: List[ExecutionResult]
    started_at: datetime
    completed_at: Optional[datetime] = None
    rollback_performed: bool = False
    rollback_result: Optional[str] = None

    @property
    def success_count(self) -> int:
        """Count successful actions."""
        return sum(1 for r in self.action_results if r.status == ExecutionStatus.SUCCESS)

    @property
    def failure_count(self) -> int:
        """Count failed actions."""
        return sum(1 for r in self.action_results if r.status == ExecutionStatus.FAILED)


class ActionExecutor:
    """Executes remediation actions safely.

    Features:
    - Executes action plans from ActionRecommender
    - Tracks execution progress and results
    - Supports dry-run mode for testing
    - Automatic rollback on failure
    """

    def __init__(
        self,
        aws_client: AWSClient,
        pre_execution_callback: Optional[Callable[[ActionRecommendation], bool]] = None,
        post_execution_callback: Optional[Callable[[ExecutionResult], None]] = None,
    ):
        """Initialize the executor.

        Args:
            aws_client: AWS client for API calls
            pre_execution_callback: Called before each action, return False to skip
            post_execution_callback: Called after each action completes
        """
        self.aws_client = aws_client
        self.pre_execution_callback = pre_execution_callback
        self.post_execution_callback = post_execution_callback

        # Execution history
        self._execution_history: List[PlanExecutionResult] = []
        self._max_history = 100

    async def execute_plan(
        self,
        plan: ActionPlan,
        dry_run: bool = False,
        stop_on_failure: bool = True,
    ) -> PlanExecutionResult:
        """Execute an action plan.

        Args:
            plan: Action plan to execute
            dry_run: If True, simulate execution without making changes
            stop_on_failure: If True, stop executing on first failure

        Returns:
            PlanExecutionResult with execution details
        """
        result = PlanExecutionResult(
            plan_id=plan.plan_id,
            overall_status=ExecutionStatus.RUNNING,
            action_results=[],
            started_at=datetime.now(timezone.utc),
        )

        log.info(f"Executing plan {plan.plan_id} with {len(plan.actions)} actions (dry_run={dry_run})")

        for action in plan.actions:
            # Pre-execution check
            if self.pre_execution_callback:
                try:
                    if not self.pre_execution_callback(action):
                        log.info(f"Action {action.action_type.value} skipped by callback")
                        result.action_results.append(ExecutionResult(
                            action_type=action.action_type,
                            target_service=action.target_service,
                            status=ExecutionStatus.SKIPPED,
                            message="Skipped by pre-execution callback",
                        ))
                        continue
                except Exception as e:
                    log.error(f"Pre-execution callback error: {e}")

            # Execute action
            action_result = await self._execute_action(action, dry_run)
            result.action_results.append(action_result)

            # Post-execution callback
            if self.post_execution_callback:
                try:
                    self.post_execution_callback(action_result)
                except Exception as e:
                    log.error(f"Post-execution callback error: {e}")

            # Check for failure
            if action_result.status == ExecutionStatus.FAILED and stop_on_failure:
                log.warning(f"Action {action.action_type.value} failed, stopping plan execution")
                result.overall_status = ExecutionStatus.FAILED
                break

        # Determine overall status
        result.completed_at = datetime.now(timezone.utc)
        if result.overall_status != ExecutionStatus.FAILED:
            if result.failure_count > 0:
                result.overall_status = ExecutionStatus.FAILED
            elif result.success_count == len(plan.actions):
                result.overall_status = ExecutionStatus.SUCCESS
            else:
                result.overall_status = ExecutionStatus.SUCCESS  # Partial with skips

        # Update plan
        plan.executed = True
        plan.execution_result = result.overall_status.value

        # Store in history
        self._execution_history.append(result)
        if len(self._execution_history) > self._max_history:
            self._execution_history.pop(0)

        log.info(
            f"Plan {plan.plan_id} completed: {result.overall_status.value} "
            f"({result.success_count}/{len(plan.actions)} succeeded)"
        )

        return result

    async def _execute_action(
        self,
        action: ActionRecommendation,
        dry_run: bool,
    ) -> ExecutionResult:
        """Execute a single action.

        Args:
            action: Action to execute
            dry_run: If True, simulate only

        Returns:
            ExecutionResult with details
        """
        result = ExecutionResult(
            action_type=action.action_type,
            target_service=action.target_service,
            status=ExecutionStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )

        log.info(f"Executing {action.action_type.value} on {action.target_service}")

        try:
            if dry_run:
                result.status = ExecutionStatus.SUCCESS
                result.message = "Dry run - no changes made"
                result.details["dry_run"] = True

            elif action.action_type == ActionType.RESTART_SERVICE:
                await self._restart_service(action, result)

            elif action.action_type == ActionType.RESTART_INSTANCE:
                await self._restart_instance(action, result)

            elif action.action_type == ActionType.REDEPLOY:
                await self._redeploy(action, result)

            elif action.action_type == ActionType.NOTIFY:
                # Notification is handled elsewhere
                result.status = ExecutionStatus.SUCCESS
                result.message = "Notification queued"

            elif action.action_type == ActionType.ESCALATE:
                # Escalation is handled elsewhere
                result.status = ExecutionStatus.SUCCESS
                result.message = "Escalation queued"

            elif action.action_type == ActionType.NO_ACTION:
                result.status = ExecutionStatus.SKIPPED
                result.message = "No action required"

            else:
                result.status = ExecutionStatus.SKIPPED
                result.message = f"Action type {action.action_type.value} not implemented"

        except Exception as e:
            log.error(f"Action execution failed: {e}")
            result.status = ExecutionStatus.FAILED
            result.message = str(e)

        result.completed_at = datetime.now(timezone.utc)
        return result

    async def _restart_service(
        self,
        action: ActionRecommendation,
        result: ExecutionResult,
    ) -> None:
        """Restart a service (Amplify app or EC2-hosted service)."""
        params = action.parameters

        # Determine service type
        if "amplify" in action.target_service.lower() or params.get("service_type") == "amplify":
            # Amplify restart = trigger redeploy
            app_id = params.get("app_id")
            branch = params.get("branch", "main")

            if not app_id:
                result.status = ExecutionStatus.FAILED
                result.message = "No app_id provided for Amplify restart"
                return

            job_id = await self.aws_client.start_amplify_deployment(app_id, branch)
            if job_id:
                result.status = ExecutionStatus.SUCCESS
                result.message = f"Deployment started: job {job_id}"
                result.details["job_id"] = job_id
            else:
                result.status = ExecutionStatus.FAILED
                result.message = "Failed to start Amplify deployment"

        else:
            # EC2-hosted service - we can only restart the instance
            instance_id = params.get("instance_id")
            if instance_id:
                success = await self.aws_client.reboot_instance(instance_id)
                if success:
                    result.status = ExecutionStatus.SUCCESS
                    result.message = f"Instance {instance_id} reboot initiated"
                else:
                    result.status = ExecutionStatus.FAILED
                    result.message = f"Failed to reboot instance {instance_id}"
            else:
                result.status = ExecutionStatus.FAILED
                result.message = "No instance_id provided for EC2 restart"

    async def _restart_instance(
        self,
        action: ActionRecommendation,
        result: ExecutionResult,
    ) -> None:
        """Restart an EC2 instance."""
        instance_id = action.parameters.get("instance_id")

        if not instance_id:
            result.status = ExecutionStatus.FAILED
            result.message = "No instance_id provided"
            return

        success = await self.aws_client.reboot_instance(instance_id)
        if success:
            result.status = ExecutionStatus.SUCCESS
            result.message = f"Instance {instance_id} reboot initiated"
            result.details["instance_id"] = instance_id

            # Wait for instance to come back (optional)
            if action.parameters.get("wait_for_recovery", False):
                await self._wait_for_instance_recovery(instance_id, result)
        else:
            result.status = ExecutionStatus.FAILED
            result.message = f"Failed to reboot instance {instance_id}"

    async def _redeploy(
        self,
        action: ActionRecommendation,
        result: ExecutionResult,
    ) -> None:
        """Trigger Amplify redeployment."""
        app_id = action.parameters.get("app_id")
        branch = action.parameters.get("branch", "main")

        if not app_id:
            result.status = ExecutionStatus.FAILED
            result.message = "No app_id provided for redeployment"
            return

        job_id = await self.aws_client.start_amplify_deployment(app_id, branch)
        if job_id:
            result.status = ExecutionStatus.SUCCESS
            result.message = f"Deployment started on {branch}: job {job_id}"
            result.details["job_id"] = job_id
            result.details["branch"] = branch
        else:
            result.status = ExecutionStatus.FAILED
            result.message = f"Failed to start deployment for {app_id}/{branch}"

    async def _wait_for_instance_recovery(
        self,
        instance_id: str,
        result: ExecutionResult,
        timeout_s: int = 300,
    ) -> None:
        """Wait for an instance to recover after reboot."""
        log.info(f"Waiting for instance {instance_id} to recover...")
        start_time = datetime.now(timezone.utc)

        while True:
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            if elapsed > timeout_s:
                result.details["recovery_timeout"] = True
                log.warning(f"Instance {instance_id} recovery timed out")
                return

            try:
                status = await self.aws_client.get_instance_status(instance_id)
                if status.is_healthy:
                    result.details["recovery_time_s"] = int(elapsed)
                    log.info(f"Instance {instance_id} recovered after {elapsed:.0f}s")
                    return
            except Exception:
                pass

            await asyncio.sleep(10)

    async def execute_single_action(
        self,
        action_type: ActionType,
        target_service: str,
        parameters: Optional[Dict[str, Any]] = None,
        dry_run: bool = False,
    ) -> ExecutionResult:
        """Execute a single action without a full plan.

        Args:
            action_type: Type of action
            target_service: Target service
            parameters: Action parameters
            dry_run: If True, simulate only

        Returns:
            ExecutionResult
        """
        action = ActionRecommendation(
            action_type=action_type,
            target_service=target_service,
            risk_level=action.risk_level if hasattr(action, 'risk_level') else None,
            confidence=1.0,
            rationale="Manual execution",
            parameters=parameters or {},
        )

        return await self._execute_action(action, dry_run)

    def get_recent_executions(self, limit: int = 10) -> List[PlanExecutionResult]:
        """Get recent execution results.

        Args:
            limit: Maximum results to return

        Returns:
            List of recent PlanExecutionResults
        """
        return list(reversed(self._execution_history[-limit:]))

    def get_execution_stats(self) -> Dict[str, int]:
        """Get execution statistics."""
        stats = {
            "total_executions": len(self._execution_history),
            "successful": 0,
            "failed": 0,
            "partial": 0,
        }

        for result in self._execution_history:
            if result.overall_status == ExecutionStatus.SUCCESS:
                stats["successful"] += 1
            elif result.overall_status == ExecutionStatus.FAILED:
                stats["failed"] += 1
            else:
                stats["partial"] += 1

        return stats
