# Path Implementation Summary

## How Path Data Works

### Path Data Sources
Path hop information in MeshCore messages comes from **RX_LOG_DATA events**, NOT from the high-level CHANNEL_MSG_RECV payload or contact out_path fields.

### Event Flow
1. **RX_LOG_DATA** - Low-level RF event containing:
   - `raw_hex`: Raw packet bytes
   - `payload`: Decoded packet hex string with path bytes
   - `snr`, `rssi`: Signal quality metrics

2. **CHANNEL_MSG_RECV** - High-level decoded message containing:
   - `text`: Message content
   - `path_len`: Number of hops (0-255)
   - `sender_pubkey`, `pubkey_prefix`: Sender identification
   - ❌ NO path hop bytes

### MeshCore Packet Structure
```
Byte 0:        Header (route_type, payload_type, version)
Bytes 1-4:     Transport codes (optional, if route_type 2/3)
Byte N:        Path length
Bytes N+1...:  Path node IDs (1 byte each)
Remaining:     Payload data
```

## Implementation

### 1. RF Data Capture
**Location:** [__init__.py:2752-2777](../meshcore_bot/__init__.py#L2752-2777)

```python
async def on_rx_log_data(event):
    """Capture raw RF data with path information."""
    # Store recent RF data (last 2 seconds)
    rf_data = {
        'timestamp': time.time(),
        'snr': payload.get('snr'),
        'rssi': payload.get('rssi'),
        'raw_hex': payload.get('raw_hex', ''),
        'payload': payload.get('payload', '')
    }
    self.recent_rf_data.append(rf_data)
```

### 2. Packet Decoding
**Location:** [__init__.py:1898-1932](../meshcore_bot/__init__.py#L1898-1932)

```python
def _decode_meshcore_packet_path(self, payload_hex: str) -> Optional[Dict]:
    """Extract path bytes from raw MeshCore packet."""
    header = packet_bytes[0]
    route_type = header & 0x03

    # Skip transport codes if present
    offset = 5 if route_type in [2, 3] else 1

    path_len = packet_bytes[offset]
    path_bytes = packet_bytes[offset+1:offset+1+path_len]
    path_nodes = [f"{b:02x}" for b in path_bytes]

    return {
        'path_len': path_len,
        'path_nodes': path_nodes,
        'path_hex': path_bytes.hex()
    }
```

### 3. Path Correlation
**Location:** [__init__.py:2468-2484](../meshcore_bot/__init__.py#L2468-2484)

When a CHANNEL_MSG_RECV arrives, correlate with most recent RF data:

```python
# Get most recent RF data
if self.recent_rf_data:
    rf_data = self.recent_rf_data[-1]
    decoded = self._decode_meshcore_packet_path(rf_data['payload'])
    if decoded and decoded.get('path_nodes'):
        path_nodes = decoded['path_nodes']
        logger.info(f"📡 Path decoded from RF: {','.join(path_nodes)} ({decoded['path_len']} hops)")
```

## Commands

### Test Command
**Location:** [commands/test_command.py](../meshcore_bot/commands/test_command.py)

Returns ack with hop count from `path_len`:
```
ack NodeName | 3hops | SNR: -17.0 dB | RSSI: -112 dBm | Received at: 12:34:56
```

### Path Command
**Location:** [commands/path_command.py](../meshcore_bot/commands/path_command.py)

Shows full routing path with suburbs and distances:
```
a1:Bob Pyrmont -> 3f:Tower Chatswood (5.2km) -> 43:Repeater North (8.3km) -> Jeff
```

**Implementation:** Uses `path_utils.get_compact_path()` which:
1. Looks up sender contact by pubkey prefix
2. Reads `out_path` field from contact (1 byte per hop)
3. Resolves each hop hash to node name via contact matching
4. Looks up suburb from NSW API nodes
5. Calculates distances between consecutive hops using Haversine formula

### Distance Calculation
**Location:** [features/path_utils.py:398-423](../meshcore_bot/features/path_utils.py#L398-423)

Uses Haversine formula to calculate great-circle distance between lat/lon coordinates.

## Contact Lookup Pattern

### Two-Tier Lookup
**Reference:** [tests/test_two_tier_lookup.py](../tests/test_two_tier_lookup.py)

```python
for key, contact in contacts.items():
    # Try both the 'public_key' field and the key itself
    pubkey = contact.get('public_key', key)

    # Normalize to hex string
    if isinstance(pubkey, bytes):
        pubkey_hex = pubkey.hex()
    else:
        pubkey_hex = pubkey

    if pubkey_hex.startswith(hash_hex):
        # Match found!
```

**Applied in:**
- [__init__.py:1868](../meshcore_bot/__init__.py#L1868) - `_get_node_name_from_hash()`
- [path_utils.py:269](../meshcore_bot/features/path_utils.py#L269) - Contact matching
- [path_discovery.py:53](../meshcore_bot/features/path_discovery.py#L53) - Hash lookup

## Logging Strategy

### Info Level
- Brief event notifications: "📡 Advertisement: NodeName"
- Path decoded from RF: "📡 Path decoded from RF: 43,36,49"
- Contact count changes: "👥 Contacts: 150 cached"
- Important message events

### Debug Level
- Raw event payloads
- Contact data dumps
- Path extraction details
- Payload type analysis
- Advertisement field details

## Key Files

### Core Bot Logic
- [meshcore_bot/__init__.py](../meshcore_bot/__init__.py) - Main bot, event handlers, RF data capture

### Commands
- [commands/test_command.py](../meshcore_bot/commands/test_command.py) - Test/ack with hop count
- [commands/path_command.py](../meshcore_bot/commands/path_command.py) - Full path display
- [commands/ping_command.py](../meshcore_bot/commands/ping_command.py) - Simple ping response

### Features
- [features/path_utils.py](../meshcore_bot/features/path_utils.py) - Path parsing, distance calc, suburb lookup
- [features/path_discovery.py](../meshcore_bot/features/path_discovery.py) - Contact discovery helpers
- [features/scheduler.py](../meshcore_bot/features/scheduler.py) - Scheduled tasks (announcements, etc.)

### Integrations
- [integrations/api.py](../meshcore_bot/integrations/api.py) - NSW/Sydney API, node location data

## Testing

Test scripts available in [tests/](../tests/):
- `test_two_tier_lookup.py` - Contact lookup pattern verification
- `test_path_storage.py` - Path data storage testing
- `test_trace_path.py` - Path tracing functionality
- `show_contacts_with_paths.py` - Display contacts with out_path data

## Discord Integration

Messages mirror to Discord webhook configured in environment:
- `DISCORD_WEBHOOK_URL` - Discord channel webhook
- `DISCORD_CHANNEL_NAME` - Channel name for filtering

**Location:** [__init__.py:2589-2636](../meshcore_bot/__init__.py#L2589-2636)
