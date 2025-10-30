#!/usr/bin/env python3
"""
Test the two-tier path lookup functionality.
"""
import asyncio
import sys
sys.path.insert(0, '/home/tom/jeff')

from meshcore import MeshCore

async def test_lookup():
    print("Connecting to MeshCore...")
    mc = await MeshCore.create_serial('/dev/ttyUSB0', auto_reconnect=False)

    print("Getting contacts...")
    await mc.ensure_contacts()
    contacts = mc.contacts
    print(f"Loaded {len(contacts)} contacts")

    # Test with a known hash (first 6 bytes of a contact)
    if contacts:
        # Get first contact
        first_key = list(contacts.keys())[0]
        first_contact = contacts[first_key]
        contact_name = first_contact.get('adv_name', 'Unknown')

        # Take first 6 bytes of pubkey as test hash
        test_hash = bytes.fromhex(first_key[:12])  # 6 bytes = 12 hex chars

        print(f"\nTest 1: Known contact in device")
        print(f"  Testing with hash: {test_hash.hex()}")
        print(f"  Expected name: {contact_name}")

        # Simulate the lookup
        matches = []
        for key, contact in contacts.items():
            pubkey = contact.get('public_key', '')
            if pubkey.startswith(test_hash.hex()):
                matches.append(contact.get('adv_name', '??'))

        if matches:
            print(f"  ✓ Found in Tier 1 (device contacts): {matches[0]}")
            if len(matches) > 1:
                print(f"  ⚠️  Collision detected: {len(matches)} matches: {matches}")
        else:
            print(f"  ✗ Not found in device contacts")

    print("\nTest 2: Random hash (should try API)")
    random_hash = bytes.fromhex("abcdef123456")
    print(f"  Testing with hash: {random_hash.hex()}")

    # Check device contacts
    device_match = None
    for key, contact in contacts.items():
        if key.startswith(random_hash.hex()):
            device_match = contact.get('adv_name', '??')
            break

    if device_match:
        print(f"  ✓ Found in Tier 1: {device_match}")
    else:
        print(f"  ✗ Not in device contacts - would fall back to API")

    await mc.close()
    print("\nTest complete!")

if __name__ == "__main__":
    asyncio.run(test_lookup())
