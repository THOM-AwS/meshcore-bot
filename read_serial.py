#!/usr/bin/env python3
import serial
import time
import sys

port = '/dev/cu.usbserial-5A683153171'
baud = 115200

try:
    ser = serial.Serial(port, baud, timeout=0.1)
    print(f"Connected to {port} at {baud} baud")
    print("Reading serial output (Ctrl+C to stop)...\n")

    while True:
        if ser.in_waiting:
            try:
                line = ser.readline().decode('utf-8', errors='ignore').rstrip()
                if line:
                    print(line)
                    sys.stdout.flush()
            except Exception as e:
                print(f"Error reading: {e}")
        time.sleep(0.01)

except KeyboardInterrupt:
    print("\nStopped by user")
except Exception as e:
    print(f"Error: {e}")
finally:
    if 'ser' in locals():
        ser.close()
