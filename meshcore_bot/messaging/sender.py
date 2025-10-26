"""
Unified message sender for MeshCore bot.

NOTE: This module is currently not used by the main bot implementation.
The MeshCoreBot class uses direct calls to meshcore.commands.send_chan_msg()
and meshcore.commands.send_contact_msg() instead.

This module is kept for future refactoring or as a reference implementation
for a cleaner message sending abstraction layer.
"""
import logging
from typing import Optional
from enum import Enum

logger = logging.getLogger('meshcore.bot')


class MessageType(Enum):
    """Types of messages that can be sent."""
    CHANNEL = "channel"
    DIRECT = "direct"
    BROADCAST = "broadcast"


class MessageSender:
    """Handles sending messages to MeshCore device."""

    def __init__(self, meshcore_client):
        """
        Initialize message sender.

        Args:
            meshcore_client: MeshCore client instance with send_channel_message/send_direct_message methods
        """
        self.meshcore = meshcore_client

    async def send_message(
        self,
        text: str,
        channel: Optional[int] = None,
        target_pubkey: Optional[str] = None,
        message_type: MessageType = MessageType.CHANNEL
    ) -> bool:
        """
        Send a message via MeshCore.

        Args:
            text: Message text to send
            channel: Channel index (for channel messages)
            target_pubkey: Target public key (for direct messages)
            message_type: Type of message to send

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            if message_type == MessageType.DIRECT and target_pubkey:
                logger.info(f"📤 Sending DM to {target_pubkey[:8]}: {text}")
                await self.meshcore.commands.send_direct_message(
                    public_key=target_pubkey,
                    text=text
                )
                return True

            elif message_type in (MessageType.CHANNEL, MessageType.BROADCAST):
                # Default to channel 0 (public) if not specified
                target_channel = channel if channel is not None else 0
                logger.info(f"📤 Sending to channel {target_channel}: {text}")
                await self.meshcore.commands.send_channel_message(
                    channel=target_channel,
                    text=text
                )
                return True

            else:
                logger.error(f"Invalid message type: {message_type}")
                return False

        except Exception as e:
            logger.error(f"❌ Error sending message: {e}", exc_info=True)
            return False

    async def send_channel_message(self, text: str, channel: int = 0) -> bool:
        """
        Send a message to a specific channel.

        Args:
            text: Message text
            channel: Channel index (default: 0 for public)

        Returns:
            True if sent successfully
        """
        return await self.send_message(text, channel=channel, message_type=MessageType.CHANNEL)

    async def send_direct_message(self, text: str, target_pubkey: str) -> bool:
        """
        Send a direct message to a specific user.

        Args:
            text: Message text
            target_pubkey: Target user's public key

        Returns:
            True if sent successfully
        """
        return await self.send_message(text, target_pubkey=target_pubkey, message_type=MessageType.DIRECT)

    async def broadcast(self, text: str, channel: int = 0) -> bool:
        """
        Broadcast a message (same as channel message, semantic alias).

        Args:
            text: Message text
            channel: Channel index (default: 0 for public)

        Returns:
            True if sent successfully
        """
        return await self.send_message(text, channel=channel, message_type=MessageType.BROADCAST)
