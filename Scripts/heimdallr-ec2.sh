#!/bin/bash
# Heimdallr EC2 instance control
#
# Configuration: Set these environment variables or edit the defaults below:
#   HEIMDALLR_INSTANCE_ID - EC2 instance ID
#   AWS_DEFAULT_REGION  - AWS region (default: us-east-1)

INSTANCE_ID="${HEIMDALLR_INSTANCE_ID:-i-0123456789abcdef0}"
REGION="${AWS_DEFAULT_REGION:-us-east-1}"

if [[ "$INSTANCE_ID" == *"0123456789"* ]]; then
    echo "Error: Please set HEIMDALLR_INSTANCE_ID environment variable or edit this script"
    echo "Example: export HEIMDALLR_INSTANCE_ID=i-0abc123def456789"
    exit 1
fi

usage() {
    echo "Usage: $0 COMMAND"
    echo ""
    echo "Commands:"
    echo "  start      Start the EC2 instance"
    echo "  stop       Stop the EC2 instance"
    echo "  reboot     Reboot the EC2 instance"
    echo "  status     Show instance status"
    echo "  ip         Get current public IP"
    echo ""
}

if [[ $# -eq 0 ]]; then
    usage
    exit 1
fi

case $1 in
    start)
        echo "Starting instance $INSTANCE_ID..."
        aws ec2 start-instances --instance-ids "$INSTANCE_ID" --region "$REGION"
        echo ""
        echo "Waiting for instance to be running..."
        aws ec2 wait instance-running --instance-ids "$INSTANCE_ID" --region "$REGION"
        echo ""
        echo "Instance started. Getting public IP..."
        aws ec2 describe-instances \
            --instance-ids "$INSTANCE_ID" \
            --region "$REGION" \
            --query 'Reservations[0].Instances[0].PublicIpAddress' \
            --output text
        ;;
    stop)
        echo "Stopping instance $INSTANCE_ID..."
        aws ec2 stop-instances --instance-ids "$INSTANCE_ID" --region "$REGION"
        ;;
    reboot)
        echo "Rebooting instance $INSTANCE_ID..."
        aws ec2 reboot-instances --instance-ids "$INSTANCE_ID" --region "$REGION"
        echo "Reboot initiated. Instance may take a minute to come back online."
        ;;
    status)
        aws ec2 describe-instances \
            --instance-ids "$INSTANCE_ID" \
            --region "$REGION" \
            --query 'Reservations[0].Instances[0].[State.Name,PublicIpAddress,InstanceType,LaunchTime]' \
            --output table
        ;;
    ip)
        aws ec2 describe-instances \
            --instance-ids "$INSTANCE_ID" \
            --region "$REGION" \
            --query 'Reservations[0].Instances[0].PublicIpAddress' \
            --output text
        ;;
    *)
        echo "Unknown command: $1"
        usage
        exit 1
        ;;
esac
