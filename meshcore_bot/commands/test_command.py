"""Test command - responds with ack and signal metadata."""
from datetime import datetime
from typing import Dict, Optional, List, Any
from .base import Command


class TestCommand(Command):
    """Test command - responds with ack similar to other bots."""

    @property
    def name(self) -> str:
        return "test"

    @property
    def aliases(self) -> List[str]:
        return ["t"]

    @property
    def help_text(self) -> str:
        return "Test connectivity with ack response"

    async def execute(self, message: Dict[str, Any], sender_id: str, **kwargs) -> Optional[str]:
        """
        Execute test command.

        Args:
            message: Message dict with SNR, RSSI, path_len, etc.
            sender_id: Sender identifier
            **kwargs: Must include 'path_utils' and 'text'

        Returns:
            Ack response string
        """
        path_utils = kwargs.get('path_utils')
        text = kwargs.get('text', '')

        now = datetime.now().strftime("%H:%M:%S")

        # Extract sender name from text (format: "NodeName: test")
        sender_name = sender_id
        if ':' in text:
            sender_name = text.split(':', 1)[0].strip()

        # Build ack response matching Father ROLO's exact format
        # Format: ack $(NAME) | $(path hops) | SNR: X dB | RSSI: X dBm | Received at: $(TIME)
        ack_parts = [f"ack {sender_name}"]

        # Get path from contact out_path data
        if path_utils:
            path_str = await path_utils.get_path_for_test(message, sender_id)
        else:
            path_str = f"{message.get('path_len', 0)}hops"
        ack_parts.append(path_str)

        # Add SNR
        snr = message.get('SNR', 'N/A')
        ack_parts.append(f"SNR: {snr} dB")

        # Add RSSI (if available)
        rssi = message.get('RSSI')
        if rssi is not None:
            ack_parts.append(f"RSSI: {rssi} dBm")
        else:
            ack_parts.append("RSSI: N/A dBm")

        # Add timestamp
        ack_parts.append(f"Received at: {now}")

        return " | ".join(ack_parts)
