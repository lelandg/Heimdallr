# AWS Log and EC2 Service Monitor

[![Version](https://img.shields.io/badge/version-0.2.0-blue.svg)](CHANGELOG.md)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)

**LLM-powered monitoring and automated remediation for AWS services**

AWS Monitor watches your AWS Amplify applications and EC2 instances, using AI to analyze errors and automatically fix common issues.

- **Released by Chameleon Labs, LLC https://chameleonlabs.ai**
- Written by **Leland Green** and **Claude Code**
- **Other free code** on GitHub and **https://lelandgreen.com**
- **Discord server: https://discord.gg/chameleonlabs**
  - Free AI Chatbot with ChatGPT, Gemini, and Claude personalities
  - Chat with multiple LLMs at once in **#multi-bot** channel

## Features

- **Real-time Log Monitoring** - Polls CloudWatch logs for errors
- **LLM-Powered Analysis** - Uses GPT-5, Claude, or Gemini to diagnose issues
- **Automated Remediation** - Restarts services, triggers redeployments
- **Multi-Provider LLM Support** - OpenAI, Anthropic, Google with automatic fallback
- **Configuration Management** - CLI tools for easy service setup
- **Service Discovery** - Auto-detect Amplify apps and EC2 instances from AWS
- **Safety Guards** - Rate limiting, cooldowns, and approval workflows
- **Notifications** - Email (SES), Slack, Discord alerts
- **Audit Trail** - Complete logging of all automated actions

## Quick Start

### Prerequisites

- Python 3.11+
- AWS account with Amplify apps or EC2 instances
- API key for at least one LLM provider (OpenAI, Anthropic, or Google)
- AWS CLI configured with appropriate permissions

### Installation

```bash
# Clone the repository
git clone https://github.com/ChameleonLabsLLC/aws-monitor.git
cd aws-monitor

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
./Scripts/monitor-discover.sh

# Add services to monitor
./Scripts/monitor-config.sh add amplify <app-id> "My App"
./Scripts/monitor-config.sh add ec2 <instance-id> "Web Server"

# Set polling intervals (recommended values)
./Scripts/monitor-config.sh interval log 120      # 2 minutes
./Scripts/monitor-config.sh interval health 300   # 5 minutes
./Scripts/monitor-config.sh interval lookback 15  # 15 minutes

# Validate configuration
./Scripts/monitor-validate.sh

# View configured services
./Scripts/monitor-config.sh list
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

### monitor-config.sh

Manage monitored services and polling intervals:

```bash
# List all configured services and settings
./Scripts/monitor-config.sh list

# Show full configuration
./Scripts/monitor-config.sh show

# Add services
./Scripts/monitor-config.sh add amplify <app-id> "App Name"
./Scripts/monitor-config.sh add ec2 <instance-id> "Server Name" [nginx,node]

# Remove services
./Scripts/monitor-config.sh remove amplify <app-id>
./Scripts/monitor-config.sh remove ec2 <instance-id>

# Set polling intervals
./Scripts/monitor-config.sh interval log <seconds>       # Log polling (default: 60)
./Scripts/monitor-config.sh interval health <seconds>    # Health checks (default: 300)
./Scripts/monitor-config.sh interval lookback <minutes>  # Error lookback (default: 15)
```

### monitor-discover.sh

Auto-discover services from your AWS account:

```bash
# Discover all Amplify apps and EC2 instances
./Scripts/monitor-discover.sh

# Discover specific service types
./Scripts/monitor-discover.sh amplify
./Scripts/monitor-discover.sh ec2
./Scripts/monitor-discover.sh logs

# Scan a different region
AWS_REGION=us-west-2 ./Scripts/monitor-discover.sh
```

### monitor-validate.sh

Validate configuration and test AWS connectivity:

```bash
./Scripts/monitor-validate.sh
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
│  CloudWatch     │────▶│  Log Collector   │────▶│  Error Analyzer │
│  Logs           │     │  (polling)       │     │  (LLM-powered)  │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                          │
┌─────────────────┐     ┌──────────────────┐              │
│  Amplify/EC2    │◀────│  Action Executor │◀─────────────┤
│  Services       │     │  (remediation)   │              │
└─────────────────┘     └──────────────────┘              │
                                                          │
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

AWS Monitor supports multiple LLM providers with automatic fallback:

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
sudo git clone https://github.com/ChameleonLabsLLC/aws-monitor.git monitor
cd monitor
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
export MONITOR_EC2_HOST=ubuntu@<your-instance-ip>
export MONITOR_SSH_KEY=$HOME/.ssh/<your-key>.pem
export MONITOR_INSTANCE_ID=i-<your-instance-id>
```

Available scripts:

| Script | Description |
|--------|-------------|
| `monitor-deploy.sh` | Deploy code and restart service |
| `monitor-logs.sh` | View live service logs |
| `monitor-status.sh` | Check service and instance status |
| `monitor-ctl.sh` | Service control (start/stop/restart) |
| `monitor-ssh.sh` | SSH into the monitor instance |

Example:

```bash
./Scripts/monitor-deploy.sh --restart  # Deploy and restart
./Scripts/monitor-logs.sh              # View live logs
./Scripts/monitor-status.sh            # Check status
./Scripts/monitor-ctl.sh restart       # Restart service
```

### systemd Service

```bash
sudo cp Scripts/monitor.service /etc/systemd/system/aws-monitor.service
sudo systemctl daemon-reload
sudo systemctl enable aws-monitor
sudo systemctl start aws-monitor
```

## Safety Features

AWS Monitor includes multiple safety mechanisms:

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
aws-monitor/
├── app/                    # Main application code
│   ├── config.py          # Configuration management
│   ├── llm_client.py      # LiteLLM wrapper
│   ├── aws_client.py      # AWS service integration
│   ├── log_collector.py   # CloudWatch log streaming
│   ├── service_monitor.py # Health monitoring
│   ├── error_analyzer.py  # LLM-powered analysis
│   ├── action_executor.py # Remediation actions
│   ├── safety_guard.py    # Rate limiting & safety
│   ├── notifier.py        # Alert notifications
│   └── prompts/           # LLM prompt templates
├── Scripts/               # Management scripts
│   ├── monitor-config.sh  # Configuration management
│   ├── monitor-discover.sh # Service discovery
│   ├── monitor-validate.sh # Config validation
│   ├── monitor-deploy.sh  # Deployment
│   ├── monitor-ctl.sh     # Service control
│   ├── monitor-logs.sh    # Log viewing
│   └── monitor-status.sh  # Status checking
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

- [GitHub Issues](https://github.com/ChameleonLabsLLC/aws-monitor/issues)
- [Documentation](./Docs/)
- [Discord](https://discord.gg/chameleonlabs)
