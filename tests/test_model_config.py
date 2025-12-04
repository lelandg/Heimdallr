"""Tests for model configuration."""
import pytest
from app.model_config import (
    get_model_config,
    get_model_info,
    supports_thinking,
    get_thinking_params,
    get_all_models,
    get_models_by_provider,
)


def test_get_model_config_known_model():
    """Test getting config for a known model."""
    config = get_model_config("gpt-4o")

    assert config.model_id == "gpt-4o"
    assert config.provider == "openai"
    assert config.max_output_tokens == 16384


def test_get_model_config_with_provider_prefix():
    """Test getting config with provider prefix."""
    config = get_model_config("openai/gpt-4o")

    assert config.model_id == "gpt-4o"
    assert config.provider == "openai"


def test_get_model_config_claude():
    """Test Claude model config."""
    config = get_model_config("claude-opus-4-5-20251101")

    assert config.provider == "anthropic"
    assert config.supports_thinking is True
    assert config.max_output_tokens == 64000


def test_get_model_config_unknown_defaults_to_openai():
    """Test unknown model defaults to OpenAI config."""
    config = get_model_config("unknown-model")

    assert config.provider == "openai"
    assert config.max_output_tokens == 16384


def test_supports_thinking():
    """Test thinking support detection."""
    assert supports_thinking("claude-opus-4-5-20251101") is True
    assert supports_thinking("o3") is True
    assert supports_thinking("gpt-4o") is False


def test_get_thinking_params():
    """Test thinking parameter generation."""
    params = get_thinking_params("claude-opus-4-5-20251101", "high")

    assert "reasoning_effort" in params or "budget_tokens" in params


def test_get_all_models():
    """Test getting all model IDs."""
    models = get_all_models()

    assert len(models) > 10
    assert "gpt-4o" in models
    assert "claude-opus-4-5-20251101" in models


def test_get_models_by_provider():
    """Test filtering models by provider."""
    openai_models = get_models_by_provider("openai")
    anthropic_models = get_models_by_provider("anthropic")
    google_models = get_models_by_provider("google")

    assert len(openai_models) > 5
    assert len(anthropic_models) > 3
    assert len(google_models) > 5

    # Check no overlap
    assert not set(openai_models) & set(anthropic_models)


def test_get_model_info():
    """Test model info string generation."""
    info = get_model_info("gpt-4o")

    assert "gpt-4o" in info
    assert "openai" in info
    assert "tokens" in info
