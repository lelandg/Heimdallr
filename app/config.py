"""Configuration management for AWS Monitor.

Loads settings from config.yaml with environment variable overrides.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import yaml


@dataclass
class AWSSettings:
    """AWS connection and credential settings."""
    region: str = "us-east-1"
    # Credentials loaded from environment or IAM role


@dataclass
class AmplifyAppConfig:
    """Configuration for a monitored Amplify app."""
    app_id: str
    name: str
    log_group: str = ""  # Auto-generated if empty

    def __post_init__(self):
        if not self.log_group:
            self.log_group = f"/aws/amplify/{self.app_id}"


@dataclass
class EC2InstanceConfig:
    """Configuration for a monitored EC2 instance."""
    instance_id: str
    name: str
    services: list[str] = field(default_factory=list)  # Services to monitor/restart


@dataclass
class MonitoringSettings:
    """Settings for what to monitor and how often."""
    amplify_apps: list[AmplifyAppConfig] = field(default_factory=list)
    ec2_instances: list[EC2InstanceConfig] = field(default_factory=list)
    log_poll_interval: int = 30  # seconds
    health_check_interval: int = 60  # seconds
    error_lookback_minutes: int = 5  # How far back to search for errors


@dataclass
class LLMSettings:
    """LLM provider configuration."""
    # Primary model for quick triage
    primary_model: str = "openai/gpt-5-mini"
    # Analysis model for detailed diagnosis
    analysis_model: str = "anthropic/claude-opus-4-5-20251101"
    # Fallback chain when primary fails
    fallback_models: list[str] = field(default_factory=lambda: [
        "google/gemini-2.5-flash",
        "openai/gpt-5",
    ])

    # API keys (also read from env if not set)
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""

    # Request behavior
    timeout_s: int = 30
    max_tokens: int = 4096
    temperature: float = 0.3  # Lower for more deterministic analysis

    # Stuck detection
    max_retries: int = 3
    stuck_timeout_s: int = 45  # Consider stuck if no response

    # System prompts
    triage_system_prompt: str = """You are an AWS operations expert analyzing error logs.
Your job is to quickly categorize errors and determine if they require action.
Be concise and actionable. Focus on:
1. Error severity (critical, warning, info)
2. Likely cause (code bug, config issue, external dependency, resource exhaustion)
3. Recommended action (restart, investigate, escalate, ignore)
"""

    analysis_system_prompt: str = """You are a senior DevOps engineer performing root cause analysis.
