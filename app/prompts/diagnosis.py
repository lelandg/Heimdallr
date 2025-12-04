"""Diagnosis prompt templates for root cause analysis."""
from __future__ import annotations

from typing import Optional, List, Dict, Any


# System prompt for root cause analysis
ROOT_CAUSE_SYSTEM = """You are a senior DevOps engineer performing root cause analysis.

Your task is to identify the underlying cause of service issues by analyzing multiple signals:
- Error logs and patterns
- Service health metrics
- Recent changes and deployments
- Infrastructure state

RESPONSE FORMAT: Respond with valid JSON:
{
    "primary_cause": "Brief statement of the root cause",
    "contributing_factors": ["Factor 1", "Factor 2", ...],
    "evidence": ["Evidence point 1", "Evidence point 2", ...],
    "confidence": 0.0-1.0,
    "related_issues": ["Related issue 1", ...],
    "timeline": "Brief description of how the issue developed"
}

ANALYSIS GUIDELINES:
1. Look for the earliest signal that indicates the problem
2. Distinguish between symptoms and causes
3. Consider cascading failures (A causes B causes C)
4. Note any timing correlations with deployments or changes
5. Identify if this is a recurring issue

BE SPECIFIC: Avoid generic statements like "something went wrong".
Identify the specific component, configuration, or condition that failed."""


def build_root_cause_prompt(
    service_name: str,
    errors: List[Dict[str, Any]],
    health_history: Optional[List[Dict[str, Any]]] = None,
    recent_deployments: Optional[List[Dict[str, Any]]] = None,
    related_services: Optional[List[str]] = None,
) -> str:
    """Build a prompt for root cause analysis.

    Args:
        service_name: Name of the affected service
        errors: List of error dictionaries with message, timestamp, type
        health_history: Recent health state changes
        recent_deployments: Recent deployment info
        related_services: Services that might be related

    Returns:
        Formatted prompt string
    """
    prompt = f"""Perform root cause analysis for: {service_name}

ERRORS (chronological order):
"""
    for i, error in enumerate(errors[:10], 1):  # Limit to 10 errors
        prompt += f"""
{i}. [{error.get('timestamp', 'unknown')}] {error.get('type', 'error')}
   {error.get('message', '')[:300]}
"""

    if health_history:
        prompt += """
HEALTH HISTORY:
"""
        for event in health_history[:5]:
            prompt += f"- {event.get('timestamp', 'unknown')}: {event.get('old_state', '?')} -> {event.get('new_state', '?')}\n"

    if recent_deployments:
        prompt += """
RECENT DEPLOYMENTS:
"""
        for deploy in recent_deployments[:3]:
            prompt += f"- {deploy.get('timestamp', 'unknown')}: {deploy.get('version', 'unknown')}\n"

    if related_services:
        prompt += f"""
RELATED SERVICES: {', '.join(related_services)}
"""

    prompt += """
Identify the root cause. Respond with the JSON structure specified."""

    return prompt


def build_impact_analysis_prompt(
    service_name: str,
    error_summary: str,
    affected_endpoints: Optional[List[str]] = None,
    error_rate: Optional[float] = None,
    user_impact_signals: Optional[List[str]] = None,
) -> str:
    """Build a prompt for impact analysis.

    Args:
        service_name: Name of the affected service
        error_summary: Summary of the error
        affected_endpoints: List of affected API endpoints
        error_rate: Current error rate (0-1)
        user_impact_signals: Signs of user impact

    Returns:
        Formatted prompt string
    """
    prompt = f"""Assess the impact of this issue:

SERVICE: {service_name}
ERROR: {error_summary}
"""

    if affected_endpoints:
        prompt += f"""
AFFECTED ENDPOINTS:
{chr(10).join(f'- {ep}' for ep in affected_endpoints)}
"""

    if error_rate is not None:
        prompt += f"""
ERROR RATE: {error_rate * 100:.1f}%
"""

    if user_impact_signals:
        prompt += f"""
USER IMPACT SIGNALS:
{chr(10).join(f'- {sig}' for sig in user_impact_signals)}
"""

    prompt += """
Respond with JSON:
{
    "severity": "critical|high|medium|low",
    "user_impact": "Description of how users are affected",
    "business_impact": "Description of business consequences",
    "affected_users_estimate": "all|most|some|few|none",
    "degradation_type": "complete_outage|partial_outage|degraded_performance|minor_issue",
    "urgency": "immediate|urgent|normal|low"
}"""

    return prompt
