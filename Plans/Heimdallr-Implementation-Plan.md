# Heimdallr Implementation Plan

*Created: 2025-12-04*
*Last Updated: 2025-12-04 11:15*

## Project Overview

**Purpose**: Python server to monitor EC2 services and AWS Amplify logs, using LLM analysis to diagnose issues and automate remediation (typically service restarts).

**Key Features**:
- Real-time monitoring of AWS Amplify logs
- EC2 service health monitoring
- LLM-powered error analysis and diagnosis
- Automated remediation actions (service restarts, etc.)
- Multi-LLM support with runtime model switching
- Fallback to alternate LLMs when primary is "stuck"
- Latest model support (GPT-5, Claude Opus 4.5, Gemini 2.5)

---

## Phase 1: Core Infrastructure ✅

**Goal:** Set up project structure, configuration, and LLM client foundation

**Status:** Phase 1 is **100% complete**.

### Tasks

1. ✅ Initialize project directories - **COMPLETED**
   - `app/` - Main application code
   - `Docs/` - Documentation
   - `Notes/` - Ideas and brainstorming
   - `Plans/` - Implementation plans
   - `Logs/` - Application logs
   - `Scripts/` - Utility scripts
   - `tests/` - Unit tests

2. ✅ Create configuration system (`app/config.py`) - **COMPLETED** (251 lines)
   - AWS credentials handling
   - LLM provider settings
   - Monitoring targets configuration
   - Action permissions (restart, notify, etc.)

3. ✅ Create LLM client with litellm (`app/llm_client.py`) - **COMPLETED** (480 lines)
   - Multi-provider support (OpenAI, Anthropic, Google)
   - Runtime model switching
   - Fallback mechanism when stuck
   - Extended thinking support

4. ✅ Create model configuration (`app/model_config.py`) - **COMPLETED** (606 lines)
   - Latest model definitions (GPT-5, Claude 4.5, Gemini 2.5)
   - Token limits and capabilities
   - Provider-specific parameters

**Deliverables:** ✅
- ✅ Project structure created
- ✅ `app/config.py` with dataclass settings (251 lines)
- ✅ `app/llm_client.py` with litellm wrapper (480 lines)
- ✅ `app/model_config.py` with latest models (606 lines)
- ✅ `config.example.yaml` template (326 lines)
- ✅ `requirements.txt` (36 lines)
- ✅ `.gitignore`
- ✅ `main.py` entry point (started)

---

## Phase 2: AWS Integration ✅

**Goal:** Implement AWS service monitoring and log collection

**Status:** Phase 2 is **100% complete**.

### Tasks

1. ✅ Create AWS client wrapper (`app/aws_client.py`) - **COMPLETED** (450 lines)
   - CloudWatch Logs integration (fetch_logs, fetch_error_logs, get_log_streams)
   - EC2 service status monitoring (get_instance_status, reboot_instance)
   - Amplify app status checking (get_amplify_app_status, start_amplify_deployment)
   - Connection testing for all services

2. ✅ Create log collector (`app/log_collector.py`) - **COMPLETED** (310 lines)
   - Real-time log polling from CloudWatch
   - Error pattern detection with severity classification
   - Fingerprint-based deduplication
   - Callback support for error handling

3. ✅ Create service monitor (`app/service_monitor.py`) - **COMPLETED** (320 lines)
   - EC2 instance health checks
   - Amplify deployment status monitoring
   - Health state change detection with callbacks
   - Health history tracking

4. ✅ Create alert manager (`app/alert_manager.py`) - **COMPLETED** (400 lines)
   - Alert creation from errors and health changes
   - Fingerprint-based deduplication
   - Priority-based escalation rules
   - Alert lifecycle management (open/acknowledged/resolved)

**Deliverables:** ✅
- ✅ `app/aws_client.py` - AWS service wrapper (450 lines)
- ✅ `app/log_collector.py` - CloudWatch log streaming (310 lines)
- ✅ `app/service_monitor.py` - Health monitoring (320 lines)
- ✅ `app/alert_manager.py` - Alert handling (400 lines)

---

## Phase 3: LLM Analysis Engine ✅

**Goal:** Implement intelligent error analysis using LLMs

**Status:** Phase 3 is **100% complete**.

### Tasks

1. ✅ Create error analyzer (`app/error_analyzer.py`) - **COMPLETED** (380 lines)
   - Error classification by category and severity
   - LLM-powered root cause analysis
   - Structured analysis results with JSON parsing
   - Fallback to heuristics when LLM fails

2. ✅ Create LLM orchestrator (`app/llm_orchestrator.py`) - **COMPLETED** (340 lines)
   - Task complexity-based model routing
   - Circuit breaker pattern for fault tolerance
   - Usage tracking and cost estimation
   - Model health monitoring

3. ✅ Create action recommender (`app/action_recommender.py`) - **COMPLETED** (380 lines)
   - Maps analysis to remediation actions
   - Safety checks and cooldown enforcement
   - Human approval routing for high-risk actions
   - Action history tracking

