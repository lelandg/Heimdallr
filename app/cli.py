#!/usr/bin/env python3
"""Command-line interface for AWS Monitor.

Provides commands for:
- Status queries
- Manual analysis triggers
- Model switching
- Alert management
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def get_config():
    """Load configuration."""
    from app.config import AppConfig
    return AppConfig.load()


def format_table(headers: list, rows: list, widths: Optional[list] = None) -> str:
    """Format data as a simple table."""
    if not widths:
        widths = [max(len(str(h)), max((len(str(r[i])) for r in rows), default=0))
                  for i, h in enumerate(headers)]

    lines = []
    header_line = " | ".join(str(h).ljust(w) for h, w in zip(headers, widths))
    lines.append(header_line)
    lines.append("-" * len(header_line))

    for row in rows:
        line = " | ".join(str(c).ljust(w) for c, w in zip(row, widths))
        lines.append(line)

    return "\n".join(lines)


# ============================================================================
# Status Commands
# ============================================================================

async def cmd_status(args):
    """Show overall status."""
    config = get_config()

    print("AWS Monitor Status")
    print("=" * 50)
    print(f"Region: {config.aws.region}")
    print(f"Amplify Apps: {len(config.monitoring.amplify_apps)}")
    print(f"EC2 Instances: {len(config.monitoring.ec2_instances)}")
    print()

    # Test AWS
    print("AWS Connections:")
    from app.aws_client import AWSClient
    aws_client = AWSClient(config.aws)
    results = await aws_client.test_connection()
    for service, connected in results.items():
        status = "✓" if connected else "✗"
        print(f"  {status} {service}")

    print()

    # Test LLM
    print("LLM Providers:")
    try:
        from app.llm_client import LLMClient
        llm_client = LLMClient(config.llm)
        results = await llm_client.test_connection()
        for provider, connected in results.items():
            status = "✓" if connected else "✗"
            print(f"  {status} {provider}")
    except ImportError:
        print("  LLM client not available (missing litellm)")


async def cmd_health(args):
    """Show service health."""
    config = get_config()

    from app.aws_client import AWSClient

    aws_client = AWSClient(config.aws)

    print("Service Health")
    print("=" * 60)

    # Amplify apps
    if config.monitoring.amplify_apps:
        print("\nAmplify Apps:")
        for app in config.monitoring.amplify_apps:
            try:
                status = await aws_client.get_amplify_app_status(app.app_id)
                health = "✓" if status.is_healthy else "✗"
                print(f"  {health} {app.name}: {status.status} ({status.branch})")
            except Exception as e:
                print(f"  ? {app.name}: Error - {e}")

    # EC2 instances
    if config.monitoring.ec2_instances:
        print("\nEC2 Instances:")
        for instance in config.monitoring.ec2_instances:
            try:
                status = await aws_client.get_instance_status(instance.instance_id)
                health = "✓" if status.is_healthy else "✗"
                print(f"  {health} {instance.name}: {status.state} ({status.status_check})")
            except Exception as e:
                print(f"  ? {instance.name}: Error - {e}")


async def cmd_logs(args):
    """Fetch recent logs."""
    config = get_config()

    from app.aws_client import AWSClient

    aws_client = AWSClient(config.aws)

    # Find app
    app = None
    for a in config.monitoring.amplify_apps:
        if a.app_id == args.app or a.name.lower() == args.app.lower():
            app = a
            break

    if not app:
        print(f"App not found: {args.app}")
        print("Available apps:")
        for a in config.monitoring.amplify_apps:
            print(f"  {a.app_id}: {a.name}")
        return

    print(f"Fetching logs from {app.name} (last {args.minutes} minutes)...")
    print()

    if args.errors:
        events = await aws_client.fetch_error_logs(
            app.log_group,
            lookback_minutes=args.minutes,
            limit=args.limit,
        )
    else:
        events = await aws_client.fetch_logs(
            app.log_group,
            start_time=datetime.now(timezone.utc) - timedelta(minutes=args.minutes),
            limit=args.limit,
        )

    if not events:
        print("No logs found.")
        return

    for event in events:
        ts = event.timestamp.strftime("%H:%M:%S")
        msg = event.message[:200] if len(event.message) > 200 else event.message
        print(f"[{ts}] {msg}")


# ============================================================================
# Analysis Commands
# ============================================================================

async def cmd_analyze(args):
    """Analyze an error message."""
    config = get_config()

    from app.llm_client import LLMClient
    from app.error_analyzer import ErrorAnalyzer
    from app.log_collector import DetectedError, ErrorSeverity

    print(f"Analyzing error...")
    print()

    llm_client = LLMClient(config.llm)
    analyzer = ErrorAnalyzer(llm_client)

    # Create synthetic error
    error = DetectedError(
        message=args.message,
        severity=ErrorSeverity.ERROR,
        source_app=args.service or "unknown",
        log_group="manual",
        timestamp=datetime.now(timezone.utc),
        error_type="manual",
    )

    if args.quick:
        result = await analyzer.quick_triage(error)
    else:
        result = await analyzer.analyze(error)

    print("Analysis Result")
    print("=" * 50)
    print(f"Category: {result.category.value}")
    print(f"Severity: {result.severity.value}")
    print(f"Confidence: {result.confidence:.0%}")
    print(f"Action: {result.recommended_action.value}")
    print()
    print("Root Cause:")
    print(f"  {result.root_cause}")
    print()
    print("Rationale:")
    print(f"  {result.action_rationale}")

    if result.remediation_steps:
        print()
        print("Remediation Steps:")
        for i, step in enumerate(result.remediation_steps, 1):
            print(f"  {i}. {step}")

    print()
    print(f"(Model: {result.model_used}, {result.analysis_latency_ms}ms)")


# ============================================================================
# Model Commands
# ============================================================================

async def cmd_models(args):
    """List available models."""
    from app.model_config import get_all_models, get_model_info

    print("Available LLM Models")
    print("=" * 70)

    models = get_all_models()
    for model in models:
        info = get_model_info(model)
        print(f"  {model}")
        print(f"    {info}")
        print()


async def cmd_switch_model(args):
    """Switch the active model."""
    config = get_config()

    from app.llm_client import LLMClient
    from app.model_config import get_model_info

    llm_client = LLMClient(config.llm)

    model_type = args.type
    model = args.model

    print(f"Switching {model_type} model to: {model}")
    print(f"Info: {get_model_info(model)}")

    if model_type == "primary":
        llm_client.set_model(model)
    else:
        llm_client.set_analysis_model(model)

    # Test the new model
    print("Testing connection...")
    try:
        response = await llm_client.complete(
            messages=[{"role": "user", "content": "Reply with just 'OK'"}],
            model=model,
            max_tokens=10,
        )
        print(f"✓ Model responding: {response.content}")
    except Exception as e:
        print(f"✗ Model failed: {e}")


# ============================================================================
# Alert Commands
# ============================================================================

async def cmd_alerts(args):
    """List alerts (requires running monitor)."""
    print("Alert listing requires connection to running monitor API.")
    print("Use: curl http://localhost:8000/alerts")


# ============================================================================
# Config Commands
# ============================================================================

async def cmd_config(args):
    """Show current configuration."""
    config = get_config()

    if args.json:
        print(json.dumps({
            "aws": {"region": config.aws.region},
            "monitoring": {
                "amplify_apps": [
                    {"app_id": a.app_id, "name": a.name}
                    for a in config.monitoring.amplify_apps
                ],
                "ec2_instances": [
                    {"instance_id": i.instance_id, "name": i.name}
                    for i in config.monitoring.ec2_instances
                ],
                "log_poll_interval": config.monitoring.log_poll_interval,
                "health_check_interval": config.monitoring.health_check_interval,
            },
            "llm": {
                "primary_model": config.llm.primary_model,
                "analysis_model": config.llm.analysis_model,
            },
            "actions": {
                "allow_restart": config.actions.allow_restart,
                "allow_redeploy": config.actions.allow_redeploy,
            },
        }, indent=2))
    else:
        print("Configuration")
        print("=" * 50)
        print(f"AWS Region: {config.aws.region}")
        print()
        print("Monitoring:")
        print(f"  Amplify Apps: {len(config.monitoring.amplify_apps)}")
        for app in config.monitoring.amplify_apps:
            print(f"    - {app.name} ({app.app_id})")
        print(f"  EC2 Instances: {len(config.monitoring.ec2_instances)}")
        for inst in config.monitoring.ec2_instances:
            print(f"    - {inst.name} ({inst.instance_id})")
        print(f"  Log Poll Interval: {config.monitoring.log_poll_interval}s")
        print(f"  Health Check Interval: {config.monitoring.health_check_interval}s")
        print()
        print("LLM:")
        print(f"  Primary Model: {config.llm.primary_model}")
        print(f"  Analysis Model: {config.llm.analysis_model}")
        print(f"  Fallbacks: {', '.join(config.llm.fallback_models)}")
        print()
        print("Actions:")
        print(f"  Allow Restart: {config.actions.allow_restart}")
        print(f"  Allow Redeploy: {config.actions.allow_redeploy}")
        print(f"  Max Restarts/Hour: {config.actions.max_restarts_per_hour}")
        print(f"  Cooldown: {config.actions.cooldown_minutes} minutes")


# ============================================================================
# Main CLI
# ============================================================================

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="AWS Monitor CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # status command
    status_parser = subparsers.add_parser("status", help="Show overall status")

    # health command
    health_parser = subparsers.add_parser("health", help="Show service health")

    # logs command
    logs_parser = subparsers.add_parser("logs", help="Fetch logs from an app")
    logs_parser.add_argument("app", help="App ID or name")
    logs_parser.add_argument("-m", "--minutes", type=int, default=5, help="Minutes to look back")
    logs_parser.add_argument("-n", "--limit", type=int, default=50, help="Max events")
    logs_parser.add_argument("-e", "--errors", action="store_true", help="Only show errors")

    # analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Analyze an error message")
    analyze_parser.add_argument("message", help="Error message to analyze")
    analyze_parser.add_argument("-s", "--service", help="Service name")
    analyze_parser.add_argument("-q", "--quick", action="store_true", help="Quick triage only")

    # models command
    models_parser = subparsers.add_parser("models", help="List available models")

    # switch command
    switch_parser = subparsers.add_parser("switch", help="Switch active model")
    switch_parser.add_argument("model", help="Model identifier")
    switch_parser.add_argument("-t", "--type", choices=["primary", "analysis"],
                               default="primary", help="Model type to switch")

    # alerts command
    alerts_parser = subparsers.add_parser("alerts", help="List alerts")

    # config command
    config_parser = subparsers.add_parser("config", help="Show configuration")
    config_parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Route to command
    commands = {
        "status": cmd_status,
        "health": cmd_health,
        "logs": cmd_logs,
        "analyze": cmd_analyze,
        "models": cmd_models,
        "switch": cmd_switch_model,
        "alerts": cmd_alerts,
        "config": cmd_config,
    }

    cmd_func = commands.get(args.command)
    if cmd_func:
        asyncio.run(cmd_func(args))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
