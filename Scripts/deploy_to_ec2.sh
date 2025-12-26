#!/bin/bash
# Deploy Heimdallr to EC2 via rsync
# Usage: ./deploy_to_ec2.sh [--restart]

set -e

# Configuration
EC2_HOST="ubuntu@18.232.50.52"
KEY_FILE="$HOME/.ssh/chatmaster-key.pem"
LOCAL_PATH="/mnt/d/Documents/Code/GitHub/Heimdallr/"
REMOTE_PATH="/home/ubuntu/heimdallr/"
SERVICE_NAME="heimdallr"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Deploying Heimdallr to EC2...${NC}"

# Check if key file exists
if [[ ! -f "$KEY_FILE" ]]; then
  echo -e "${RED}Error: SSH key not found at $KEY_FILE${NC}"
  exit 1
fi

# Sync files
rsync -avz --progress \
  --exclude '.git' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.venv*' \
  --exclude 'venv' \
  --exclude '*.log' \
  --exclude '.env' \
  --exclude 'config.yaml' \
  --exclude 'Logs/' \
  --exclude '.idea' \
  --exclude '.claude' \
  --exclude '*.local.md' \
  -e "ssh -i $KEY_FILE" \
  "$LOCAL_PATH" \
  "$EC2_HOST:$REMOTE_PATH"

echo -e "${GREEN}Files synced successfully!${NC}"

# Restart service if --restart flag is passed
if [[ "$1" == "--restart" ]]; then
  echo -e "${YELLOW}Restarting $SERVICE_NAME service...${NC}"
  ssh -i "$KEY_FILE" "$EC2_HOST" "sudo systemctl restart $SERVICE_NAME"
  sleep 2
  echo -e "${GREEN}Service restarted!${NC}"

  # Show service status
  echo -e "${YELLOW}Service status:${NC}"
  ssh -i "$KEY_FILE" "$EC2_HOST" "sudo systemctl status $SERVICE_NAME --no-pager -l | head -15"

  # Show recent logs
  echo -e "${YELLOW}Recent logs:${NC}"
  ssh -i "$KEY_FILE" "$EC2_HOST" "sudo journalctl -u $SERVICE_NAME -n 10 --no-pager"
else
  echo -e "${YELLOW}To restart the service, run: ./Scripts/deploy_to_ec2.sh --restart${NC}"
fi
