#!/bin/bash
# Heimdallr - Configuration Validator
# Validate config.yaml and test AWS connectivity for configured services
#
# Checks:
# - Config file syntax
# - Required fields present
# - AWS credentials valid
# - Configured services exist and are accessible
# - LLM API keys valid (optional)

# Note: Not using set -e because grep/aws commands may return non-zero legitimately

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="${HEIMDALLR_CONFIG:-$PROJECT_DIR/config.yaml}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"

# Counters
PASS=0
FAIL=0
WARN=0

# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────

pass() {
    echo -e "  ${GREEN}✓${NC} $1"
    ((PASS++))
}

fail() {
    echo -e "  ${RED}✗${NC} $1"
    ((FAIL++))
}

warn() {
    echo -e "  ${YELLOW}⚠${NC} $1"
    ((WARN++))
}

info() {
    echo -e "  ${BLUE}ℹ${NC} $1"
}

# ─────────────────────────────────────────────────────────────────────────────
# Validation Functions
# ─────────────────────────────────────────────────────────────────────────────

validate_config_file() {
    echo -e "${CYAN}Config File${NC}"

    if [[ ! -f "$CONFIG_FILE" ]]; then
        fail "Config file not found: $CONFIG_FILE"
        return 1
    fi
    pass "Config file exists: $CONFIG_FILE"

    # Validate YAML syntax
    if python3 -c "import yaml; yaml.safe_load(open('$CONFIG_FILE'))" 2>/dev/null; then
        pass "YAML syntax valid"
    else
        fail "YAML syntax error"
        return 1
    fi

    # Check required sections
    python3 << PYTHON
import yaml
import sys

with open('$CONFIG_FILE') as f:
    config = yaml.safe_load(f)

required = ['monitoring', 'llm']
for section in required:
    if section not in config:
        print(f"MISSING:{section}")
    else:
        print(f"OK:{section}")
PYTHON
    echo ""
}

validate_aws() {
    echo -e "${CYAN}AWS Connectivity${NC}"

    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        fail "AWS CLI not installed"
        return 1
    fi
    pass "AWS CLI installed"

    # Check credentials
    if aws sts get-caller-identity &> /dev/null; then
        identity=$(aws sts get-caller-identity --query 'Arn' --output text 2>/dev/null)
        pass "AWS credentials valid: $identity"
    else
        fail "AWS credentials not configured or expired"
        return 1
    fi

    # Check region
    info "Region: $REGION"
    echo ""
}

