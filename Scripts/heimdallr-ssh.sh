#!/bin/bash
# SSH into Heimdallr EC2 instance
#
# Configuration: Set these environment variables or edit the defaults below:
#   HEIMDALLR_EC2_HOST - EC2 user@ip (e.g., ubuntu@198.51.100.1)
#   HEIMDALLR_SSH_KEY  - Path to SSH private key

EC2_HOST="${HEIMDALLR_EC2_HOST:-ubuntu@your-instance-ip}"
SSH_KEY="${HEIMDALLR_SSH_KEY:-$HOME/.ssh/heimdallr-key.pem}"

if [[ "$EC2_HOST" == *"your-instance-ip"* ]]; then
    echo "Error: Please set HEIMDALLR_EC2_HOST environment variable or edit this script"
    echo "Example: export HEIMDALLR_EC2_HOST=ubuntu@198.51.100.1"
    exit 1
fi

ssh -i "$SSH_KEY" "$EC2_HOST" "$@"