Analyze the error context thoroughly and provide:
1. Root cause identification
2. Impact assessment
3. Recommended remediation steps
4. Prevention recommendations
Be thorough but focused on actionable insights.
"""


@dataclass
class ActionSettings:
    """Settings for automated remediation actions."""
    # What actions are allowed
    allow_restart: bool = True
    allow_redeploy: bool = False  # Requires manual approval by default

    # Safety limits
    max_restarts_per_hour: int = 3
    cooldown_minutes: int = 10
    require_approval_for: list[str] = field(default_factory=lambda: ["redeploy", "terminate"])


@dataclass
class NotificationSettings:
    """Notification channel configuration."""
    # Email via SES
    email_enabled: bool = True
    email_recipients: list[str] = field(default_factory=list)
    email_from: str = "monitor@yourdomain.com"

    # Slack webhook
    slack_enabled: bool = False
    slack_webhook_url: str = ""

    # Discord webhook
    discord_enabled: bool = False
    discord_webhook_url: str = ""


@dataclass
class LoggingSettings:
    """Application logging configuration."""
    log_dir: str = "Logs"
    log_level: str = "INFO"
    log_max_bytes: int = 10_000_000  # 10MB
    log_backup_count: int = 5
    log_llm_interactions: bool = True


@dataclass
class AppConfig:
    """Main application configuration."""
    aws: AWSSettings
    monitoring: MonitoringSettings
    llm: LLMSettings
    actions: ActionSettings
    notifications: NotificationSettings
    logging: LoggingSettings

    @staticmethod
    def load(path: str | None = None) -> "AppConfig":
        """Load configuration from YAML file with environment overrides.

        Args:
            path: Path to config file. Defaults to config.yaml or config.example.yaml

        Returns:
            Populated AppConfig instance
        """
        path = path or "config.yaml"
        if not Path(path).exists():
            path = "config.example.yaml"
            if not Path(path).exists():
                # Return defaults if no config file
                return AppConfig(
                    aws=AWSSettings(),
                    monitoring=MonitoringSettings(),
                    llm=LLMSettings(),
                    actions=ActionSettings(),
                    notifications=NotificationSettings(),
                    logging=LoggingSettings(),
                )

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        aws_data = data.get("aws", {})
        mon_data = data.get("monitoring", {})
        llm_data = data.get("llm", {})
        act_data = data.get("actions", {})
        notif_data = data.get("notifications", {})
        log_data = data.get("logging", {})

        # Parse Amplify apps
        amplify_apps = []
        for app in mon_data.get("amplify_apps", []):
            if isinstance(app, dict):
                amplify_apps.append(AmplifyAppConfig(
                    app_id=app.get("app_id", ""),
                    name=app.get("name", ""),
                    log_group=app.get("log_group", ""),
                ))

        # Parse EC2 instances
        ec2_instances = []
        for inst in mon_data.get("ec2_instances", []):
            if isinstance(inst, dict):
                ec2_instances.append(EC2InstanceConfig(
                    instance_id=inst.get("instance_id", ""),
                    name=inst.get("name", ""),
                    services=inst.get("services", []),
                ))

        return AppConfig(
            aws=AWSSettings(
                region=os.environ.get("AWS_REGION", aws_data.get("region", "us-east-1")),
            ),
            monitoring=MonitoringSettings(
                amplify_apps=amplify_apps,
                ec2_instances=ec2_instances,
                log_poll_interval=int(mon_data.get("log_poll_interval", 30)),
                health_check_interval=int(mon_data.get("health_check_interval", 60)),
                error_lookback_minutes=int(mon_data.get("error_lookback_minutes", 5)),
            ),
            llm=LLMSettings(
                primary_model=str(llm_data.get("primary_model", "openai/gpt-5-mini")),
                analysis_model=str(llm_data.get("analysis_model", "anthropic/claude-opus-4-5-20251101")),
                fallback_models=llm_data.get("fallback_models", ["google/gemini-2.5-flash", "openai/gpt-5"]),
                openai_api_key=os.environ.get("OPENAI_API_KEY", llm_data.get("openai_api_key", "")),
                anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", llm_data.get("anthropic_api_key", "")),
                gemini_api_key=os.environ.get("GEMINI_API_KEY", llm_data.get("gemini_api_key", "")),
                timeout_s=int(llm_data.get("timeout_s", 30)),
                max_tokens=int(llm_data.get("max_tokens", 4096)),
                temperature=float(llm_data.get("temperature", 0.3)),
                max_retries=int(llm_data.get("max_retries", 3)),
                stuck_timeout_s=int(llm_data.get("stuck_timeout_s", 45)),
                triage_system_prompt=str(llm_data.get("triage_system_prompt", LLMSettings.triage_system_prompt)),
                analysis_system_prompt=str(llm_data.get("analysis_system_prompt", LLMSettings.analysis_system_prompt)),
            ),
            actions=ActionSettings(
                allow_restart=bool(act_data.get("allow_restart", True)),
                allow_redeploy=bool(act_data.get("allow_redeploy", False)),
                max_restarts_per_hour=int(act_data.get("max_restarts_per_hour", 3)),
                cooldown_minutes=int(act_data.get("cooldown_minutes", 10)),
                require_approval_for=act_data.get("require_approval_for", ["redeploy", "terminate"]),
            ),
            notifications=NotificationSettings(
                email_enabled=bool(notif_data.get("email", {}).get("enabled", True)),
                email_recipients=notif_data.get("email", {}).get("recipients", []),
                email_from=str(notif_data.get("email", {}).get("from", "monitor@yourdomain.com")),
                slack_enabled=bool(notif_data.get("slack", {}).get("enabled", False)),
                slack_webhook_url=str(notif_data.get("slack", {}).get("webhook_url", "")),
                discord_enabled=bool(notif_data.get("discord", {}).get("enabled", False)),
                discord_webhook_url=str(notif_data.get("discord", {}).get("webhook_url", "")),
            ),
            logging=LoggingSettings(
                log_dir=str(log_data.get("log_dir", "Logs")),
                log_level=str(log_data.get("log_level", "INFO")),
                log_max_bytes=int(log_data.get("log_max_bytes", 10_000_000)),
                log_backup_count=int(log_data.get("log_backup_count", 5)),
                log_llm_interactions=bool(log_data.get("log_llm_interactions", True)),
            ),
        )
