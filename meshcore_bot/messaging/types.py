"""Message types and data structures."""
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any


class MessageType(Enum):
    """Type of message being sent."""
    RESPONSE = "response"      # Reply to user message
    BROADCAST = "broadcast"    # Scheduled broadcast
    DISCORD_RELAY = "discord"  # Relayed from Discord
    COMMAND = "command"        # Direct command via API


@dataclass
class OutgoingMessage:
    """Represents a message to be sent to the mesh."""
    text: str
    channel: int
    message_type: MessageType
    include_bot_name: bool = True
    log_to_chat: bool = True
    sync_to_discord: Optional[bool] = None  # Auto-detect if None


@dataclass
class IncomingMessage:
    """Represents a message received from the mesh."""
    text: str
    from_id: str
    channel: int
    channel_name: str
    message_id: str
    snr: Optional[float]
    rssi: Optional[int]
    path: Optional[bytes]
    path_len: int
    sender_pubkey: str
    pubkey_prefix: str
    raw_payload: Dict[str, Any]
