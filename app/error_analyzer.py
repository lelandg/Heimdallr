"""Error analyzer using LLM for intelligent error diagnosis.

Provides:
- Error classification by type and severity
- Root cause analysis using LLM
- Solution recommendations
- Structured analysis output
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from app.llm_client import LLMClient, LLMResponse
from app.log_collector import DetectedError, ErrorSeverity

log = logging.getLogger("monitor.error_analyzer")


class ErrorCategory(Enum):
    """Categories of errors for classification."""
    INFRASTRUCTURE = "infrastructure"  # AWS, network, resources
    APPLICATION = "application"        # Code bugs, logic errors
    CONFIGURATION = "configuration"    # Config issues, env vars
    DEPENDENCY = "dependency"          # External services, APIs
    PERFORMANCE = "performance"        # Timeouts, slow responses
    SECURITY = "security"              # Auth failures, access denied
    DATA = "data"                      # Data integrity, validation
    UNKNOWN = "unknown"


class RecommendedAction(Enum):
    """Recommended remediation actions."""
    RESTART_SERVICE = "restart_service"
    REDEPLOY = "redeploy"
    SCALE_UP = "scale_up"
    CHECK_DEPENDENCIES = "check_dependencies"
    FIX_CONFIGURATION = "fix_configuration"
    INVESTIGATE = "investigate"
    ESCALATE = "escalate"
    IGNORE = "ignore"


@dataclass
class AnalysisResult:
    """Structured result from error analysis."""
    error_fingerprint: str
    error_message: str
    source_service: str

    # Classification
    category: ErrorCategory
    severity: ErrorSeverity
    confidence: float  # 0-1

    # Analysis
    root_cause: str
    impact: str
    context_summary: str

    # Recommendations
    recommended_action: RecommendedAction
    action_rationale: str
    remediation_steps: List[str]
    prevention_suggestions: List[str]

    # Metadata
    analyzed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    model_used: str = ""
    analysis_tokens: int = 0
    analysis_latency_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "error_fingerprint": self.error_fingerprint,
            "error_message": self.error_message[:200],
            "source_service": self.source_service,
            "category": self.category.value,
            "severity": self.severity.value,
            "confidence": self.confidence,
            "root_cause": self.root_cause,
            "impact": self.impact,
            "recommended_action": self.recommended_action.value,
            "action_rationale": self.action_rationale,
            "remediation_steps": self.remediation_steps,
            "prevention_suggestions": self.prevention_suggestions,
            "analyzed_at": self.analyzed_at.isoformat(),
            "model_used": self.model_used,
        }


class ErrorAnalyzer:
    """LLM-powered error analysis engine.

    Uses LLM to:
    - Classify errors by category
    - Perform root cause analysis
    - Recommend remediation actions
    - Suggest prevention measures
    """

    def __init__(self, llm_client: LLMClient):
        """Initialize the error analyzer.

        Args:
            llm_client: LLM client for analysis requests
        """
        self.llm_client = llm_client

        # Analysis system prompt
        self._analysis_prompt = """You are an expert DevOps engineer analyzing errors from AWS services.

Given error information, you will provide structured analysis in JSON format.

IMPORTANT: Your response MUST be valid JSON matching this exact structure:
{
    "category": "<infrastructure|application|configuration|dependency|performance|security|data|unknown>",
    "severity": "<critical|error|warning|info>",
    "confidence": <0.0-1.0>,
    "root_cause": "<brief root cause explanation>",
    "impact": "<impact on users/service>",
    "recommended_action": "<restart_service|redeploy|scale_up|check_dependencies|fix_configuration|investigate|escalate|ignore>",
    "action_rationale": "<why this action is recommended>",
    "remediation_steps": ["step 1", "step 2", ...],
    "prevention_suggestions": ["suggestion 1", "suggestion 2", ...]
}

Guidelines:
- Be concise but thorough
- Focus on actionable insights
- Consider the service context when making recommendations
- Only recommend restart/redeploy if likely to help
- Escalate when human judgment is needed
- Include specific steps, not generic advice
"""

        # Quick triage prompt
        self._triage_prompt = """You are a DevOps triage assistant. Quickly assess errors.

Respond with ONLY a single line in this format:
SEVERITY | CATEGORY | ACTION | BRIEF_REASON

Where:
- SEVERITY: critical, error, warning, or info
- CATEGORY: infrastructure, application, configuration, dependency, performance, security, data, or unknown
- ACTION: restart_service, redeploy, check_dependencies, investigate, escalate, or ignore
- BRIEF_REASON: One sentence explanation

