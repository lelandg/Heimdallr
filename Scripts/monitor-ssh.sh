#!/bin/bash
# SSH into AWS Monitor EC2 instance
#
# Configuration: Set these environment variables or edit the defaults below:
#   MONITOR_EC2_HOST - EC2 user@ip (e.g., ubuntu@198.51.100.1)
#   MONITOR_SSH_KEY  - Path to SSH private key

EC2_HOST="${MONITOR_EC2_HOST:-ubuntu@your-instance-ip}"
SSH_KEY="${MONITOR_SSH_KEY:-$HOME/.ssh/aws-monitor-key.pem}"

if [[ "$EC2_HOST" == *"your-instance-ip"* ]]; then
    echo "Error: Please set MONITOR_EC2_HOST environment variable or edit this script"
    echo "Example: export MONITOR_EC2_HOST=ubuntu@198.51.100.1"
    exit 1
fi

ssh -i "$SSH_KEY" "$EC2_HOST" "$@"
