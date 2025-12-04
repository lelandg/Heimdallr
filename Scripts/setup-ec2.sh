#!/bin/bash
# AWS Monitor - EC2 Instance Setup Script
# Run this ONCE on a fresh Ubuntu EC2 instance to prepare for deployment

set -e

# Configuration
APP_DIR="/opt/monitor"
USER="ubuntu"
PYTHON_VERSION="3.11"

echo "=========================================="
echo "AWS Monitor - EC2 Setup"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (sudo)"
    exit 1
fi

echo "[1/8] Updating system packages..."
apt-get update
apt-get upgrade -y

echo "[2/8] Installing Python ${PYTHON_VERSION}..."
apt-get install -y software-properties-common
add-apt-repository -y ppa:deadsnakes/ppa
apt-get update
apt-get install -y python${PYTHON_VERSION} python${PYTHON_VERSION}-venv python${PYTHON_VERSION}-dev

# Make python3.11 the default python3
update-alternatives --install /usr/bin/python3 python3 /usr/bin/python${PYTHON_VERSION} 1

echo "[3/8] Installing system dependencies..."
apt-get install -y \
    git \
    curl \
    unzip \
    build-essential \
    libffi-dev \
    libssl-dev

echo "[4/8] Installing AWS CLI v2..."
if ! command -v aws &> /dev/null; then
    curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "/tmp/awscliv2.zip"
    unzip -q /tmp/awscliv2.zip -d /tmp
    /tmp/aws/install
    rm -rf /tmp/aws /tmp/awscliv2.zip
fi
aws --version

echo "[5/8] Creating application directory..."
mkdir -p "$APP_DIR"
mkdir -p "$APP_DIR/Logs"
chown -R $USER:$USER "$APP_DIR"

echo "[6/8] Setting up firewall (UFW)..."
if command -v ufw &> /dev/null; then
    ufw allow ssh
    ufw allow 8000/tcp  # API port
    ufw --force enable
fi

echo "[7/8] Creating log rotation config..."
cat > /etc/logrotate.d/aws-monitor << 'EOF'
/opt/monitor/Logs/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 640 ubuntu ubuntu
    sharedscripts
    postrotate
        systemctl reload aws-monitor > /dev/null 2>&1 || true
    endscript
}
EOF

echo "[8/8] System configuration..."
# Increase file descriptor limits
cat >> /etc/security/limits.conf << 'EOF'
ubuntu soft nofile 65535
ubuntu hard nofile 65535
EOF

# Optimize network settings for monitoring
cat >> /etc/sysctl.conf << 'EOF'
# AWS Monitor optimizations
net.core.somaxconn = 1024
net.ipv4.tcp_max_syn_backlog = 1024
EOF
sysctl -p

echo ""
echo "=========================================="
echo "EC2 Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Clone the repository:"
echo "   cd /opt && sudo git clone <your-repo-url> monitor"
echo ""
echo "2. Create configuration file:"
echo "   sudo cp /opt/monitor/config.example.yaml /opt/monitor/config.yaml"
echo "   sudo nano /opt/monitor/config.yaml"
echo ""
echo "3. Create .env file with API keys:"
echo "   sudo nano /opt/monitor/.env"
echo "   # Add: OPENAI_API_KEY=sk-..."
echo "   # Add: ANTHROPIC_API_KEY=sk-ant-..."
echo ""
echo "4. Configure AWS credentials (if not using IAM role):"
echo "   aws configure"
echo ""
echo "5. Run deployment:"
echo "   sudo /opt/monitor/Scripts/deploy.sh"
echo ""
echo "6. Verify service is running:"
echo "   systemctl status aws-monitor"
echo "   curl http://localhost:8000/health"
echo ""
