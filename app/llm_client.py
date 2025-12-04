"""LLM client with multi-provider support via litellm.

Provides:
- Unified API for OpenAI, Anthropic, and Google models
- Runtime model switching
- Automatic fallback when models are stuck or fail
- Extended thinking support for supported models
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.config import LLMSettings
from app.model_config import (
    get_model_config,
    get_thinking_params,
    get_model_info,
)

log = logging.getLogger("monitor.llm")
log_interactions = logging.getLogger("monitor.llm.interactions")


class LLMError(Exception):
    """Base exception for LLM errors."""
    pass


class LLMTimeoutError(LLMError):
    """Raised when LLM request times out."""
    pass


class LLMBlockedError(LLMError):
    """Raised when LLM refuses to respond due to safety filters."""
    pass


class LLMStuckError(LLMError):
    """Raised when LLM appears stuck (repetitive, incomplete, etc.)."""
    pass


@dataclass
class LLMResponse:
    """Structured response from LLM."""
    content: str
    model: str
    provider: str
    tokens_used: int = 0
    latency_ms: int = 0
    was_fallback: bool = False
    fallback_reason: Optional[str] = None


class LLMClient:
    """Multi-provider LLM client with fallback support.

    Uses litellm for unified API access to:
    - OpenAI (GPT-4o, GPT-5, o-series)
    - Anthropic (Claude 4/4.5 series)
    - Google (Gemini 2.0/2.5 series)

    Features:
    - Runtime model switching via set_model()
    - Automatic fallback on failures
    - Extended thinking support
    - Stuck detection
    """

    def __init__(self, settings: LLMSettings):
        """Initialize the LLM client.

        Args:
            settings: LLM configuration settings
        """
        self.settings = settings
        self._current_model = settings.primary_model
        self._analysis_model = settings.analysis_model
        self._fallback_models = settings.fallback_models.copy()

        # Import litellm
        try:
            import litellm
            self._litellm = litellm
        except ImportError:
            log.error("litellm not installed. Run: pip install litellm")
            raise

        # Configure litellm
        self._litellm.drop_params = True  # Drop unsupported params
        self._litellm.suppress_debug_info = True

        # Suppress verbose logging
        logging.getLogger("LiteLLM").setLevel(logging.WARNING)
        logging.getLogger("litellm").setLevel(logging.WARNING)

        # Set API keys from settings/environment
        self._setup_api_keys()

        log.info(f"LLM Client initialized with primary model: {self._current_model}")
        log.info(f"Analysis model: {self._analysis_model}")
        log.info(f"Fallback chain: {self._fallback_models}")

    def _setup_api_keys(self) -> None:
        """Set up API keys in environment for litellm."""
        if self.settings.openai_api_key and not os.environ.get("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = self.settings.openai_api_key

        if self.settings.anthropic_api_key and not os.environ.get("ANTHROPIC_API_KEY"):
            os.environ["ANTHROPIC_API_KEY"] = self.settings.anthropic_api_key

        if self.settings.gemini_api_key and not os.environ.get("GEMINI_API_KEY"):
            os.environ["GEMINI_API_KEY"] = self.settings.gemini_api_key

    @property
    def current_model(self) -> str:
        """Get the current active model."""
        return self._current_model

    def set_model(self, model: str) -> None:
        """Switch to a different model at runtime.

        Args:
            model: Model identifier (e.g., "openai/gpt-4o", "anthropic/claude-opus-4-5-20251101")
        """
        old_model = self._current_model
        self._current_model = model
        log.info(f"Model switched: {old_model} -> {model}")
        log.info(f"New model info: {get_model_info(model)}")

    def set_analysis_model(self, model: str) -> None:
        """Set the model used for detailed analysis.

        Args:
            model: Model identifier
        """
        old_model = self._analysis_model
        self._analysis_model = model
        log.info(f"Analysis model switched: {old_model} -> {model}")

    async def complete(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        thinking_effort: Optional[str] = None,
        use_fallback: bool = True,
    ) -> LLMResponse:
        """Send a completion request to the LLM.

        Args:
            messages: List of message dicts with 'role' and 'content'
            system_prompt: Optional system prompt to prepend
            model: Override the current model for this request
            temperature: Sampling temperature (default from settings)
            max_tokens: Max response tokens (default from settings)
            thinking_effort: Enable thinking mode ('ultra', 'high', 'medium', 'low')
            use_fallback: Whether to try fallback models on failure

        Returns:
            LLMResponse with the completion result

        Raises:
            LLMError: If all models fail
        """
        active_model = model or self._current_model
        models_to_try = [active_model]

        if use_fallback:
            # Add fallbacks that aren't already the active model
            models_to_try.extend(m for m in self._fallback_models if m != active_model)

        last_error: Optional[Exception] = None
        fallback_reason: Optional[str] = None

        for i, try_model in enumerate(models_to_try):
            is_fallback = i > 0

            try:
                response = await self._complete_single(
                    messages=messages,
                    system_prompt=system_prompt,
                    model=try_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    thinking_effort=thinking_effort,
                )

                # Check for stuck response
                if self._is_stuck_response(response.content):
                    raise LLMStuckError(f"Model {try_model} appears stuck")

                if is_fallback:
                    response.was_fallback = True
                    response.fallback_reason = fallback_reason

                return response

            except LLMStuckError as e:
                fallback_reason = f"stuck: {e}"
                last_error = e
                log.warning(f"Model {try_model} stuck, trying fallback: {e}")
                continue

            except asyncio.TimeoutError as e:
                fallback_reason = "timeout"
                last_error = LLMTimeoutError(f"Model {try_model} timed out")
                log.warning(f"Model {try_model} timed out, trying fallback")
                continue

            except Exception as e:
                fallback_reason = str(e)[:50]
                last_error = e
                log.warning(f"Model {try_model} failed: {e}, trying fallback")
                continue

        # All models failed
        raise LLMError(f"All models failed. Last error: {last_error}")

    async def _complete_single(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str],
        model: str,
        temperature: Optional[float],
        max_tokens: Optional[int],
        thinking_effort: Optional[str],
    ) -> LLMResponse:
        """Execute a single completion request without fallback.

        Args:
            messages: Conversation messages
            system_prompt: Optional system prompt
            model: Model to use
            temperature: Sampling temperature
            max_tokens: Max response tokens
            thinking_effort: Thinking mode level

        Returns:
            LLMResponse with completion result
        """
        model_config = get_model_config(model)
        start_time = time.time()

        # Build message list
        full_messages: List[Dict[str, str]] = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        # Build kwargs
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": full_messages,
            "timeout": self.settings.timeout_s,
        }

        # Temperature
        if temperature is not None:
            kwargs["temperature"] = temperature
        else:
            kwargs["temperature"] = self.settings.temperature

        # Max tokens
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        else:
            kwargs["max_tokens"] = min(
                self.settings.max_tokens,
                model_config.default_output_tokens
            )

        # Thinking mode
        if thinking_effort and model_config.supports_thinking:
            thinking_params = get_thinking_params(model, thinking_effort)
            kwargs.update(thinking_params)
            log.info(f"Extended thinking enabled: {model} at {thinking_effort} level")

        # Log request
        log_interactions.info(
            "REQUEST,model=%s,messages=%d,max_tokens=%d,temp=%.2f,thinking=%s",
            model,
            len(full_messages),
            kwargs.get("max_tokens", 0),
            kwargs.get("temperature", 0),
            thinking_effort or "off",
        )

        # Execute request
        try:
            resp = await asyncio.wait_for(
                self._litellm.acompletion(**kwargs),
                timeout=self.settings.stuck_timeout_s,
            )
        except asyncio.TimeoutError:
            log.error(f"Request to {model} timed out after {self.settings.stuck_timeout_s}s")
            raise

        # Parse response
        choice = resp["choices"][0]
        finish_reason = choice.get("finish_reason") or resp.get("finish_reason")

        # Check for safety blocks
        if finish_reason and str(finish_reason).lower() in {"content_filter", "safety"}:
            raise LLMBlockedError(f"Response blocked: {finish_reason}")

        content = choice.get("message", {}).get("content", "")
        if not content:
            content = choice.get("text", "")

        # Calculate metrics
        latency_ms = int((time.time() - start_time) * 1000)
        tokens_used = resp.get("usage", {}).get("total_tokens", 0)

        # Log response
        content_preview = content[:100] + "..." if len(content) > 100 else content
        log_interactions.info(
            "RESPONSE,model=%s,tokens=%d,latency=%dms,finish=%s,preview=%s",
            model,
            tokens_used,
            latency_ms,
            finish_reason or "stop",
            repr(content_preview),
        )

        return LLMResponse(
            content=content.strip(),
            model=model,
            provider=model_config.provider,
            tokens_used=tokens_used,
            latency_ms=latency_ms,
        )

    def _is_stuck_response(self, content: str) -> bool:
        """Detect if a response appears stuck or malformed.

        Args:
            content: Response content to check

        Returns:
            True if response appears stuck
        """
        if not content or len(content) < 10:
            return True

        # Check for repetitive patterns (same phrase repeated)
        words = content.split()
        if len(words) > 20:
            # Check if any 5-word phrase repeats more than 3 times
            for i in range(len(words) - 5):
                phrase = " ".join(words[i:i+5])
                if content.count(phrase) > 3:
                    log.warning(f"Detected repetitive phrase: {phrase[:30]}...")
                    return True

        # Check for incomplete JSON or markdown
        open_brackets = content.count("{") + content.count("[")
        close_brackets = content.count("}") + content.count("]")
        if open_brackets > close_brackets + 2:
            log.warning("Detected potentially incomplete structured output")
            return True

        return False

    async def analyze_error(
        self,
        error_logs: str,
        context: Optional[str] = None,
        use_analysis_model: bool = True,
    ) -> LLMResponse:
        """Analyze error logs using the analysis model.

        Args:
            error_logs: The error log content to analyze
            context: Additional context (app name, recent changes, etc.)
            use_analysis_model: Whether to use the dedicated analysis model

        Returns:
            LLMResponse with analysis
        """
        model = self._analysis_model if use_analysis_model else self._current_model

        messages = [
            {
                "role": "user",
                "content": f"""Analyze these error logs and provide a diagnosis:

