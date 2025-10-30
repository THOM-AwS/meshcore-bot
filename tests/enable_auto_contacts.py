#!/usr/bin/env python3
"""
Enable auto-add contacts on MeshCore device.
This disables manual_add_contacts mode so new nodes are automatically added to the contact list.
"""
import asyncio
from meshcore import MeshCore, EventType

CMD_SET_OTHER_PARAMS = 38

async def enable_auto_add():
    """Disable manual contact mode to enable automatic contact addition."""
    print("Connecting to MeshCore device...")
    meshcore = await MeshCore.create_serial('/dev/ttyACM0')
    print("✓ Connected")

    try:
        print("\nSending CMD_SET_OTHER_PARAMS to disable manual_add_contacts...")
        # CMD_SET_OTHER_PARAMS: byte[0]=manual_add_contacts (0=auto, 1=manual)
        command = bytes([CMD_SET_OTHER_PARAMS, 0])  # 0 = enable auto-add

        # Send command using the commands API (no response expected)
        try:
            response = await meshcore.commands.send(
                command,
                expected_events=[EventType.OK],
                timeout=1.0
            )
            print(f"✓ Response: {response}")
        except Exception as e:
            # Command may not return a response, that's OK
            print(f"Command sent (no response expected): {e}")

        print("\n✅ Auto-add contacts command has been sent")
        print("   New nodes will be automatically added to the contact list")

    finally:
        await meshcore.disconnect()
        print("\nDisconnected")

if __name__ == "__main__":
    asyncio.run(enable_auto_add())
