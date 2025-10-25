"""Status command - responds with network status."""
from typing import Dict, Optional, List, Any
import logging
from .base import Command

logger = logging.getLogger('meshcore.bot')


class StatusCommand(Command):
    """Status command - returns online status and node counts."""

    @property
    def name(self) -> str:
        return "status"

    @property
    def aliases(self) -> List[str]:
        return []

    @property
    def help_text(self) -> str:
        return "Show network status and node counts"

    async def execute(self, message: Dict[str, Any], sender_id: str, **kwargs) -> Optional[str]:
        """
        Execute status command.

        Args:
            message: Message dict (not used)
            sender_id: Sender identifier (not used)
            **kwargs: Must include 'meshcore_api' and 'filter_nodes_fn'

        Returns:
            Status response string
        """
        api = kwargs.get('meshcore_api')
        filter_nodes_fn = kwargs.get('filter_nodes_fn')

        if not api or not filter_nodes_fn:
            return "Online|nodes unavailable"

        try:
            sydney_nodes = api.get_sydney_nodes()
            nsw_nodes = api.get_nsw_nodes()

            # Filter to nodes seen in last 7 days
            sydney_active = filter_nodes_fn(sydney_nodes, days=7)
            nsw_active = filter_nodes_fn(nsw_nodes, days=7)

            # Count companions (type 1) vs repeaters (type 2)
            sydney_companions = len([n for n in sydney_active if n.get('type') == 1])
            sydney_repeaters = len([n for n in sydney_active if n.get('type') == 2])
            nsw_companions = len([n for n in nsw_active if n.get('type') == 1])
            nsw_repeaters = len([n for n in nsw_active if n.get('type') == 2])

            return f"Online | Sydney {sydney_companions} companions / {sydney_repeaters} repeaters | NSW {nsw_companions} companions / {nsw_repeaters} repeaters (7d)"

        except Exception as e:
            logger.error(f"Error getting node counts: {e}")
            return "Online|nodes unavailable"
