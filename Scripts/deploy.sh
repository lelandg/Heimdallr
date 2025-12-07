#!/bin/bash
# Heimdallr Deployment Script
# Run this on the EC2 instance after initial setup

set -e

# Configuration
APP_DIR="/opt/heimdallr"
VENV_DIR="$APP_DIR/.venv"
SERVICE_NAME="heimdallr"
USER="ubuntu"

echo "=========================================="
echo "Heimdallr Deployment"
echo "=========================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (sudo)"
    exit 1
fi

# Navigate to app directory
cd "$APP_DIR"

echo "[1/6] Updating code..."
if [ -d ".git" ]; then
    git pull origin main || git pull origin master || echo "Git pull skipped"
fi

echo "[2/6] Setting up Python virtual environment..."
if [ ! -d "$VENV_DIR" ]; then
    python3.11 -m venv "$VENV_DIR" || python3 -m venv "$VENV_DIR"
fi

echo "[3/6] Installing dependencies..."
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r requirements.txt

echo "[4/6] Creating directories..."
mkdir -p Logs
chown -R $USER:$USER Logs

echo "[5/6] Installing systemd service..."
cp Scripts/heimdallr.service /etc/systemd/system/$SERVICE_NAME.service
systemctl daemon-reload
systemctl enable $SERVICE_NAME

echo "[6/6] Starting service..."
systemctl restart $SERVICE_NAME
sleep 2

# Check status
if systemctl is-active --quiet $SERVICE_NAME; then
    echo ""
    echo "=========================================="
    echo "✓ Deployment successful!"
    echo "=========================================="
    echo ""
    echo "Service status: $(systemctl is-active $SERVICE_NAME)"
    echo ""
    echo "Useful commands:"
    echo "  View logs:     journalctl -u $SERVICE_NAME -f"
    echo "  Check status:  systemctl status $SERVICE_NAME"
    echo "  Restart:       systemctl restart $SERVICE_NAME"
    echo "  Stop:          systemctl stop $SERVICE_NAME"
    echo ""
    echo "API available at: http://localhost:8000"
    echo ""
else
    echo ""
    echo "=========================================="
    echo "✗ Service failed to start"
    echo "=========================================="
    echo ""
    echo "Check logs with: journalctl -u $SERVICE_NAME -n 50"
    exit 1
fi
