#!/usr/bin/env python3
"""
Direct path discovery test - run on base with bot stopped.

Usage:
    python3 test_discover_direct.py "Father ROLO"
    python3 test_discover_direct.py Cherrybrook
    python3 test_discover_direct.py "Tower Chatswood"
"""
import asyncio
import sys
sys.path.insert(0, '/home/tom/jeff')

from meshcore import MeshCore, EventType
from meshcore_bot.features.path_discovery import PathDiscovery


async def test_discovery(target_name: str):
    """Test path discovery for a specific node."""
    print("="*70)
    print(f"PATH DISCOVERY TEST: {target_name}")
    print("="*70)

    # Connect
    print("\n1. Connecting to /dev/ttyACM0...")
    mc = await MeshCore.create_serial('/dev/ttyACM0')
    print("   ✓ Connected")

    # Get contacts
    print("\n2. Getting contacts...")
    result = await mc.commands.get_contacts()
    print(f"   ✓ Got {len(mc.contacts)} contacts")

    # Show if target exists and has current path
    print(f"\n3. Looking for '{target_name}'...")
    target = None
    for pk, c in mc.contacts.items():
        if target_name.lower() in c.get('adv_name', '').lower():
            target = c
            name = c.get('adv_name')
            out_path_len = c.get('out_path_len', -1)
            out_path = c.get('out_path', b'')

            print(f"   ✓ Found: {name}")
            print(f"   Public key: {pk[:16]}...")
            print(f"   Current out_path_len: {out_path_len}")

            if out_path_len > 0:
                print(f"   Current out_path: {out_path.hex() if out_path else 'empty'}")
                # Parse existing hops
                if out_path:
                    hops = [f"{b:02x}" for b in out_path[:out_path_len]]
                    print(f"   Current hops: {' -> '.join(hops)}")
            elif out_path_len == 0:
                print(f"   Status: Direct connection (0 hops)")
            else:
                print(f"   Status: No path (uses flood mode)")
            break

    if not target:
        print(f"   ❌ '{target_name}' not found in contacts")
        await mc.disconnect()
        return

    # Initialize PathDiscovery
    print(f"\n4. Initializing PathDiscovery...")
    pd = PathDiscovery(mc)
    print("   ✓ Initialized")

    # Run discovery
    print(f"\n5. Running path discovery (30s timeout)...")
    print("   📤 Sending CMD_SEND_PATH_DISCOVERY_REQ (0x34)...")

    result = await pd.discover_path_to_contact(target_name, timeout=30.0)

    # Show results
    print("\n" + "="*70)
    print("RESULTS:")
    print("="*70)

    if result.get('success'):
        print("✅ SUCCESS!")
        print(f"\nContact: {result.get('contact_name')}")
        print(f"Old path length: {result.get('old_path_len', 'N/A')}")
        print(f"New path length: {result.get('out_path_len', 0)}")

        out_hops = result.get('out_path_hops', [])
        in_hops = result.get('in_path_hops', [])

        if out_hops:
            print(f"\nOutbound path (TO {target_name}):")
            print(f"  Hops: {' -> '.join(out_hops)}")

            # Try to resolve names
            print(f"  Resolving node names...")
            for hop in out_hops:
                name = await pd.get_node_name_from_hash(hop, mc.contacts)
                print(f"    {hop} = {name}")

        if in_hops:
            print(f"\nInbound path (FROM {target_name}):")
            print(f"  Hops: {' -> '.join(in_hops)}")

            print(f"  Resolving node names...")
            for hop in in_hops:
                name = await pd.get_node_name_from_hash(hop, mc.contacts)
                print(f"    {hop} = {name}")

        mode = result.get('mode', 'unknown')
        if mode:
            print(f"\nRouting mode: {mode}")

    else:
        print("❌ FAILED")
        error = result.get('error', 'Unknown error')
        print(f"Error: {error}")
        print(f"Old path length: {result.get('old_path_len', 'N/A')}")

    print("="*70)

    # Disconnect
    print("\n6. Disconnecting...")
    await mc.disconnect()
    print("   ✓ Done\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 test_discover_direct.py <node_name>")
        print("\nExamples:")
        print('  python3 test_discover_direct.py "Father ROLO"')
        print('  python3 test_discover_direct.py Cherrybrook')
        print('  python3 test_discover_direct.py "Tower Chatswood"')
        sys.exit(1)

    target_name = sys.argv[1]
    asyncio.run(test_discovery(target_name))
