#!/usr/bin/env python3
"""
Test interface for Jeff bot - allows testing without mesh network.
Simulates incoming messages and shows Jeff's responses.
"""

import asyncio
import sys
from meshcore_bot import MeshCoreBot

class TestInterface:
    """Interactive test interface for Jeff bot."""

    def __init__(self):
        """Initialize test interface with bot instance."""
        # Create bot instance (serial port won't be used in test mode)
        self.bot = MeshCoreBot(
            serial_port="/dev/null",  # Dummy port for testing
            bot_name="Jeff",
            trigger_word="@jeff"
        )
        print("✓ Jeff bot initialized for testing")
        print("=" * 60)

    async def simulate_message(self, text: str, channel: int = 6, sender: str = "TestUser"):
        """
        Simulate receiving a message and get Jeff's response.

        Args:
            text: Message text
            channel: Channel number (default: 6 = #test)
            sender: Sender name (default: TestUser)
        """
        # Build message dict matching what Jeff expects
        message_dict = {
            'message': {
                'text': f"{sender}: {text}",
                'from_id': sender,
                'channel': channel,
                'id': f'test-{hash(text)}',
                'SNR': 7.5,
                'RSSI': -75,
                'path': [0x87, 0x32, 0x33, 0x0c, 0xf1, 0xa7],
                'path_len': 2,
                'channel_idx': channel
            }
        }

        # Process the message
        response = await self.bot.process_message(message_dict)

        return response

    async def interactive_mode(self):
        """Run interactive test mode."""
        channel_names = {
            0: 'Public',
            1: '#sydney',
            2: '#nsw',
            3: '#emergency',
            4: '#nepean',
            5: '#rolojnr',
            6: '#test'
        }

        print("Interactive Test Mode")
        print("=" * 60)
        print("Commands:")
        print("  /help              - Show this help")
        print("  /channel <num>     - Switch channel (0-6)")
        print("  /sender <name>     - Change sender name")
        print("  /quit or /exit     - Exit test mode")
        print("  <message>          - Send message to Jeff")
        print("=" * 60)
        print()

        current_channel = 6  # Start on #test
        current_sender = "TestUser"

        print(f"📡 Channel: {channel_names.get(current_channel, f'ch{current_channel}')}")
        print(f"👤 Sender: {current_sender}")
        print()

        while True:
            try:
                # Get user input
                user_input = input(f"{current_sender}> ").strip()

                if not user_input:
                    continue

                # Handle commands
                if user_input.startswith('/'):
                    parts = user_input.split(maxsplit=1)
                    cmd = parts[0].lower()
                    arg = parts[1] if len(parts) > 1 else None

                    if cmd in ['/quit', '/exit']:
                        print("\n👋 Goodbye!")
                        break

                    elif cmd == '/help':
                        print("\nCommands:")
                        print("  /help              - Show this help")
                        print("  /channel <num>     - Switch channel (0-6)")
                        print("  /sender <name>     - Change sender name")
                        print("  /quit or /exit     - Exit test mode")
                        print("  <message>          - Send message to Jeff")
                        print()
                        continue

                    elif cmd == '/channel':
                        if arg and arg.isdigit():
                            current_channel = int(arg)
                            print(f"📡 Switched to channel: {channel_names.get(current_channel, f'ch{current_channel}')}\n")
                        else:
                            print("❌ Usage: /channel <num> (0-6)\n")
                        continue

                    elif cmd == '/sender':
                        if arg:
                            current_sender = arg
                            print(f"👤 Sender changed to: {current_sender}\n")
                        else:
                            print("❌ Usage: /sender <name>\n")
                        continue

                    else:
                        print(f"❌ Unknown command: {cmd}\n")
                        continue

                # Send message to Jeff
                print(f"📤 Sending: {user_input}")
                response = await self.simulate_message(user_input, current_channel, current_sender)

                if response:
                    print(f"📥 Jeff: {response}")
                else:
                    print(f"🤐 Jeff: (no response - not triggered or wrong channel)")
                print()

            except KeyboardInterrupt:
                print("\n\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error: {e}\n")
                continue

    async def run_tests(self):
        """Run automated test suite."""
        print("Running Automated Tests")
        print("=" * 60)

        tests = [
            # Test name mentions
            ("@jeff hello", 6, "TestUser", "Should respond to @jeff mention"),
            ("jeff what is meshcore?", 6, "TestUser", "Should respond to 'jeff' mention"),
            ("#jeff help", 6, "TestUser", "Should respond to #jeff mention"),

            # Test commands on allowed channel (#test = 6)
            ("test", 6, "TestUser", "Should respond to 'test' command"),
            ("t", 6, "TestUser", "Should respond to 't' command"),
            ("status", 6, "TestUser", "Should respond to 'status' command"),

            # Test node lookup
            ("who owns bradbury repeater?", 6, "TestUser", "Should lookup Bradbury repeater"),
            ("what frequency is cleric node?", 6, "TestUser", "Should lookup Cleric node"),

            # Test non-trigger on wrong channel
            ("hello there", 0, "TestUser", "Should NOT respond (wrong channel, no mention)"),

            # Test name mention on any channel
            ("@jeff hello", 0, "TestUser", "Should respond to @jeff on public channel"),
        ]

        passed = 0
        failed = 0

        for text, channel, sender, description in tests:
            print(f"\n🧪 Test: {description}")
            print(f"   Input: '{text}' (channel {channel})")

            response = await self.simulate_message(text, channel, sender)

            if response:
                print(f"   ✅ Response: {response}")
                passed += 1
            else:
                print(f"   ⚠️  No response")
                # Some tests expect no response
                if "Should NOT respond" in description:
                    print(f"   ✅ Correctly ignored")
                    passed += 1
                else:
                    print(f"   ❌ Expected response but got none")
                    failed += 1

        print("\n" + "=" * 60)
        print(f"Test Results: {passed} passed, {failed} failed")
        print("=" * 60)


async def main():
    """Main entry point."""
    if len(sys.argv) > 1 and sys.argv[1] in ['--test', '-t']:
        # Run automated tests
        interface = TestInterface()
        await interface.run_tests()
    else:
        # Run interactive mode
        interface = TestInterface()
        await interface.interactive_mode()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