validate_amplify_apps() {
    echo -e "${CYAN}Amplify Apps${NC}"

    apps=$(python3 -c "
import yaml
with open('$CONFIG_FILE') as f:
    config = yaml.safe_load(f)
apps = config.get('monitoring', {}).get('amplify_apps', [])
for app in apps:
    print(f\"{app.get('app_id')}|{app.get('name', 'unnamed')}\")
" 2>/dev/null)

    if [[ -z "$apps" ]]; then
        warn "No Amplify apps configured"
        echo ""
        return
    fi

    while IFS='|' read -r app_id name; do
        # Check app exists
        if aws amplify get-app --app-id "$app_id" --region "$REGION" &> /dev/null; then
            pass "$name ($app_id) - exists"

            # Check log group
            log_group="/aws/amplify/$app_id"
            if aws logs describe-log-groups --log-group-name-prefix "$log_group" --region "$REGION" --query 'logGroups[0].logGroupName' --output text 2>/dev/null | grep -q "$log_group"; then
                pass "$name - log group accessible"
            else
                warn "$name - log group not found (may be new app)"
            fi
        else
            fail "$name ($app_id) - app not found or no access"
        fi
    done <<< "$apps"
    echo ""
}

validate_ec2_instances() {
    echo -e "${CYAN}EC2 Instances${NC}"

    instances=$(python3 -c "
import yaml
with open('$CONFIG_FILE') as f:
    config = yaml.safe_load(f)
instances = config.get('monitoring', {}).get('ec2_instances', [])
for inst in instances:
    print(f\"{inst.get('instance_id')}|{inst.get('name', 'unnamed')}\")
" 2>/dev/null)

    if [[ -z "$instances" ]]; then
        info "No EC2 instances configured"
        echo ""
        return
    fi

    while IFS='|' read -r instance_id name; do
        [[ -z "$instance_id" ]] && continue

        # Check instance exists
        state=$(aws ec2 describe-instances \
            --instance-ids "$instance_id" \
            --region "$REGION" \
            --query 'Reservations[0].Instances[0].State.Name' \
            --output text 2>/dev/null)

        if [[ -n "$state" ]] && [[ "$state" != "None" ]]; then
            if [[ "$state" == "running" ]]; then
                pass "$name ($instance_id) - $state"
            else
                warn "$name ($instance_id) - $state"
            fi
        else
            fail "$name ($instance_id) - instance not found or no access"
        fi
    done <<< "$instances"
    echo ""
}

validate_llm_keys() {
    echo -e "${CYAN}LLM API Keys${NC}"

    # OpenAI
    key="${OPENAI_API_KEY:-}"
    if [[ -z "$key" ]]; then
        key=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG_FILE')).get('llm', {}).get('openai_api_key', ''))" 2>/dev/null)
    fi
    if [[ -n "$key" ]] && [[ "$key" != "sk-..." ]]; then
        # Quick validation - just check format
        if [[ "$key" == sk-* ]]; then
            pass "OpenAI API key configured (sk-...)"
        else
            warn "OpenAI API key format unexpected"
        fi
    else
        info "OpenAI API key not configured"
    fi

    # Anthropic
    key="${ANTHROPIC_API_KEY:-}"
    if [[ -z "$key" ]]; then
        key=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG_FILE')).get('llm', {}).get('anthropic_api_key', ''))" 2>/dev/null)
    fi
    if [[ -n "$key" ]] && [[ "$key" != "sk-ant-..." ]]; then
        if [[ "$key" == sk-ant-* ]]; then
            pass "Anthropic API key configured (sk-ant-...)"
        else
            warn "Anthropic API key format unexpected"
        fi
    else
        info "Anthropic API key not configured"
    fi

    # Gemini
    key="${GEMINI_API_KEY:-}"
    if [[ -z "$key" ]]; then
        key=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG_FILE')).get('llm', {}).get('gemini_api_key', ''))" 2>/dev/null)
    fi
    if [[ -n "$key" ]] && [[ "$key" != "AIza..." ]]; then
        if [[ "$key" == AIza* ]]; then
            pass "Gemini API key configured (AIza...)"
        else
            warn "Gemini API key format unexpected"
        fi
    else
        info "Gemini API key not configured"
    fi

    echo ""
}

validate_intervals() {
    echo -e "${CYAN}Polling Intervals${NC}"

    python3 - "$CONFIG_FILE" << 'PYTHON'
import yaml
import sys

with open(sys.argv[1]) as f:
    config = yaml.safe_load(f)

mon = config.get('monitoring', {})
log_poll = mon.get('log_poll_interval', 30)
health = mon.get('health_check_interval', 60)
lookback = mon.get('error_lookback_minutes', 5)

# Recommendations
if log_poll < 30:
    print(f"WARN:Log polling at {log_poll}s is aggressive (recommend 60-120s)")
elif log_poll > 300:
    print(f"WARN:Log polling at {log_poll}s may be slow for quick detection")
else:
    print(f"OK:Log polling: {log_poll}s")

if health < 60:
    print(f"WARN:Health check at {health}s is aggressive (recommend 300s for stable services)")
else:
    print(f"OK:Health check: {health}s")

if lookback < 5:
    print(f"WARN:Error lookback at {lookback}m may miss context (recommend 10-15m)")
else:
    print(f"OK:Error lookback: {lookback}m")
PYTHON

    echo ""
}

# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

echo ""
echo -e "${CYAN}═══════════════════════════════════════════${NC}"
echo -e "${CYAN}  Heimdallr - Configuration Validation${NC}"
echo -e "${CYAN}═══════════════════════════════════════════${NC}"
echo ""

validate_config_file || exit 1
validate_aws || exit 1
validate_amplify_apps
validate_ec2_instances
validate_llm_keys
validate_intervals

# Summary
echo -e "${CYAN}═══════════════════════════════════════════${NC}"
echo -e "${CYAN}  Summary${NC}"
echo -e "${CYAN}═══════════════════════════════════════════${NC}"
echo ""
echo -e "  ${GREEN}Passed:${NC}   $PASS"
echo -e "  ${YELLOW}Warnings:${NC} $WARN"
echo -e "  ${RED}Failed:${NC}   $FAIL"
echo ""

if [[ $FAIL -gt 0 ]]; then
    echo -e "${RED}Validation failed - please fix errors above${NC}"
    exit 1
elif [[ $WARN -gt 0 ]]; then
    echo -e "${YELLOW}Validation passed with warnings${NC}"
    exit 0
else
    echo -e "${GREEN}All checks passed!${NC}"
    exit 0
fi
