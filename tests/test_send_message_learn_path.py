#!/usr/bin/env python3
"""
Send a message to a contact to trigger path learning.

How path discovery works in MeshCore:
1. Send a FLOOD message to destination
2. Destination sends back a delivery report (ACK) with the path
3. Path is stored in contact's out_path
4. Future messages use the stored path for DIRECT routing

This script sends a simple text message to trigger this process.
"""

import asyncio
import sys
from meshcore import MeshCore, EventType

async def send_message_to_learn_path(meshcore, contact_name, message="ping"):
    """
    Send a message to a contact to learn the path.

    After sending, the device should receive a delivery report
    with the path information, which gets stored in the contact.
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

    contact_name = contact.get('adv_name', contact_name)
    out_path_len_before = contact.get('out_path_len', -1)

    print(f"\n📤 Sending message to: {contact_name}")
    print(f"   Current path status: {out_path_len_before} hops")

    if out_path_len_before == 0:
        print(f"   ℹ️  Direct connection - no path learning needed")
    elif out_path_len_before > 0:
        print(f"   ℹ️  Already has stored path")
    else:
        print(f"   📡 Flood mode - will trigger path learning!")

    # Send the message
    print(f"\n   Message: \"{message}\"")
    print(f"   Sending...")

    try:
        # Use the library's send_text_message method
        result = await meshcore.commands.send_text_message(
            contact_pubkey,
            message
        )

        if result.type == EventType.MSG_SENT:
            sent_data = result.data
            is_flood = sent_data.get('flood', False)

            print(f"\n✅ Message sent!")
            print(f"   Routing: {'FLOOD' if is_flood else 'DIRECT'}")

            if is_flood:
                print(f"\n⏳ Message sent via FLOOD - waiting for delivery report...")
                print(f"   The destination should send back a delivery report with the path.")
                print(f"   This will be stored in the contact's out_path field.")
                print(f"\n   Waiting 30 seconds for path to be learned...")

                await asyncio.sleep(30)

                # Re-fetch contacts to see if path was learned
                print(f"\n🔍 Checking if path was learned...")
                contacts_result2 = await meshcore.commands.get_contacts()
                if contacts_result2.type == EventType.CONTACTS:
                    contacts2 = contacts_result2.payload

                    for key, c in contacts2.items():
                        name = c.get('adv_name', '')
                        if name == contact_name:
                            out_path_len_after = c.get('out_path_len', -1)
                            out_path = c.get('out_path', '')

                            print(f"\n   Path status after: {out_path_len_after} hops")

                            if out_path_len_after > 0:
                                path_bytes = bytes.fromhex(out_path) if out_path else b''
                                path_hops = [f"{b:02x}" for b in path_bytes[:out_path_len_after]]
                                print(f"   ✅ Path learned: {' → '.join(path_hops)}")
                                return {
                                    'contact': contact_name,
                                    'path_len': out_path_len_after,
                                    'path_hops': path_hops
                                }
                            elif out_path_len_after == 0:
                                print(f"   ℹ️  Direct connection (0 hops)")
                            else:
                                print(f"   ⚠️  Path not learned yet - still flood mode")
                                print(f"   Possible reasons:")
                                print(f"     - Destination didn't send delivery report")
                                print(f"     - Message didn't reach destination")
                                print(f"     - Delivery report got lost")
                                print(f"     - Need to wait longer")
                            break
            else:
                print(f"   ℹ️  Used existing DIRECT path")

            return None

        else:
            print(f"❌ Failed to send: {result}")
            return None

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


async def send_to_multiple(meshcore, contact_names, message="ping"):
    """
    Send messages to multiple contacts to learn paths.
    """
    print(f"\n📤 Sending to {len(contact_names)} contacts to learn paths...")
    print(f"   Message: \"{message}\"")

    results = []

    for i, name in enumerate(contact_names, 1):
        print(f"\n{'='*70}")
        print(f"[{i}/{len(contact_names)}] {name}")
        print(f"{'='*70}")

        result = await send_message_to_learn_path(meshcore, name, message)
        if result:
            results.append(result)

        # Brief pause between messages
        if i < len(contact_names):
            print(f"\n⏸  Waiting 5 seconds before next message...")
            await asyncio.sleep(5)

    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print(f"{'='*70}")
    print(f"\n✅ Learned paths for {len(results)} contacts:")
    for r in results:
        path_display = ' → '.join(r['path_hops'])
        print(f"  📡 {r['contact']:<25} | {r['path_len']} hops | {path_display}")

    if len(results) < len(contact_names):
        print(f"\n⚠️  {len(contact_names) - len(results)} contacts didn't learn paths")


async def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 test_send_message_learn_path.py <contact_name> [message]")
        print("  python3 test_send_message_learn_path.py --batch <name1> <name2> ...")
        print()
        print("Examples:")
        print("  python3 test_send_message_learn_path.py 'Camperdown'")
        print("  python3 test_send_message_learn_path.py 'Leonay' 'Hello!'")
        print("  python3 test_send_message_learn_path.py --batch 'Leonay' 'Cherrybrook' 'Camperdown'")
        sys.exit(1)

    meshcore = await MeshCore.create_serial("/dev/ttyACM0")

    try:
        if sys.argv[1] == "--batch":
            contacts = sys.argv[2:]
            if not contacts:
                print("❌ No contacts specified for batch mode")
                sys.exit(1)
            await send_to_multiple(meshcore, contacts)
        else:
            contact_name = sys.argv[1]
            message = sys.argv[2] if len(sys.argv) > 2 else "ping from Jeff - path discovery test"
            await send_message_to_learn_path(meshcore, contact_name, message)

    finally:
        await meshcore.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
