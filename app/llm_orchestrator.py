"""LLM orchestrator for multi-model management and intelligent routing.

Provides:
- Model selection based on task complexity
- Load balancing across providers
- Stuck detection and automatic failover
- Usage tracking and cost optimization
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from app.config import LLMSettings
from app.llm_client import LLMClient, LLMResponse, LLMError, LLMTimeoutError, LLMStuckError
from app.model_config import get_model_config, supports_thinking

log = logging.getLogger("monitor.llm_orchestrator")


class TaskComplexity(Enum):
    """Complexity level for routing decisions."""
    SIMPLE = "simple"      # Quick triage, yes/no decisions
    MODERATE = "moderate"  # Standard analysis, recommendations
    COMPLEX = "complex"    # Deep analysis, multi-step reasoning


class ModelState(Enum):
    """Health state of a model."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"  # Slower than usual, occasional failures
    UNHEALTHY = "unhealthy"  # Frequent failures
    CIRCUIT_OPEN = "circuit_open"  # Temporarily disabled


@dataclass
class ModelHealth:
    """Health metrics for a model."""
    model: str
    state: ModelState = ModelState.HEALTHY
    consecutive_failures: int = 0
    total_requests: int = 0
    total_failures: int = 0
    avg_latency_ms: float = 0
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    circuit_open_until: Optional[datetime] = None

    def record_success(self, latency_ms: int) -> None:
        """Record a successful request."""
        self.total_requests += 1
        self.consecutive_failures = 0
        self.last_success = datetime.now(timezone.utc)

        # Update rolling average latency
        if self.avg_latency_ms == 0:
            self.avg_latency_ms = latency_ms
        else:
            self.avg_latency_ms = (self.avg_latency_ms * 0.9) + (latency_ms * 0.1)

        # Recover from degraded state
        if self.state == ModelState.DEGRADED:
            self.state = ModelState.HEALTHY

    def record_failure(self) -> None:
        """Record a failed request."""
        self.total_requests += 1
        self.total_failures += 1
        self.consecutive_failures += 1
        self.last_failure = datetime.now(timezone.utc)

        # Update state based on failures
        if self.consecutive_failures >= 5:
            self.state = ModelState.CIRCUIT_OPEN
            self.circuit_open_until = datetime.now(timezone.utc) + timedelta(minutes=5)
        elif self.consecutive_failures >= 3:
            self.state = ModelState.UNHEALTHY
        elif self.consecutive_failures >= 2:
            self.state = ModelState.DEGRADED

    def is_available(self) -> bool:
        """Check if model is available for requests."""
        if self.state == ModelState.CIRCUIT_OPEN:
            if self.circuit_open_until and datetime.now(timezone.utc) > self.circuit_open_until:
                # Circuit breaker recovery
                self.state = ModelState.DEGRADED
                self.circuit_open_until = None
                return True
            return False
        return True

    @property
    def failure_rate(self) -> float:
        """Calculate failure rate."""
        if self.total_requests == 0:
            return 0.0
        return self.total_failures / self.total_requests


@dataclass
class UsageMetrics:
    """Usage metrics for cost tracking."""
    model: str
    total_tokens: int = 0
    total_requests: int = 0
    total_cost_usd: float = 0.0


