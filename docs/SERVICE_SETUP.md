# Setting Up MeshCore Bot as a System Service

This will configure Jeff to run automatically on boot and restart if it crashes.

## Installation

### 1. Edit the Service File

First, update the service file with your username:

```bash
cd ~/jeff
nano meshcore-bot.service
```

Replace `YOUR_USERNAME` with your actual username (use `whoami` to check):

```
User=your_actual_username
WorkingDirectory=/home/your_actual_username/jeff
Environment="PATH=/home/your_actual_username/jeff/venv/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=/home/your_actual_username/jeff/.env
ExecStart=/home/your_actual_username/jeff/venv/bin/python3 /home/your_actual_username/jeff/meshcore_bot.py
```

### 2. Copy Service File

```bash
sudo cp meshcore-bot.service /etc/systemd/system/
```

### 3. Reload Systemd

```bash
sudo systemctl daemon-reload
```

### 4. Enable the Service

This makes the bot start automatically on boot:

```bash
sudo systemctl enable meshcore-bot
```

### 5. Start the Service

```bash
sudo systemctl start meshcore-bot
```

## Managing the Service

### Check Status

```bash
sudo systemctl status meshcore-bot
```

### View Logs

```bash
# View recent logs
sudo journalctl -u meshcore-bot -n 50

# Follow logs in real-time
sudo journalctl -u meshcore-bot -f

# View logs since last boot
sudo journalctl -u meshcore-bot -b
```

### Stop the Service

```bash
sudo systemctl stop meshcore-bot
```

### Restart the Service

```bash
sudo systemctl restart meshcore-bot
```

### Disable Auto-Start

```bash
sudo systemctl disable meshcore-bot
```

## Updating the Bot

When you update the bot code:

1. Pull new changes or copy new files
2. Restart the service:

```bash
cd ~/jeff
git pull  # if using git
# OR copy new files
sudo systemctl restart meshcore-bot
```

## Troubleshooting

### Service Won't Start

Check the logs:
```bash
sudo journalctl -u meshcore-bot -n 100 --no-pager
```

Common issues:
- Wrong paths in service file
- Missing environment variables
- Serial port permissions

### Serial Port Permissions

Make sure your user is in the `dialout` group:

```bash
sudo usermod -a -G dialout $USER
sudo systemctl restart meshcore-bot
```

### Environment Variables Not Loading

Verify `.env` file exists and is readable:

```bash
ls -la ~/jeff/.env
cat ~/jeff/.env
```

### AWS Credentials Issues

If using AWS profiles, ensure the service can access the credentials:

```bash
# The service runs as your user, so credentials should be at:
ls -la ~/.aws/credentials
```

## Advanced Configuration

### Custom Log File

To log to a file instead of journald, modify the service:

```ini
[Service]
StandardOutput=append:/home/YOUR_USERNAME/jeff/jeff.log
StandardError=append:/home/YOUR_USERNAME/jeff/jeff-error.log
```

Then reload and restart:
```bash
sudo systemctl daemon-reload
sudo systemctl restart meshcore-bot
```

### Resource Limits

Add to `[Service]` section if needed:

```ini
# Limit memory to 512MB
MemoryMax=512M

# Limit CPU usage
CPUQuota=50%
```
