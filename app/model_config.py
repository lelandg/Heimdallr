"""Model configuration with max tokens, thinking modes, and capabilities.

This module provides model-specific configurations for all supported LLM providers,
including maximum output tokens and extended thinking/reasoning support.

Updated: December 2025
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Dict, Tuple, Any
import logging

log = logging.getLogger("monitor.model_config")


@dataclass
class ModelConfig:
    """Configuration for a specific LLM model."""

    # Model identification
    model_id: str
    provider: str  # openai, anthropic, google

    # Token limits
    max_output_tokens: int
    default_output_tokens: int = 4096
    context_window: int = 128000

    # Thinking/reasoning support
    supports_thinking: bool = False
    thinking_param: Optional[str] = None  # reasoning_effort, extended_thinking, thinkingBudget

    # Provider-specific notes
    uses_max_completion_tokens: bool = False  # OpenAI reasoning models
    requires_beta_header: bool = False  # Anthropic extended thinking


# ============================================================================
# Model Registry - All supported models with their capabilities (Dec 2025)
# ============================================================================

MODEL_CONFIGS: Dict[str, ModelConfig] = {
    # -------------------------------------------------------------------------
    # OpenAI Models
    # -------------------------------------------------------------------------

    # GPT-5 (flagship)
    "gpt-5": ModelConfig(
        model_id="gpt-5",
        provider="openai",
        max_output_tokens=128000,
        default_output_tokens=16000,
        context_window=400000,
        supports_thinking=False,
        uses_max_completion_tokens=True,
    ),
    "openai/gpt-5": ModelConfig(
        model_id="gpt-5",
        provider="openai",
        max_output_tokens=128000,
        default_output_tokens=16000,
        context_window=400000,
        supports_thinking=False,
        uses_max_completion_tokens=True,
    ),
    "openai/gpt-5-chat-latest": ModelConfig(
        model_id="gpt-5-chat-latest",
        provider="openai",
        max_output_tokens=128000,
        default_output_tokens=16000,
        context_window=400000,
        supports_thinking=False,
        uses_max_completion_tokens=True,
    ),
    "gpt-5-chat-latest": ModelConfig(
        model_id="gpt-5-chat-latest",
        provider="openai",
        max_output_tokens=128000,
        default_output_tokens=16000,
        context_window=400000,
        supports_thinking=False,
        uses_max_completion_tokens=True,
    ),

    # GPT-4.1 series
    "gpt-4.1": ModelConfig(
        model_id="gpt-4.1",
        provider="openai",
        max_output_tokens=32768,
        default_output_tokens=8192,
        context_window=1000000,
        uses_max_completion_tokens=True,
    ),
    "gpt-4.1-mini": ModelConfig(
        model_id="gpt-4.1-mini",
        provider="openai",
        max_output_tokens=32768,
        default_output_tokens=8192,
        context_window=1000000,
        uses_max_completion_tokens=True,
    ),

    # GPT-5 Mini and Nano (fast/efficient)
    "gpt-5-mini": ModelConfig(
        model_id="gpt-5-mini",
        provider="openai",
        max_output_tokens=32768,
        default_output_tokens=8192,
        context_window=200000,
        uses_max_completion_tokens=True,
    ),
    "openai/gpt-5-mini": ModelConfig(
        model_id="gpt-5-mini",
        provider="openai",
        max_output_tokens=32768,
        default_output_tokens=8192,
        context_window=200000,
        uses_max_completion_tokens=True,
    ),
    "gpt-5-nano": ModelConfig(
        model_id="gpt-5-nano",
        provider="openai",
        max_output_tokens=16384,
        default_output_tokens=4096,
        context_window=128000,
        uses_max_completion_tokens=True,
    ),
    "openai/gpt-5-nano": ModelConfig(
        model_id="gpt-5-nano",
        provider="openai",
        max_output_tokens=16384,
        default_output_tokens=4096,
        context_window=128000,
        uses_max_completion_tokens=True,
    ),

    # GPT-5.1 Codex (optimized for coding/agentic tasks)
    "gpt-5.1-codex": ModelConfig(
        model_id="gpt-5.1-codex",
        provider="openai",
        max_output_tokens=128000,
        default_output_tokens=16000,
        context_window=400000,
        uses_max_completion_tokens=True,
    ),
    "openai/gpt-5.1-codex": ModelConfig(
        model_id="gpt-5.1-codex",
        provider="openai",
        max_output_tokens=128000,
        default_output_tokens=16000,
        context_window=400000,
        uses_max_completion_tokens=True,
    ),
    "gpt-5.1-codex-mini": ModelConfig(
        model_id="gpt-5.1-codex-mini",
        provider="openai",
        max_output_tokens=32768,
        default_output_tokens=8192,
        context_window=200000,
        uses_max_completion_tokens=True,
    ),
    "openai/gpt-5.1-codex-mini": ModelConfig(
        model_id="gpt-5.1-codex-mini",
        provider="openai",
        max_output_tokens=32768,
        default_output_tokens=8192,
        context_window=200000,
        uses_max_completion_tokens=True,
    ),

    # GPT-4o series (legacy, still supported)
    "gpt-4o": ModelConfig(
        model_id="gpt-4o",
        provider="openai",
        max_output_tokens=16384,
        default_output_tokens=4096,
        context_window=128000,
        uses_max_completion_tokens=True,
    ),
    "openai/gpt-4o": ModelConfig(
        model_id="gpt-4o",
        provider="openai",
        max_output_tokens=16384,
        default_output_tokens=4096,
        context_window=128000,
        uses_max_completion_tokens=True,
    ),
    "gpt-4o-mini": ModelConfig(
        model_id="gpt-4o-mini",
        provider="openai",
        max_output_tokens=16384,
        default_output_tokens=4096,
        context_window=128000,
        uses_max_completion_tokens=True,
    ),
    "openai/gpt-4o-mini": ModelConfig(
        model_id="gpt-4o-mini",
        provider="openai",
        max_output_tokens=16384,
        default_output_tokens=4096,
        context_window=128000,
        uses_max_completion_tokens=True,
    ),

    # OpenAI Reasoning Models (o-series)
    "o1": ModelConfig(
        model_id="o1",
        provider="openai",
        max_output_tokens=100000,
        default_output_tokens=16000,
        context_window=200000,
        supports_thinking=True,
        thinking_param="reasoning_effort",
        uses_max_completion_tokens=True,
    ),
    "o3": ModelConfig(
        model_id="o3",
        provider="openai",
        max_output_tokens=100000,
        default_output_tokens=16000,
        context_window=200000,
        supports_thinking=True,
        thinking_param="reasoning_effort",
        uses_max_completion_tokens=True,
    ),
    "o3-mini": ModelConfig(
        model_id="o3-mini",
        provider="openai",
        max_output_tokens=100000,
        default_output_tokens=16000,
        context_window=200000,
        supports_thinking=True,
        thinking_param="reasoning_effort",
        uses_max_completion_tokens=True,
    ),
    "o4-mini": ModelConfig(
        model_id="o4-mini",
        provider="openai",
        max_output_tokens=100000,
        default_output_tokens=16000,
        context_window=200000,
        supports_thinking=True,
        thinking_param="reasoning_effort",
        uses_max_completion_tokens=True,
    ),

    # -------------------------------------------------------------------------
    # Anthropic Claude Models
    # -------------------------------------------------------------------------

    # Claude 4.5 series (latest - Nov 2025)
    "claude-opus-4-5-20251101": ModelConfig(
        model_id="claude-opus-4-5-20251101",
        provider="anthropic",
        max_output_tokens=64000,
        default_output_tokens=8192,
        context_window=200000,
        supports_thinking=True,
        thinking_param="extended_thinking",
        requires_beta_header=True,
    ),
    "anthropic/claude-opus-4-5-20251101": ModelConfig(
        model_id="claude-opus-4-5-20251101",
        provider="anthropic",
        max_output_tokens=64000,
        default_output_tokens=8192,
        context_window=200000,
        supports_thinking=True,
        thinking_param="extended_thinking",
        requires_beta_header=True,
    ),
    "claude-sonnet-4-5-20250929": ModelConfig(
        model_id="claude-sonnet-4-5-20250929",
        provider="anthropic",
        max_output_tokens=64000,
        default_output_tokens=8192,
        context_window=200000,
        supports_thinking=True,
        thinking_param="extended_thinking",
        requires_beta_header=True,
    ),
    "anthropic/claude-sonnet-4-5-20250929": ModelConfig(
        model_id="claude-sonnet-4-5-20250929",
        provider="anthropic",
        max_output_tokens=64000,
        default_output_tokens=8192,
        context_window=200000,
        supports_thinking=True,
        thinking_param="extended_thinking",
        requires_beta_header=True,
    ),

    # Claude 4 series
    "claude-opus-4-20250514": ModelConfig(
        model_id="claude-opus-4-20250514",
        provider="anthropic",
        max_output_tokens=64000,
        default_output_tokens=8192,
        context_window=200000,
        supports_thinking=True,
        thinking_param="extended_thinking",
        requires_beta_header=True,
    ),
    "claude-sonnet-4-20250514": ModelConfig(
        model_id="claude-sonnet-4-20250514",
        provider="anthropic",
        max_output_tokens=64000,
        default_output_tokens=8192,
        context_window=200000,
        supports_thinking=True,
        thinking_param="extended_thinking",
        requires_beta_header=True,
    ),
    "anthropic/claude-sonnet-4-20250514": ModelConfig(
        model_id="claude-sonnet-4-20250514",
        provider="anthropic",
        max_output_tokens=64000,
        default_output_tokens=8192,
        context_window=200000,
        supports_thinking=True,
        thinking_param="extended_thinking",
        requires_beta_header=True,
    ),

    # Claude 3.5 series (still supported)
    "claude-3-5-sonnet-20241022": ModelConfig(
        model_id="claude-3-5-sonnet-20241022",
        provider="anthropic",
        max_output_tokens=8192,
        default_output_tokens=4096,
        context_window=200000,
        supports_thinking=False,
    ),

    # -------------------------------------------------------------------------
    # Google Gemini Models
    # -------------------------------------------------------------------------

    # Gemini 2.5 series (latest)
    "gemini-2.5-pro": ModelConfig(
        model_id="gemini-2.5-pro",
        provider="google",
        max_output_tokens=65536,
        default_output_tokens=8192,
        context_window=1000000,
        supports_thinking=True,
        thinking_param="thinkingBudget",
    ),
    "google/gemini-2.5-pro": ModelConfig(
        model_id="gemini-2.5-pro",
        provider="google",
        max_output_tokens=65536,
        default_output_tokens=8192,
        context_window=1000000,
        supports_thinking=True,
        thinking_param="thinkingBudget",
    ),
    "gemini-2.5-flash": ModelConfig(
        model_id="gemini-2.5-flash",
        provider="google",
        max_output_tokens=65536,
        default_output_tokens=8192,
        context_window=1000000,
        supports_thinking=True,
        thinking_param="thinkingBudget",
    ),
    "google/gemini-2.5-flash": ModelConfig(
        model_id="gemini-2.5-flash",
        provider="google",
        max_output_tokens=65536,
        default_output_tokens=8192,
        context_window=1000000,
        supports_thinking=True,
        thinking_param="thinkingBudget",
    ),
    "gemini-2.5-flash-lite": ModelConfig(
        model_id="gemini-2.5-flash-lite",
        provider="google",
        max_output_tokens=65536,
        default_output_tokens=8192,
        context_window=1000000,
        supports_thinking=True,
        thinking_param="thinkingBudget",
    ),

    # Gemini 2.0 series
    "gemini-2.0-pro": ModelConfig(
        model_id="gemini-2.0-pro",
        provider="google",
        max_output_tokens=8192,
        default_output_tokens=4096,
        context_window=2000000,
        supports_thinking=False,
    ),
    "gemini-2.0-flash": ModelConfig(
        model_id="gemini-2.0-flash",
        provider="google",
        max_output_tokens=8192,
        default_output_tokens=4096,
        context_window=1000000,
        supports_thinking=False,
    ),
    "google/gemini-2.0-flash": ModelConfig(
        model_id="gemini-2.0-flash",
        provider="google",
        max_output_tokens=8192,
        default_output_tokens=4096,
        context_window=1000000,
        supports_thinking=False,
    ),

    # Gemini 1.5 series (still supported)
    "gemini-1.5-pro": ModelConfig(
        model_id="gemini-1.5-pro",
        provider="google",
        max_output_tokens=8192,
        default_output_tokens=4096,
        context_window=2000000,
        supports_thinking=False,
    ),
    "gemini-1.5-flash": ModelConfig(
        model_id="gemini-1.5-flash",
        provider="google",
        max_output_tokens=8192,
        default_output_tokens=4096,
        context_window=1000000,
        supports_thinking=False,
    ),
}

# Maps effort levels to provider-specific values
EFFORT_MAPPING = {
    # OpenAI reasoning_effort values
    "openai": {
        "ultra": "high",  # OpenAI max is "high"
        "high": "high",
        "medium": "medium",
        "low": "low",
    },
    # Anthropic budget_tokens (with extended_thinking=True)
    "anthropic": {
        "ultra": 64000,   # Maximum budget
        "high": 32000,
        "medium": 16000,
        "low": 8000,
    },
    # Google thinkingBudget tokens
    "google": {
        "ultra": 24576,   # Maximum
        "high": 16384,
        "medium": 8192,
        "low": 4096,
    },
}


def get_model_config(model: str) -> ModelConfig:
    """Get configuration for a model, with fallback for unknown models.

    Args:
        model: Model identifier (e.g., "gpt-4o", "anthropic/claude-opus-4-5-20251101")

    Returns:
        ModelConfig for the model, or a default config for unknown models
    """
    # Try exact match first
    if model in MODEL_CONFIGS:
        return MODEL_CONFIGS[model]

    # Try lowercase match
    model_lower = model.lower()
    for key, config in MODEL_CONFIGS.items():
        if key.lower() == model_lower:
            return config

    # Try matching just the model part after provider prefix
    if "/" in model:
        _, model_name = model.split("/", 1)
        if model_name in MODEL_CONFIGS:
            return MODEL_CONFIGS[model_name]
        for key, config in MODEL_CONFIGS.items():
            if key.lower() == model_name.lower():
                return config

    # Infer provider and create default config
    provider = "openai"  # default
    if "claude" in model.lower() or "anthropic" in model.lower():
        provider = "anthropic"
    elif "gemini" in model.lower() or "google" in model.lower():
        provider = "google"

    log.warning(f"Unknown model '{model}', using default config for {provider}")

    # Return sensible defaults based on provider
    if provider == "anthropic":
        return ModelConfig(
            model_id=model,
            provider=provider,
            max_output_tokens=8192,
            default_output_tokens=4096,
            context_window=200000,
        )
    elif provider == "google":
        return ModelConfig(
            model_id=model,
            provider=provider,
            max_output_tokens=8192,
            default_output_tokens=4096,
            context_window=1000000,
        )
    else:  # openai
        return ModelConfig(
            model_id=model,
            provider=provider,
            max_output_tokens=16384,
            default_output_tokens=4096,
            context_window=128000,
            uses_max_completion_tokens=True,
        )


def get_thinking_params(model: str, effort: str) -> Dict[str, Any]:
    """Get provider-specific parameters for thinking mode.

    Args:
        model: Model identifier
        effort: Effort level ('ultra', 'high', 'medium', 'low')

    Returns:
        Dict of parameters to pass to litellm
    """
    config = get_model_config(model)

    if not config.supports_thinking:
        log.debug(f"Model {model} does not support thinking mode")
        return {}

    provider = config.provider
    params: Dict[str, Any] = {}

    if provider == "openai":
        # OpenAI uses reasoning_effort parameter
        params["reasoning_effort"] = EFFORT_MAPPING["openai"].get(effort, "medium")

    elif provider == "anthropic":
        # Anthropic uses extended_thinking + budget_tokens
        params["reasoning_effort"] = effort
        budget = EFFORT_MAPPING["anthropic"].get(effort, 16000)
        params["budget_tokens"] = budget

    elif provider == "google":
        # Google uses thinkingBudget
        params["reasoning_effort"] = effort

    log.info(f"Thinking params for {model} at {effort}: {params}")
    return params


def get_max_tokens_for_model(model: str, use_maximum: bool = False) -> int:
    """Get appropriate max tokens for a model.

    Args:
        model: Model identifier
        use_maximum: If True, return the absolute maximum; otherwise return default

    Returns:
        Max tokens value
    """
    config = get_model_config(model)
    if use_maximum:
        return config.max_output_tokens
    return config.default_output_tokens


def supports_thinking(model: str) -> bool:
    """Check if a model supports extended thinking mode."""
    config = get_model_config(model)
    return config.supports_thinking


def get_model_info(model: str) -> str:
    """Get a human-readable description of model capabilities."""
    config = get_model_config(model)
    thinking_status = "with extended thinking" if config.supports_thinking else "standard"
    return (
        f"{config.model_id} ({config.provider}): "
        f"max {config.max_output_tokens:,} tokens, "
        f"{config.context_window:,} context, "
        f"{thinking_status}"
    )


def get_all_models() -> list[str]:
    """Get list of all registered model IDs."""
    return sorted(set(config.model_id for config in MODEL_CONFIGS.values()))


def get_models_by_provider(provider: str) -> list[str]:
    """Get all models for a specific provider."""
    return sorted(set(
        config.model_id for config in MODEL_CONFIGS.values()
        if config.provider == provider.lower()
    ))
