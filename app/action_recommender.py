"""Action recommender for automated remediation decisions.

Provides:
- Intelligent action recommendations based on error analysis
- Safety checks before recommending destructive actions
- Action prioritization and sequencing
- Human approval routing for sensitive actions
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Callable

from app.config import ActionSettings
from app.error_analyzer import AnalysisResult, ErrorCategory, RecommendedAction
from app.service_monitor import HealthState, ServiceHealth

log = logging.getLogger("monitor.action_recommender")


class ActionType(Enum):
    """Types of remediation actions."""
    RESTART_SERVICE = "restart_service"
    RESTART_INSTANCE = "restart_instance"
    REDEPLOY = "redeploy"
    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    CLEAR_CACHE = "clear_cache"
    ROTATE_LOGS = "rotate_logs"
    NOTIFY = "notify"
    ESCALATE = "escalate"
    NO_ACTION = "no_action"


class ActionRisk(Enum):
    """Risk level of an action."""
    LOW = "low"        # Safe, no service impact
    MEDIUM = "medium"  # Brief service impact possible
    HIGH = "high"      # Service disruption likely
    CRITICAL = "critical"  # Major impact, requires approval


@dataclass
class ActionRecommendation:
    """A recommended remediation action."""
    action_type: ActionType
    target_service: str
    risk_level: ActionRisk
    confidence: float  # 0-1 confidence in recommendation
    rationale: str
    requires_approval: bool = False
    estimated_downtime_s: int = 0
    prerequisites: List[str] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_safe_to_execute(self) -> bool:
        """Check if action is safe to execute automatically."""
        return (
            not self.requires_approval
            and self.risk_level in {ActionRisk.LOW, ActionRisk.MEDIUM}
            and self.confidence >= 0.7
        )


@dataclass
class ActionPlan:
    """A plan containing one or more actions."""
    plan_id: str
    trigger_source: str  # error fingerprint or service id
    actions: List[ActionRecommendation]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    approved: bool = False
    approved_by: Optional[str] = None
    executed: bool = False
    execution_result: Optional[str] = None

    @property
    def total_estimated_downtime(self) -> int:
        """Total estimated downtime for all actions."""
        return sum(a.estimated_downtime_s for a in self.actions)

    @property
    def max_risk(self) -> ActionRisk:
        """Highest risk level in the plan."""
        risk_order = {
            ActionRisk.LOW: 0,
            ActionRisk.MEDIUM: 1,
            ActionRisk.HIGH: 2,
            ActionRisk.CRITICAL: 3,
        }
        return max(self.actions, key=lambda a: risk_order[a.risk_level]).risk_level if self.actions else ActionRisk.LOW

    @property
    def requires_approval(self) -> bool:
        """Check if any action requires approval."""
        return any(a.requires_approval for a in self.actions)


class ActionHistory:
    """Tracks action history for cooldown enforcement."""

    def __init__(self):
        self._actions: List[Dict[str, Any]] = []
        self._max_history = 1000

    def record_action(
        self,
        action_type: ActionType,
        target_service: str,
        success: bool,
    ) -> None:
        """Record an executed action."""
        self._actions.append({
            "action_type": action_type.value,
            "target_service": target_service,
            "success": success,
            "timestamp": datetime.now(timezone.utc),
        })
        if len(self._actions) > self._max_history:
            self._actions.pop(0)

    def get_recent_actions(
        self,
        target_service: str,
        action_type: Optional[ActionType] = None,
        minutes: int = 60,
    ) -> List[Dict]:
        """Get recent actions for a service."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        results = []
        for action in self._actions:
            if action["timestamp"] < cutoff:
                continue
            if action["target_service"] != target_service:
                continue
            if action_type and action["action_type"] != action_type.value:
                continue
            results.append(action)
        return results

    def count_actions(
        self,
        target_service: str,
        action_type: ActionType,
        minutes: int = 60,
    ) -> int:
        """Count actions of a type within time window."""
        return len(self.get_recent_actions(target_service, action_type, minutes))


