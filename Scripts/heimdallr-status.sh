#!/bin/bash
# Check Heimdallr status
#
# Configuration: Set these environment variables or edit the defaults below:
#   HEIMDALLR_EC2_HOST   - EC2 user@ip (e.g., ubuntu@198.51.100.1)
#   HEIMDALLR_SSH_KEY    - Path to SSH private key
#   HEIMDALLR_INSTANCE_ID - EC2 instance ID (for AWS CLI queries)

EC2_HOST="${HEIMDALLR_EC2_HOST:-ubuntu@your-instance-ip}"
SSH_KEY="${HEIMDALLR_SSH_KEY:-$HOME/.ssh/heimdallr-key.pem}"
SERVICE="heimdallr"
INSTANCE_ID="${HEIMDALLR_INSTANCE_ID:-i-0123456789abcdef0}"

# Extract IP from EC2_HOST for curl
EC2_IP=$(echo "$EC2_HOST" | cut -d'@' -f2)

echo "=========================================="
echo "Heimdallr Status"
echo "=========================================="
echo ""

if [[ "$EC2_HOST" == *"your-instance-ip"* ]]; then
    echo "Warning: HEIMDALLR_EC2_HOST not configured"
    echo "Set environment variables or edit this script"
    echo ""
fi

# EC2 Instance Status
echo "EC2 Instance:"
if [[ "$INSTANCE_ID" != *"0123456789"* ]]; then
    aws ec2 describe-instances \
        --instance-ids "$INSTANCE_ID" \
        --region us-east-1 \
        --query 'Reservations[0].Instances[0].[State.Name,PublicIpAddress,InstanceType]' \
        --output table 2>/dev/null || echo "  (AWS CLI not configured or instance not found)"
else
    echo "  (HEIMDALLR_INSTANCE_ID not configured)"
fi
echo ""

# Service Status
echo "Service Status:"
if [[ "$EC2_HOST" != *"your-instance-ip"* ]]; then
    ssh -i "$SSH_KEY" -o ConnectTimeout=5 "$EC2_HOST" "systemctl is-active $SERVICE && echo 'Running on port 8000'" 2>/dev/null || echo "  Cannot connect to instance"
else
    echo "  (HEIMDALLR_EC2_HOST not configured)"
fi
echo ""

# Recent Activity
echo "Recent Activity (last 5 lines):"
if [[ "$EC2_HOST" != *"your-instance-ip"* ]]; then
    ssh -i "$SSH_KEY" -o ConnectTimeout=5 "$EC2_HOST" "sudo journalctl -u $SERVICE -n 5 --no-pager" 2>/dev/null || echo "  Cannot connect to instance"
else
    echo "  (HEIMDALLR_EC2_HOST not configured)"
fi
echo ""

# API Health (if accessible)
echo "API Health:"
if [[ "$EC2_IP" != "your-instance-ip" ]]; then
    curl -s --connect-timeout 5 "http://${EC2_IP}:8000/health" 2>/dev/null || echo "  API not accessible (may not be running)"
else
    echo "  (HEIMDALLR_EC2_HOST not configured)"
fi
echo ""
