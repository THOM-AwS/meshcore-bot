"""Ping command - responds with pong and signal data."""
from datetime import datetime
from typing import Dict, Optional, List, Any
from .base import Command


class PingCommand(Command):
    """Ping command - responds with pong and signal quality."""

    @property
    def name(self) -> str:
        return "ping"

    @property
    def aliases(self) -> List[str]:
        return []

    @property
    def help_text(self) -> str:
        return "Ping with signal quality data"

    async def execute(self, message: Dict[str, Any], sender_id: str, **kwargs) -> Optional[str]:
        """
        Execute ping command.

        Args:
            message: Message dict with SNR, RSSI
            sender_id: Sender identifier
            **kwargs: Not used

        Returns:
            Pong response string
        """
        now = datetime.now().strftime("%H:%M:%S")
        pong_parts = ["pong"]

        # Add signal quality data if available
        snr = message.get('SNR')
        rssi = message.get('RSSI')
        if snr is not None:
            pong_parts.append(f"SNR:{snr}dB")
        if rssi is not None:
            pong_parts.append(f"RSSI:{rssi}dBm")
        pong_parts.append(now)

        return "|".join(pong_parts)
