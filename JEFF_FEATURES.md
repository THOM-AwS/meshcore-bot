# Jeff - MeshCore Bot Features

## Current Status
✅ **LIVE and OPERATIONAL**

Jeff is running on the base server, connected to T-Beam on `/dev/ttyACM0`, monitoring the NSW MeshCore network.

## Core Features

### Sydney-Focused Intelligence
- **Primary search area**: Greater Sydney (-34.5 to -33.0, 150.0 to 151.5)
- **Fallback**: Expands to NSW-wide if no Sydney match found
- **60-minute API cache** with regional pre-filtering (Sydney + NSW caches)
- **Node context**: Passes top 30 Sydney nodes to Claude for spatial awareness

### Follow-Up Conversations
- **5-minute conversation tracking** per sender
- Responds to follow-up questions without requiring @jeff mention
- Maintains conversation context with previous responses
- Auto-expires conversations after timeout

### Dual Logging System
- **`/var/log/jeff.log`**: Chat conversations (incoming + outgoing messages)
- **`/var/log/bot.log`**: System events, errors, status updates
- Minimal journal output (systemd logs only critical events)

### Signal Metrics Capture
- Subscribes to `RX_LOG_DATA` events for RSSI/SNR data
- Captures and stores signal strength for responses
- Used in `ping` and `test` command responses

## Trigger Behavior

### Name Mentions (Any Channel)
Jeff responds when mentioned by name on **any channel**:
- `@jeff` - Direct mention
- `jeff` - Case-insensitive name match
- `#jeff` - Hash tag style

**Example**: Works on Public, #sydney, #test, #rolojnr, #emergency, etc.

### Keywords (Restricted Channels)
Jeff responds to keywords **only on**: #sydney, #test, #rolojnr

Keywords: `test`, `t`, `ping`, `status`, `path`, `nodes`, `help`, `route`, `trace`

## Commands

| Command | Response | Example |
|---------|----------|---------|
| `test` or `t` | Acknowledgement with signal data and path | `ack clerics_father_rolo\|VK2IOL>VK2RGW>VK2HCB\|SNR:7dB\|RSSI:-74dBm\|16:00:52` |
| `ping` | Pong with signal metrics | `pong\|SNR:7dB\|RSSI:-74dBm\|16:00:52` |
| `status` | Online status with Sydney node count | `Online\|nodes in sydney:45` |
| `help` | Command list | `Commands: test,ping,path,status,nodes,route,trace,help \| Or ask me about MeshCore` |
| `path` | Path information | Returns message path details |
| `route` | Routing information | Returns routing details |
| `trace` | Trace information | Returns trace details |
| `nodes` | Node query | Searches Sydney nodes, falls back to NSW |

### Test Command Example
```
User: test
Jeff: ack clerics_father_rolo|VK2IOL>VK2RGW>VK2HCB|SNR:7dB|RSSI:-74dBm|16:00:52
```

Shows:
- Sender acknowledgement
- Full hop path with callsigns
- Signal-to-Noise Ratio
- Received Signal Strength Indicator
- Timestamp

## LLM Integration

### Technical Tone for Experts
System prompt optimized for **highly skilled radio operators and mesh networking experts**:
- NO pleasantries like "How can I help?", "You're absolutely right", "Meshcore is up and running"
- NO greetings, confirmations, or status updates unless asked
- Skip small talk - straight to technical info
- NO filler words like "absolutely", "definitely", "great question"

### Context Provided to Claude
- **Sydney nodes**: Top 30 with name, type, frequency, SF, location
- **Previous response**: If follow-up conversation
- **Recent messages**: Last 5 messages in conversation
- **Message metadata**: SNR, RSSI, path, channel info

### Response Optimization for LoRa
- **Maximum 280 characters** (enforced hard limit)
- **Target: 1 sentence or less**
- Uses abbreviations (vs, msg, comms, etc)
- No markdown or formatting
- Lower temperature (0.5) for concise answers
- Max tokens: 100 (~280 chars)

