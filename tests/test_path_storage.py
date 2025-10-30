#!/usr/bin/env python3
"""
Test Path Storage - Manual test to verify automatic path learning and storage.

This script demonstrates the complete path learning flow:
1. Connect to device with auto_update_contacts enabled
2. Send direct message to a contact (triggers FLOOD)
3. Wait for PATH_UPDATE event
4. Verify path is stored in contact cache
5. Send another message (should use ROUTED mode)

Usage:
    python3 test_path_storage.py "ContactName"
    python3 test_path_storage.py "ContactName" --verify  # Send 2 messages to verify
"""

import asyncio
import sys
import time
from meshcore import MeshCore, EventType

class PathStorageTest:
    def __init__(self):
        self.path_updates = []
        self.msg_sent_events = []
        self.ack_events = []

    async def on_path_update(self, event):
        """Track PATH_UPDATE events"""
        pubkey = event.payload.get('public_key', '')
        timestamp = time.time()

        print(f"\n🛤️  PATH_UPDATE EVENT!")
        print(f"   Timestamp: {timestamp:.3f}")
        print(f"   Public key: {pubkey[:16]}...")

        self.path_updates.append({
            'timestamp': timestamp,
            'pubkey': pubkey,
            'event': event
        })

    async def on_msg_sent(self, event):
        """Track MSG_SENT events to see routing mode"""
        if hasattr(event, 'payload'):
            payload = event.payload
            flood = payload.get('flood', False)
            expected_ack = payload.get('expected_ack', b'')
            suggested_timeout = payload.get('suggested_timeout', 0)
            timestamp = time.time()

            routing_mode = "FLOOD" if flood else "ROUTED"
            print(f"\n📮 MSG_SENT: {routing_mode} mode")
            print(f"   Expected ACK: {expected_ack.hex()[:8]}...")
            print(f"   Timeout: {suggested_timeout}ms")

            self.msg_sent_events.append({
                'timestamp': timestamp,
                'flood': flood,
                'routing_mode': routing_mode,
                'expected_ack': expected_ack.hex(),
                'timeout': suggested_timeout
            })

    async def on_ack(self, event):
        """Track ACK events"""
        if hasattr(event, 'payload'):
            payload = event.payload
            ack_code = payload.get('code', '')
            timestamp = time.time()

            print(f"\n✉️  ACK RECEIVED")
            print(f"   Code: {ack_code[:8] if isinstance(ack_code, str) else ack_code}...")

            self.ack_events.append({
                'timestamp': timestamp,
                'code': ack_code,
                'event': event
            })

