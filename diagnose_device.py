#!/usr/bin/env python3
"""
Diagnostic script to check MeshCore device status and configuration
"""

import asyncio
from meshcore import MeshCore, EventType


async def diagnose():
    """Run diagnostics on the MeshCore device."""

    print("="*60)
    print("MeshCore Device Diagnostics")
    print("="*60)

    try:
        # Connect to device
        print("\n1. Connecting to /dev/ttyACM0...")
        meshcore = await MeshCore.create_serial('/dev/ttyACM0')
        print("   ✓ Connected")

        # Get device info
        print("\n2. Getting device information...")
        if meshcore.self_info:
            print(f"   Device info: {meshcore.self_info}")
        else:
            print("   ⚠ No self_info available")

        # Get contacts
        print("\n3. Getting contacts (other nodes visible)...")
        await meshcore.ensure_contacts()
        contacts = meshcore.contacts
        print(f"   Found {len(contacts)} contacts:")
        for contact in contacts:
            print(f"     - {contact}")

        # Check for messages
        print("\n4. Checking for messages...")
        result = await meshcore.commands.get_msg()
        print(f"   Result: {result}")

        # Try to get more messages
        msg_count = 0
        while msg_count < 10:
            result = await meshcore.commands.get_msg()
            if result.type == EventType.NO_MORE_MSGS or result.type == EventType.ERROR:
                print(f"   No more messages (checked {msg_count} times)")
                break
            else:
                print(f"   Message {msg_count + 1}: {result}")
                msg_count += 1

        print("\n5. Device Status:")
        print(f"   Connected: {meshcore.is_connected}")
        print(f"   Contacts: {len(meshcore.contacts)}")
        print(f"   Pending contacts: {len(meshcore.pending_contacts)}")

        # Disconnect
        await meshcore.disconnect()
        print("\n✓ Diagnostics complete")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(diagnose())
