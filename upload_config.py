#!/usr/bin/env python3
"""
Upload MeshCore configuration to T-Beam device via serial
"""
import serial
import json
import time
import sys

CONFIG_FILE = '/Users/thomashamer/Downloads/Mermann_meshcore_config_2025-10-22-085744.json'
SERIAL_PORT = '/dev/cu.usbserial-5A683153171'
BAUD_RATE = 115200

def send_command(ser, cmd, wait=0.5):
    """Send command and wait for response"""
    print(f"→ {cmd}")
    ser.write(f"{cmd}\r".encode())
    time.sleep(wait)

    # Read response
    response = ""
    while ser.in_waiting:
        response += ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
        time.sleep(0.1)

    if response.strip():
        print(f"← {response.strip()}")
    return response

def upload_config(config_path, port, baud):
    """Upload configuration to device"""

    # Load config
    print(f"\n📂 Loading config from {config_path}")
    with open(config_path, 'r') as f:
        config = json.load(f)

    print(f"✓ Config loaded: {config['name']}")
    print(f"  - {len(config['channels'])} channels")
    print(f"  - {len(config['contacts'])} contacts")

    # Connect to device
    print(f"\n🔌 Connecting to {port} at {baud} baud...")
    ser = serial.Serial(port, baud, timeout=1)
    time.sleep(2)  # Wait for device to be ready

    # Clear any startup messages
    ser.reset_input_buffer()

    print("\n📡 Uploading configuration...\n")

    # 1. Set identity (name, keys)
    print("=== Identity ===")
    send_command(ser, f"set-name {config['name']}")

    # Import private key
    private_key = config['private_key']
    send_command(ser, f"import-key {private_key}", wait=1.0)

    # 2. Set radio settings
    print("\n=== Radio Settings ===")
    rs = config['radio_settings']
    send_command(ser, f"set-freq {rs['frequency']/1000000}")  # Convert Hz to MHz
    send_command(ser, f"set-bw {rs['bandwidth']/1000}")  # Convert Hz to kHz
    send_command(ser, f"set-sf {rs['spreading_factor']}")
    send_command(ser, f"set-cr {rs['coding_rate']}")
    send_command(ser, f"set-power {rs['tx_power']}")

    # 3. Set position
    print("\n=== Position ===")
    ps = config['position_settings']
    send_command(ser, f"set-lat {ps['latitude']}")
    send_command(ser, f"set-lon {ps['longitude']}")

    # 4. Set other settings
    print("\n=== Other Settings ===")
    os = config['other_settings']
    send_command(ser, f"set-manual-add {os['manual_add_contacts']}")
    send_command(ser, f"set-advert-policy {os['advert_location_policy']}")

    # 5. Add channels
    print("\n=== Channels ===")
    for i, channel in enumerate(config['channels']):
        print(f"Channel {i}: {channel['name']}")
        send_command(ser, f"add-channel {i} {channel['name']} {channel['secret']}", wait=0.3)

    # 6. Add contacts (this will take a while with 74 contacts)
    print("\n=== Contacts ===")
    print(f"Adding {len(config['contacts'])} contacts (this may take a few minutes)...")

    for i, contact in enumerate(config['contacts']):
        if i % 10 == 0:
            print(f"  Progress: {i}/{len(config['contacts'])}")

        # Build add-contact command
        cmd = f"add-contact {contact['public_key']} {contact['name']}"
        send_command(ser, cmd, wait=0.2)

    print(f"  Progress: {len(config['contacts'])}/{len(config['contacts'])}")

    # 7. Save configuration
    print("\n=== Saving ===")
    send_command(ser, "save", wait=2.0)

    ser.close()

    print("\n✅ Configuration uploaded successfully!")
    print("\nThe device should now reboot with your configuration.")

if __name__ == '__main__':
    try:
        upload_config(CONFIG_FILE, SERIAL_PORT, BAUD_RATE)
    except FileNotFoundError:
        print(f"❌ Error: Config file not found at {CONFIG_FILE}")
        sys.exit(1)
    except serial.SerialException as e:
        print(f"❌ Error: Could not connect to device: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Upload interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
