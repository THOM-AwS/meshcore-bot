#!/usr/bin/env python3
"""
Simple path test - diagnose why ROUTED mode is used when path_len = -1
"""

import asyncio
import sys
from meshcore import MeshCore, EventType

async def main():
    if len(sys.argv) < 2:
        print("Usage: python3 test_path_simple.py <contact_name>")
        sys.exit(1)

    contact_name = sys.argv[1]

    print("Connecting...")
    mc = await MeshCore.create_serial("/dev/ttyACM0", auto_reconnect=True)
    mc.auto_update_contacts = True

    # Track MSG_SENT events
    msg_sent_events = []

    async def on_msg_sent(event):
        if hasattr(event, 'payload'):
            payload = event.payload
            # Firmware sends type field: 1=FLOOD, 0=ROUTED
            msg_type = payload.get('type', 0)
            flood = (msg_type == 1)
            routing = "FLOOD" if flood else "ROUTED"
            print(f"\n📮 MSG_SENT: {routing} mode (type={msg_type})")
            print(f"   Payload: {payload}")
            msg_sent_events.append(event)

    mc.subscribe(EventType.MSG_SENT, on_msg_sent)

    # Load contacts
    print("Loading contacts...")
    await mc.ensure_contacts()
    await asyncio.sleep(2)

    # Find contact
    contact = None
    for key, c in mc.contacts.items():
        if c.get('adv_name', '').lower() == contact_name.lower():
            contact = c
            break

    if not contact:
        print(f"Contact not found: {contact_name}")
        await mc.disconnect()
        sys.exit(1)

    pubkey = contact['public_key']
    pubkey_bytes = bytes.fromhex(pubkey)

    print(f"\nContact: {contact.get('adv_name')}")
    print(f"  Pubkey: {pubkey[:16]}...")
    print(f"  out_path_len: {contact.get('out_path_len', 'missing')}")

    # out_path might be str (hex) or bytes
    out_path_raw = contact.get('out_path', '')
    if isinstance(out_path_raw, bytes):
        out_path_hex = out_path_raw.hex() or 'empty'
    else:
        out_path_hex = out_path_raw or 'empty'

    print(f"  out_path: {out_path_hex}")

    # Check if path_len is -1 but path data exists
    out_path_len = contact.get('out_path_len', -1)

    if out_path_len == -1 and out_path_hex != 'empty':
        print(f"  ⚠️  WARNING: path_len=-1 but path data exists")
        print(f"     Path hex: {out_path_hex}")
        print(f"     This might confuse the firmware!")

    # Try resetting path first
    print(f"\n1. Resetting path to force FLOOD mode...")
    reset_result = await mc.commands.reset_path(pubkey_bytes)
    print(f"   Reset result: {reset_result.type}")

    # Wait a moment
    await asyncio.sleep(1)

    # Re-fetch contact
    await mc.ensure_contacts(follow=True)
    contact = None
    for key, c in mc.contacts.items():
        if c.get('adv_name', '').lower() == contact_name.lower():
            contact = c
            break

    if contact:
        out_path_raw = contact.get('out_path', '')
        if isinstance(out_path_raw, bytes):
            out_path_hex = out_path_raw.hex() or 'empty'
        else:
            out_path_hex = out_path_raw or 'empty'

        print(f"   After reset:")
        print(f"     out_path_len: {contact.get('out_path_len', 'missing')}")
        print(f"     out_path: {out_path_hex}")

    # Now try sending
    print(f"\n2. Sending message with simple send_msg() (no retry)...")

    result = await mc.commands.send_msg(pubkey_bytes, "Simple test message")

    print(f"   Send result: {result.type}")

    if result.type == EventType.MSG_SENT:
        payload = result.payload
        flood = payload.get('flood', False)
        print(f"   Routing mode: {'FLOOD' if flood else 'ROUTED'}")
        print(f"   Expected ACK: {payload.get('expected_ack', b'').hex()[:8]}...")
        print(f"   Timeout: {payload.get('suggested_timeout', 0)}ms")

        # Wait for ACK
        print(f"\n3. Waiting for ACK (10s)...")
        ack = await mc.wait_for_event(EventType.ACK, timeout=10.0)

        if ack:
            print(f"   ✅ ACK received!")
        else:
            print(f"   ❌ No ACK - message not delivered")

        # Wait for PATH_UPDATE
        print(f"\n4. Waiting for PATH_UPDATE (5s)...")
        path_update = await mc.wait_for_event(EventType.PATH_UPDATE, timeout=5.0)

        if path_update:
            print(f"   ✅ PATH_UPDATE received!")

            # Check updated path
            await mc.ensure_contacts(follow=True)
            contact = None
            for key, c in mc.contacts.items():
                if c.get('adv_name', '').lower() == contact_name.lower():
                    contact = c
                    break

            if contact:
                out_path_raw = contact.get('out_path', '')
                if isinstance(out_path_raw, bytes):
                    out_path_hex = out_path_raw.hex() or 'empty'
                else:
                    out_path_hex = out_path_raw or 'empty'

                print(f"   Updated contact:")
                print(f"     out_path_len: {contact.get('out_path_len', 'missing')}")
                print(f"     out_path: {out_path_hex}")
        else:
            print(f"   ⚠️  No PATH_UPDATE - path not learned")

    await mc.disconnect()
    print("\nDone.")

if __name__ == "__main__":
    asyncio.run(main())
