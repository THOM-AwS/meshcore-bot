# Discord Integration Setup for Jeff

Jeff supports both one-way and bidirectional Discord integration:

- **One-way** (webhook): MeshCore → Discord only
- **Two-way** (bot): MeshCore ↔ Discord bidirectional mirroring

## Option 1: One-Way Integration (Webhook Only)

This forwards MeshCore messages to Discord but does NOT mirror Discord messages back to MeshCore.

### 1. Create Discord Webhook

1. Open Discord and go to your server
2. Click **Server Settings** (gear icon)
3. Go to **Integrations** → **Webhooks**
4. Click **New Webhook**
5. Configure the webhook:
   - **Name**: Jeff Bot
   - **Channel**: #jeff
   - **Icon**: Optional - upload a bot avatar
6. Click **Copy Webhook URL**

### 2. Configure on Server

SSH into your base server and set up the webhook:

```bash
# Navigate to meshcore directory
cd ~/meshcore

# Create .env.local file (not tracked in git)
nano .env.local
```

Add this content (paste your actual webhook URL):

```bash
# Discord Webhook for Jeff (one-way: MeshCore -> Discord)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN
```

Save and exit (Ctrl+X, Y, Enter)

### 3. Restart Jeff

```bash
sudo systemctl restart meshcore-bot
```

### 4. Verify

Check the logs to ensure Discord integration is working:

```bash
# Watch bot logs
tail -f /var/log/bot.log

# Watch chat logs
tail -f /var/log/jeff.log
```

You should see messages appearing in your Discord #jeff channel when MeshCore messages are received!

---

## Option 2: Bidirectional Integration (Bot + Webhook)

This provides full two-way sync: MeshCore ↔ Discord. Messages from Discord #jeff are forwarded to MeshCore #jeff channel.

### 1. Create Discord Bot

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **New Application**
   - Name: `Jeff MeshCore Bot`
3. Go to **Bot** tab
   - Click **Reset Token** and copy the token (save it securely!)
   - Enable **Message Content Intent** under Privileged Gateway Intents
4. Go to **OAuth2** → **URL Generator**
   - Scopes: `bot`
   - Permissions:
     - Send Messages
     - Read Message History
     - Read Messages/View Channels
5. Copy the generated URL and open it in your browser to invite the bot to your server

### 2. Get Discord Channel ID

1. Enable Developer Mode in Discord:
   - User Settings → Advanced → Developer Mode (toggle on)
2. Right-click the **#jeff** channel
3. Click **Copy Channel ID**
4. Save this ID for the next step

### 3. Configure on Server

SSH into your base server:

```bash
cd ~/meshcore
nano .env.local
```

Add BOTH the webhook URL AND bot credentials:

```bash
# Discord Webhook for Jeff (MeshCore -> Discord)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN

# Discord Bot Token (Discord -> MeshCore)
DISCORD_BOT_TOKEN=YOUR_BOT_TOKEN_HERE

# Discord Channel ID (the #jeff channel)
DISCORD_CHANNEL_ID=YOUR_CHANNEL_ID_HERE
```

Save and exit (Ctrl+X, Y, Enter)

### 4. Install discord.py

```bash
cd ~/meshcore
source venv/bin/activate  # or ~/jeff/venv/bin/activate
pip install discord.py>=2.3.0
```

### 5. Restart Jeff

```bash
sudo systemctl restart meshcore-bot
```

### 6. Verify

Check logs for the Discord bot connection:

```bash
tail -f /var/log/bot.log
```

You should see:
```
🤖 Discord bot connected as Jeff MeshCore Bot#1234
💬 Discord→MeshCore: [Discord] YourName: test message
```

Now messages flow **both ways**:
- MeshCore #jeff → Discord #jeff ✅
- Discord #jeff → MeshCore #jeff ✅

---

## How It Works

- **Only #jeff channel messages** are synced (channel 7)
- Jeff **only responds on #jeff** - confined to his own channel
- **Webhook messages are ignored** by the bot to prevent loops
- **Discord usernames** are prefixed with `[Discord]` when forwarded to MeshCore
- **Message format** (MeshCore→Discord) includes:
  - Sender name
  - Original message text
  - Channel name (#jeff)
  - Bot response (if any)
  - Timestamp

## Adding #jeff Channel to Your Device

To use Jeff, you need to add the #jeff channel (index 7) to your MeshCore device:

**Via Web/Mobile App:**
1. Connect to your device
2. Go to Channels
3. Add new channel:
   - **Name**: `#jeff`
   - **Index**: 7
   - **Secret**: `[generate or request shared secret]`

**Via Serial/CLI:**
```bash
add-channel 7 #jeff [your-secret-key]
save
```

## Disable Discord Integration

To disable, simply remove or comment out the `DISCORD_WEBHOOK_URL` line in `.env.local` and restart Jeff.

## Security Notes

- `.env.local` is **NOT** committed to git (listed in .gitignore)
- The webhook URL should be kept secret
- Anyone with the webhook URL can post to your Discord channel
- You can regenerate the webhook URL in Discord if it's compromised

## Troubleshooting

**No messages appearing in Discord?**
```bash
# Check if .env.local exists and has webhook URL
cat ~/jeff/.env.local

# Check Jeff is reading the file
sudo journalctl -u meshcore-bot -n 50

# Check Discord webhook is valid
curl -X POST YOUR_WEBHOOK_URL \
  -H "Content-Type: application/json" \
  -d '{"content": "Test from Jeff"}'
```

**Messages delayed?**
- This is normal - Discord webhooks are sent asynchronously with 5s timeout
- If Discord is slow/down, Jeff will continue operating normally
