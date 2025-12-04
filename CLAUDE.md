# AWS Monitor - Project Configuration

*For Claude Code / AI-assisted development*

## Project Overview

AWS Monitor is an open-source Python server that monitors AWS Amplify and EC2 services, using LLM analysis to diagnose issues and automate remediation.

## Project Structure

```
Monitor/
├── app/                    # Main application code
│   ├── __init__.py
│   ├── config.py          # Configuration management
│   ├── llm_client.py      # LiteLLM wrapper with multi-provider support
│   ├── model_config.py    # Model definitions and capabilities
│   ├── aws_client.py      # AWS service integration
│   ├── log_collector.py   # CloudWatch log streaming
│   ├── service_monitor.py # Health monitoring
│   ├── error_analyzer.py  # LLM-powered error analysis
│   ├── llm_orchestrator.py # Multi-LLM management
│   ├── action_executor.py # Remediation actions
│   └── prompts/           # LLM prompt templates
├── Docs/                   # Documentation
├── Plans/                  # Implementation plans
├── Logs/                   # Application logs (gitignored)
├── Scripts/                # Deployment and utility scripts
├── tests/                  # Test suite
├── main.py                 # Application entry point
├── config.yaml             # Runtime configuration (gitignored)
├── config.example.yaml     # Configuration template
└── requirements.txt        # Python dependencies
```

## Key Technologies

- **Python 3.11+** - Async/await for concurrent operations
- **litellm** - Unified LLM API for OpenAI, Anthropic, Google
- **boto3/aiobotocore** - AWS SDK for CloudWatch, EC2, Amplify
- **FastAPI** - REST API for management
- **aiohttp** - Async HTTP client
- **PyYAML** - Configuration parsing

## LLM Integration

### Supported Providers

- **OpenAI**: GPT-4o, GPT-4o-mini, GPT-5, o-series
- **Anthropic**: Claude Opus 4.5, Claude Sonnet 4.5, Claude Sonnet 4
- **Google**: Gemini 2.5 Pro/Flash, Gemini 2.0 Pro/Flash

### Model Selection Strategy

| Task | Recommendation |
|------|----------------|
| Quick triage | GPT-4o-mini, Gemini Flash |
| Error analysis | GPT-5, Claude Opus 4.5 |
| Complex diagnosis | Claude with extended thinking |

## AWS Integration

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
        "ec2:DescribeRegions",
        "ec2:RebootInstances",
        "ses:SendEmail",
        "ses:SendRawEmail"
      ],
      "Resource": "*"
    }
  ]
}
```

## Development Guidelines

### Running Locally

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure
cp config.example.yaml config.yaml
# Edit config.yaml with your settings

# Set API keys
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
export GEMINI_API_KEY=AIza...

# Run
python main.py
```

### Testing

```bash
pytest tests/ -v
pytest tests/ --cov=app --cov-report=html
```

### Configuration

Environment variables override config.yaml:

- `AWS_REGION` / `AWS_DEFAULT_REGION`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GEMINI_API_KEY`

## Deployment

### EC2 Deployment

```bash
# Set environment variables for scripts
export MONITOR_EC2_HOST=ubuntu@your-instance-ip
export MONITOR_SSH_KEY=$HOME/.ssh/your-key.pem
export MONITOR_INSTANCE_ID=i-your-instance-id

# Use helper scripts
./Scripts/monitor-deploy.sh --restart
./Scripts/monitor-logs.sh
./Scripts/monitor-status.sh
```

### systemd Service

```bash
sudo cp Scripts/monitor.service /etc/systemd/system/aws-monitor.service
sudo systemctl daemon-reload
sudo systemctl enable aws-monitor
sudo systemctl start aws-monitor
```

## Logging

- Application logs: `Logs/monitor.log`
- LLM interaction logs: `Logs/llm_interactions.log`
- Audit logs: `Logs/audit.log`

## Plan File

Implementation plan: `Plans/AWS-Monitor-Implementation-Plan.md`
