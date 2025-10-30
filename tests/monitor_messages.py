#!/usr/bin/env python3
"""Monitor incoming messages to see path_len data."""
import asyncio
from meshcore import MeshCore, EventType

async def monitor_messages():
    """Monitor messages and dump path data."""

    print("Connecting to /dev/ttyACM0...")
    meshcore = await MeshCore.create_serial("/dev/ttyACM0")
    print("✓ Connected! Monitoring messages...\n")
    print("=" * 80)

    async def handle_message(event):
        """Handle incoming messages."""
        if hasattr(event, 'payload'):
            msg = event.payload

            sender = msg.get('sender_pubkey', 'Unknown')[:16]
            text = msg.get('text', '(no text)')
            path_len = msg.get('path_len', 'N/A')
            snr = msg.get('SNR', 'N/A')
            rssi = msg.get('RSSI', 'N/A')

            print(f"\n📨 MESSAGE:")
            print(f"   From: {sender}...")
            print(f"   Text: {text[:50]}")
            print(f"   path_len: {path_len}")
            print(f"   SNR: {snr} dB | RSSI: {rssi} dBm")
            print(f"   Full payload: {msg}")
            print("-" * 80)

    async def handle_path_update(event):
        """Handle path update events."""
        if hasattr(event, 'payload'):
            path_data = event.payload
            print(f"\n🛤️  PATH UPDATE:")
            print(f"   Full payload: {path_data}")
            print("-" * 80)

    # Subscribe to message and path events
    meshcore.subscribe(EventType.CHANNEL_MSG_RECV, handle_message)
    meshcore.subscribe(EventType.CONTACT_MSG_RECV, handle_message)
    meshcore.subscribe(EventType.PATH_UPDATE, handle_path_update)

    # Keep running
    print("Waiting for messages... (Ctrl+C to stop)")
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")

if __name__ == "__main__":
    asyncio.run(monitor_messages())
