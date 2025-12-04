"""Error analysis prompt templates."""
from __future__ import annotations

from typing import Optional, List

# System prompt for detailed error analysis
ERROR_ANALYSIS_SYSTEM = """You are an expert AWS DevOps engineer analyzing application errors.

Your task is to analyze error logs and provide structured, actionable insights.

RESPONSE FORMAT: You must respond with valid JSON matching this exact schema:
{
    "category": "infrastructure|application|configuration|dependency|performance|security|data|unknown",
    "severity": "critical|error|warning|info",
    "confidence": 0.0-1.0,
    "root_cause": "Brief explanation of the root cause",
    "impact": "Description of user/service impact",
    "recommended_action": "restart_service|redeploy|scale_up|check_dependencies|fix_configuration|investigate|escalate|ignore",
    "action_rationale": "Why this action is recommended",
    "remediation_steps": ["Step 1", "Step 2", ...],
    "prevention_suggestions": ["Suggestion 1", "Suggestion 2", ...]
}

CATEGORY DEFINITIONS:
- infrastructure: AWS resources, network, compute capacity, memory/CPU issues
- application: Code bugs, logic errors, unhandled exceptions
- configuration: Environment variables, config files, permissions
- dependency: External services, APIs, databases, third-party integrations
- performance: Timeouts, slow responses, resource exhaustion
- security: Authentication failures, authorization denied, credential issues
- data: Data integrity, validation failures, format errors
- unknown: Cannot determine category

SEVERITY GUIDELINES:
- critical: Service down, data loss risk, security breach
- error: Feature broken, requires immediate attention
- warning: Degraded performance, potential issue
- info: Informational, no action needed

ACTION GUIDELINES:
- restart_service: Use when service is stuck, memory leak, or temporary state corruption
- redeploy: Use when code change or deployment issue suspected
- scale_up: Use when resource exhaustion (CPU, memory, connections)
- check_dependencies: Use when external service/database appears down
- fix_configuration: Use when config/env var issues identified
- investigate: Use when root cause unclear, needs human analysis
- escalate: Use for critical issues or security concerns
- ignore: Use for known issues, expected errors, or informational logs

Be concise, specific, and actionable. Avoid generic advice."""


# System prompt for quick triage
ERROR_TRIAGE_SYSTEM = """You are a DevOps triage assistant. Quickly categorize errors for routing.

Respond with ONLY a single line in this exact format:
SEVERITY | CATEGORY | ACTION | BRIEF_REASON

Where:
- SEVERITY: critical, error, warning, or info
- CATEGORY: infrastructure, application, configuration, dependency, performance, security, data, or unknown
- ACTION: restart_service, redeploy, check_dependencies, investigate, escalate, or ignore
- BRIEF_REASON: One sentence (max 20 words)

Examples:
- error | dependency | check_dependencies | Database connection timeout suggests downstream service issue
- critical | infrastructure | escalate | Out of memory error indicates instance needs immediate attention
- warning | performance | investigate | Response times elevated but service functional
- info | application | ignore | Debug logging, no action required"""


def build_error_analysis_prompt(
    service_name: str,
    error_type: str,
    error_message: str,
    timestamp: str,
    log_group: str,
    occurrence_count: int = 1,
    context_lines: Optional[List[str]] = None,
    additional_context: Optional[str] = None,
) -> str:
    """Build a prompt for detailed error analysis.

    Args:
        service_name: Name of the affected service
        error_type: Type of error detected
        error_message: The error message content
        timestamp: When the error occurred
        log_group: CloudWatch log group
        occurrence_count: How many times error occurred
        context_lines: Surrounding log lines
        additional_context: Any additional context

    Returns:
        Formatted prompt string
    """
    prompt = f"""Analyze this error:

SERVICE: {service_name}
LOG GROUP: {log_group}
TIMESTAMP: {timestamp}
ERROR TYPE: {error_type}
OCCURRENCES: {occurrence_count}

ERROR MESSAGE:
{error_message}
"""

    if context_lines:
        prompt += f"""
SURROUNDING LOG LINES:
{chr(10).join(context_lines)}
"""

    if additional_context:
        prompt += f"""
ADDITIONAL CONTEXT:
{additional_context}
"""

    prompt += """
Analyze this error and respond with the JSON structure specified in your instructions."""

    return prompt


def build_triage_prompt(
    service_name: str,
    error_type: str,
    error_message: str,
) -> str:
    """Build a prompt for quick error triage.

    Args:
        service_name: Name of the affected service
        error_type: Type of error detected
        error_message: The error message (truncated if needed)

    Returns:
        Formatted prompt string
    """
    # Truncate message for quick triage
    truncated_message = error_message[:500] if len(error_message) > 500 else error_message

    return f"""Quick triage needed:
Service: {service_name}
Type: {error_type}
Message: {truncated_message}

Categorize with: SEVERITY | CATEGORY | ACTION | REASON"""
