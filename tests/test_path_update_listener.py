#!/usr/bin/env python3
"""
Test script to listen for PATH_UPDATE events and display learned paths.

This demonstrates that the MeshCore library DOES support path update notifications.
When you send a direct message and the path is learned, you'll see the event here.
"""

import asyncio
import sys
from meshcore import MeshCore, EventType

async def main():
    print("🎧 Path Update Listener")
    print("="*70)
    print("Listening for path updates from MeshCore device...")
    print("Send direct messages to contacts to trigger path learning.")
    print()

    meshcore = await MeshCore.create_serial("/dev/ttyACM0")

    path_updates_received = 0

    async def on_path_update(event):
        nonlocal path_updates_received
        path_updates_received += 1

        pubkey = event.payload.get('public_key', '')
        pubkey_prefix = pubkey[:12] if pubkey else 'unknown'

        print(f"\n🔔 PATH UPDATE #{path_updates_received}")
        print(f"   Public key: {pubkey_prefix}...")
        print(f"   Full key: {pubkey}")

        # Fetch the updated contact to see the new path
        try:
            contacts_result = await meshcore.commands.get_contacts()
            if contacts_result.type == EventType.CONTACTS:
                contacts = contacts_result.payload

                # Find the contact
                for key, contact in contacts.items():
                    if contact.get('public_key', '') == pubkey:
                        name = contact.get('adv_name', 'Unknown')
                        out_path_len = contact.get('out_path_len', -1)
                        out_path = contact.get('out_path', '')

                        print(f"\n   Contact: {name}")
                        print(f"   Path length: {out_path_len} hops")

                        if out_path_len > 0:
                            path_bytes = bytes.fromhex(out_path) if out_path else b''
                            path_hops = [f"{b:02x}" for b in path_bytes[:out_path_len]]
                            print(f"   Path: {' → '.join(path_hops)}")
                            print(f"   ✅ PATH LEARNED!")
                        elif out_path_len == 0:
                            print(f"   Direct connection (0 hops)")
                        else:
                            print(f"   Still in flood mode")
                        break
        except Exception as e:
            print(f"   Error fetching contact: {e}")

    # Subscribe to PATH_UPDATE events
    subscription = meshcore.dispatcher.subscribe(
        EventType.PATH_UPDATE,
        on_path_update
    )

    print("✅ Subscribed to PATH_UPDATE events")
    print()
    print("Waiting for path updates... (Ctrl+C to exit)")
    print()
    print("💡 Tip: In another terminal, run:")
    print("   python3 test_send_message_learn_path.py 'ContactName'")
    print()

    try:
        # Keep running until interrupted
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print(f"\n\n📊 Summary: Received {path_updates_received} path updates")
    finally:
        subscription.unsubscribe()
        await meshcore.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