Example: error | dependency | check_dependencies | Database connection timeout suggests downstream service issue"""

    async def analyze(
        self,
        error: DetectedError,
        context: Optional[str] = None,
        use_analysis_model: bool = True,
    ) -> AnalysisResult:
        """Perform full analysis of an error.

        Args:
            error: Detected error to analyze
            context: Additional context (recent changes, related errors, etc.)
            use_analysis_model: Use the dedicated analysis model

        Returns:
            AnalysisResult with full diagnosis
        """
        # Build analysis request
        request = self._build_analysis_request(error, context)

        try:
            response = await self.llm_client.complete(
                messages=[{"role": "user", "content": request}],
                system_prompt=self._analysis_prompt,
                model=self.llm_client._analysis_model if use_analysis_model else None,
                temperature=0.2,  # More deterministic
                thinking_effort="medium" if use_analysis_model else None,
            )

            result = self._parse_analysis_response(response, error)
            return result

        except Exception as e:
            log.error(f"Error analysis failed: {e}")
            # Return fallback analysis
            return self._fallback_analysis(error, str(e))

    async def quick_triage(
        self,
        error: DetectedError,
    ) -> AnalysisResult:
        """Perform quick triage of an error.

        Uses a faster model for rapid assessment.

        Args:
            error: Detected error to triage

        Returns:
            AnalysisResult with quick assessment
        """
        request = f"""Quick triage:
Service: {error.source_app}
Error type: {error.error_type}
Message: {error.message[:300]}
"""

        try:
            response = await self.llm_client.complete(
                messages=[{"role": "user", "content": request}],
                system_prompt=self._triage_prompt,
                max_tokens=150,
                temperature=0.1,
            )

            result = self._parse_triage_response(response, error)
            return result

        except Exception as e:
            log.error(f"Quick triage failed: {e}")
            return self._fallback_analysis(error, str(e))

    async def analyze_batch(
        self,
        errors: List[DetectedError],
        use_analysis_model: bool = False,
    ) -> List[AnalysisResult]:
        """Analyze multiple errors efficiently.

        Uses quick triage for batch analysis.

        Args:
            errors: List of errors to analyze
            use_analysis_model: Use analysis model (slower but more thorough)

        Returns:
            List of AnalysisResults
        """
        results = []

        for error in errors:
            try:
                if use_analysis_model:
                    result = await self.analyze(error)
                else:
                    result = await self.quick_triage(error)
                results.append(result)
            except Exception as e:
                log.error(f"Batch analysis error: {e}")
                results.append(self._fallback_analysis(error, str(e)))

        return results

    def _build_analysis_request(
        self,
        error: DetectedError,
        context: Optional[str],
    ) -> str:
        """Build the analysis request content."""
        request = f"""Analyze this error:

Service: {error.source_app}
Log Group: {error.log_group}
Timestamp: {error.timestamp.isoformat()}
Error Type: {error.error_type}
Detected Severity: {error.severity.value}
Occurrence Count: {error.count}

Error Message:
{error.message}
"""

        if error.context_lines:
            request += f"""
Context (surrounding log lines):
{chr(10).join(error.context_lines)}
"""

        if context:
            request += f"""
Additional Context:
{context}
"""

        request += """