class ActionRecommender:
    """Recommends remediation actions based on error analysis.

    Features:
    - Maps error analysis to appropriate actions
    - Enforces safety limits (cooldowns, max actions)
    - Routes high-risk actions for approval
    - Tracks action history
    """

    def __init__(
        self,
        settings: ActionSettings,
        approval_callback: Optional[Callable[[ActionPlan], None]] = None,
    ):
        """Initialize the recommender.

        Args:
            settings: Action configuration
            approval_callback: Called when plan needs approval
        """
        self.settings = settings
        self.approval_callback = approval_callback
        self.history = ActionHistory()

        # Action risk mappings
        self._action_risks = {
            ActionType.NOTIFY: ActionRisk.LOW,
            ActionType.ROTATE_LOGS: ActionRisk.LOW,
            ActionType.CLEAR_CACHE: ActionRisk.LOW,
            ActionType.SCALE_UP: ActionRisk.MEDIUM,
            ActionType.SCALE_DOWN: ActionRisk.MEDIUM,
            ActionType.RESTART_SERVICE: ActionRisk.MEDIUM,
            ActionType.RESTART_INSTANCE: ActionRisk.HIGH,
            ActionType.REDEPLOY: ActionRisk.HIGH,
            ActionType.ESCALATE: ActionRisk.LOW,
            ActionType.NO_ACTION: ActionRisk.LOW,
        }

        # Estimated downtime per action
        self._action_downtime = {
            ActionType.NOTIFY: 0,
            ActionType.ROTATE_LOGS: 0,
            ActionType.CLEAR_CACHE: 5,
            ActionType.SCALE_UP: 60,
            ActionType.SCALE_DOWN: 60,
            ActionType.RESTART_SERVICE: 30,
            ActionType.RESTART_INSTANCE: 120,
            ActionType.REDEPLOY: 300,
            ActionType.ESCALATE: 0,
            ActionType.NO_ACTION: 0,
        }

    def recommend_for_analysis(
        self,
        analysis: AnalysisResult,
        service_health: Optional[ServiceHealth] = None,
    ) -> ActionPlan:
        """Generate action recommendations from error analysis.

        Args:
            analysis: Error analysis result
            service_health: Current service health (optional)

        Returns:
            ActionPlan with recommended actions
        """
        actions: List[ActionRecommendation] = []

        # Map recommended action to action type
        primary_action = self._map_recommended_action(analysis.recommended_action)

        # Check if action is allowed
        if not self._is_action_allowed(primary_action, analysis.source_service):
            # Fall back to notification/escalation
            primary_action = ActionType.ESCALATE if analysis.severity.value == "critical" else ActionType.NOTIFY

        # Create primary recommendation
        primary = ActionRecommendation(
            action_type=primary_action,
            target_service=analysis.source_service,
            risk_level=self._action_risks[primary_action],
            confidence=analysis.confidence,
            rationale=analysis.action_rationale or analysis.root_cause,
            requires_approval=self._requires_approval(primary_action),
            estimated_downtime_s=self._action_downtime[primary_action],
            parameters={
                "error_fingerprint": analysis.error_fingerprint,
                "error_category": analysis.category.value,
            },
        )
        actions.append(primary)

        # Add notification if service is down
        if service_health and service_health.state == HealthState.UNHEALTHY:
            notify = ActionRecommendation(
                action_type=ActionType.NOTIFY,
                target_service=analysis.source_service,
                risk_level=ActionRisk.LOW,
                confidence=1.0,
                rationale="Service is unhealthy, notifying operators",
            )
            actions.insert(0, notify)

        # Add escalation for critical errors
        if analysis.severity.value == "critical" and primary_action != ActionType.ESCALATE:
            escalate = ActionRecommendation(
                action_type=ActionType.ESCALATE,
                target_service=analysis.source_service,
                risk_level=ActionRisk.LOW,
                confidence=1.0,
                rationale="Critical error requires immediate attention",
            )
            actions.append(escalate)

        plan = ActionPlan(
            plan_id=f"plan-{analysis.error_fingerprint[:8]}",
            trigger_source=analysis.error_fingerprint,
            actions=actions,
        )

        # Request approval if needed
        if plan.requires_approval and self.approval_callback:
            self.approval_callback(plan)

        return plan

    def recommend_for_health_change(
        self,
        service_health: ServiceHealth,
        previous_state: Optional[HealthState] = None,
    ) -> ActionPlan:
        """Generate recommendations based on health state change.

        Args:
            service_health: Current health status
            previous_state: Previous health state

        Returns:
            ActionPlan with recommended actions
        """
        actions: List[ActionRecommendation] = []

        service = service_health.service_name
        state = service_health.state

        # Determine action based on state transition
        if state == HealthState.UNHEALTHY:
            # Service is down - recommend restart if allowed
            action_type = ActionType.RESTART_SERVICE
            if not self._is_action_allowed(action_type, service):
                action_type = ActionType.ESCALATE

            actions.append(ActionRecommendation(
                action_type=action_type,
                target_service=service,
                risk_level=self._action_risks[action_type],
                confidence=0.8,
                rationale=f"Service unhealthy: {service_health.message}",
                requires_approval=self._requires_approval(action_type),
                estimated_downtime_s=self._action_downtime[action_type],
            ))

            # Always notify on unhealthy
            actions.append(ActionRecommendation(
                action_type=ActionType.NOTIFY,
                target_service=service,
                risk_level=ActionRisk.LOW,
                confidence=1.0,
                rationale="Notifying operators of unhealthy service",
            ))

        elif state == HealthState.DEGRADED:
            # Service degraded - monitor closely, notify
            actions.append(ActionRecommendation(
                action_type=ActionType.NOTIFY,
                target_service=service,
                risk_level=ActionRisk.LOW,
                confidence=0.9,
                rationale=f"Service degraded: {service_health.message}",
            ))

        elif state == HealthState.HEALTHY and previous_state in {HealthState.UNHEALTHY, HealthState.DEGRADED}:
            # Recovery - notify
            actions.append(ActionRecommendation(
                action_type=ActionType.NOTIFY,
                target_service=service,
                risk_level=ActionRisk.LOW,
                confidence=1.0,
                rationale=f"Service recovered: {service_health.message}",
            ))

        # If no actions needed
        if not actions:
            actions.append(ActionRecommendation(
                action_type=ActionType.NO_ACTION,
                target_service=service,
                risk_level=ActionRisk.LOW,
                confidence=1.0,
                rationale="No action required",
            ))

        plan = ActionPlan(
            plan_id=f"plan-{service_health.service_id}",
            trigger_source=service_health.service_id,
            actions=actions,
        )

        if plan.requires_approval and self.approval_callback:
            self.approval_callback(plan)

        return plan

    def _map_recommended_action(self, recommended: RecommendedAction) -> ActionType:
        """Map analysis recommendation to action type."""
        mapping = {
            RecommendedAction.RESTART_SERVICE: ActionType.RESTART_SERVICE,
            RecommendedAction.REDEPLOY: ActionType.REDEPLOY,
            RecommendedAction.SCALE_UP: ActionType.SCALE_UP,
            RecommendedAction.CHECK_DEPENDENCIES: ActionType.NOTIFY,  # Can't auto-fix deps
            RecommendedAction.FIX_CONFIGURATION: ActionType.NOTIFY,   # Needs human
            RecommendedAction.INVESTIGATE: ActionType.NOTIFY,
            RecommendedAction.ESCALATE: ActionType.ESCALATE,
            RecommendedAction.IGNORE: ActionType.NO_ACTION,
        }
        return mapping.get(recommended, ActionType.NOTIFY)

    def _is_action_allowed(self, action_type: ActionType, service: str) -> bool:
        """Check if action is allowed by settings and cooldowns."""
        # Check settings
        if action_type == ActionType.RESTART_SERVICE and not self.settings.allow_restart:
            return False
        if action_type == ActionType.REDEPLOY and not self.settings.allow_redeploy:
            return False

        # Check cooldown
        if action_type in {ActionType.RESTART_SERVICE, ActionType.RESTART_INSTANCE}:
            recent_restarts = self.history.count_actions(
                service, action_type, minutes=60
            )
            if recent_restarts >= self.settings.max_restarts_per_hour:
                log.warning(f"Action {action_type.value} blocked for {service}: max restarts reached")
                return False

            # Check cooldown period
            recent = self.history.get_recent_actions(
                service, action_type, minutes=self.settings.cooldown_minutes
            )
            if recent:
                log.warning(f"Action {action_type.value} blocked for {service}: in cooldown")
                return False

        return True

    def _requires_approval(self, action_type: ActionType) -> bool:
        """Check if action requires human approval."""
        approval_required = {
            ActionType.REDEPLOY,
            ActionType.RESTART_INSTANCE,
        }

        # Check settings
        if action_type.value in self.settings.require_approval_for:
            return True

        return action_type in approval_required

    def approve_plan(self, plan: ActionPlan, approved_by: str = "operator") -> None:
        """Approve an action plan for execution.

        Args:
            plan: Plan to approve
            approved_by: Who approved
        """
        plan.approved = True
        plan.approved_by = approved_by
        log.info(f"Plan {plan.plan_id} approved by {approved_by}")

    def record_execution(
        self,
        plan: ActionPlan,
        success: bool,
        result: str = "",
    ) -> None:
        """Record plan execution in history.

        Args:
            plan: Executed plan
            success: Whether execution succeeded
            result: Execution result message
        """
        plan.executed = True
        plan.execution_result = result

        for action in plan.actions:
            if action.action_type not in {ActionType.NOTIFY, ActionType.ESCALATE, ActionType.NO_ACTION}:
                self.history.record_action(
                    action.action_type,
                    action.target_service,
                    success,
                )

    def get_pending_approvals(self) -> List[ActionPlan]:
        """Get plans waiting for approval.

        Note: This would typically be backed by persistent storage.
        For now, returns empty as plans are not persisted.
        """
        return []

    def get_action_stats(self, minutes: int = 60) -> Dict[str, int]:
        """Get action statistics."""
        stats: Dict[str, int] = {}
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)

        for action in self.history._actions:
            if action["timestamp"] >= cutoff:
                action_type = action["action_type"]
                stats[action_type] = stats.get(action_type, 0) + 1

        return stats
