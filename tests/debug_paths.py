#!/usr/bin/env python3
"""Debug script to inspect contact out_path data directly from device."""
import asyncio
import sys
from meshcore import MeshCore, EventType

async def debug_contacts():
    """Connect to device and dump contact path data."""

    # Connect to device
    print("Connecting to /dev/ttyACM0...")
    meshcore = await MeshCore.create_serial("/dev/ttyACM0")
    print("✓ Connected!")

    # Get contacts
    print("\nFetching contacts...")
    contacts_result = await meshcore.commands.get_contacts()

    if contacts_result.type != EventType.CONTACTS:
        print(f"❌ Failed to get contacts: {contacts_result.type}")
        return

    contacts = contacts_result.payload
    print(f"✓ Got {len(contacts)} contacts\n")

    # Display contact path data
    print("=" * 80)
    print("CONTACT PATH DATA:")
    print("=" * 80)

    for key, contact in contacts.items():
        adv_name = contact.get('adv_name', 'Unknown')
        pubkey = contact.get('public_key', '')
        out_path = contact.get('out_path', b'')
        out_path_len = contact.get('out_path_len', -1)

        print(f"\n{adv_name}")
        print(f"  Pubkey:        {pubkey[:16]}... (prefix: {pubkey[:2]})")
        print(f"  out_path_len:  {out_path_len}")
        print(f"  out_path size: {len(out_path)} bytes")

        if out_path and out_path_len > 0:
            print(f"  out_path hex:  {out_path.hex()}")

            # Try parsing as 6-byte hops
            if len(out_path) >= out_path_len * 6:
                print(f"  Path (6-byte hops):")
                for i in range(out_path_len):
                    start = i * 6
                    end = start + 6
                    hop = out_path[start:end]
                    print(f"    Hop {i}: {hop.hex()} (prefix: {hop.hex()[:2]})")

            # Try parsing as 8-byte hops
            if len(out_path) >= out_path_len * 8:
                print(f"  Path (8-byte hops):")
                for i in range(out_path_len):
                    start = i * 8
                    end = start + 8
                    hop = out_path[start:end]
                    print(f"    Hop {i}: {hop.hex()} (prefix: {hop.hex()[:2]})")
        else:
            print(f"  (No path data or direct)")

    print("\n" + "=" * 80)

if __name__ == "__main__":
    asyncio.run(debug_contacts())
