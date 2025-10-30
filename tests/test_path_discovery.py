#!/usr/bin/env python3
"""
Test script for MeshCore path discovery.

Usage:
    python3 test_path_discovery.py <contact_name>
    python3 test_path_discovery.py --batch <name1> <name2> <name3>
    python3 test_path_discovery.py --list-no-paths
"""
import asyncio
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from meshcore import MeshCore, EventType
from meshcore_bot.features.path_discovery import PathDiscovery


async def test_single_discovery(contact_name: str, serial_port: str = '/dev/ttyACM0'):
    """Test path discovery for a single contact."""
    print(f"╔═══════════════════════════════════════════════════════════╗")
    print(f"║  MeshCore Path Discovery Test                             ║")
    print(f"╚═══════════════════════════════════════════════════════════╝\n")

    # Connect to device
    print(f"📡 Connecting to MeshCore device on {serial_port}...")
    meshcore = await MeshCore.create_serial(serial_port)
    print("✓ Connected\n")

    # Get initial contact info
    print("📋 Fetching current contacts...")
    contacts_result = await meshcore.commands.get_contacts()
    print(f"✓ {len(meshcore.contacts)} contacts loaded\n")

    # Initialize path discovery
    pd = PathDiscovery(meshcore)

    # Show contact's current path status
    contact = pd._find_contact_by_name(contact_name)
    if contact:
        pubkey = contact.get('public_key', '')
        out_path_len = contact.get('out_path_len', -1)
        out_path = contact.get('out_path', b'')

        print(f"📍 Current status for '{contact_name}':")
        print(f"   Public key: {pubkey[:16]}...")
        print(f"   out_path_len: {out_path_len}")
        print(f"   out_path: {out_path.hex() if out_path else '(empty)'}")
        print()
    else:
        print(f"❌ Contact '{contact_name}' not found\n")
        await meshcore.disconnect()
        return

    # Attempt path discovery
    print(f"🔍 Starting path discovery for '{contact_name}'...\n")

    result = await pd.discover_path_to_contact(contact_name, timeout=30.0)

    # Display results
    print("\n" + "="*60)
    print("RESULTS:")
    print("="*60)

    if result.get('success'):
        print(f"✅ SUCCESS!")
        print(f"   Contact: {result.get('contact_name')}")
        print(f"   Old path length: {result.get('old_path_len', 'N/A')}")
        print(f"   New path length: {result.get('new_path_len', 'N/A')}")

        out_path_hex = result.get('out_path', '')
        if out_path_hex:
            print(f"   Path data: {out_path_hex}")

        if result.get('note'):
            print(f"   Note: {result.get('note')}")
    else:
        print(f"❌ FAILED")
        print(f"   Contact: {result.get('contact_name')}")
        print(f"   Error: {result.get('error')}")
        print(f"   Path length: {result.get('old_path_len', 'N/A')} (unchanged)")

    print("="*60 + "\n")

    # Disconnect
    await meshcore.disconnect()
    print("✓ Disconnected")


async def test_batch_discovery(contact_names: list, serial_port: str = '/dev/ttyACM0'):
    """Test path discovery for multiple contacts."""
    print(f"╔═══════════════════════════════════════════════════════════╗")
    print(f"║  MeshCore Batch Path Discovery Test                       ║")
    print(f"╚═══════════════════════════════════════════════════════════╝\n")

    # Connect to device
    print(f"📡 Connecting to MeshCore device on {serial_port}...")
    meshcore = await MeshCore.create_serial(serial_port)
    print("✓ Connected\n")

    # Get initial contact info
    print("📋 Fetching current contacts...")
    contacts_result = await meshcore.commands.get_contacts()
    print(f"✓ {len(meshcore.contacts)} contacts loaded\n")

    # Initialize path discovery
    pd = PathDiscovery(meshcore)

    # Run batch discovery
    print(f"🔍 Starting batch discovery for {len(contact_names)} contacts...\n")

    results = await pd.discover_paths_batch(
        contact_names,
        delay_between=3.0,
        timeout_per_contact=30.0
    )

    # Display summary
    print("\n" + "="*60)
    print("BATCH RESULTS:")
    print("="*60)

    for name, result in results.items():
        success = "✅" if result.get('success') else "❌"
        old_len = result.get('old_path_len', 'N/A')
        new_len = result.get('new_path_len', 'N/A')
        error = result.get('error', '')

        print(f"{success} {name}: {old_len} → {new_len} {f'({error})' if error else ''}")

    print("="*60 + "\n")

    # Disconnect
    await meshcore.disconnect()
    print("✓ Disconnected")


async def list_contacts_without_paths(serial_port: str = '/dev/ttyACM0', limit: int = 20):
    """List contacts that don't have paths."""
    print(f"╔═══════════════════════════════════════════════════════════╗")
    print(f"║  Contacts Without Paths                                   ║")
    print(f"╚═══════════════════════════════════════════════════════════╝\n")

    # Connect to device
    print(f"📡 Connecting to MeshCore device on {serial_port}...")
    meshcore = await MeshCore.create_serial(serial_port)
    print("✓ Connected\n")

    # Get contacts
    print("📋 Fetching current contacts...")
    contacts_result = await meshcore.commands.get_contacts()
    print(f"✓ {len(meshcore.contacts)} contacts loaded\n")

    # Initialize path discovery
    pd = PathDiscovery(meshcore)

    # Get contacts without paths
    no_paths = pd.get_contacts_without_paths(limit=limit)

    print(f"📊 Contacts without paths (showing {len(no_paths)}):\n")
    for i, name in enumerate(no_paths, 1):
        print(f"  {i}. {name}")

    print(f"\nTotal contacts without paths: {len(no_paths)}")
    if len(no_paths) >= limit:
        print(f"(Limited to {limit}, may be more)")

    print()

    # Disconnect
    await meshcore.disconnect()
    print("✓ Disconnected")


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage:")
        print(f"  {sys.argv[0]} <contact_name>")
        print(f"  {sys.argv[0]} --batch <name1> <name2> <name3>")
        print(f"  {sys.argv[0]} --list-no-paths")
        sys.exit(1)

    if sys.argv[1] == '--list-no-paths':
        asyncio.run(list_contacts_without_paths())
    elif sys.argv[1] == '--batch':
        if len(sys.argv) < 3:
            print("Error: --batch requires at least one contact name")
            sys.exit(1)
        contact_names = sys.argv[2:]
        asyncio.run(test_batch_discovery(contact_names))
    else:
        contact_name = sys.argv[1]
        asyncio.run(test_single_discovery(contact_name))


if __name__ == "__main__":
    main()
