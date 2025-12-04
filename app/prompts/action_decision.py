"""Action decision prompt templates for remediation recommendations."""
from __future__ import annotations

from typing import Optional, List, Dict, Any


# System prompt for action decisions
ACTION_DECISION_SYSTEM = """You are an automated remediation advisor for AWS services.

Your task is to recommend appropriate remediation actions based on error analysis.

RESPONSE FORMAT: Respond with valid JSON:
{
    "recommended_action": "restart|redeploy|scale_up|notify|escalate|investigate|no_action",
    "confidence": 0.0-1.0,
    "rationale": "Why this action is appropriate",
    "risks": ["Risk 1", "Risk 2", ...],
    "prerequisites": ["Prerequisite 1", ...],
    "expected_outcome": "What should happen after the action",
    "fallback_action": "What to do if primary action fails",
    "requires_approval": true|false
}

ACTION DEFINITIONS:
- restart: Restart the service/container (resolves stuck processes, memory leaks)
- redeploy: Trigger new deployment (resolves code/config issues from recent deploy)
- scale_up: Add capacity (resolves resource exhaustion)
- notify: Alert operators but take no automated action
- escalate: Urgent human intervention needed
- investigate: Needs more analysis before action
- no_action: Issue is transient or self-resolving

DECISION GUIDELINES:
1. PREFER less disruptive actions (notify > restart > redeploy)
2. AVOID actions that could make things worse
3. REQUIRE approval for: redeploy, scale operations, anything affecting multiple services
4. RECOMMEND restart for: memory leaks, stuck processes, connection pool exhaustion
5. RECOMMEND escalate for: security issues, data corruption, repeated failures
6. RECOMMEND no_action for: transient errors, expected behavior, low severity

SAFETY CONSIDERATIONS:
- Never recommend destructive actions (terminate, delete)
- Consider the blast radius of each action
- Factor in time of day and change freeze periods
- Respect rate limits (don't restart too frequently)"""


def build_action_decision_prompt(
    service_name: str,
    error_category: str,
    error_severity: str,
    root_cause: str,
    current_state: str,
    recent_actions: Optional[List[Dict[str, Any]]] = None,
    constraints: Optional[Dict[str, Any]] = None,
) -> str:
    """Build a prompt for action decision.

    Args:
        service_name: Name of the affected service
        error_category: Category of the error
        error_severity: Severity level
        root_cause: Identified root cause
        current_state: Current service state
        recent_actions: Recently taken actions
        constraints: Operational constraints (change freeze, etc.)

    Returns:
        Formatted prompt string
    """
    prompt = f"""Recommend remediation action:

SERVICE: {service_name}
ERROR CATEGORY: {error_category}
SEVERITY: {error_severity}
ROOT CAUSE: {root_cause}
CURRENT STATE: {current_state}
"""

    if recent_actions:
        prompt += """
RECENT ACTIONS (last hour):
"""
        for action in recent_actions:
            prompt += f"- {action.get('action', 'unknown')} at {action.get('timestamp', 'unknown')}: {action.get('result', 'unknown')}\n"

    if constraints:
        prompt += """
CONSTRAINTS:
"""
        if constraints.get('change_freeze'):
            prompt += "- Change freeze in effect\n"
        if constraints.get('max_restarts_reached'):
            prompt += "- Maximum restarts reached for this hour\n"
        if constraints.get('cooldown_active'):
            prompt += "- Cooldown period active\n"
        if constraints.get('business_hours'):
            prompt += "- Currently business hours (higher risk tolerance)\n"

    prompt += """
What action should be taken? Respond with the JSON structure specified."""

    return prompt


def build_remediation_steps_prompt(
    service_name: str,
    service_type: str,
    action: str,
    error_context: str,
) -> str:
    """Build a prompt for detailed remediation steps.

    Args:
        service_name: Name of the service
        service_type: Type (amplify, ec2, lambda, etc.)
        action: The action to be taken
        error_context: Context about the error

    Returns:
        Formatted prompt string
    """
    prompt = f"""Generate detailed remediation steps:

SERVICE: {service_name}
TYPE: {service_type}
ACTION: {action}
CONTEXT: {error_context}

Respond with JSON:
{{
    "pre_checks": [
        {{"check": "Description", "command": "Command to run", "expected": "Expected result"}}
    ],
    "steps": [
        {{"step": 1, "description": "What to do", "command": "Command if applicable", "verification": "How to verify success"}}
    ],
    "post_checks": [
        {{"check": "Description", "command": "Command", "expected": "Expected result"}}
    ],
    "rollback_steps": [
        {{"step": 1, "description": "How to rollback", "command": "Command"}}
    ],
    "estimated_duration_minutes": 5,
    "requires_downtime": true|false
}}

Be specific to AWS {service_type}. Include actual AWS CLI commands where appropriate."""

    return prompt


def build_approval_request_prompt(
    action: str,
    service_name: str,
    risk_level: str,
    rationale: str,
    expected_impact: str,
) -> str:
    """Build a human-readable approval request.

    Args:
        action: Action requiring approval
        service_name: Target service
        risk_level: Risk assessment
        rationale: Why action is recommended
        expected_impact: Expected service impact

    Returns:
        Formatted approval request text
    """
    return f"""APPROVAL REQUIRED

Action: {action.upper()}
Service: {service_name}
Risk Level: {risk_level.upper()}

Rationale:
{rationale}

Expected Impact:
{expected_impact}

To approve, respond with: APPROVE
To reject, respond with: REJECT [reason]
To defer, respond with: DEFER [duration]

This request will expire in 30 minutes."""