{f"Context: {context}" if context else ""}

Error Logs:
```
{error_logs}
```

Provide:
1. Error classification (severity, type)
2. Root cause analysis
3. Recommended action (restart, investigate, escalate, or ignore)
4. Specific remediation steps if action needed
"""
            }
        ]

        return await self.complete(
            messages=messages,
            system_prompt=self.settings.analysis_system_prompt,
            model=model,
            thinking_effort="medium" if use_analysis_model else None,
        )

    async def quick_triage(
        self,
        error_message: str,
    ) -> LLMResponse:
        """Quick triage of a single error message.

        Args:
            error_message: Single error message to triage

        Returns:
            LLMResponse with quick assessment
        """
        messages = [
            {
                "role": "user",
                "content": f"""Quick triage this error (1-2 sentences):
{error_message}

Respond with: SEVERITY (critical/warning/info) | LIKELY_CAUSE | ACTION (restart/investigate/escalate/ignore)
"""
            }
        ]

        return await self.complete(
            messages=messages,
            system_prompt=self.settings.triage_system_prompt,
            max_tokens=200,  # Keep it brief
        )

    async def test_connection(self) -> Dict[str, bool]:
        """Test connection to all configured providers.

        Returns:
            Dict mapping provider name to connection success
        """
        results = {}
        test_message = [{"role": "user", "content": "Hello, respond with just 'OK'"}]

        providers = {
            "openai": "openai/gpt-4o-mini",
            "anthropic": "anthropic/claude-sonnet-4-5-20250929",
            "google": "gemini/gemini-1.5-flash",
        }

        for provider, model in providers.items():
            try:
                await self._complete_single(
                    messages=test_message,
                    system_prompt="Respond only with 'OK'",
                    model=model,
                    temperature=0,
                    max_tokens=10,
                    thinking_effort=None,
                )
                results[provider] = True
                log.info(f"Provider {provider} connection: OK")
            except Exception as e:
                results[provider] = False
                log.warning(f"Provider {provider} connection failed: {e}")

        return results
