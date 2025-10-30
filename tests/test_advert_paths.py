#!/usr/bin/env python3
"""
Test script to query advert_path table from MeshCore device.

The advert_path table contains paths from recently received messages.
Every time you receive a message from someone, the firmware automatically
stores the path that message took in the advert_paths[] table.

This is MUCH better than path discovery because:
1. No telemetry permissions needed
2. Works for any node you've received messages from
3. Automatically updated with every received message
4. Stored in a 16-entry cache (ADVERT_PATH_TABLE_SIZE = 16)
"""

import asyncio
import sys
from meshcore import MeshCore, EventType

CMD_GET_ADVERT_PATH = 42  # 0x2A
RESP_CODE_ADVERT_PATH = 22
RESP_CODE_ERR = 1


async def get_advert_path(meshcore, contact_name):
    """
    Query the advert_path table for a specific contact.

    Returns the path from the most recent message received from that contact.
    """

    # Get contact by name
    contacts_result = await meshcore.commands.get_contacts()
    if contacts_result.type != EventType.CONTACTS:
        print(f"❌ Failed to get contacts")
        return None
    contacts = contacts_result.payload
    contact = None
    contact_pubkey = None

    for key, c in contacts.items():
        name = c.get('adv_name', c.get('name', ''))
        if name.lower() == contact_name.lower():
            contact = c
            contact_pubkey = c.get('public_key', '')
            break

    if not contact or not contact_pubkey:
        print(f"❌ Contact '{contact_name}' not found")
        return None

    pubkey_bytes = bytes.fromhex(contact_pubkey)

    print(f"\n🔍 Querying advert_path for: {contact.get('name', contact_name)}")
    print(f"   Pub key: {contact_pubkey[:16]}...")

    # Send CMD_GET_ADVERT_PATH
    cmd_frame = bytearray([CMD_GET_ADVERT_PATH, 0x00])  # command + reserved byte
    cmd_frame.extend(pubkey_bytes)

    try:
        response = await meshcore.commands.send(
            bytes(cmd_frame),
            expected_events=[EventType.COMMAND_RESPONSE, EventType.ERROR],
            timeout=5.0
        )

        if response.type == EventType.ERROR:
            print(f"❌ Error: {response.data.get('message', 'Unknown error')}")
            return None

        if response.type == EventType.COMMAND_RESPONSE:
            data = response.data.get('data', b'')

            if len(data) < 1:
                print("❌ Empty response")
                return None

            response_code = data[0]

            if response_code == RESP_CODE_ERR:
                error_code = data[1] if len(data) > 1 else 0
                if error_code == 2:  # ERR_CODE_NOT_FOUND
                    print(f"📭 No recent messages from {contact.get('name', contact_name)}")
                    print(f"   (Path not in advert_path table)")
                else:
                    print(f"❌ Error code: {error_code}")
                return None

            if response_code == RESP_CODE_ADVERT_PATH:
                if len(data) < 6:
                    print("❌ Response too short")
                    return None

                # Parse RESP_CODE_ADVERT_PATH response:
                # byte 0: RESP_CODE_ADVERT_PATH (22)
                # bytes 1-4: recv_timestamp (uint32)
                # byte 5: path_len
                # bytes 6+: path (path_len bytes, 1 byte per hop)

                recv_timestamp = int.from_bytes(data[1:5], byteorder='little')
                path_len = data[5]
                path_bytes = data[6:6+path_len]

                print(f"\n✅ Found path in advert_path table!")
                print(f"   Last received: {recv_timestamp} (unix timestamp)")
                print(f"   Path length: {path_len} hops")

                if path_len > 0:
                    path_hops = [f"{b:02x}" for b in path_bytes]
                    print(f"   Path: {' → '.join(path_hops)}")
                else:
                    print(f"   Path: DIRECT (0 hops)")

                return {
                    'contact': contact.get('name', contact_name),
                    'recv_timestamp': recv_timestamp,
                    'path_len': path_len,
                    'path': path_bytes.hex(),
                    'path_hops': [f"{b:02x}" for b in path_bytes] if path_len > 0 else []
                }

            print(f"❌ Unexpected response code: {response_code}")
            return None

    except asyncio.TimeoutError:
        print(f"❌ Timeout waiting for response")
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


async def list_all_advert_paths(meshcore):
    """
    Query advert_path table for all contacts that have sent messages.
    """
    print("\n" + "="*70)
    print("ADVERT PATH TABLE - Paths from Recently Received Messages")
    print("="*70)

    contacts_result = await meshcore.commands.get_contacts()
    if contacts_result.type != EventType.CONTACTS:
        print(f"❌ Failed to get contacts")
        return []
    contacts = contacts_result.payload
    found_paths = []
    not_found = []

    for key, contact in contacts.items():
        pubkey = contact.get('public_key', '')
        name = contact.get('adv_name', contact.get('name', key))

        if not pubkey:
            not_found.append(name)
            continue

        pubkey_bytes = bytes.fromhex(pubkey)

        # Send CMD_GET_ADVERT_PATH
        cmd_frame = bytearray([CMD_GET_ADVERT_PATH, 0x00])
        cmd_frame.extend(pubkey_bytes)

        try:
            response = await meshcore.commands.send(
                bytes(cmd_frame),
                expected_events=[EventType.COMMAND_RESPONSE, EventType.ERROR],
                timeout=2.0
            )

            if response.type == EventType.COMMAND_RESPONSE:
                data = response.data.get('data', b'')

                if len(data) >= 6 and data[0] == RESP_CODE_ADVERT_PATH:
                    recv_timestamp = int.from_bytes(data[1:5], byteorder='little')
                    path_len = data[5]
                    path_bytes = data[6:6+path_len]

                    found_paths.append({
                        'name': name,
                        'timestamp': recv_timestamp,
                        'path_len': path_len,
                        'path_hops': [f"{b:02x}" for b in path_bytes] if path_len > 0 else []
                    })
                else:
                    not_found.append(name)
        except:
            not_found.append(name)

    # Sort by most recent first
    found_paths.sort(key=lambda x: x['timestamp'], reverse=True)

    print(f"\n✅ Found {len(found_paths)} contacts with stored paths:\n")

    for p in found_paths:
        path_display = ' → '.join(p['path_hops']) if p['path_hops'] else 'DIRECT'
        print(f"  📨 {p['name']:<25} | {p['path_len']} hops | {path_display}")

    print(f"\n📭 {len(not_found)} contacts without stored paths (no recent messages)")

    return found_paths


async def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 test_advert_paths.py <contact_name>   # Query specific contact")
        print("  python3 test_advert_paths.py --all            # List all stored paths")
        sys.exit(1)

    meshcore = await MeshCore.create_serial("/dev/ttyACM0")

    try:
        if sys.argv[1] == "--all":
            await list_all_advert_paths(meshcore)
        else:
            contact_name = sys.argv[1]
            result = await get_advert_path(meshcore, contact_name)

            if result:
                print(f"\n✨ You can use this path to send direct messages!")
                print(f"   The path is automatically updated every time you receive")
                print(f"   a message from {result['contact']}.")

    finally:
        await meshcore.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
