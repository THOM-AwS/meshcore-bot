#!/usr/bin/env python3
"""Test basic connection."""
import asyncio
from meshcore import MeshCore

async def test():
    print("Connecting...")
    mc = await MeshCore.create_serial('/dev/ttyACM0')
    print("Connected!")

    print("Getting contacts...")
    result = await asyncio.wait_for(mc.commands.get_contacts(), timeout=10)
    print(f"Got {len(mc.contacts)} contacts")

    for pk, c in list(mc.contacts.items())[:5]:
        print(f"  - {c.get('adv_name', '?')}: out_path_len={c.get('out_path_len', -1)}")

    await mc.disconnect()
    print("Done!")

asyncio.run(test())
