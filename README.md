# AWS Log and EC2 Service Monitor
**LLM-powered monitoring and automated remediation for AWS services**

AWS Monitor watches your AWS Amplify applications and EC2 instances, using AI to analyze errors and automatically fix common issues.

- **Released by Chameleon Labs, LLC https://chameleonlabs.ai**<br> 
<small>Written by **Leland Green** and **Claude Code**</small><br>
- **Other _free_ code** on GitHub and **https://lelandgreen.com**<br>
- **Discord server: https://discord.gg/chameleonlabs** 
  - Free AI Chatbot!
  - Use ChatGPT, Gemini or Claude, with helpful and fun personalities
  - Chat with multiple LLMs at once
  - **Free access** to **#🗨️—multi-bot🤖💻🤖💬🤖** (AKA **multi-bot**) channel on request!
  - Includes personalities useful for coders
  - Features **Cluade Code-like** messages while "thinking"
  - Use extended thinking with plain language, or common LLM keywords

## Features

- **Real-time Log Monitoring** - Polls CloudWatch logs for errors
- **LLM-Powered Analysis** - Uses GPT-5, Claude, or Gemini to diagnose issues
- **Automated Remediation** - Restarts services, triggers redeployments
- **Multi-Provider LLM Support** - OpenAI, Anthropic, Google with automatic fallback
- **Safety Guards** - Rate limiting, cooldowns, and approval workflows
- **Notifications** - Email (SES), Slack, Discord alerts
- **Audit Trail** - Complete logging of all automated actions

## Quick Start

### Prerequisites

- Python 3.11+
- AWS account with Amplify apps or EC2 instances
- API key for at least one LLM provider (OpenAI, Anthropic, or Google)

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/aws-monitor.git
cd aws-monitor

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure
cp config.example.yaml config.yaml
# Edit config.yaml with your settings
```

### Configuration

1. **Add your Amplify apps** to `config.yaml`:
   ```yaml
   monitoring:
     amplify_apps:
       - app_id: d1234567890abc
         name: MyApp
   ```

2. **Set API keys** as environment variables:
   ```bash
   export OPENAI_API_KEY=sk-...
   export ANTHROPIC_API_KEY=sk-ant-...
   export GEMINI_API_KEY=AIza...
   ```

3. **Configure AWS credentials** (use IAM role on EC2, or AWS CLI locally):
   ```bash
   aws configure
   ```

### Running

```bash
python main.py
```

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
sudo git clone https://github.com/yourusername/aws-monitor.git monitor
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
        "logs:GetLogEvents",
        "amplify:GetApp",
        "amplify:ListApps",
        "amplify:StartDeployment",
        "ec2:DescribeInstances",
        "ec2:RebootInstances",
        "ses:SendEmail"
      ],
      "Resource": "*"
    }
  ]
}
```

### Helper Scripts

Configure environment variables for the helper scripts:

```bash
export MONITOR_EC2_HOST=ubuntu@your-instance-ip
export MONITOR_SSH_KEY=$HOME/.ssh/your-key.pem
export MONITOR_INSTANCE_ID=i-your-instance-id
```

Then use:

```bash
./Scripts/monitor-deploy.sh --restart  # Deploy and restart
./Scripts/monitor-logs.sh              # View live logs
./Scripts/monitor-status.sh            # Check status
./Scripts/monitor-ctl.sh restart       # Restart service
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
  log_poll_interval: 30      # Seconds between log checks
  health_check_interval: 60  # Seconds between health checks

actions:
  allow_restart: true        # Allow automatic restarts
  allow_redeploy: false      # Require approval for redeploys
  max_restarts_per_hour: 3   # Rate limit
  cooldown_minutes: 10       # Minimum time between restarts
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

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions welcome! Please read the contributing guidelines and submit a PR.

## Support

- [GitHub Issues](https://github.com/yourusername/aws-monitor/issues)
- [Documentation](./Docs/)
