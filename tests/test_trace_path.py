#!/usr/bin/env python3
"""
Test TRACE path discovery using CMD_SEND_TRACE_PATH.

This sends a TRACE packet along a stored path to discover the actual
route and SNR (signal strength) at each hop.

NOTE: This requires the contact to already have a stored path (out_path).
You can't trace to nodes you've never received messages from.
"""

import asyncio
import sys
import random
from meshcore import MeshCore, EventType


async def trace_path(meshcore, contact_name):
    """
    Send a TRACE packet to a contact and wait for the trace response.

    The trace follows the stored out_path and records SNR at each hop.
    """

    # Use library's built-in contact lookup
    contact = meshcore.get_contact_by_name(contact_name)

    if not contact:
        print(f"❌ Contact '{contact_name}' not found")
        print(f"   Try: python3 test_trace_path.py --list")
        return None

    contact_name = contact.get('adv_name', contact_name)
    out_path_len = contact.get('out_path_len', -1)
    out_path_hex = contact.get('out_path', '')

    print(f"\n🔍 Tracing path to: {contact_name}")
    print(f"   Stored path length: {out_path_len} hops")

    # Check if contact has a stored path
    if out_path_len < 0:
        print(f"   ❌ No stored path (flood mode only)")
        print(f"   Cannot trace - contact must have a known path")
        return None

    if out_path_len == 0:
        print(f"   ℹ️  Direct connection (0 hops)")
        print(f"   No intermediaries to trace")
        return None

    # Parse out_path
    out_path_bytes = bytes.fromhex(out_path_hex) if out_path_hex else b''

    if len(out_path_bytes) < out_path_len:
        print(f"   ❌ Path data incomplete")
        return None

    path_hops = [f"{b:02x}" for b in out_path_bytes[:out_path_len]]
    print(f"   Path: {' → '.join(path_hops)}")

    # Generate random tag and auth code for this trace
    tag = random.randint(1, 0xFFFFFFFF)
    auth_code = random.randint(1, 0xFFFFFFFF)
    flags = 0  # No special flags

    print(f"\n📡 Sending TRACE packet...")
    print(f"   Tag: 0x{tag:08x}")
    print(f"   Auth: 0x{auth_code:08x}")

    try:
        # Use the library's built-in send_trace() method instead of manually building frames
        response = await meshcore.commands.send_trace(
            auth_code=auth_code,
            tag=tag,
            flags=flags,
            path=out_path_bytes[:out_path_len]
        )

        if response.type == EventType.ERROR:
            print(f"❌ Error: {response.payload.get('reason', 'Unknown error')}")
            return None

        if response.type == EventType.MSG_SENT:
            payload = response.payload
            est_timeout = payload.get('suggested_timeout', 5000)

            print(f"✅ TRACE sent successfully")
            print(f"   Est timeout: {est_timeout}ms")
            print(f"\n⏳ Waiting for TRACE_DATA event (tag: 0x{tag:08x})...")

            # Use wait_for_event with attribute filter to match our specific tag
            timeout_sec = (est_timeout + 5000) / 1000.0

            trace_event = await meshcore.wait_for_event(
                EventType.TRACE_DATA,
                attribute_filters={'tag': tag},
                timeout=timeout_sec
            )

            if trace_event:
                print(f"\n✅ TRACE_DATA received!")
                trace_payload = trace_event.payload

                print(f"   Tag: 0x{trace_payload.get('tag', 0):08x}")
                print(f"   Flags: {trace_payload.get('flags', 0)}")
                print(f"   Path Length: {trace_payload.get('path_len', 0)}")

                if 'path' in trace_payload:
                    print(f"\n   📡 Path with SNR data:")
                    for i, node in enumerate(trace_payload['path']):
                        if 'hash' in node:
                            # Repeater node - look up name
                            hash_prefix = node['hash']
                            repeater = meshcore.get_contact_by_key_prefix(hash_prefix)
                            repeater_name = repeater.get('adv_name', f'Unknown ({hash_prefix})') if repeater else f'Unknown ({hash_prefix})'
                            print(f"      Hop {i+1}: {repeater_name:<25} | SNR: {node.get('snr', 0):.1f} dB")
                        else:
                            # Final destination
                            print(f"      Hop {i+1}: Destination                | SNR: {node.get('snr', 0):.1f} dB")

                return {
                    'tag': tag,
                    'auth_code': auth_code,
                    'path_len': out_path_len,
                    'path_hops': path_hops,
                    'est_timeout': est_timeout,
                    'trace_data': trace_payload
                }
            else:
                print(f"\n⚠️  Timeout - no TRACE_DATA received")
                print(f"   Tag 0x{tag:08x} not seen within {timeout_sec:.1f}s")
                print(f"   Path may be broken or unreachable")
                return None
        else:
            print(f"❌ Unexpected response type: {response.type}")
            return None

    except asyncio.TimeoutError:
        print(f"❌ Timeout waiting for response")
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


async def list_traceable_contacts(meshcore):
    """
    List all contacts that have stored paths (can be traced).
    """
    print("\n" + "="*70)
    print("TRACEABLE CONTACTS - Contacts with Stored Paths")
    print("="*70)

    # Ensure contacts are loaded
    await meshcore.ensure_contacts()
    contacts = meshcore.contacts
    traceable = []
    direct = []
    flood_only = []

    for key, contact in contacts.items():
        name = contact.get('adv_name', contact.get('name', key))
        out_path_len = contact.get('out_path_len', -1)
        out_path_hex = contact.get('out_path', '')

        if out_path_len == 0:
            direct.append(name)
        elif out_path_len > 0:
            out_path_bytes = bytes.fromhex(out_path_hex) if out_path_hex else b''
            path_hops = [f"{b:02x}" for b in out_path_bytes[:out_path_len]]
            traceable.append({
                'name': name,
                'path_len': out_path_len,
                'path_hops': path_hops
            })
        else:
            flood_only.append(name)

    print(f"\n✅ {len(traceable)} contacts with traceable paths:\n")
    for c in traceable:
        path_display = ' → '.join(c['path_hops'])
        print(f"  📡 {c['name']:<25} | {c['path_len']} hops | {path_display}")

    print(f"\n📍 {len(direct)} direct connections (0 hops - no trace needed):")
    for name in direct[:10]:
        print(f"  🔗 {name}")
    if len(direct) > 10:
        print(f"  ... and {len(direct) - 10} more")

    print(f"\n📭 {len(flood_only)} contacts with no stored path (flood mode only)")

    return traceable


async def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 test_trace_path.py <contact_name>   # Trace path to contact")
        print("  python3 test_trace_path.py --list           # List traceable contacts")
        sys.exit(1)

    # Create connection with auto-reconnect for reliability
    meshcore = await MeshCore.create_serial(
        "/dev/ttyACM0",
        auto_reconnect=True,
        max_reconnect_attempts=3
    )

    try:
        if sys.argv[1] == "--list":
            traceable = await list_traceable_contacts(meshcore)

            if traceable:
                print(f"\n💡 Try tracing one of these:")
                for c in traceable[:3]:
                    print(f"   python3 test_trace_path.py \"{c['name']}\"")
        else:
            contact_name = sys.argv[1]
            result = await trace_path(meshcore, contact_name)

            if result:
                print(f"\n✨ Trace initiated successfully!")
                print(f"\nℹ️  TRACE path sends a packet along the stored route and")
                print(f"   records SNR (signal strength) at each hop. The response")
                print(f"   contains path hashes and SNR values for each intermediate node.")

    finally:
        await meshcore.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
