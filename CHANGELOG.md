# Changelog

All notable changes to AWS Monitor will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2025-12-07

### Added

- **Configuration Management Scripts**
  - `monitor-config.sh` - Manage monitored services and polling intervals via CLI
    - Add/remove Amplify apps and EC2 instances
    - Set polling intervals (log, health, lookback)
    - List and show configuration
  - `monitor-discover.sh` - Auto-discover AWS resources
    - Scan for Amplify applications
    - Scan for EC2 instances
    - List CloudWatch log groups
    - Region-aware scanning
  - `monitor-validate.sh` - Validate configuration and connectivity
    - Check YAML syntax
    - Verify AWS credentials
    - Test access to configured services
    - Validate LLM API key formats
    - Provide interval recommendations

- **Recommended Default Settings**
  - Log polling interval: 60-120 seconds (was 30s)
  - Health check interval: 300 seconds (was 60s)
  - Error lookback window: 15 minutes (was 5 minutes)

- **Documentation**
  - Comprehensive README with all features documented
  - Configuration management section
  - Recommended settings table
  - Project structure overview

### Changed

- Updated `config.example.yaml` with recommended interval defaults
- Improved README organization and clarity
- Added version badges to README

### Fixed

- Script compatibility with various shell environments

## [0.1.0] - 2025-12-06

### Added

- **Core Monitoring**
  - Real-time CloudWatch log polling for Amplify apps
  - EC2 instance health monitoring
  - Configurable polling intervals

- **LLM-Powered Analysis**
  - Multi-provider support (OpenAI, Anthropic, Google)
  - Automatic fallback between providers
  - Error triage and root cause analysis
  - Configurable primary and analysis models

- **Automated Remediation**
  - Service restart capabilities
  - Amplify redeployment triggers
  - EC2 instance reboot

- **Safety Features**
  - Rate limiting (max restarts per hour)
  - Cooldown periods between actions
  - Approval workflow for high-risk actions
  - Circuit breaker for repeated failures

- **Notifications**
  - Email alerts via AWS SES
  - Slack webhook integration
  - Discord webhook integration

- **Audit & Logging**
  - Complete action audit trail
  - LLM interaction logging
  - Configurable log levels and rotation

- **Deployment Tools**
  - `deploy.sh` - Initial deployment script
  - `setup-ec2.sh` - EC2 instance setup
  - `monitor-deploy.sh` - Code deployment
  - `monitor-ctl.sh` - Service control
  - `monitor-logs.sh` - Log viewing
  - `monitor-status.sh` - Status checking
  - `monitor-ssh.sh` - SSH access
  - systemd service configuration

- **Configuration**
  - YAML-based configuration
  - Environment variable overrides
  - Example configuration template

- **API**
  - FastAPI-based REST API
  - Health check endpoint
  - Status endpoints

### Security

- API keys stored in environment variables or config (gitignored)
- IAM role support for EC2 deployment
- No credentials in version control

---

## Version History

| Version | Date | Description |
|---------|------|-------------|
| 0.2.0 | 2025-12-07 | Configuration management scripts |
| 0.1.0 | 2025-12-06 | Initial release |
