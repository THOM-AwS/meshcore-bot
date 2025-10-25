#!/bin/bash
#
# Send a message through Jeff without stopping the bot service.
#
# Usage:
#   ./jeff_say.sh "message"              - Send to #jeff (channel 7)
#   ./jeff_say.sh "message" 0            - Send to Public (channel 0)
#   ./jeff_say.sh "message" 6            - Send to #test (channel 6)
#

if [ $# -lt 1 ]; then
    echo "Usage: $0 <message> [channel]"
    echo ""
    echo "Examples:"
    echo "  $0 'Hello mesh'           - Send to #jeff (channel 7)"
    echo "  $0 'Hello public' 0       - Send to Public"
    echo "  $0 'Testing' 6            - Send to #test"
    exit 1
fi

MESSAGE="$1"
CHANNEL="${2:-7}"  # Default to channel 7 (#jeff)

# Send via HTTP API
response=$(curl -s -X POST http://localhost:8080/send \
    -H "Content-Type: application/json" \
    -d "{\"message\": \"$MESSAGE\", \"channel\": $CHANNEL}")

# Check if successful
if echo "$response" | grep -q '"status":"ok"'; then
    echo "✓ Sent to channel $CHANNEL: $MESSAGE"
else
    echo "✗ Error: $response"
    exit 1
fi
