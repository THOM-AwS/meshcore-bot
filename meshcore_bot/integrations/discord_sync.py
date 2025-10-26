"""Discord integration for bidirectional MeshCore ↔ Discord sync."""
import logging
import asyncio
from typing import Optional, Callable
from datetime import datetime, timezone
import os
import discord
import requests

logger = logging.getLogger('meshcore.bot')


class DiscordSync:
    """Handles bidirectional synchronization between MeshCore and Discord."""

    def __init__(
        self,
        bot_token: Optional[str],
        webhook_url: Optional[str],
        channel_id: Optional[int],
        bot_name: str = "Jeff",
        meshcore_send_callback: Optional[Callable] = None
    ):
        """
        Initialize Discord sync.

        Args:
            bot_token: Discord bot token for receiving messages (two-way sync)
            webhook_url: Discord webhook URL for sending messages (one-way: MeshCore → Discord)
            channel_id: Discord channel ID to monitor for incoming messages
            bot_name: Bot name to display in Discord embeds
            meshcore_send_callback: Async callback to send messages to MeshCore (called when Discord messages arrive)
        """
        self.bot_token = bot_token
        self.webhook_url = webhook_url
        self.channel_id = channel_id
        self.bot_name = bot_name
        self.meshcore_send_callback = meshcore_send_callback
        self.discord_client: Optional[discord.Client] = None
        self.jeff_channel: Optional[int] = None  # MeshCore #jeff channel index

        # Initialize Discord bot client if token provided
        if self.bot_token:
            self.discord_client = self._init_discord_client()

    def set_jeff_channel(self, channel_index: int):
        """Set the MeshCore #jeff channel index for forwarding."""
        self.jeff_channel = channel_index
        logger.info(f"Discord sync will forward to MeshCore channel {channel_index}")

    def _init_discord_client(self) -> discord.Client:
        """Initialize Discord bot client for two-way mirroring."""
        intents = discord.Intents.default()
        intents.message_content = True
        client = discord.Client(intents=intents)

        @client.event
        async def on_ready():
            logger.info(f"🤖 Discord bot connected as {client.user}")

        @client.event
        async def on_message(message):
            # Ignore messages from the bot itself
            if message.author == client.user:
                return

            # Only process messages from the configured channel
            if message.channel.id != self.channel_id:
                return

            # Ignore webhook messages (from MeshCore → Discord)
            if message.webhook_id:
                return

            # Forward Discord message to MeshCore #jeff channel
            text = f"[Discord] {message.author.display_name}: {message.content}"
            logger.info(f"💬 Discord→MeshCore: {text}")

            # Send to MeshCore via callback
            if self.meshcore_send_callback:
                target_channel = self.jeff_channel if self.jeff_channel is not None else 0
                await self.meshcore_send_callback(text, channel=target_channel)

        return client

    async def start_bot(self):
        """Start Discord bot for receiving messages (bidirectional sync)."""
        if not self.discord_client or not self.bot_token:
            logger.warning("Discord bot not configured - skipping bidirectional sync")
            return

        try:
            logger.info("🚀 Starting Discord bot for bidirectional sync...")
            await self.discord_client.start(self.bot_token)
        except Exception as e:
            logger.error(f"Discord bot error: {e}", exc_info=True)

    async def send_to_discord(
        self,
        sender: str,
        message: str,
        channel_name: str = "unknown",
        response: Optional[str] = None
    ):
        """
        Send message to Discord webhook (MeshCore → Discord).

        Args:
            sender: Name of the sender
            message: Original message text
            channel_name: Channel name (e.g., #jeff)
            response: Bot's response (if any)
        """
        if not self.webhook_url:
            return  # Silently skip if no webhook configured

        try:
            # Format the Discord message
            embed = {
                "title": f"📡 Message from {sender}",
                "description": message,
                "color": 0x5865F2,  # Discord blue
                "fields": [
                    {"name": "Channel", "value": channel_name, "inline": True}
                ],
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            # Add response field if Jeff replied
            if response:
                embed["fields"].append({
                    "name": f"🤖 {self.bot_name} replied",
                    "value": response,
                    "inline": False
                })
                embed["color"] = 0x57F287  # Green when bot responds

            payload = {"embeds": [embed]}

            # Send to Discord (async)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: requests.post(self.webhook_url, json=payload, timeout=5))

        except Exception as e:
            logger.error(f"❌ Error sending to Discord: {e}")
