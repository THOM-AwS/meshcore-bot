#!/usr/bin/env python3
"""
Extract channel configuration from MeshCore device config export.
Usage: python3 extract_channels.py <config_file.json>
"""
import json
import sys

if len(sys.argv) != 2:
    print("Usage: python3 extract_channels.py <config_file.json>")
    sys.exit(1)

config_file = sys.argv[1]

try:
    with open(config_file, 'r') as f:
        config = json.load(f)

    if 'channels' not in config:
        print("Error: No channels found in config file")
        sys.exit(1)

    channel_config = {'channels': config['channels']}

    # Print to stdout
    print(json.dumps(channel_config, indent=2))

    # Also save to ~/.meshcore_channels.json
    import os
    output_path = os.path.expanduser('~/.meshcore_channels.json')
    with open(output_path, 'w') as f:
        json.dump(channel_config, f, indent=2)

    print(f"\n✓ Saved channel configuration to {output_path}", file=sys.stderr)
    print(f"✓ Found {len(config['channels'])} channels:", file=sys.stderr)
    for idx, ch in enumerate(config['channels']):
        name = ch.get('name', f'Channel {idx}')
        print(f"  - Index {idx}: {name}", file=sys.stderr)

except FileNotFoundError:
    print(f"Error: Config file not found: {config_file}")
    sys.exit(1)
except json.JSONDecodeError as e:
    print(f"Error: Invalid JSON in config file: {e}")
    sys.exit(1)
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
