# Jeff HTTP API Documentation

Jeff now includes an HTTP API that allows you to send messages without interrupting the bot service.

## Endpoints

### POST /send
Send a message to the mesh network.

**Request:**
```bash
curl -X POST http://localhost:8080/send \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello mesh", "channel": 7}'
```

**Parameters:**
- `message` (required): The message text to send
- `channel` (optional): Channel number (default: 7 for #jeff)

**Response:**
```json
{
  "status": "ok",
  "message": "Hello mesh",
  "channel": 7
}
```

### GET /status
Get bot status and channel information.

**Request:**
```bash
curl http://localhost:8080/status
```

**Response:**
```json
{
  "status": "ok",
  "bot_name": "Jeff",
  "connected": true,
  "channels": {
    "0": "Public",
    "1": "#sydney",
    "2": "#nsw",
    ...
  }
}
```

### GET /health
Health check endpoint.

**Request:**
```bash
curl http://localhost:8080/health
```

**Response:**
```json
{
  "status": "healthy"
}
```

## Helper Script

Use `jeff_say.sh` for easy message sending:

```bash
# Send to #jeff (default)
./jeff_say.sh "Hello mesh"

# Send to Public channel
./jeff_say.sh "Hello public" 0

# Send to #test channel
./jeff_say.sh "Testing" 6
```

## Configuration

Set these environment variables in `.env` or `.env.local`:

```bash
# Enable/disable API (default: true)
API_ENABLED=true

# API host (default: localhost - only local access)
API_HOST=localhost

# API port (default: 8080)
API_PORT=8080
```

## Security

- The API binds to `localhost` by default (local access only)
- No authentication - assumes trusted local environment
- To expose remotely, change `API_HOST` and add reverse proxy with auth

## Examples

### Send status update
```bash
./jeff_say.sh "Jeff is online and ready" 7
```

### Broadcast to public
```bash
./jeff_say.sh "MeshCore bot testing" 0
```

### Via curl with error handling
```bash
response=$(curl -s -X POST http://localhost:8080/send \
  -H "Content-Type: application/json" \
  -d '{"message": "test", "channel": 7}')

if echo "$response" | grep -q '"status":"ok"'; then
  echo "✓ Message sent"
else
  echo "✗ Error: $response"
fi
```
