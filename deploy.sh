#!/bin/bash
# Deployment script for MeshCore bot to base server

set -e

REMOTE_USER="base"
REMOTE_DIR="jeff"

echo "============================================================"
echo "MeshCore Bot Deployment Script"
echo "============================================================"

# Step 1: Create remote directory
echo ""
echo "Step 1: Creating remote directory ~/jeff on base server..."
echo "----------------------------------------"
ssh base "mkdir -p ~/${REMOTE_DIR}"

# Step 2: Copy files
echo ""
echo "Step 2: Copying bot files to base server..."
echo "----------------------------------------"
scp meshcore_bot.py base:~/${REMOTE_DIR}/
scp test_jeff.py base:~/${REMOTE_DIR}/
scp diagnose_device.py base:~/${REMOTE_DIR}/
scp requirements.txt base:~/${REMOTE_DIR}/
scp .env.example base:~/${REMOTE_DIR}/.env
scp meshcore-bot.service base:~/${REMOTE_DIR}/
scp SETUP.md base:~/${REMOTE_DIR}/
scp SERVICE_SETUP.md base:~/${REMOTE_DIR}/
scp JEFF_FEATURES.md base:~/${REMOTE_DIR}/
scp README.md base:~/${REMOTE_DIR}/

# Step 3: Install dependencies
echo ""
echo "Step 3: Installing Python dependencies on base server..."
echo "----------------------------------------"
ssh base << 'ENDSSH'
cd ~/jeff
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
ENDSSH

# Step 4: Find serial port and configure
echo ""
echo "Step 4: Finding MeshCore device and configuring..."
echo "----------------------------------------"
SERIAL_PORT=$(ssh base "ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null | head -1" || echo "/dev/ttyUSB0")
echo "Detected serial port: $SERIAL_PORT"

ssh base "sed -i 's|MESHCORE_SERIAL_PORT=.*|MESHCORE_SERIAL_PORT=${SERIAL_PORT}|' ~/jeff/.env"
ssh base "sed -i 's|AWS_PROFILE=.*|AWS_PROFILE=meshcore-bot|' ~/jeff/.env"

# Step 5: Set up log files
echo ""
echo "Step 5: Setting up log files..."
echo "----------------------------------------"
ssh base << 'ENDSSH'
sudo touch /var/log/jeff.log /var/log/bot.log
sudo chown $USER:$USER /var/log/jeff.log /var/log/bot.log
sudo chmod 644 /var/log/jeff.log /var/log/bot.log
ENDSSH

echo ""
echo "============================================================"
echo "Deployment Complete!"
echo "============================================================"
echo ""
echo "Next steps:"
echo ""
echo "1. SSH to base server:"
echo "   ssh base"
echo ""
echo "2. Test the bot manually:"
echo "   cd ~/jeff"
echo "   source venv/bin/activate"
echo "   python3 meshcore_bot.py"
echo ""
echo "3. Set up as a service (optional):"
echo "   See ~/jeff/SERVICE_SETUP.md"
echo ""