4. ✅ Create prompt templates (`app/prompts/`) - **COMPLETED**
   - `error_analysis.py` - Error analysis and triage prompts
   - `diagnosis.py` - Root cause and impact analysis prompts
   - `action_decision.py` - Action recommendation prompts

**Deliverables:** ✅
- ✅ `app/error_analyzer.py` - LLM-powered analysis (380 lines)
- ✅ `app/llm_orchestrator.py` - Multi-LLM management (340 lines)
- ✅ `app/action_recommender.py` - Remediation logic (380 lines)
- ✅ `app/prompts/` - Prompt templates (4 files)

---

## Phase 4: Automated Remediation ✅

**Goal:** Implement safe automated service recovery

**Status:** Phase 4 is **100% complete**.

### Tasks

1. ✅ Create action executor (`app/action_executor.py`) - **COMPLETED** (310 lines)
   - Service restart via AWS API
   - Amplify redeployment triggers
   - Instance reboot with recovery wait
   - Dry-run mode support

2. ✅ Create safety guard (`app/safety_guard.py`) - **COMPLETED** (340 lines)
   - Action rate limiting per service
   - Cooldown period enforcement
   - Circuit breaker pattern
   - Change freeze management
   - Maintenance window awareness

3. ✅ Create audit logger (`app/audit_logger.py`) - **COMPLETED** (350 lines)
   - Comprehensive action logging
   - Before/after state capture
   - Searchable audit trail
   - Compliance report generation

4. ✅ Create notification system (`app/notifier.py`) - **COMPLETED** (380 lines)
   - Email notifications via AWS SES
   - Slack webhook integration
   - Discord webhook integration
   - Priority-based routing
   - Rate limiting

**Deliverables:** ✅
- ✅ `app/action_executor.py` - Safe action execution (310 lines)
- ✅ `app/safety_guard.py` - Protection mechanisms (340 lines)
- ✅ `app/audit_logger.py` - Comprehensive logging (350 lines)
- ✅ `app/notifier.py` - Alert notifications (380 lines)

---

## Phase 5: Server & API ✅

**Goal:** Create the monitoring server with management API

**Status:** Phase 5 is **100% complete**.

### Tasks

1. ✅ Update main server (`main.py`) - **COMPLETED** (435 lines)
   - Full MonitorApp class with all components
   - Async event loop with graceful shutdown
   - Signal handling (SIGINT, SIGTERM)
   - Component initialization and coordination

2. ✅ Create REST API (`app/api.py`) - **COMPLETED** (420 lines)
   - Health endpoints (/health, /health/services)
   - Alert management (/alerts, acknowledge, resolve)
   - Action execution (/actions/execute)
   - Analysis endpoint (/analyze)
   - Statistics and audit (/stats, /audit)
   - Configuration and triggers

3. ✅ Create scheduler (`app/scheduler.py`) - **COMPLETED** (250 lines)
   - Interval-based task scheduling
   - Concurrent task execution
   - Health check, cleanup, and maintenance tasks
   - Task enable/disable and history

4. ✅ Create CLI interface (`app/cli.py`) - **COMPLETED** (350 lines)
   - Status and health commands
   - Log fetching with filters
   - Error analysis command
   - Model listing and switching
   - Configuration display

**Deliverables:** ✅
- ✅ `main.py` - Full application entry point (435 lines)
- ✅ `app/api.py` - FastAPI REST endpoints (420 lines)
- ✅ `app/scheduler.py` - Task scheduling (250 lines)
- ✅ `app/cli.py` - Management CLI (350 lines)

---

## Phase 6: Testing & Deployment ⏳

**Goal:** Testing, documentation, and production deployment

**Status:** Phase 6 is **75% complete**. EC2 deployed and running, local CLI scripts created.

**Last Updated:** 2025-12-04 15:40

### Deployment Template

| Component | Example Value |
|-----------|---------------|
| Instance ID | `i-0123456789abcdef0` |
| Public IP | `your-instance-ip` |
| Instance Type | t3.small (recommended) |
| OS | Ubuntu 24.04 LTS |
| Service Name | heimdallr |
| IAM Role | AWSMonitorRole |
| Security Group | heimdallr-sg |

### Tasks

1. ⏳ Unit tests for all modules - **PENDING**
2. ⏳ Integration tests with AWS mocks - **PENDING**
3. ⏳ Load testing for log volume - **PENDING**
4. ✅ Create systemd service file - **COMPLETED** (`Scripts/monitor.service`)
5. ✅ Create deployment scripts - **COMPLETED**
   - `Scripts/deploy.sh` (80 lines) - Server-side deploy script
   - `Scripts/setup-ec2.sh` (115 lines) - Initial EC2 setup
