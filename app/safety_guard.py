"""Safety guard for automated remediation actions.

Provides:
- Action rate limiting
- Cooldown period enforcement
- Human approval thresholds
- Change freeze awareness
- Circuit breaker patterns
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, time, timezone
from enum import Enum
from typing import Callable, Dict, List, Optional, Set

from app.config import ActionSettings
from app.action_recommender import ActionType, ActionRisk, ActionPlan

log = logging.getLogger("monitor.safety_guard")


class SafetyCheckResult(Enum):
    """Result of a safety check."""
    ALLOWED = "allowed"
    BLOCKED_RATE_LIMIT = "blocked_rate_limit"
    BLOCKED_COOLDOWN = "blocked_cooldown"
    BLOCKED_CHANGE_FREEZE = "blocked_change_freeze"
    BLOCKED_HIGH_RISK = "blocked_high_risk"
    BLOCKED_CIRCUIT_OPEN = "blocked_circuit_open"
    REQUIRES_APPROVAL = "requires_approval"


@dataclass
class SafetyViolation:
    """Details of a safety check violation."""
    check_type: SafetyCheckResult
    action_type: ActionType
    target_service: str
    reason: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    can_override: bool = False


@dataclass
class ActionRecord:
    """Record of an executed action for tracking."""
    action_type: ActionType
    target_service: str
    timestamp: datetime
    success: bool


@dataclass
class ChangeFreeze:
    """Definition of a change freeze period."""
    name: str
    start: datetime
    end: datetime
    allowed_actions: Set[ActionType] = field(default_factory=set)  # Actions allowed during freeze
    reason: str = ""

    def is_active(self, at: Optional[datetime] = None) -> bool:
        """Check if freeze is currently active."""
        now = at or datetime.now(timezone.utc)
        return self.start <= now <= self.end


class SafetyGuard:
    """Guards against unsafe automated actions.

    Features:
    - Rate limiting per service and action type
    - Cooldown enforcement after actions
    - Change freeze period awareness
    - Circuit breaker for repeated failures
    - Human approval routing
    """

    def __init__(
        self,
        settings: ActionSettings,
        approval_callback: Optional[Callable[[ActionPlan, str], None]] = None,
    ):
        """Initialize the safety guard.

        Args:
            settings: Action configuration settings
            approval_callback: Called when approval is needed (plan, reason)
        """
        self.settings = settings
        self.approval_callback = approval_callback

        # Action history for rate limiting
        self._action_history: List[ActionRecord] = []
        self._max_history = 10000

        # Active change freezes
        self._change_freezes: List[ChangeFreeze] = []

        # Circuit breaker state (service -> failure count)
        self._circuit_breakers: Dict[str, int] = {}
        self._circuit_threshold = 3  # Open circuit after 3 consecutive failures
        self._circuit_reset_after = timedelta(minutes=30)
        self._circuit_last_failure: Dict[str, datetime] = {}

        # Violations log
        self._violations: List[SafetyViolation] = []
        self._max_violations = 500

        # Default maintenance window (when higher-risk actions are allowed)
        self._maintenance_windows: List[Dict] = [
            # Example: 2 AM - 5 AM UTC on weekdays
            {"days": [0, 1, 2, 3, 4], "start": time(2, 0), "end": time(5, 0)},
        ]

    def check_action(
        self,
        action_type: ActionType,
        target_service: str,
        risk_level: ActionRisk,
    ) -> SafetyCheckResult:
        """Check if an action is safe to execute.

        Args:
            action_type: Type of action
            target_service: Target service
            risk_level: Risk level of the action

        Returns:
            SafetyCheckResult indicating if action is allowed
        """
        now = datetime.now(timezone.utc)

        # Check circuit breaker
        if self._is_circuit_open(target_service):
            self._record_violation(
                SafetyCheckResult.BLOCKED_CIRCUIT_OPEN,
                action_type,
                target_service,
                f"Circuit breaker open for {target_service}",
            )
            return SafetyCheckResult.BLOCKED_CIRCUIT_OPEN

        # Check change freeze
        active_freeze = self._get_active_freeze()
        if active_freeze:
            if action_type not in active_freeze.allowed_actions:
                self._record_violation(
                    SafetyCheckResult.BLOCKED_CHANGE_FREEZE,
                    action_type,
                    target_service,
                    f"Change freeze active: {active_freeze.name}",
                )
                return SafetyCheckResult.BLOCKED_CHANGE_FREEZE

        # Check rate limits
        if not self._check_rate_limit(action_type, target_service):
            self._record_violation(
                SafetyCheckResult.BLOCKED_RATE_LIMIT,
                action_type,
                target_service,
                f"Rate limit exceeded for {action_type.value} on {target_service}",
            )
            return SafetyCheckResult.BLOCKED_RATE_LIMIT

        # Check cooldown
        if not self._check_cooldown(action_type, target_service):
            self._record_violation(
                SafetyCheckResult.BLOCKED_COOLDOWN,
                action_type,
                target_service,
                f"Cooldown active for {target_service}",
            )
            return SafetyCheckResult.BLOCKED_COOLDOWN

        # Check high-risk actions
        if risk_level in {ActionRisk.HIGH, ActionRisk.CRITICAL}:
            if not self._is_maintenance_window():
                self._record_violation(
                    SafetyCheckResult.BLOCKED_HIGH_RISK,
                    action_type,
                    target_service,
                    f"High-risk action {action_type.value} requires maintenance window",
                    can_override=True,
                )
                return SafetyCheckResult.REQUIRES_APPROVAL

        # Check approval requirements
        if action_type.value in self.settings.require_approval_for:
            return SafetyCheckResult.REQUIRES_APPROVAL

        return SafetyCheckResult.ALLOWED

    def check_plan(self, plan: ActionPlan) -> List[SafetyViolation]:
        """Check all actions in a plan for safety.

        Args:
            plan: Action plan to check

        Returns:
            List of violations (empty if all clear)
        """
        violations = []

        for action in plan.actions:
            result = self.check_action(
                action.action_type,
                action.target_service,
                action.risk_level,
            )

            if result not in {SafetyCheckResult.ALLOWED, SafetyCheckResult.REQUIRES_APPROVAL}:
                violations.append(SafetyViolation(
                    check_type=result,
                    action_type=action.action_type,
                    target_service=action.target_service,
                    reason=f"Safety check failed: {result.value}",
                ))

        return violations

    def record_action(
        self,
        action_type: ActionType,
        target_service: str,
        success: bool,
    ) -> None:
        """Record an executed action.

        Args:
            action_type: Type of action executed
            target_service: Target service
            success: Whether action succeeded
        """
        record = ActionRecord(
            action_type=action_type,
            target_service=target_service,
            timestamp=datetime.now(timezone.utc),
            success=success,
        )

        self._action_history.append(record)
        if len(self._action_history) > self._max_history:
            self._action_history.pop(0)

        # Update circuit breaker
        if not success:
            self._record_failure(target_service)
        else:
            self._record_success(target_service)

        log.info(
            f"Recorded action: {action_type.value} on {target_service} "
            f"(success={success})"
        )

    def _check_rate_limit(
        self,
        action_type: ActionType,
        target_service: str,
    ) -> bool:
        """Check if action is within rate limits."""
        if action_type not in {ActionType.RESTART_SERVICE, ActionType.RESTART_INSTANCE, ActionType.REDEPLOY}:
            return True

        # Count actions in last hour
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        count = sum(
            1 for r in self._action_history
            if r.target_service == target_service
            and r.action_type == action_type
            and r.timestamp > cutoff
        )

        max_allowed = self.settings.max_restarts_per_hour
        return count < max_allowed

    def _check_cooldown(
        self,
        action_type: ActionType,
        target_service: str,
    ) -> bool:
        """Check if cooldown period has passed."""
        if action_type not in {ActionType.RESTART_SERVICE, ActionType.RESTART_INSTANCE, ActionType.REDEPLOY}:
            return True

        cutoff = datetime.now(timezone.utc) - timedelta(minutes=self.settings.cooldown_minutes)

        # Find most recent action
        recent = [
            r for r in self._action_history
            if r.target_service == target_service
            and r.action_type == action_type
            and r.timestamp > cutoff
        ]

        return len(recent) == 0

    def _is_circuit_open(self, service: str) -> bool:
        """Check if circuit breaker is open for a service."""
        if service not in self._circuit_breakers:
            return False

        failures = self._circuit_breakers[service]
        if failures < self._circuit_threshold:
            return False

        # Check if enough time has passed to reset
        last_failure = self._circuit_last_failure.get(service)
        if last_failure:
            if datetime.now(timezone.utc) - last_failure > self._circuit_reset_after:
                # Reset circuit
                self._circuit_breakers[service] = 0
                log.info(f"Circuit breaker reset for {service}")
                return False

        return True

    def _record_failure(self, service: str) -> None:
        """Record a failure for circuit breaker."""
        self._circuit_breakers[service] = self._circuit_breakers.get(service, 0) + 1
        self._circuit_last_failure[service] = datetime.now(timezone.utc)

        if self._circuit_breakers[service] >= self._circuit_threshold:
            log.warning(f"Circuit breaker OPEN for {service}")

    def _record_success(self, service: str) -> None:
        """Record success, potentially resetting circuit breaker."""
        if service in self._circuit_breakers:
            self._circuit_breakers[service] = 0

    def _get_active_freeze(self) -> Optional[ChangeFreeze]:
        """Get currently active change freeze if any."""
        now = datetime.now(timezone.utc)
        for freeze in self._change_freezes:
            if freeze.is_active(now):
                return freeze
        return None

    def _is_maintenance_window(self) -> bool:
        """Check if currently in a maintenance window."""
        now = datetime.now(timezone.utc)
        for window in self._maintenance_windows:
            if now.weekday() in window["days"]:
                current_time = now.time()
                if window["start"] <= current_time <= window["end"]:
                    return True
        return False

    def _record_violation(
        self,
        check_type: SafetyCheckResult,
        action_type: ActionType,
        target_service: str,
        reason: str,
        can_override: bool = False,
    ) -> None:
        """Record a safety violation."""
        violation = SafetyViolation(
            check_type=check_type,
            action_type=action_type,
            target_service=target_service,
            reason=reason,
            can_override=can_override,
        )
        self._violations.append(violation)
        if len(self._violations) > self._max_violations:
            self._violations.pop(0)

        log.warning(f"Safety violation: {reason}")

    def add_change_freeze(
        self,
        name: str,
        start: datetime,
        end: datetime,
        allowed_actions: Optional[Set[ActionType]] = None,
        reason: str = "",
    ) -> None:
        """Add a change freeze period.

        Args:
            name: Freeze name
            start: Start time
            end: End time
            allowed_actions: Actions still allowed during freeze
            reason: Reason for freeze
        """
        freeze = ChangeFreeze(
            name=name,
            start=start,
            end=end,
            allowed_actions=allowed_actions or {ActionType.NOTIFY, ActionType.ESCALATE},
            reason=reason,
        )
        self._change_freezes.append(freeze)
        log.info(f"Change freeze added: {name} ({start} to {end})")

    def remove_change_freeze(self, name: str) -> bool:
        """Remove a change freeze by name."""
        for i, freeze in enumerate(self._change_freezes):
            if freeze.name == name:
                self._change_freezes.pop(i)
                log.info(f"Change freeze removed: {name}")
                return True
        return False

    def override_circuit_breaker(self, service: str) -> None:
        """Manually reset circuit breaker for a service."""
        if service in self._circuit_breakers:
            self._circuit_breakers[service] = 0
            log.info(f"Circuit breaker manually reset for {service}")

    def get_violations(self, limit: int = 50) -> List[SafetyViolation]:
        """Get recent safety violations."""
        return list(reversed(self._violations[-limit:]))

    def get_stats(self) -> Dict:
        """Get safety guard statistics."""
        now = datetime.now(timezone.utc)
        hour_ago = now - timedelta(hours=1)

        recent_actions = sum(1 for r in self._action_history if r.timestamp > hour_ago)
        recent_failures = sum(
            1 for r in self._action_history
            if r.timestamp > hour_ago and not r.success
        )

        return {
            "actions_last_hour": recent_actions,
            "failures_last_hour": recent_failures,
            "open_circuits": sum(1 for c in self._circuit_breakers.values() if c >= self._circuit_threshold),
            "active_freezes": sum(1 for f in self._change_freezes if f.is_active()),
            "violations_recorded": len(self._violations),
            "in_maintenance_window": self._is_maintenance_window(),
        }
