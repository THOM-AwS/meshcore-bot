#!/usr/bin/env python3
"""
MeshCore LLM Bot - Entry point with HTTP API support.

This wraps the existing meshcore_bot.py and adds HTTP API functionality
without breaking existing functionality.
"""
import asyncio
import sys
import os

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from meshcore_bot.integrations.api import CommandAPI
from meshcore_bot.config.settings import Settings

# Import the existing bot
from meshcore_bot import MeshCoreBot


async def main():
    """Main entry point with HTTP API support."""
    # Load settings
    settings = Settings.from_env()

    # Initialize the existing bot
    bot = MeshCoreBot(
        serial_port=settings.serial_port,
        aws_profile=settings.aws_profile,
        bedrock_model_id=settings.bedrock_model_id,
        aws_region=settings.aws_region,
        bot_name=settings.bot_name,
        trigger_word=settings.trigger_word
    )

    # Add HTTP API if enabled
    api_server = None
    if settings.api_enabled:
        api_server = CommandAPI(bot, settings.api_host, settings.api_port)

    try:
        # Start API server before bot (non-blocking)
        if api_server:
            await api_server.start()

        # Run the bot (blocking)
        await bot.run()

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        if api_server:
            await api_server.stop()


if __name__ == "__main__":
    asyncio.run(main())