6. ✅ Create local CLI scripts - **COMPLETED**
   - `Scripts/monitor-ssh.sh` - SSH to instance
   - `Scripts/monitor-logs.sh` - View logs (live/recent/errors/llm)
   - `Scripts/monitor-deploy.sh` - Deploy from local
   - `Scripts/monitor-status.sh` - Check status
   - `Scripts/monitor-ctl.sh` - Service control (start/stop/restart)
   - `Scripts/monitor-ec2.sh` - EC2 control (start/stop/reboot)
7. ✅ Deploy to EC2 - **COMPLETED**
   - Instance launched and configured
   - IAM role with CloudWatch, Amplify, EC2, SES permissions
   - Service running and monitoring Amplify apps
8. ⏳ Documentation (README, API docs) - **PENDING**

**Deliverables:**
- ⏳ `tests/` - Comprehensive test suite
- ✅ `Scripts/deploy.sh` - Server deploy script (80 lines)
- ✅ `Scripts/setup-ec2.sh` - EC2 setup script (115 lines)
- ✅ `Scripts/monitor.service` - systemd unit (41 lines)
- ✅ `Scripts/monitor-*.sh` - Local CLI scripts (6 files)
- ⏳ `README.md` - Setup documentation
- ⏳ `Docs/API.md` - API documentation

---

## Architecture Decisions

### LLM Strategy

1. **Primary Model**: Configurable, default to cost-effective model (GPT-4o or Claude Sonnet)
2. **Analysis Model**: Use more capable model for complex analysis (GPT-5 or Claude Opus 4.5)
3. **Fallback Chain**: Primary -> Secondary -> Tertiary (different providers)
4. **Stuck Detection**:
   - Response timeout (30s default)
   - Token exhaustion without conclusion
   - Repetitive/looping responses

### Model Selection (Latest as of Dec 2025)

| Use Case | Primary | Fallback |
|----------|---------|----------|
| Quick triage | GPT-4o-mini | Gemini 2.5 Flash |
| Error analysis | GPT-5 | Claude Opus 4.5 |
| Complex diagnosis | Claude Opus 4.5 | GPT-5 + thinking |
| Action decision | GPT-4o | Claude Sonnet 4 |

### EC2 Deployment Recommendation

**RECOMMENDATION: Separate EC2 Instance**

**Reasons:**
1. **Isolation**: If monitored services crash, the monitor must remain running
2. **Resource Contention**: LLM calls can be memory-intensive; avoid competing with your services
3. **Security**: Monitor needs broad AWS permissions; isolate from application servers
4. **Reliability**: Single point of failure if monitor and services share instance
5. **Scaling**: Can scale monitor independently as log volume grows

**Alternative: Same Instance (Acceptable for Small Scale)**
- Use if cost is primary concern and services are stable
- Run monitor in Docker container for isolation
- Ensure monitor has restart policies independent of services
- Use lower memory LLM models (GPT-4o-mini, Gemini Flash)

**Recommended Instance Types:**
- **Dedicated Monitor**: t3.small or t3.medium (2-4GB RAM)
- **Shared Instance**: Ensure at least 1GB overhead for monitor

---

## Configuration Schema

```yaml
# config.yaml structure
aws:
  region: us-east-1
  # Credentials from env or IAM role

monitoring:
  amplify_apps:
    - app_id: d1234567890abc
      name: MyApp
    # - app_id: d0987654321xyz
    #   name: AnotherApp
  ec2_instances: []  # Optional EC2 monitoring

  # Polling intervals (seconds)
  log_poll_interval: 30
  health_check_interval: 60

llm:
  # Primary model for quick triage
  primary_model: openai/gpt-4o
  # Analysis model for detailed diagnosis
  analysis_model: anthropic/claude-opus-4-5-20251101
  # Fallback chain
  fallback_models:
    - google/gemini-2.5-pro
    - openai/gpt-5
  # Stuck detection
  timeout_s: 30
  max_retries: 3

actions:
  # Allowed automatic actions
  allow_restart: true
  allow_redeploy: false  # Require manual approval
  # Safety limits
  max_restarts_per_hour: 3
  cooldown_minutes: 10

notifications:
  email:
    enabled: false
    recipients: [admin@yourdomain.com]
  slack:
    enabled: false
    webhook_url: ""
```

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| LLM hallucination causing bad action | Strict action whitelist, human approval for destructive actions |
| Infinite restart loop | Cooldown periods, max restart limits |
| High AWS costs from log volume | Log sampling, error-only filtering |
| LLM API costs | Use cheaper models for triage, expensive for analysis only |
| Monitor crashes | systemd auto-restart, health endpoint for external monitoring |

---

## Success Criteria

1. Detects errors in Amplify logs within 60 seconds
2. LLM correctly diagnoses common errors (500s, timeouts, crashes) 80%+ of time
3. Safe automated restart reduces MTTR by 50%
4. Zero unintended destructive actions
5. Audit trail for all automated actions

---

## Next Steps

1. Complete Phase 1 core infrastructure
2. Set up development environment
3. Test LLM integration with sample error logs
4. Deploy to dedicated t3.small EC2 instance
