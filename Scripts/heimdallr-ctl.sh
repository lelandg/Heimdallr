#!/bin/bash
# Heimdallr service control
#
# Configuration: Set these environment variables or edit the defaults below:
#   HEIMDALLR_EC2_HOST - EC2 user@ip (e.g., ubuntu@198.51.100.1)
#   HEIMDALLR_SSH_KEY  - Path to SSH private key

EC2_HOST="${HEIMDALLR_EC2_HOST:-ubuntu@your-instance-ip}"
SSH_KEY="${HEIMDALLR_SSH_KEY:-$HOME/.ssh/heimdallr-key.pem}"
SERVICE="heimdallr"

if [[ "$EC2_HOST" == *"your-instance-ip"* ]]; then
    echo "Error: Please set HEIMDALLR_EC2_HOST environment variable or edit this script"
    echo "Example: export HEIMDALLR_EC2_HOST=ubuntu@198.51.100.1"
    exit 1
fi

usage() {
    echo "Usage: $0 COMMAND"
    echo ""
    echo "Commands:"
    echo "  start      Start the Heimdallr service"
    echo "  stop       Stop the Heimdallr service"
    echo "  restart    Restart the Heimdallr service"
    echo "  status     Show service status"
    echo "  enable     Enable service at boot"
    echo "  disable    Disable service at boot"
    echo ""
}

if [[ $# -eq 0 ]]; then
    usage
    exit 1
fi

case $1 in
    start)
        ssh -i "$SSH_KEY" "$EC2_HOST" "sudo systemctl start $SERVICE && systemctl is-active $SERVICE"
        ;;
    stop)
        ssh -i "$SSH_KEY" "$EC2_HOST" "sudo systemctl stop $SERVICE && echo 'Service stopped'"
        ;;
    restart)
        ssh -i "$SSH_KEY" "$EC2_HOST" "sudo systemctl restart $SERVICE && sleep 2 && systemctl is-active $SERVICE"
        ;;
    status)
        ssh -i "$SSH_KEY" "$EC2_HOST" "sudo systemctl status $SERVICE"
        ;;
    enable)
        ssh -i "$SSH_KEY" "$EC2_HOST" "sudo systemctl enable $SERVICE && echo 'Service enabled at boot'"
        ;;
    disable)
        ssh -i "$SSH_KEY" "$EC2_HOST" "sudo systemctl disable $SERVICE && echo 'Service disabled at boot'"
        ;;
    *)
        echo "Unknown command: $1"
        usage
        exit 1
        ;;
esac