Provide your analysis as JSON matching the specified structure."""

        return request

    def _parse_analysis_response(
        self,
        response: LLMResponse,
        error: DetectedError,
    ) -> AnalysisResult:
        """Parse LLM response into AnalysisResult."""
        content = response.content

        # Try to extract JSON from response
        try:
            # Look for JSON block
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                data = json.loads(json_match.group())
            else:
                raise ValueError("No JSON found in response")

            return AnalysisResult(
                error_fingerprint=error.fingerprint,
                error_message=error.message,
                source_service=error.source_app,
                category=ErrorCategory(data.get("category", "unknown")),
                severity=ErrorSeverity(data.get("severity", error.severity.value)),
                confidence=float(data.get("confidence", 0.7)),
                root_cause=str(data.get("root_cause", "Unable to determine")),
                impact=str(data.get("impact", "Unknown impact")),
                context_summary="",
                recommended_action=RecommendedAction(
                    data.get("recommended_action", "investigate")
                ),
                action_rationale=str(data.get("action_rationale", "")),
                remediation_steps=data.get("remediation_steps", []),
                prevention_suggestions=data.get("prevention_suggestions", []),
                model_used=response.model,
                analysis_tokens=response.tokens_used,
                analysis_latency_ms=response.latency_ms,
            )

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            log.warning(f"Failed to parse analysis response: {e}")
            # Try to extract what we can from free-form text
            return self._parse_freeform_response(content, response, error)

    def _parse_freeform_response(
        self,
        content: str,
        response: LLMResponse,
        error: DetectedError,
    ) -> AnalysisResult:
        """Parse a free-form text response into AnalysisResult."""
        content_lower = content.lower()

        # Infer category from content
        category = ErrorCategory.UNKNOWN
        for cat in ErrorCategory:
            if cat.value in content_lower:
                category = cat
                break

        # Infer action from content
        action = RecommendedAction.INVESTIGATE
        action_keywords = {
            "restart": RecommendedAction.RESTART_SERVICE,
            "redeploy": RecommendedAction.REDEPLOY,
            "scale": RecommendedAction.SCALE_UP,
            "dependency": RecommendedAction.CHECK_DEPENDENCIES,
            "config": RecommendedAction.FIX_CONFIGURATION,
            "escalate": RecommendedAction.ESCALATE,
            "ignore": RecommendedAction.IGNORE,
        }
        for keyword, act in action_keywords.items():
            if keyword in content_lower:
                action = act
                break

        return AnalysisResult(
            error_fingerprint=error.fingerprint,
            error_message=error.message,
            source_service=error.source_app,
            category=category,
            severity=error.severity,
            confidence=0.5,  # Lower confidence for parsed response
            root_cause=content[:200] if content else "Analysis inconclusive",
            impact="See full analysis",
            context_summary="",
            recommended_action=action,
            action_rationale=content[:100] if content else "",
            remediation_steps=[],
            prevention_suggestions=[],
            model_used=response.model,
            analysis_tokens=response.tokens_used,
            analysis_latency_ms=response.latency_ms,
        )

    def _parse_triage_response(
        self,
        response: LLMResponse,
        error: DetectedError,
    ) -> AnalysisResult:
        """Parse quick triage response."""
        content = response.content.strip()

        # Expected format: SEVERITY | CATEGORY | ACTION | REASON
        parts = [p.strip() for p in content.split("|")]

        if len(parts) >= 4:
            try:
                severity = ErrorSeverity(parts[0].lower())
            except ValueError:
                severity = error.severity

            try:
                category = ErrorCategory(parts[1].lower())
            except ValueError:
                category = ErrorCategory.UNKNOWN

            try:
                action = RecommendedAction(parts[2].lower())
            except ValueError:
                action = RecommendedAction.INVESTIGATE

            rationale = parts[3] if len(parts) > 3 else ""

        else:
            # Fallback parsing
            severity = error.severity
            category = ErrorCategory.UNKNOWN
            action = RecommendedAction.INVESTIGATE
            rationale = content

        return AnalysisResult(
            error_fingerprint=error.fingerprint,
            error_message=error.message,
            source_service=error.source_app,
            category=category,
            severity=severity,
            confidence=0.7,
            root_cause=rationale,
            impact="Quick triage - see full analysis for details",
            context_summary="",
            recommended_action=action,
            action_rationale=rationale,
            remediation_steps=[],
            prevention_suggestions=[],
            model_used=response.model,
            analysis_tokens=response.tokens_used,
            analysis_latency_ms=response.latency_ms,
        )

    def _fallback_analysis(
        self,
        error: DetectedError,
        reason: str,
    ) -> AnalysisResult:
        """Create fallback analysis when LLM fails."""
        # Use heuristics for basic classification
        category = self._heuristic_category(error)
        action = self._heuristic_action(error, category)

        return AnalysisResult(
            error_fingerprint=error.fingerprint,
            error_message=error.message,
            source_service=error.source_app,
            category=category,
            severity=error.severity,
            confidence=0.3,
            root_cause=f"LLM analysis failed: {reason}",
            impact="Unable to assess - manual review required",
            context_summary="",
            recommended_action=action,
            action_rationale="Heuristic-based recommendation",
            remediation_steps=["Review error logs manually", "Check service health"],
            prevention_suggestions=[],
            model_used="fallback",
            analysis_tokens=0,
            analysis_latency_ms=0,
        )

    def _heuristic_category(self, error: DetectedError) -> ErrorCategory:
        """Use heuristics to categorize error."""
        error_type = error.error_type.lower()
        message = error.message.lower()

        if any(k in error_type for k in ["timeout", "connection", "network"]):
            return ErrorCategory.DEPENDENCY
        if any(k in error_type for k in ["memory", "oom", "cpu"]):
            return ErrorCategory.INFRASTRUCTURE
        if any(k in message for k in ["config", "environment", "variable"]):
            return ErrorCategory.CONFIGURATION
        if any(k in message for k in ["auth", "permission", "denied", "forbidden"]):
            return ErrorCategory.SECURITY
        if any(k in error_type for k in ["exception", "error", "traceback"]):
            return ErrorCategory.APPLICATION

        return ErrorCategory.UNKNOWN

    def _heuristic_action(
        self,
        error: DetectedError,
        category: ErrorCategory,
    ) -> RecommendedAction:
        """Use heuristics to recommend action."""
        if error.severity == ErrorSeverity.CRITICAL:
            return RecommendedAction.ESCALATE

        if category == ErrorCategory.DEPENDENCY:
            return RecommendedAction.CHECK_DEPENDENCIES
        if category == ErrorCategory.CONFIGURATION:
            return RecommendedAction.FIX_CONFIGURATION
        if category in {ErrorCategory.INFRASTRUCTURE, ErrorCategory.PERFORMANCE}:
            return RecommendedAction.RESTART_SERVICE
        if category == ErrorCategory.SECURITY:
            return RecommendedAction.ESCALATE

        return RecommendedAction.INVESTIGATE
