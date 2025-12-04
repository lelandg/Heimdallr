#!/bin/bash
# View AWS Monitor logs (live or recent)
#
# Configuration: Set these environment variables or edit the defaults below:
#   MONITOR_EC2_HOST - EC2 user@ip (e.g., ubuntu@198.51.100.1)
#   MONITOR_SSH_KEY  - Path to SSH private key

EC2_HOST="${MONITOR_EC2_HOST:-ubuntu@your-instance-ip}"
SSH_KEY="${MONITOR_SSH_KEY:-$HOME/.ssh/aws-monitor-key.pem}"
SERVICE="aws-monitor"

if [[ "$EC2_HOST" == *"your-instance-ip"* ]]; then
    echo "Error: Please set MONITOR_EC2_HOST environment variable or edit this script"
    echo "Example: export MONITOR_EC2_HOST=ubuntu@198.51.100.1"
    exit 1
fi

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -f, --follow     Follow logs in real-time (default)"
    echo "  -n, --lines N    Show last N lines (default: 50)"
    echo "  --errors         Filter to errors only"
    echo "  --llm            Show LLM interaction logs"
    echo "  -h, --help       Show this help"
    echo ""
    echo "Examples:"
    echo "  $0                    # Follow live logs"
    echo "  $0 -n 100             # Show last 100 lines"
    echo "  $0 --errors -n 50     # Last 50 error lines"
    echo "  $0 --llm              # View LLM interactions"
}

LINES=50
FOLLOW=true
FILTER=""
LOG_TYPE="journalctl"

while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--follow)
            FOLLOW=true
            shift
            ;;
        -n|--lines)
            LINES="$2"
            FOLLOW=false
            shift 2
            ;;
        --errors)
            FILTER="ERROR"
            shift
            ;;
        --llm)
            LOG_TYPE="llm"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

if [[ "$LOG_TYPE" == "llm" ]]; then
    if [[ "$FOLLOW" == "true" ]]; then
        ssh -i "$SSH_KEY" "$EC2_HOST" "tail -f /home/ubuntu/monitor/Logs/llm_interactions.log"
    else
        ssh -i "$SSH_KEY" "$EC2_HOST" "tail -n $LINES /home/ubuntu/monitor/Logs/llm_interactions.log"
    fi
else
    if [[ "$FOLLOW" == "true" ]]; then
        if [[ -n "$FILTER" ]]; then
            ssh -i "$SSH_KEY" "$EC2_HOST" "sudo journalctl -u $SERVICE -f" | grep --line-buffered "$FILTER"
        else
            ssh -i "$SSH_KEY" "$EC2_HOST" "sudo journalctl -u $SERVICE -f"
        fi
    else
        if [[ -n "$FILTER" ]]; then
            ssh -i "$SSH_KEY" "$EC2_HOST" "sudo journalctl -u $SERVICE -n $LINES --no-pager" | grep "$FILTER"
        else
            ssh -i "$SSH_KEY" "$EC2_HOST" "sudo journalctl -u $SERVICE -n $LINES --no-pager"
        fi
    fi
fi
