#!/bin/bash
# Deploy Heimdallr to EC2 instance
# Usage: ./heimdallr-deploy.sh [--restart]
#
# Configuration: Set these environment variables or edit the defaults below:
#   HEIMDALLR_EC2_HOST  - EC2 user@ip (e.g., ubuntu@198.51.100.1)
#   HEIMDALLR_SSH_KEY   - Path to SSH private key
#   HEIMDALLR_LOCAL_PATH - Local path to Heimdallr repo
#   HEIMDALLR_REMOTE_PATH - Remote path on EC2

set -e

EC2_HOST="${HEIMDALLR_EC2_HOST:-ubuntu@your-instance-ip}"
SSH_KEY="${HEIMDALLR_SSH_KEY:-$HOME/.ssh/heimdallr-key.pem}"
LOCAL_PATH="${HEIMDALLR_LOCAL_PATH:-$(dirname "$(dirname "$(realpath "$0")")")/}"
REMOTE_PATH="${HEIMDALLR_REMOTE_PATH:-/home/ubuntu/heimdallr/}"
SERVICE="heimdallr"

if [[ "$EC2_HOST" == *"your-instance-ip"* ]]; then
    echo "Error: Please set HEIMDALLR_EC2_HOST environment variable or edit this script"
    echo "Example: export HEIMDALLR_EC2_HOST=ubuntu@198.51.100.1"
    exit 1
fi

RESTART=false

for arg in "$@"; do
    case $arg in
        --restart)
            RESTART=true
            shift
            ;;
    esac
done

echo "=========================================="
echo "Heimdallr - Deploy to EC2"
echo "=========================================="
echo ""
echo "Host: $EC2_HOST"
echo "Local: $LOCAL_PATH"
echo "Remote: $REMOTE_PATH"
echo ""

echo "[1/3] Syncing files..."
rsync -avz \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.venv*' \
    --exclude='venv' \
    --exclude='*.log' \
    --exclude='.env' \
    --exclude='.idea' \
    --exclude='.claude' \
    --exclude='Logs/*.log' \
    -e "ssh -i $SSH_KEY" \
    "$LOCAL_PATH" "$EC2_HOST:$REMOTE_PATH"

echo ""
echo "[2/3] Installing dependencies..."
ssh -i "$SSH_KEY" "$EC2_HOST" "cd $REMOTE_PATH && if [ ! -d .venv ]; then python3 -m venv .venv; fi && source .venv/bin/activate && pip install -q -r requirements.txt"

if [[ "$RESTART" == "true" ]]; then
    echo ""
    echo "[3/3] Restarting service..."
    ssh -i "$SSH_KEY" "$EC2_HOST" "sudo systemctl restart $SERVICE"
    sleep 2

    # Check status
    STATUS=$(ssh -i "$SSH_KEY" "$EC2_HOST" "systemctl is-active $SERVICE")
    if [[ "$STATUS" == "active" ]]; then
        echo ""
        echo "=========================================="
        echo "✓ Deployment successful! Service running."
        echo "=========================================="
    else
        echo ""
        echo "=========================================="
        echo "✗ Service failed to start"
        echo "=========================================="
        ssh -i "$SSH_KEY" "$EC2_HOST" "sudo journalctl -u $SERVICE -n 20 --no-pager"
        exit 1
    fi
else
    echo ""
    echo "[3/3] Skipped restart (use --restart to restart service)"
    echo ""
    echo "=========================================="
    echo "✓ Files synced successfully"
    echo "=========================================="
    echo ""
    echo "To restart manually:"
    echo "  ./heimdallr-ssh.sh 'sudo systemctl restart heimdallr'"
fi

echo ""
echo "View logs: ./heimdallr-logs.sh"