async def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 test_path_storage.py <contact_name>")
        print("  python3 test_path_storage.py <contact_name> --verify")
        print()
        print("Examples:")
        print("  python3 test_path_storage.py \"Thomas Haberfield\"")
        print("  python3 test_path_storage.py \"Leonay\" --verify")
        sys.exit(1)

    contact_name = sys.argv[1]
    verify_mode = "--verify" in sys.argv

    print("="*70)
    print("PATH STORAGE TEST")
    print("="*70)
    print(f"Target: {contact_name}")
    print(f"Mode: {'Verify (2 messages)' if verify_mode else 'Single message'}")
    print()

    # Create test tracker
    test = PathStorageTest()

    # Connect with auto_update_contacts enabled (THIS IS KEY!)
    print("Connecting to device...")
    mc = await MeshCore.create_serial(
        "/dev/ttyACM0",
        auto_reconnect=True,
        max_reconnect_attempts=3
    )
    print("✓ Connected")

    # Enable automatic contact refresh on path updates
    mc.auto_update_contacts = True
    print("✓ auto_update_contacts enabled")

    # Subscribe to events
    print("✓ Subscribing to events...")
    mc.subscribe(EventType.PATH_UPDATE, test.on_path_update)
    mc.subscribe(EventType.MSG_SENT, test.on_msg_sent)
    mc.subscribe(EventType.ACK, test.on_ack)

    print()
    print("-"*70)
    print("STEP 1: Find contact and check initial path state")
    print("-"*70)

    # Ensure contacts loaded and give time for device to respond
    print("Loading contacts...")
    await mc.ensure_contacts()
    await asyncio.sleep(2)  # Give device time to respond

    # Refresh contacts property
    await mc.ensure_contacts(follow=True)

    print(f"Loaded {len(mc.contacts)} contacts")

    # Find contact (case-insensitive search)
    contact = None
    contact_name_lower = contact_name.lower()

    for key, c in mc.contacts.items():
        name = c.get('adv_name', c.get('name', ''))
        if name.lower() == contact_name_lower:
            contact = c
            break

    # If not found, show available contacts
    if not contact:
        print(f"❌ Contact '{contact_name}' not found")
        print(f"\nAvailable contacts ({len(mc.contacts)}):")

        contact_list = []
        for key, c in mc.contacts.items():
            name = c.get('adv_name', c.get('name', 'Unknown'))
            if name and name != 'Unknown':
                contact_list.append(name)

        contact_list.sort()
        for i, name in enumerate(contact_list[:20], 1):
            print(f"  {i}. {name}")

        if len(contact_list) > 20:
            print(f"  ... and {len(contact_list) - 20} more")

        print(f"\nTry one of these names exactly as shown above.")
        await mc.disconnect()
        sys.exit(1)

    pubkey = contact.get('public_key', '')
    pubkey_bytes = bytes.fromhex(pubkey)
    initial_path_len = contact.get('out_path_len', -1)
    initial_path = contact.get('out_path', b'')

    print(f"✓ Found: {contact_name}")
    print(f"  Public key: {pubkey[:16]}...")
    print(f"  Initial path_len: {initial_path_len}")
    print(f"  Initial path: {initial_path.hex() if initial_path else 'none'}")

    if initial_path_len > 0:
        print(f"  ⚠️  Contact already has stored path ({initial_path_len} hops)")
        print(f"  To test fresh learning, reset path first:")
        print(f"     await mc.commands.reset_path(pubkey_bytes)")
        print()

        if not verify_mode:
            print("  Running in verify mode to confirm path is used...")
            verify_mode = True
    elif initial_path_len == 0:
        print(f"  ℹ️  Direct connection (neighbor) - no path to learn")
    else:
        print(f"  ✓ No stored path - will learn via FLOOD")

    print()
    print("-"*70)
    print("STEP 2: Send direct message (with retry)")
    print("-"*70)

    message = f"Path test at {time.strftime('%H:%M:%S')}"
    print(f"Message: {message}")

    print("\nSending message with send_msg_with_retry()...")
    start_time = time.time()

    result = await mc.commands.send_msg_with_retry(
        pubkey_bytes,
        message,
        max_attempts=3,
        flood_after=2,  # Reset path after 2 failures
        timeout=0  # Use device suggested timeout
    )

    send_duration = time.time() - start_time

    if result is None:
        print(f"❌ Message failed after retries ({send_duration:.2f}s)")
        await mc.disconnect()
        sys.exit(1)
    else:
        print(f"✓ Message sent successfully ({send_duration:.2f}s)")

    # Check routing mode from MSG_SENT event
    if test.msg_sent_events:
        last_sent = test.msg_sent_events[-1]
        print(f"  Routing: {last_sent['routing_mode']}")
        print(f"  Timeout: {last_sent['timeout']}ms")

        if last_sent['flood']:
            print(f"  ℹ️  FLOOD mode - should trigger path learning")
        else:
            print(f"  ℹ️  ROUTED mode - using existing path")

    print()
    print("-"*70)
    print("STEP 3: Wait for PATH_UPDATE event and ACK")
    print("-"*70)

    print("Waiting 10 seconds for PATH_UPDATE and ACK...")

    # Wait for path update
    path_update_received = False
    for i in range(10):
        await asyncio.sleep(1)

        if test.path_updates and not path_update_received:
            print(f"\n✅ PATH_UPDATE received at +{test.path_updates[-1]['timestamp'] - start_time:.2f}s")
            path_update_received = True

        if test.ack_events:
            ack_time = test.ack_events[-1]['timestamp'] - start_time
            print(f"✅ ACK received at +{ack_time:.2f}s")
            break

        print(f"  Waiting... {i+1}/10s", end='\r')

    print()

    if not test.ack_events:
        print("⚠️  No ACK received - message may not have been delivered")
        if not test.path_updates:
            print("⚠️  No PATH_UPDATE - path not learned")

    print()
    print("-"*70)
    print("STEP 4: Check if path was stored")
    print("-"*70)

    # Re-fetch contact to see updated path
    # (auto_update_contacts should have already done this, but double-check)
    await mc.ensure_contacts()
    contact_updated = mc.get_contact_by_name(contact_name)

    if not contact_updated:
        print("❌ Contact disappeared?!")
    else:
        new_path_len = contact_updated.get('out_path_len', -1)
        new_path = contact_updated.get('out_path', b'')

        print(f"Contact: {contact_name}")
        print(f"  New path_len: {new_path_len}")
        print(f"  New path: {new_path.hex() if new_path else 'none'}")

        if new_path_len != initial_path_len or new_path != initial_path:
            print(f"\n✅ PATH CHANGED!")
            print(f"   Before: len={initial_path_len}, path={initial_path.hex() if initial_path else 'none'}")
            print(f"   After:  len={new_path_len}, path={new_path.hex() if new_path else 'none'}")

            if new_path_len > 0:
                print(f"\n✅ Path successfully learned and stored!")
                print(f"   Hops: {new_path_len}")

                # Try to resolve hop names
                print(f"   Route:")
                for i in range(new_path_len):
                    hop_hash = new_path[i:i+1].hex()
                    hop_contact = mc.get_contact_by_key_prefix(hop_hash)
                    hop_name = hop_contact.get('adv_name', f'Unknown ({hop_hash})') if hop_contact else f'Unknown ({hop_hash})'
                    print(f"     Hop {i+1}: {hop_name}")
        else:
            if initial_path_len > 0:
                print(f"\n✓ Path unchanged (already had path)")
            elif new_path_len == 0:
                print(f"\n✓ Direct connection (no path needed)")
            else:
                print(f"\n⚠️  Path not learned (still flood mode)")
                print(f"   Possible reasons:")
                print(f"   - Message not delivered (no ACK)")
                print(f"   - Contact didn't send PATH response")
                print(f"   - PATH_UPDATE event not received")

    # Verify mode - send second message to confirm ROUTED mode
    if verify_mode:
        print()
        print("-"*70)
        print("STEP 5: VERIFY - Send second message to confirm ROUTED mode")
        print("-"*70)

        # Clear events
        test.msg_sent_events.clear()
        test.ack_events.clear()

        await asyncio.sleep(2)  # Small delay

        message2 = f"Verify test at {time.strftime('%H:%M:%S')}"
        print(f"Message: {message2}")

        print("\nSending second message...")
        start_time2 = time.time()

        result2 = await mc.commands.send_msg_with_retry(
            pubkey_bytes,
            message2,
            max_attempts=3,
            flood_after=2,
            timeout=0
        )

        send_duration2 = time.time() - start_time2

        if result2 is None:
            print(f"❌ Second message failed ({send_duration2:.2f}s)")
        else:
            print(f"✓ Second message sent ({send_duration2:.2f}s)")

            if test.msg_sent_events:
                last_sent = test.msg_sent_events[-1]
                print(f"  Routing: {last_sent['routing_mode']}")

                if last_sent['flood']:
                    print(f"  ⚠️  Still FLOOD mode - path not being used")
                    print(f"     Possible reasons:")
                    print(f"     - Path not actually stored")
                    print(f"     - auto_update_contacts didn't refresh")
                    print(f"     - Path was reset")
                else:
                    print(f"\n  ✅ ROUTED mode - using stored path!")
                    print(f"     Path storage is working correctly!")

        # Wait for ACK
        print("\nWaiting for ACK...")
        await asyncio.sleep(5)

        if test.ack_events:
            ack_time = test.ack_events[-1]['timestamp'] - start_time2
            print(f"✅ ACK received at +{ack_time:.2f}s")
        else:
            print("⚠️  No ACK received")

    print()
    print("="*70)
    print("SUMMARY")
    print("="*70)

    print(f"\nContact: {contact_name}")
    print(f"  Initial path: {initial_path_len} hops")
    print(f"  Final path: {contact_updated.get('out_path_len', -1) if contact_updated else 'unknown'} hops")

    print(f"\nEvents:")
    print(f"  MSG_SENT events: {len(test.msg_sent_events)}")
    print(f"  PATH_UPDATE events: {len(test.path_updates)}")
    print(f"  ACK events: {len(test.ack_events)}")

    if test.msg_sent_events:
        flood_count = sum(1 for e in test.msg_sent_events if e['flood'])
        routed_count = len(test.msg_sent_events) - flood_count
        print(f"  FLOOD messages: {flood_count}")
        print(f"  ROUTED messages: {routed_count}")

    print(f"\nPath Storage Test: ", end='')

    if contact_updated:
        final_path_len = contact_updated.get('out_path_len', -1)

        if verify_mode:
            # In verify mode, check if second message used ROUTED
            if len(test.msg_sent_events) >= 2:
                second_msg_routed = not test.msg_sent_events[-1]['flood']
                if second_msg_routed:
                    print("✅ PASSED")
                    print("   Path learned and used for second message!")
                else:
                    print("⚠️  PARTIAL")
                    print("   Path may be learned but not being used")
            else:
                print("❌ FAILED")
                print("   Did not send second message")
        else:
            # Single message mode - just check if path changed
            if final_path_len != initial_path_len:
                print("✅ PASSED")
                print("   Path was learned and stored!")
            elif initial_path_len > 0:
                print("✓ N/A")
                print("   Contact already had path")
            else:
                print("⚠️  INCONCLUSIVE")
                print("   Path not learned (may need ACK or more time)")
    else:
        print("❌ FAILED")
        print("   Could not verify path storage")

    print()
    await mc.disconnect()
    print("Disconnected.")

if __name__ == "__main__":
    asyncio.run(main())
