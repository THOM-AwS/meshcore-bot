#!/usr/bin/env python3
"""Inline test of path discovery - run on base."""
import asyncio
import sys
sys.path.insert(0, '/home/tom/jeff')

from meshcore import MeshCore, EventType
from meshcore_bot.features.path_discovery import PathDiscovery


async def test():
    print("="*60)
    print("INLINE PATH DISCOVERY TEST")
    print("="*60)

    # Connect
    print("\n1. Connecting to device...")
    mc = await MeshCore.create_serial('/dev/ttyACM0')
    print("   ✓ Connected")

    # Get contacts
    print("\n2. Getting contacts...")
    result = await mc.commands.get_contacts()
    print(f"   Result type: {result.type}")
    if result.type == EventType.ERROR:
        print(f"   ❌ ERROR: {result.payload}")
        return
    print(f"   ✓ Got {len(mc.contacts)} contacts")

    # Initialize PathDiscovery
    print("\n3. Initializing PathDiscovery...")
    pd = PathDiscovery(mc)
    print("   ✓ Initialized")

    # Test discovery
    target = "Cherrybrook"
    print(f"\n4. Discovering path to {target}...")

    # Enable debug logging
    import logging
    logging.basicConfig(level=logging.DEBUG)

    try:
        result = await pd.discover_path_to_contact(target, timeout=30.0)

        print("\n" + "="*60)
        print("RESULT:")
        print("="*60)
        print(result)
        print("="*60)

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

    # Disconnect
    print("\n5. Disconnecting...")
    await mc.disconnect()
    print("   ✓ Done")


if __name__ == "__main__":
    asyncio.run(test())
