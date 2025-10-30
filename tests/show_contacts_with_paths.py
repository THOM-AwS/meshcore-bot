#!/usr/bin/env python3
"""Show contacts that have paths."""
import asyncio
import sys
sys.path.insert(0, '/home/tom/jeff')

from meshcore import MeshCore

async def main():
    mc = await MeshCore.create_serial('/dev/ttyACM0')
    await mc.commands.get_contacts()

    print(f"Total contacts: {len(mc.contacts)}\n")
    print("Contacts WITH paths (likely online/reachable):")
    print("=" * 60)

    with_paths = []
    for pk, c in mc.contacts.items():
        out_path_len = c.get('out_path_len', -1)
        if out_path_len >= 0:  # Has a path
            name = c.get('adv_name', '?')
            with_paths.append((name, out_path_len))

    with_paths.sort(key=lambda x: x[1])  # Sort by hop count

    for name, hops in with_paths[:20]:  # Show first 20
        print(f"  {name:30s} - {hops} hops")

    print(f"\n({len(with_paths)} total contacts with paths)")

    await mc.disconnect()

asyncio.run(main())
