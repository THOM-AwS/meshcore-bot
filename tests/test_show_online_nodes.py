#!/usr/bin/env python3
"""
Show nodes that are likely online (have existing paths).

Usage:
    python3 test_show_online_nodes.py
"""
import asyncio
import sys
sys.path.insert(0, '/home/tom/jeff')

from meshcore import MeshCore


async def main():
    print("="*70)
    print("ONLINE NODES (with existing paths)")
    print("="*70)

    # Connect
    print("\n📡 Connecting to /dev/ttyACM0...")
    mc = await MeshCore.create_serial('/dev/ttyACM0')
    print("✓ Connected\n")

    # Get contacts
    print("📋 Fetching contacts...")
    await mc.commands.get_contacts()
    print(f"✓ Got {len(mc.contacts)} total contacts\n")

    # Find contacts with paths
    with_paths = []
    direct = []
    flood_only = []

    for pk, c in mc.contacts.items():
        name = c.get('adv_name', 'Unknown')
        out_path_len = c.get('out_path_len', -1)

        if out_path_len == 0:
            direct.append(name)
        elif out_path_len > 0:
            out_path = c.get('out_path', b'')
            hops = [f"{b:02x}" for b in out_path[:out_path_len]] if out_path else []
            with_paths.append((name, out_path_len, hops))
        else:
            flood_only.append(name)

    # Sort by hop count
    with_paths.sort(key=lambda x: x[1])

    # Display results
    print("DIRECTLY CONNECTED (0 hops):")
    print("-" * 70)
    if direct:
        for name in sorted(direct)[:10]:
            print(f"  ✓ {name}")
        if len(direct) > 10:
            print(f"  ... and {len(direct) - 10} more")
    else:
        print("  (none)")

    print(f"\nROUTED CONNECTIONS (with stored paths):")
    print("-" * 70)
    if with_paths:
        for name, hop_count, hops in with_paths[:20]:
            hops_str = ' -> '.join(hops) if hops else 'N/A'
            print(f"  {hop_count} hops | {name}")
            print(f"           {hops_str}")
        if len(with_paths) > 20:
            print(f"  ... and {len(with_paths) - 20} more")
    else:
        print("  (none)")

    print(f"\nFLOOD MODE ONLY (no stored path):")
    print("-" * 70)
    print(f"  {len(flood_only)} contacts use flood mode")
    if flood_only[:5]:
        print(f"  Examples: {', '.join(flood_only[:5])}")

    # Summary
    print("\n" + "="*70)
    print("SUMMARY:")
    print(f"  Direct connections:  {len(direct)}")
    print(f"  Routed connections:  {len(with_paths)}")
    print(f"  Flood mode only:     {len(flood_only)}")
    print(f"  Total contacts:      {len(mc.contacts)}")
    print("="*70)

    # Best candidates for testing
    print("\n💡 BEST NODES TO TEST PATH DISCOVERY:")
    print("-" * 70)
    print("Test with nodes that have paths (likely online and responsive):\n")

    test_candidates = []

    # Direct connections
    if direct:
        test_candidates.extend([(n, 0, "direct") for n in direct[:3]])

    # 1-2 hop connections (most reliable)
    good_routes = [(n, h, "routed") for n, h, hops in with_paths if h <= 2]
    test_candidates.extend(good_routes[:3])

    for i, (name, hops, mode) in enumerate(test_candidates, 1):
        print(f"  {i}. {name:30s} ({hops} hops, {mode})")
        print(f"     python3 test_discover_direct.py \"{name}\"")

    print("\n" + "="*70)

    # Disconnect
    await mc.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
