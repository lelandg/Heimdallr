#!/bin/bash
# Heimdallr - Service Discovery
# Auto-discover Amplify apps and EC2 instances from your AWS account
#
# Requires: AWS CLI configured with appropriate permissions

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"

# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────

check_aws_cli() {
    if ! command -v aws &> /dev/null; then
        echo -e "${RED}AWS CLI not found. Please install it first.${NC}"
        exit 1
    fi

    # Check credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        echo -e "${RED}AWS credentials not configured or expired.${NC}"
        echo "Run: aws configure"
        exit 1
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# Discovery Functions
# ─────────────────────────────────────────────────────────────────────────────

discover_amplify() {
    echo -e "${CYAN}═══════════════════════════════════════════${NC}"
    echo -e "${CYAN}  Amplify Applications (Region: $REGION)${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════${NC}"
    echo ""

    apps=$(aws amplify list-apps --region "$REGION" --query 'apps[*].[appId,name,defaultDomain]' --output json 2>/dev/null)

    if [[ "$apps" == "[]" ]] || [[ -z "$apps" ]]; then
        echo -e "${YELLOW}No Amplify apps found in $REGION${NC}"
        return
    fi

    echo "$apps" | python3 -c "
import json
import sys

apps = json.load(sys.stdin)
for app_id, name, domain in apps:
    print(f'  \033[1;32m{name}\033[0m')
    print(f'    App ID:    {app_id}')
    print(f'    Domain:    {domain}')
    print(f'    Log Group: /aws/amplify/{app_id}')
    print(f'    Add cmd:   ./monitor-config.sh add amplify {app_id} \"{name}\"')
    print()
"
}

discover_ec2() {
    echo -e "${CYAN}═══════════════════════════════════════════${NC}"
    echo -e "${CYAN}  EC2 Instances (Region: $REGION)${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════${NC}"
    echo ""

    instances=$(aws ec2 describe-instances \
        --region "$REGION" \
        --filters "Name=instance-state-name,Values=running,stopped" \
        --query 'Reservations[*].Instances[*].[InstanceId,InstanceType,State.Name,PublicIpAddress,Tags[?Key==`Name`].Value|[0]]' \
        --output json 2>/dev/null)

    if [[ "$instances" == "[[]]" ]] || [[ -z "$instances" ]]; then
        echo -e "${YELLOW}No EC2 instances found in $REGION${NC}"
        return
    fi

    echo "$instances" | python3 -c "
import json
import sys

reservations = json.load(sys.stdin)
for res in reservations:
    for inst in res:
        inst_id, inst_type, state, ip, name = inst
        name = name or 'unnamed'
        ip = ip or 'no public IP'
        state_color = '\033[1;32m' if state == 'running' else '\033[1;33m'
        print(f'  \033[1;32m{name}\033[0m ({state_color}{state}\033[0m)')
        print(f'    Instance ID: {inst_id}')
        print(f'    Type:        {inst_type}')
        print(f'    IP:          {ip}')
        print(f'    Add cmd:     ./monitor-config.sh add ec2 {inst_id} \"{name}\"')
        print()
"
}

discover_cloudwatch_log_groups() {
    echo -e "${CYAN}═══════════════════════════════════════════${NC}"
    echo -e "${CYAN}  CloudWatch Log Groups (Region: $REGION)${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════${NC}"
    echo ""

    # Get log groups, filter for common patterns
    log_groups=$(aws logs describe-log-groups \
        --region "$REGION" \
        --query 'logGroups[*].[logGroupName,storedBytes]' \
        --output json 2>/dev/null)

    if [[ "$log_groups" == "[]" ]] || [[ -z "$log_groups" ]]; then
        echo -e "${YELLOW}No log groups found in $REGION${NC}"
        return
    fi

    echo "$log_groups" | python3 -c "
import json
import sys

def format_bytes(b):
    if b is None:
        return '0 B'
    for unit in ['B', 'KB', 'MB', 'GB']:
        if b < 1024:
            return f'{b:.1f} {unit}'
        b /= 1024
    return f'{b:.1f} TB'

groups = json.load(sys.stdin)
# Categorize
amplify = []
lambda_logs = []
ec2 = []
other = []

for name, size in groups:
    if '/aws/amplify/' in name:
        amplify.append((name, size))
    elif '/aws/lambda/' in name:
        lambda_logs.append((name, size))
    elif '/aws/ec2/' in name or '/var/log/' in name:
        ec2.append((name, size))
    else:
        other.append((name, size))

if amplify:
    print('\033[1;34mAmplify Logs:\033[0m')
    for name, size in amplify[:10]:
        print(f'  • {name} ({format_bytes(size)})')
    print()

if lambda_logs:
    print('\033[1;34mLambda Logs:\033[0m')
    for name, size in lambda_logs[:10]:
        print(f'  • {name} ({format_bytes(size)})')
    if len(lambda_logs) > 10:
        print(f'  ... and {len(lambda_logs) - 10} more')
    print()

if ec2:
    print('\033[1;34mEC2 Logs:\033[0m')
    for name, size in ec2[:10]:
        print(f'  • {name} ({format_bytes(size)})')
    print()

if other:
    print('\033[1;34mOther Logs:\033[0m')
    for name, size in other[:10]:
        print(f'  • {name} ({format_bytes(size)})')
    if len(other) > 10:
        print(f'  ... and {len(other) - 10} more')
    print()
"
}

# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

usage() {
    echo -e "${CYAN}Heimdallr - Service Discovery${NC}"
    echo ""
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo -e "${YELLOW}Commands:${NC}"
    echo "  all          Discover all resources (default)"
    echo "  amplify      Discover Amplify applications only"
    echo "  ec2          Discover EC2 instances only"
    echo "  logs         List CloudWatch log groups"
    echo ""
    echo -e "${YELLOW}Environment:${NC}"
    echo "  AWS_REGION   AWS region to scan (default: us-east-1)"
    echo ""
    echo -e "${YELLOW}Examples:${NC}"
    echo "  $0"
    echo "  $0 amplify"
    echo "  AWS_REGION=us-west-2 $0 ec2"
    echo ""
}

check_aws_cli

case ${1:-all} in
    all)
        discover_amplify
        discover_ec2
        ;;
    amplify)
        discover_amplify
        ;;
    ec2)
        discover_ec2
        ;;
    logs)
        discover_cloudwatch_log_groups
        ;;
    help|-h|--help)
        usage
        ;;
    *)
        echo -e "${RED}Unknown command: $1${NC}"
        usage
        exit 1
        ;;
esac