**Why 280 characters?**
LoRa networks have very limited bandwidth:
- **LoRa SF7**: ~5.47 kbps
- **LoRa SF12**: ~293 bps

280 characters ≈ 280 bytes ≈ **2,240 bits**
- At SF12 (worst case): ~7.6 seconds transmission time
- At SF7 (best case): ~0.4 seconds transmission time

Every byte counts!

## Event Subscriptions

Jeff subscribes to these MeshCore events:

1. **CHANNEL_MSG_RECV** - Channel messages (all channels)
2. **RX_LOG_DATA** - Radio receive logs with RSSI/SNR
3. **PATH_UPDATE** - Routing path updates (logged)
4. **TRACE_DATA** - Message trace information (logged)

## API Integration

### MeshCore Map API
Queries `https://map.meshcore.dev/api/v1/nodes` with:
- **60-minute cache** for efficiency
- **Regional pre-filtering**: Sydney bounds, NSW bounds
- **Hierarchical search**: Sydney first → NSW if no match → global

Node data includes:
- Node name and type (repeater vs node)
- Frequency and spreading factor
- Last heard time
- Geographic coordinates

### AWS Bedrock Model
- **Model**: `us.anthropic.claude-3-5-haiku-20241022-v1:0`
- **Region**: `us-east-1`
- **Profile**: `meshcore-bot`

## Monitoring Jeff

### View Chat Logs
```bash
tail -f /var/log/jeff.log
```

### View System Logs
```bash
tail -f /var/log/bot.log
```

### View Live Systemd Journal
```bash
ssh base "sudo journalctl -u meshcore-bot -f"
```

### Check Service Status
```bash
ssh base "sudo systemctl status meshcore-bot"
```

## Example Interactions

```
# Name mention - any channel
User: @jeff what is meshcore?
Jeff: Lightweight C++ mesh lib, direct comms + learned routing, ultra low power

# Follow-up (no @jeff needed within 5 minutes)
User: how does routing work?
Jeff: Flood first msg, learn path, use direct on reply, fallback to flood if stale

# Test command - allowed channels only
User: test
Jeff: ack clerics_father_rolo|VK2IOL>VK2RGW>VK2HCB|SNR:7dB|RSSI:-74dBm|16:00:52

# Ping command
User: ping
Jeff: pong|SNR:7dB|RSSI:-74dBm|16:00:52

# Status command
User: status
Jeff: Online|nodes in sydney:45

# Help command
User: help
Jeff: Commands: test,ping,path,status,nodes,route,trace,help | Or ask me about MeshCore

# Node query (Sydney-focused)
User: @jeff nodes near Bradbury
Jeff: [Searches Sydney nodes first, returns Bradbury Repeater info]
```

## Configuration

Current settings in `~/jeff/.env`:
```bash
MESHCORE_SERIAL_PORT=/dev/ttyACM0
AWS_PROFILE=meshcore-bot
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=us.anthropic.claude-3-5-haiku-20241022-v1:0
BOT_NAME=Jeff
TRIGGER_WORD=@jeff
```

## Testing Offline

Use `test_jeff.py` for offline testing without mesh network:
```bash
python3 test_jeff.py

# Run automated tests
python3 test_jeff.py --test
```

Supports:
- Interactive CLI mode with `/channel`, `/sender` commands
- Automated test suite
- Simulates realistic message metadata (SNR, RSSI, path)
- Tests all trigger logic and commands

## System Requirements

- Linux server (Raspberry Pi, x86_64, etc.)
- Python 3.10+ (tested with 3.13)
- MeshCore T-Beam or compatible device
- AWS account with Bedrock access
- Internet connection for API calls

## Auto-Start on Boot

Jeff runs as a systemd service and auto-starts on boot:
```bash
sudo systemctl enable meshcore-bot
sudo systemctl start meshcore-bot
```

See [SERVICE_SETUP.md](SERVICE_SETUP.md) for details.
