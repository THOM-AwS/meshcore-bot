# MeshCore Bot Setup Instructions

This guide will help you set up Jeff, the MeshCore LLM bot, on your Linux server.

## Prerequisites

- Linux server with Python 3.10+ (tested with Python 3.13)
- MeshCore T-Beam device connected via USB
- AWS credentials configured with Bedrock access
- Internet connection for AWS Bedrock API calls

## Installation Steps

### 1. SSH to Your Linux Server

```bash
ssh base
```

### 2. Create Jeff Directory

```bash
mkdir -p ~/jeff
cd ~/jeff
```

### 3. Copy Files to Server

From your local machine, copy the bot files to the server:

```bash
scp meshcore_bot.py base:~/jeff/
scp test_jeff.py base:~/jeff/
scp diagnose_device.py base:~/jeff/
scp requirements.txt base:~/jeff/
scp .env.example base:~/jeff/
```

### 4. Install Python Dependencies

On the server:

```bash
cd ~/jeff
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

This will install:
- `meshcore>=2.1.0` - MeshCore library
- `boto3>=1.34.0` - AWS SDK
- `python-dotenv>=1.0.0` - Environment variable loader
- `requests>=2.31.0` - HTTP client
- `pyserial>=3.5` - Serial port communication

### 5. Find Your MeshCore Device

Find the serial port for your T-Beam:

```bash
# List USB devices
ls -la /dev/ttyUSB* /dev/ttyACM*

# Or use dmesg to see recent USB connections
dmesg | grep -i tty
```

Common ports:
- `/dev/ttyUSB0` - Most common for USB-to-serial adapters
- `/dev/ttyACM0` - Common for devices with built-in USB

**Tip**: Use `diagnose_device.py` to help identify your device:
```bash
python3 diagnose_device.py
```

### 6. Configure Environment Variables

Create your configuration file:

```bash
cp .env.example .env
nano .env
```

Update with your settings:

```bash
# Your serial port
MESHCORE_SERIAL_PORT=/dev/ttyACM0

# AWS profile name (if using named profiles)
AWS_PROFILE=meshcore-bot

# AWS region with Bedrock access
AWS_REGION=us-east-1

# Model ID
BEDROCK_MODEL_ID=us.anthropic.claude-3-5-haiku-20241022-v1:0

# Bot configuration
BOT_NAME=Jeff
TRIGGER_WORD=@jeff
```

### 7. Set Up AWS Credentials

If you haven't already, configure AWS credentials:

```bash
# Install AWS CLI if needed
pip install awscli

# Configure credentials (if not using a profile)
aws configure

# OR use a specific profile
aws configure --profile meshcore-bot
```

Make sure your AWS credentials have access to Bedrock. Test with:

```bash
aws bedrock list-foundation-models --region us-east-1
```

**Required IAM Permissions**:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream"
      ],
      "Resource": "arn:aws:bedrock:*::foundation-model/*"
    }
  ]
}
```

### 8. Set Up Log Files

Create log directories with proper permissions:

```bash
sudo touch /var/log/jeff.log /var/log/bot.log
sudo chown $USER:$USER /var/log/jeff.log /var/log/bot.log
sudo chmod 644 /var/log/jeff.log /var/log/bot.log
```

Jeff uses dual logging:
- **`/var/log/jeff.log`**: Chat conversations (incoming + outgoing messages)
- **`/var/log/bot.log`**: System events, errors, status updates

### 9. Test the Bot

Run the bot manually first to ensure everything works:

```bash
cd ~/jeff
source venv/bin/activate
python3 meshcore_bot.py
```

You should see:
```
============================================================
MeshCore LLM Bot Starting
============================================================
Serial Port: /dev/ttyACM0
...
✓ Bot is now listening for messages (Ctrl+C to stop)
```

### 10. Test from MeshCore Device

From another MeshCore device, send a message:
```
@jeff what is meshcore?
```

Jeff should respond with MeshCore information!

### 11. Test Offline (Optional)

You can test Jeff without a mesh network using the testing interface:

```bash
cd ~/jeff
source venv/bin/activate
python3 test_jeff.py

# Or run automated tests
python3 test_jeff.py --test
```

## Troubleshooting

### Serial Port Permission Denied

If you get "Permission denied" accessing `/dev/ttyUSB0` or `/dev/ttyACM0`:

```bash
# Add your user to dialout group
sudo usermod -a -G dialout $USER

# Log out and back in for changes to take effect
# Or use:
newgrp dialout
```

### MeshCore Library Issues

If the meshcore library isn't found:

```bash
pip install --upgrade meshcore
```

### Python Version Too Old

Jeff requires Python 3.10+. Check your version:

```bash
python3 --version
```

If you need to upgrade:
```bash
# On Debian/Ubuntu
sudo apt update
sudo apt install python3.11

# On macOS with Homebrew
brew install python@3.13
```

### AWS Bedrock Access Issues

1. Verify your credentials are configured:
```bash
aws configure list
```

2. Test Bedrock access:
```bash
aws bedrock list-foundation-models --region us-east-1
```

3. Check IAM permissions (see Step 7 above)

### Bot Not Responding

1. Check that the trigger word is in the message: `@jeff`
2. Check bot logs for errors:
```bash
tail -f /var/log/bot.log
```
3. Verify AWS credentials are working
4. Test serial connection independently using `diagnose_device.py`

### Log Files Not Writing

If log files remain empty:

1. Check file permissions:
```bash
ls -la /var/log/jeff.log /var/log/bot.log
```

2. Ensure your user owns the files:
```bash
sudo chown $USER:$USER /var/log/jeff.log /var/log/bot.log
```

## Running as a Service

See [SERVICE_SETUP.md](SERVICE_SETUP.md) to run Jeff automatically on boot as a systemd service.

## Monitoring

### View Chat Logs
```bash
tail -f /var/log/jeff.log
```

### View System Logs
```bash
tail -f /var/log/bot.log
```

### View Service Logs (if running as systemd service)
```bash
sudo journalctl -u meshcore-bot -f
```

## Next Steps

1. **Run as a service**: See [SERVICE_SETUP.md](SERVICE_SETUP.md)
2. **Learn about features**: See [JEFF_FEATURES.md](JEFF_FEATURES.md)
3. **Understand commands**: See [README.md](README.md)