class LLMOrchestrator:
    """Orchestrates LLM requests across multiple models.

    Features:
    - Intelligent model routing based on task complexity
    - Circuit breaker pattern for fault tolerance
    - Usage tracking for cost optimization
    - Runtime model switching
    """

    # Cost per 1K tokens (approximate, Dec 2025)
    TOKEN_COSTS = {
        "gpt-5": {"input": 0.005, "output": 0.015},
        "gpt-5-mini": {"input": 0.0003, "output": 0.0012},
        "gpt-4o": {"input": 0.0025, "output": 0.01},
        "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
        "claude-opus-4-5-20251101": {"input": 0.015, "output": 0.075},
        "claude-sonnet-4-20250514": {"input": 0.003, "output": 0.015},
        "gemini-2.5-pro": {"input": 0.00125, "output": 0.005},
        "gemini-2.5-flash": {"input": 0.000075, "output": 0.0003},
    }

    def __init__(
        self,
        llm_client: LLMClient,
        settings: LLMSettings,
        on_model_switch: Optional[Callable[[str, str, str], None]] = None,
    ):
        """Initialize the orchestrator.

        Args:
            llm_client: LLM client for making requests
            settings: LLM configuration
            on_model_switch: Callback when models are switched (old, new, reason)
        """
        self.llm_client = llm_client
        self.settings = settings
        self.on_model_switch = on_model_switch

        # Model health tracking
        self._model_health: Dict[str, ModelHealth] = {}

        # Usage metrics
        self._usage: Dict[str, UsageMetrics] = {}

        # Model preferences by complexity
        self._model_preferences = {
            TaskComplexity.SIMPLE: [
                settings.primary_model,
                "openai/gpt-4o-mini",
                "google/gemini-2.5-flash",
            ],
            TaskComplexity.MODERATE: [
                settings.primary_model,
                "openai/gpt-4o",
                "anthropic/claude-sonnet-4-20250514",
            ],
            TaskComplexity.COMPLEX: [
                settings.analysis_model,
                "openai/gpt-5",
                "anthropic/claude-opus-4-5-20251101",
            ],
        }

        # Stuck detection
        self._stuck_patterns = [
            "I apologize",  # Repeated apologies
            "I cannot",     # Repeated refusals
            "As an AI",     # Meta-commentary
        ]

    async def complete(
        self,
        messages: List[Dict[str, Any]],
        complexity: TaskComplexity = TaskComplexity.MODERATE,
        system_prompt: Optional[str] = None,
        require_thinking: bool = False,
        max_retries: int = 3,
    ) -> LLMResponse:
        """Execute a completion with intelligent routing.

        Args:
            messages: Conversation messages
            complexity: Task complexity for routing
            system_prompt: Optional system prompt
            require_thinking: Require extended thinking support
            max_retries: Maximum retry attempts

        Returns:
            LLMResponse from the selected model

        Raises:
            LLMError: If all models fail
        """
        # Get preferred models for complexity
        preferred_models = self._get_available_models(complexity, require_thinking)

        if not preferred_models:
            raise LLMError("No models available (all circuit breakers open)")

        last_error: Optional[Exception] = None
        switched_model = False

        for attempt, model in enumerate(preferred_models[:max_retries]):
            try:
                # Get model health
                health = self._get_health(model)

                log.debug(f"Attempting completion with {model} (attempt {attempt + 1})")

                # Make request
                start_time = time.time()
                response = await self.llm_client.complete(
                    messages=messages,
                    system_prompt=system_prompt,
                    model=model,
                    thinking_effort="medium" if require_thinking and supports_thinking(model) else None,
                    use_fallback=False,  # We handle fallback at orchestrator level
                )

                # Record success
                latency_ms = int((time.time() - start_time) * 1000)
                health.record_success(latency_ms)

                # Track usage
                self._record_usage(model, response.tokens_used)

                # Check for stuck response
                if self._is_stuck_response(response.content):
                    raise LLMStuckError(f"Response from {model} appears stuck")

                # Note if we switched models
                if switched_model and self.on_model_switch:
                    self.on_model_switch(
                        preferred_models[0],
                        model,
                        f"Switched after {attempt} failures",
                    )

                return response

            except (LLMTimeoutError, LLMStuckError) as e:
                health = self._get_health(model)
                health.record_failure()
                last_error = e
                switched_model = True
                log.warning(f"Model {model} failed: {e}")

            except Exception as e:
                health = self._get_health(model)
                health.record_failure()
                last_error = e
                switched_model = True
                log.warning(f"Model {model} error: {e}")

        raise LLMError(f"All models failed after {max_retries} attempts. Last error: {last_error}")

    async def analyze_error(
        self,
        error_message: str,
        context: Optional[str] = None,
        quick: bool = False,
    ) -> LLMResponse:
        """Analyze an error using appropriate model.

        Args:
            error_message: Error to analyze
            context: Additional context
            quick: Use quick triage (simple model)

        Returns:
            LLMResponse with analysis
        """
        complexity = TaskComplexity.SIMPLE if quick else TaskComplexity.COMPLEX

        messages = [
            {
                "role": "user",
                "content": f"Analyze this error:\n\n{error_message}\n\n{f'Context: {context}' if context else ''}"
            }
        ]

        return await self.complete(
            messages=messages,
            complexity=complexity,
            require_thinking=not quick,
        )

    def _get_available_models(
        self,
        complexity: TaskComplexity,
        require_thinking: bool,
    ) -> List[str]:
        """Get available models for the given requirements."""
        preferred = self._model_preferences.get(complexity, [])
        fallbacks = self.settings.fallback_models

        # Combine preferred and fallback, removing duplicates
        all_models = []
        seen = set()
        for model in preferred + fallbacks:
            if model not in seen:
                all_models.append(model)
                seen.add(model)

        # Filter by requirements
        available = []
        for model in all_models:
            health = self._get_health(model)
            if not health.is_available():
                continue

            if require_thinking and not supports_thinking(model):
                continue

            available.append(model)

        return available

    def _get_health(self, model: str) -> ModelHealth:
        """Get or create health tracker for model."""
        if model not in self._model_health:
            self._model_health[model] = ModelHealth(model=model)
        return self._model_health[model]

    def _record_usage(self, model: str, tokens: int) -> None:
        """Record token usage for a model."""
        if model not in self._usage:
            self._usage[model] = UsageMetrics(model=model)

        metrics = self._usage[model]
        metrics.total_tokens += tokens
        metrics.total_requests += 1

        # Estimate cost
        model_id = model.split("/")[-1] if "/" in model else model
        costs = self.TOKEN_COSTS.get(model_id, {"input": 0.001, "output": 0.004})
        # Rough estimate: assume 30% input, 70% output
        estimated_cost = (tokens * 0.3 * costs["input"] + tokens * 0.7 * costs["output"]) / 1000
        metrics.total_cost_usd += estimated_cost

    def _is_stuck_response(self, content: str) -> bool:
        """Check if response indicates model is stuck."""
        if not content or len(content) < 20:
            return True

        # Check for stuck patterns appearing multiple times
        for pattern in self._stuck_patterns:
            if content.count(pattern) > 2:
                return True

        # Check for excessive repetition
        words = content.split()
        if len(words) > 50:
            unique_ratio = len(set(words)) / len(words)
            if unique_ratio < 0.3:  # Less than 30% unique words
                return True

        return False

    def get_model_health(self) -> Dict[str, Dict]:
        """Get health status for all models."""
        return {
            model: {
                "state": health.state.value,
                "failure_rate": round(health.failure_rate * 100, 1),
                "avg_latency_ms": round(health.avg_latency_ms),
                "consecutive_failures": health.consecutive_failures,
                "total_requests": health.total_requests,
                "available": health.is_available(),
            }
            for model, health in self._model_health.items()
        }

    def get_usage_stats(self) -> Dict[str, Dict]:
        """Get usage statistics for all models."""
        return {
            model: {
                "total_tokens": metrics.total_tokens,
                "total_requests": metrics.total_requests,
                "estimated_cost_usd": round(metrics.total_cost_usd, 4),
            }
            for model, metrics in self._usage.items()
        }

    def reset_circuit_breaker(self, model: str) -> bool:
        """Manually reset circuit breaker for a model.

        Args:
            model: Model to reset

        Returns:
            True if reset, False if model not found
        """
        if model in self._model_health:
            health = self._model_health[model]
            health.state = ModelState.HEALTHY
            health.consecutive_failures = 0
            health.circuit_open_until = None
            log.info(f"Circuit breaker reset for {model}")
            return True
        return False

    def set_model_preference(
        self,
        complexity: TaskComplexity,
        models: List[str],
    ) -> None:
        """Update model preferences for a complexity level.

        Args:
            complexity: Complexity level to update
            models: Ordered list of preferred models
        """
        self._model_preferences[complexity] = models
        log.info(f"Updated {complexity.value} model preferences: {models}")
