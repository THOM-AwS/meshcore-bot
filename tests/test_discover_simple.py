#!/usr/bin/env python3
"""Simple test for path discovery without bot dependencies."""
import asyncio
import sys
from meshcore import MeshCore, EventType


async def test_discovery(contact_name: str):
    """Test CMD_SEND_PATH_DISCOVERY_REQ directly."""
    print(f"╔═══════════════════════════════════════════╗")
    print(f"║  Path Discovery Test (Simple)             ║")
    print(f"╚═══════════════════════════════════════════╝\n")

    # Connect
    print("📡 Connecting to /dev/ttyACM0...")
    meshcore = await asyncio.wait_for(
        MeshCore.create_serial('/dev/ttyACM0'),
        timeout=10
    )
    print("✓ Connected\n")

    # Get contacts
    print("📋 Fetching contacts...")
    contacts_result = await asyncio.wait_for(
        meshcore.commands.get_contacts(),
        timeout=10
    )
    print(f"✓ {len(meshcore.contacts)} contacts\n")

    # Find contact
    target_contact = None
    for pubkey, contact in meshcore.contacts.items():
        if contact_name.lower() in contact.get('adv_name', '').lower():
            target_contact = contact
            break

    if not target_contact:
        print(f"❌ Contact '{contact_name}' not found")
        await meshcore.disconnect()
        return

    pubkey = target_contact.get('public_key', '')
    name = target_contact.get('adv_name', '')
    print(f"📍 Found: {name}")
    print(f"   Public key: {pubkey[:16]}...")
    print(f"   Current out_path_len: {target_contact.get('out_path_len', -1)}\n")

    # Send path discovery request
    CMD_SEND_PATH_DISCOVERY_REQ = 0x34
    pubkey_bytes = bytes.fromhex(pubkey[:64])
    cmd_frame = bytearray([CMD_SEND_PATH_DISCOVERY_REQ, 0x00])
    cmd_frame.extend(pubkey_bytes)

    print(f"📤 Sending CMD_SEND_PATH_DISCOVERY_REQ (0x34)...")
    print(f"   Command: {cmd_frame[:10].hex()}... ({len(cmd_frame)} bytes)")

    try:
        response = await meshcore.commands.send(
            bytes(cmd_frame),
            expected_events=[EventType.PATH_RESPONSE, EventType.ERROR],
            timeout=30.0
        )

        print(f"\n📥 Response received!")
        print(f"   Type: {response.type}")
        print(f"   Payload: {response.payload}\n")

        if response.type == EventType.PATH_RESPONSE:
            payload = response.payload

            out_path_len = payload.get('out_path_len', 0)
            out_path_hex = payload.get('out_path', '')
            in_path_len = payload.get('in_path_len', 0)
            in_path_hex = payload.get('in_path', '')

            print("✅ SUCCESS!")
            print(f"   Out path (TO {name}): {out_path_len} hops")
            if out_path_hex:
                out_hops = [f"{b:02x}" for b in bytes.fromhex(out_path_hex)[:out_path_len]]
                print(f"      Hops: {' -> '.join(out_hops)}")

            print(f"   In path (FROM {name}): {in_path_len} hops")
            if in_path_hex:
                in_hops = [f"{b:02x}" for b in bytes.fromhex(in_path_hex)[:in_path_len]]
                print(f"      Hops: {' -> '.join(in_hops)}")

        elif response.type == EventType.ERROR:
            print(f"❌ ERROR: {response.payload}")

        else:
            print(f"⚠️  Unexpected response: {response.type}")

    except asyncio.TimeoutError:
        print("⏱️  TIMEOUT (30s) - No response received")
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

    # Disconnect
    print("\n✓ Disconnecting...")
    await meshcore.disconnect()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 test_discover_simple.py <contact_name>")
        sys.exit(1)

    contact_name = sys.argv[1]
    asyncio.run(test_discovery(contact_name))
