# MeshCore Bot - Jeff

An intelligent LLM-powered bot for MeshCore mesh networks using AWS Bedrock Claude 3.5 Haiku.

## Project Status

✅ **FULLY OPERATIONAL!**

Jeff is running as a systemd daemon on the base server, actively monitoring the NSW MeshCore network.

## Features

### Smart Triggering
- **Channels**: Jeff responds on **#jeff** (channel 7) and **#test** (channel 6)
- **Keywords**: Responds to `test`, `ping`, `path`, `status`, `nodes`, `help`, `route`, `trace`
- **Node questions**: Automatically detects queries about specific nodes/repeaters
- **Follow-ups**: Maintains 5-minute conversation context
- **Discord Bridge**: Bidirectional sync - Discord ↔ MeshCore #jeff channel
- **HTTP API**: Send messages without interrupting bot service (localhost:8080)

### Commands

| Command | Response | Example |
|---------|----------|---------|
| `test` or `t` | Ack with SNR, RSSI, path, timestamp | `ack Tom \| 2 \| SNR: 7.0 dB \| RSSI: -74 dBm \| Received at: 16:00:52` |
| `ping` | Pong with signal data | `pong\|SNR:7dB\|RSSI:-74dBm\|16:00:52` |
| `status` | Online status + node counts | `Online \| Sydney 8 companions / 7 repeaters \| NSW 14 companions / 46 repeaters (7d)` |
| `path` | Path details with suburbs | `a1:Bob Pyrmont -> 3f:Tower Chatswood -> YOU` |
| `help` | Shows available commands | `Commands: test,ping,path,status,nodes,route,trace,help \| Or ask me about MeshCore` |
| `@jeff what can you do?` | Capabilities question | `Say 'jeff help' for more info` |
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
- **Channels**: #jeff (channel 7) only - Discord bridged
- **Discord**: Webhook integration for message mirroring (see [DISCORD_SETUP.md](DISCORD_SETUP.md))

## Project Structure

```
meshcore/
├── main.py                    # Entry point with HTTP API
├── meshcore_bot/              # Modular architecture
│   ├── config/                # Configuration management
│   │   └── settings.py
│   ├── integrations/          # External services
│   │   ├── api.py            # HTTP API server
│   │   ├── discord_sync.py   # Discord bidirectional sync
│   │   ├── llm_client.py     # AWS Bedrock Claude client
│   │   └── meshcore_api.py   # MeshCore Map API client
│   ├── messaging/             # Message handling
│   │   ├── sender.py         # Unified message sender
│   │   └── types.py          # Message types
│   ├── commands/              # Command pattern
│   │   ├── base.py           # Command registry
│   │   ├── test_command.py   # Test/ack command
│   │   ├── ping_command.py   # Ping/pong command
│   │   ├── status_command.py # Network status
│   │   ├── path_command.py   # Path display
│   │   └── help_command.py   # Help command
│   ├── features/              # Bot features
│   │   ├── path_utils.py     # Routing path utilities
│   │   └── scheduler.py      # Broadcast scheduler
│   └── utils/                 # Utilities
│       └── logging.py        # Logging setup
├── jeff_say.sh                # Helper script for HTTP API
├── requirements.txt           # Python dependencies
├── meshcore-bot.service       # Systemd service
└── docs/                      # Documentation
    ├── API.md                 # HTTP API reference
    ├── SETUP.md               # Setup guide
    ├── SERVICE_SETUP.md       # Systemd configuration
    ├── DISCORD_SETUP.md       # Discord integration
    ├── JEFF_FEATURES.md       # Feature documentation
    └── JEFF_CHANNEL_CONFIG.md # Channel configuration
```

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
python3 main.py
```

## Managing Jeff (Production)

### Send Messages (Without Interrupting Bot)
```bash
# Send to #jeff channel (default)
ssh base "cd ~/jeff && ./jeff_say.sh 'Your message here'"

# Send to specific channel
ssh base "cd ~/jeff && ./jeff_say.sh 'Hello public' 0"
ssh base "cd ~/jeff && ./jeff_say.sh 'Testing' 6"

# Via HTTP API directly
ssh base "curl -X POST http://localhost:8080/send -H 'Content-Type: application/json' -d '{\"message\": \"Hello\", \"channel\": 7}'"

# Check bot status
ssh base "curl http://localhost:8080/status"
```

See [docs/API.md](docs/API.md) for full HTTP API documentation.

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
scp -r meshcore_bot main.py jeff_say.sh requirements.txt base:~/jeff/
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
