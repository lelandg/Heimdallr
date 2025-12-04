"""Tests for configuration loading."""
import pytest
from app.config import AppConfig, LLMSettings, MonitoringSettings


def test_config_loads_defaults():
    """Test that config loads with sensible defaults when no file exists."""
    # This will use defaults since no config.yaml exists
    config = AppConfig.load("nonexistent.yaml")

    assert config.aws.region == "us-east-1"
    assert config.llm.primary_model == "openai/gpt-4o-mini"
    assert config.llm.timeout_s == 30
    assert config.actions.allow_restart is True
    assert config.actions.allow_redeploy is False


def test_llm_settings_defaults():
    """Test LLM settings have correct defaults."""
    settings = LLMSettings()

    assert settings.primary_model == "openai/gpt-4o-mini"
    assert settings.analysis_model == "anthropic/claude-opus-4-5-20251101"
    assert len(settings.fallback_models) >= 2
    assert settings.max_retries == 3


def test_monitoring_settings_defaults():
    """Test monitoring settings have correct defaults."""
    settings = MonitoringSettings()

    assert settings.log_poll_interval == 30
    assert settings.health_check_interval == 60
    assert settings.error_lookback_minutes == 5
