# Heimdallr

[![Version](https://img.shields.io/badge/version-0.2.0-blue.svg)](CHANGELOG.md)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)

<p align="center">
  <img src="logo.png" alt="Heimdallr Logo" width="100%">
</p>

**AI-Powered Eyes on Your Stack**

Heimdallr watches your cloud services, databases, and Linux infrastructure, using AI to analyze errors and automatically fix common issues.

> **Why "Heimdallr"?** In Norse mythology, Heimdallr is the all-seeing guardian of the Bifrost bridge, blessed with extraordinary perception - he can see for hundreds of miles and hear grass growing. We use the Old Norse spelling (*Heimdallr* rather than the anglicized *Heimdall*) to distinguish this project and honor the original mythology. Like its namesake, this tool maintains constant vigilance over your infrastructure, seeing problems before they become crises.

---

- **Released by [Chameleon Labs, LLC](https://chameleonlabs.ai)**
- Written by **Leland Green** and **Claude Code**
- **More free code** on [GitHub](https://github.com/ChameleonLabsLLC) and [lelandgreen.com](https://lelandgreen.com)
- **[Discord Community](https://discord.gg/chameleonlabs)** - Free AI chatbots, coding help, and more

## Features

- **Real-time Log Monitoring** - Polls CloudWatch, systemd journals, and database logs
- **LLM-Powered Analysis** - Uses GPT-5, Claude, or Gemini to diagnose root causes
- **Automated Remediation** - Restarts services, triggers redeployments, executes runbooks
- **Multi-Provider LLM Support** - OpenAI, Anthropic, Google with automatic fallback
- **Broad Infrastructure Support** - AWS Amplify, EC2, databases, Linux services
- **Configuration Management** - CLI tools for easy service setup
- **Service Discovery** - Auto-detect services from AWS and local system
- **Safety Guards** - Rate limiting, cooldowns, and approval workflows
- **Notifications** - Email (SES), Slack, Discord webhooks, ChatMaster DMs
- **Audit Trail** - Complete logging of all automated actions

## Quick Start

### Prerequisites

- Python 3.11+
- AWS account (for cloud monitoring) or Linux server (for local monitoring)
- API key for at least one LLM provider (OpenAI, Anthropic, or Google)

### Installation

```bash
# Clone the repository
git clone https://github.com/ChameleonLabsLLC/heimdallr.git
cd heimdallr

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create configuration
cp config.example.yaml config.yaml
```

### Quick Configuration

Use the configuration management scripts to set up your services:

```bash
# Discover available services in your AWS account
./Scripts/heimdallr-discover.sh

# Add services to monitor
./Scripts/heimdallr-config.sh add amplify <app-id> "My App"
./Scripts/heimdallr-config.sh add ec2 <instance-id> "Web Server"

# Set polling intervals (recommended values)
./Scripts/heimdallr-config.sh interval log 120      # 2 minutes
./Scripts/heimdallr-config.sh interval health 300   # 5 minutes
./Scripts/heimdallr-config.sh interval lookback 15  # 15 minutes

# Validate configuration
./Scripts/heimdallr-validate.sh

# View configured services
./Scripts/heimdallr-config.sh list
```

### Set API Keys

```bash
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
export GEMINI_API_KEY=AIza...
```

### Running

```bash
python main.py
```

## Configuration Management

### heimdallr-config.sh

Manage monitored services and polling intervals:

```bash
# List all configured services and settings
./Scripts/heimdallr-config.sh list

# Show full configuration
./Scripts/heimdallr-config.sh show

# Add services
./Scripts/heimdallr-config.sh add amplify <app-id> "App Name"
./Scripts/heimdallr-config.sh add ec2 <instance-id> "Server Name" [nginx,node]

# Remove services
./Scripts/heimdallr-config.sh remove amplify <app-id>
./Scripts/heimdallr-config.sh remove ec2 <instance-id>

# Set polling intervals
./Scripts/heimdallr-config.sh interval log <seconds>       # Log polling (default: 60)
./Scripts/heimdallr-config.sh interval health <seconds>    # Health checks (default: 300)
./Scripts/heimdallr-config.sh interval lookback <minutes>  # Error lookback (default: 15)
```

### heimdallr-discover.sh

Auto-discover services from your AWS account:

```bash
# Discover all Amplify apps and EC2 instances
./Scripts/heimdallr-discover.sh

# Discover specific service types
./Scripts/heimdallr-discover.sh amplify
./Scripts/heimdallr-discover.sh ec2
./Scripts/heimdallr-discover.sh logs

# Scan a different region
AWS_REGION=us-west-2 ./Scripts/heimdallr-discover.sh
```

### heimdallr-validate.sh

Validate configuration and test connectivity:

```bash
./Scripts/heimdallr-validate.sh
```

Checks:
- Configuration file syntax
- Required fields present
- AWS credentials valid
- Configured services exist and are accessible
- LLM API key formats
- Polling interval recommendations

## Recommended Settings

| Setting | Default | Recommended | Description |
|---------|---------|-------------|-------------|
| `log_poll_interval` | 60s | 60-120s | Time between log checks |
| `health_check_interval` | 300s | 300s | Time between health checks |
| `error_lookback_minutes` | 15min | 10-15min | How far back to look for errors |

**Note:** Polling more frequently than 60 seconds may increase AWS costs and API usage.

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Log Sources    │────▶│  Log Collector   │────▶│  Error Analyzer │
│  (CloudWatch,   │     │  (polling)       │     │  (LLM-powered)  │
│   journald, DB) │     └──────────────────┘     └────────┬────────┘
└─────────────────┘                                       │
                                                          │
┌─────────────────┐     ┌──────────────────┐              │
│  Services       │◀────│  Action Executor │◀─────────────┤
│  (AWS, Linux,   │     │  (remediation)   │              │
│   Databases)    │     └──────────────────┘              │
└─────────────────┘                                       │
                        ┌──────────────────┐              │
                        │  Safety Guard    │◀─────────────┤
                        │  (rate limiting) │              │
                        └──────────────────┘              │
                                                          │
                        ┌──────────────────┐              │
                        │  Notifier        │◀─────────────┘
                        │  (alerts)        │
                        └──────────────────┘
```

## LLM Providers

Heimdallr supports multiple LLM providers with automatic fallback:

| Provider | Models | Best For |
|----------|--------|----------|
| OpenAI | GPT-4o, GPT-4o-mini, GPT-5 | Fast triage, general analysis |
| Anthropic | Claude Opus 4.5, Claude Sonnet 4.5 | Complex diagnosis, extended thinking |
| Google | Gemini 2.5 Pro/Flash | Cost-effective analysis |

Configure your preferred models in `config.yaml`:

```yaml
llm:
  primary_model: openai/gpt-4o-mini      # Fast triage
  analysis_model: anthropic/claude-opus-4-5-20251101  # Deep analysis
  fallback_models:
    - google/gemini-2.5-flash
    - openai/gpt-5
```

## Deployment

### EC2 Deployment (Recommended)

1. Launch Ubuntu 24.04 EC2 instance (t3.small recommended)
2. Attach IAM role with required permissions
3. Run setup:

```bash
# On EC2 instance
cd /opt
sudo git clone https://github.com/ChameleonLabsLLC/heimdallr.git
cd heimdallr
sudo ./Scripts/deploy.sh
```

### Required IAM Permissions

```json
{
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:FilterLogEvents",
        "logs:DescribeLogGroups",
        "logs:DescribeLogStreams",
        "logs:GetLogEvents",
        "amplify:GetApp",
        "amplify:ListApps",
        "amplify:ListBranches",
        "amplify:StartDeployment",
        "ec2:DescribeInstances",
        "ec2:DescribeInstanceStatus",
        "ec2:RebootInstances",
        "ses:SendEmail",
        "ses:SendRawEmail"
      ],
      "Resource": "*"
    }
  ]
}
```

### Remote Management Scripts

Configure environment variables for remote management:

```bash
export HEIMDALLR_EC2_HOST=ubuntu@<your-instance-ip>
export HEIMDALLR_SSH_KEY=$HOME/.ssh/<your-key>.pem
export HEIMDALLR_INSTANCE_ID=i-<your-instance-id>
```

Available scripts:

| Script | Description |
|--------|-------------|
| `heimdallr-deploy.sh` | Deploy code and restart service |
| `heimdallr-logs.sh` | View live service logs |
| `heimdallr-status.sh` | Check service and instance status |
| `heimdallr-ctl.sh` | Service control (start/stop/restart) |
| `heimdallr-ssh.sh` | SSH into the monitor instance |

Example:

```bash
./Scripts/heimdallr-deploy.sh --restart  # Deploy and restart
./Scripts/heimdallr-logs.sh              # View live logs
./Scripts/heimdallr-status.sh            # Check status
./Scripts/heimdallr-ctl.sh restart       # Restart service
```

### systemd Service

```bash
sudo cp Scripts/heimdallr.service /etc/systemd/system/heimdallr.service
sudo systemctl daemon-reload
sudo systemctl enable heimdallr
sudo systemctl start heimdallr
```

## Notifications

### Channels

| Channel | Type | Best For |
|---------|------|----------|
| Email (SES) | AWS Simple Email Service | Formal alerts, audit trail |
| Slack | Webhook | Team channels |
| Discord Webhook | Webhook | Server channels |
| ChatMaster | API | Personal Discord DMs |

### ChatMaster Setup

ChatMaster sends alerts directly to your Discord DMs - useful when you're not watching a channel.

1. **Get API credentials** - Use `/alert_api register` in a Discord server with ChatMaster bot
2. **Configure Heimdallr**:

```yaml
notifications:
  chatmaster:
    enabled: true
    api_url: "http://98.89.20.116:8080/api/v1"  # ChatMaster Alert API
    api_key: ""       # Set via CHATMASTER_API_KEY env var
    api_secret: ""    # Set via CHATMASTER_API_SECRET env var

    routing:
      p1_alerts: true       # Critical alerts
      p2_alerts: true       # High priority
      p3_alerts: false      # Normal (can be noisy)
      health_changes: true  # Service state changes
      action_results: false # Remediation results
```

**Why ChatMaster vs Discord Webhooks?**
- Webhooks post to channels; ChatMaster sends DMs directly to you
- Works even if you're not watching the channel
- Per-user routing - different alerts to different people

## Safety Features

Heimdallr includes multiple safety mechanisms:

- **Rate Limiting** - Max restarts per hour per service
- **Cooldown Periods** - Minimum time between actions
- **Circuit Breaker** - Stops automation if too many failures
- **Approval Workflow** - High-risk actions require human approval
- **Change Freeze** - Disable automation during maintenance
- **Audit Logging** - Complete trail of all actions

## Configuration Reference

See `config.example.yaml` for all options. Key settings:

```yaml
monitoring:
  log_poll_interval: 60        # Seconds between log checks
  health_check_interval: 300   # Seconds between health checks
  error_lookback_minutes: 15   # Minutes to look back for errors

actions:
  allow_restart: true          # Allow automatic restarts
  allow_redeploy: false        # Require approval for redeploys
  max_restarts_per_hour: 3     # Rate limit
  cooldown_minutes: 10         # Minimum time between restarts
```

## Project Structure

```
heimdallr/
├── app/                    # Main application code
│   ├── config.py          # Configuration management
│   ├── llm_client.py      # LiteLLM wrapper
│   ├── aws_client.py      # AWS service integration
│   ├── log_collector.py   # Log streaming
│   ├── service_monitor.py # Health monitoring
│   ├── error_analyzer.py  # LLM-powered analysis
│   ├── action_executor.py # Remediation actions
│   ├── safety_guard.py    # Rate limiting & safety
│   ├── notifier.py        # Alert notifications
│   └── prompts/           # LLM prompt templates
├── Scripts/               # Management scripts
│   ├── heimdallr-config.sh   # Configuration management
│   ├── heimdallr-discover.sh # Service discovery
│   ├── heimdallr-validate.sh # Config validation
│   ├── heimdallr-deploy.sh   # Deployment
│   ├── heimdallr-ctl.sh      # Service control
│   ├── heimdallr-logs.sh     # Log viewing
│   └── heimdallr-status.sh   # Status checking
├── Docs/                  # Documentation
├── tests/                 # Test suite
├── main.py               # Application entry point
├── config.example.yaml   # Configuration template
└── requirements.txt      # Python dependencies
```

## Development

```bash
# Run tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=app --cov-report=html

# Type checking
mypy app/
```

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Submit a Pull Request

## Support

- [GitHub Issues](https://github.com/ChameleonLabsLLC/heimdallr/issues)
- [Documentation](./Docs/)
- [Discord](https://discord.gg/chameleonlabs)
