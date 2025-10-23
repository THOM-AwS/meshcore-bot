# MeshCore Bot - Jeff

An intelligent LLM-powered bot for MeshCore mesh networks using AWS Bedrock Claude 3.5 Haiku.

## Project Status

✅ **FULLY OPERATIONAL!**

Jeff is running as a systemd daemon on the base server, actively monitoring the NSW MeshCore network.

## Features

### Smart Triggering
- **Name mentions**: Responds to `@jeff`, `#jeff`, or `jeff` on ANY channel
- **Keywords**: Responds to `test`, `ping`, `path`, `status`, `nodes`, `help`, `route`, `trace` on allowed channels (sydney, test, rolojnr)
- **Node questions**: Automatically detects queries about specific nodes/repeaters
- **Follow-ups**: Maintains 5-minute conversation context - no need to mention @jeff for every message

### Commands

| Command | Response | Example |
|---------|----------|---------|
| `test` or `t` | Ack with SNR, RSSI, path, timestamp | `ack Tom \| 2 \| SNR: 7.0 dB \| RSSI: -74 dBm \| Received at: 16:00:52` |
| `ping` | Pong with signal data | `pong\|SNR:7dB\|RSSI:-74dBm\|16:00:52` |
| `status` | Online status + Sydney node count | `Online\|nodes in sydney:45` |
| `path` | Path details | `Path: 2 hops \| SNR: 7.0 dB \| 16:00:52` |
| `help` | Shows available commands | `Commands: test,ping,path,status,nodes,route,trace,help \| Or ask me about MeshCore` |
| `@jeff [question]` | Technical answer | Direct, concise responses about MeshCore |

### Node Lookup
Ask about any node/repeater:
- "who owns bradbury repeater?"
- "what frequency is cleric node?"
- "where is BEES?"

Returns: `Bradbury Repeater ☢(RPT)\|-34.09,150.81\|915.8MHz\|SF11\|BW250`

**Search hierarchy**: Sydney first → NSW if no match → Returns "No match" if not found

### Intelligent Features
- **Sydney-focused**: Searches Greater Sydney nodes first (primary coverage area)
- **Cached API**: 60-minute cache of network nodes (reduces API load)
- **Context-aware**: Passes Sydney node data + conversation history to Claude
- **Technical tone**: Assumes expert-level knowledge, no pleasantries
- **Bandwidth-optimized**: Max 280 characters per response
- **Dual logging**:
  - `/var/log/jeff.log` - Chat conversations
  - `/var/log/bot.log` - System logs
  - Minimal journal output (errors only)

### Technical Details
- **MeshCore library**: v2.1+ with BLE, Serial, TCP support
- **LLM**: AWS Bedrock Claude 3.5 Haiku (fast, cost-effective)
- **API**: MeshCore Map API (https://map.meshcore.dev/api/v1/nodes)
- **Regions**: Greater Sydney (-34.5 to -33.0, 150.0 to 151.5) + NSW fallback
- **Channels**: Responds on sydney(1), rolojnr(5), test(6) for keywords; any channel for name mentions

## Files

- **`meshcore_bot.py`** - Main bot application
- **`test_jeff.py`** - Offline testing interface
- **`requirements.txt`** - Python dependencies
- **`.env.example`** - Configuration template
- **`meshcore-bot.service`** - Systemd service file
- **`SETUP.md`** - Detailed setup instructions
- **`SERVICE_SETUP.md`** - Systemd service configuration
- **`JEFF_FEATURES.md`** - Complete feature documentation

## Quick Start

### Configuration
Copy `.env.example` to `.env` and configure:

```bash
MESHCORE_SERIAL_PORT=/dev/ttyACM0
AWS_PROFILE=meshcore-bot
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=us.anthropic.claude-3-5-haiku-20241022-v1:0
BOT_NAME=Jeff
TRIGGER_WORD=@jeff
```

### Installation
```bash
# Install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run bot
python3 meshcore_bot.py
```

### Testing (Offline)
```bash
# Interactive mode
python3 test_jeff.py

# Automated test suite
python3 test_jeff.py --test
```

## Managing Jeff (Production)

### Check Status
```bash
ssh base "sudo systemctl status meshcore-bot"
```

### View Logs
```bash
# Chat logs
ssh base "tail -f /var/log/jeff.log"

# System logs
ssh base "tail -f /var/log/bot.log"

# Journal (errors only)
ssh base "sudo journalctl -u meshcore-bot -f"
```

### Control Service
```bash
# Restart
ssh base "sudo systemctl restart meshcore-bot"

# Stop
ssh base "sudo systemctl stop meshcore-bot"

# Start
ssh base "sudo systemctl start meshcore-bot"

# Disable auto-start
ssh base "sudo systemctl disable meshcore-bot"
```

### Update Jeff
```bash
# Deploy new version
scp meshcore_bot.py base:~/jeff/
ssh base "sudo systemctl restart meshcore-bot"
```

## AWS Setup

### IAM User
- **User**: `meshcore-bot`
- **Access Key**: AKIAXEPC336FGNI7OOPK
- **Region**: us-east-1
- **Permissions**: Bedrock inference access

### Credentials
Stored in `~/.aws/credentials` on base server:
```ini
[meshcore-bot]
aws_access_key_id = AKIAXEPC336FGNI7OOPK
aws_secret_access_key = [your-secret-key]
region = us-east-1
```

## Architecture

### Message Flow
1. MeshCore radio receives message → Serial/BLE → meshcore library
2. Event fired (`CHANNEL_MSG_RECV` or `CONTACT_MSG_RECV`)
3. Jeff checks triggers (name mention / keywords / follow-up)
4. For commands (test/ping/status): Direct response
5. For node queries: API lookup → Direct response
6. For questions: Claude Haiku with context → Response
7. Response sent back to radio → Transmitted on network

### Context Passed to Claude
- **Sydney nodes**: Top 30 nodes with name, type, freq, SF, location
- **Previous conversation**: Last response to this user (if follow-up)
- **Recent history**: Last 5 messages on network
- **Message metadata**: SNR, RSSI, path hops, channel

### Caching Strategy
- **60-minute TTL**: Network topology doesn't change frequently
- **Regional caches**: Separate caches for Sydney vs NSW
- **Stale fallback**: Returns old cache if API fails

## Troubleshooting

### Jeff not responding?
```bash
# Check service status
ssh base "sudo systemctl status meshcore-bot"

# Check logs for errors
ssh base "sudo journalctl -u meshcore-bot -n 100"

# Check serial connection
ssh base "ls -la /dev/ttyACM0"

# Restart service
ssh base "sudo systemctl restart meshcore-bot"
```

### Testing AWS Bedrock
```bash
ssh base "cd ~/jeff && source venv/bin/activate && python3 test_bedrock.py"
```

### Testing Offline
```bash
cd /path/to/meshcore
source venv/bin/activate
python3 test_jeff.py
```

## Development

### Code Style
- Python 3.10+
- Type hints where applicable
- Docstrings for public methods
- Async/await for I/O operations

### Key Classes
- **`MeshCoreAPI`**: API client with regional filtering and caching
- **`MeshCoreBot`**: Main bot logic, message processing, LLM integration

### Adding Features
1. Update `meshcore_bot.py`
2. Test with `test_jeff.py`
3. Deploy to base server
4. Update documentation

## License

[Your License Here]

## Credits

- **MeshCore**: https://meshcore.nz
- **AWS Bedrock**: Claude 3.5 Haiku by Anthropic
- **meshcore Python library**: https://github.com/liamcottle/meshcore-python
