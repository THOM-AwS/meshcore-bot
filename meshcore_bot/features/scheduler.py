"""Scheduled broadcasts for MeshCore bot."""
import logging
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Dict

logger = logging.getLogger('meshcore.bot')
chat_logger = logging.getLogger('meshcore.chat')


class BroadcastScheduler:
    """Handles scheduled status broadcasts to MeshCore channels."""

    def __init__(
        self,
        meshcore_api,
        send_callback: Callable,
        jeff_channel: int,
        channel_map: Dict[int, str],
        broadcast_hours: List[int] = None
    ):
        """
        Initialize broadcast scheduler.

        Args:
            meshcore_api: MeshCoreAPI instance for node lookups
            send_callback: Async callback to send messages (takes text, channel)
            jeff_channel: Channel index for #jeff broadcasts
            channel_map: Map of channel indices to names
            broadcast_hours: Hours to broadcast (default: [0, 6, 12, 18])
        """
        self.api = meshcore_api
        self.send_callback = send_callback
        self.jeff_channel = jeff_channel
        self.channel_map = channel_map
        self.broadcast_hours = broadcast_hours or [0, 6, 12, 18]
        self._running = False

    def filter_nodes_by_days(self, nodes: List[Dict], days: int = 7) -> List[Dict]:
        """
        Filter nodes seen in the last N days.

        Args:
            nodes: List of node dictionaries
            days: Number of days to look back

        Returns:
            Filtered list of active nodes
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        active_nodes = []

        for node in nodes:
            last_advert = node.get('last_advert')
            if last_advert:
                try:
                    last_dt = datetime.fromisoformat(last_advert.replace('Z', '+00:00'))
                    if last_dt >= cutoff:
                        active_nodes.append(node)
                except:
                    pass  # Skip nodes with unparseable timestamps

        return active_nodes

    async def broadcast_status(self):
        """Broadcast network status on #jeff channel."""
        try:
            # Ensure we have a jeff channel configured
            if self.jeff_channel is None:
                logger.error("❌ Cannot broadcast: #jeff channel not found")
                return

            # Get current time
            now = datetime.now()
            time_str = now.strftime("%I:%M %p").lstrip("0")  # e.g., "6:00 AM"

            # Get network status from API
            sydney_nodes = self.api.get_sydney_nodes()
            nsw_nodes = self.api.get_nsw_nodes()

            # Filter to nodes seen in last 7 days
            sydney_active = self.filter_nodes_by_days(sydney_nodes, days=7)
            nsw_active = self.filter_nodes_by_days(nsw_nodes, days=7)

            # Count companions (type 1) vs repeaters (type 2), exclude other types
            sydney_companions = len([n for n in sydney_active if n.get('type') == 1])
            sydney_repeaters = len([n for n in sydney_active if n.get('type') == 2])
            nsw_companions = len([n for n in nsw_active if n.get('type') == 1])
            nsw_repeaters = len([n for n in nsw_active if n.get('type') == 2])

            # Format status message
            status_msg = (f"Companion/Repeater Count | "
                         f"NSW {nsw_companions}/{nsw_repeaters} | "
                         f"Sydney {sydney_companions}/{sydney_repeaters}")

            logger.info(f"📢 Broadcasting scheduled status to channel {self.jeff_channel}: {status_msg}")

            # Log to chat file
            channel_name = self.channel_map.get(self.jeff_channel, f'ch{self.jeff_channel}')
            chat_logger.info(f"[{channel_name}] Jeff: {status_msg}")

            # Send via callback
            await self.send_callback(status_msg, channel=self.jeff_channel)

        except Exception as e:
            logger.error(f"❌ Error broadcasting status: {e}", exc_info=True)

    async def run(self):
        """Background task that broadcasts status at configured hours."""
        logger.info(f"🕐 Starting scheduled broadcast loop ({', '.join([f'{h}:00' for h in self.broadcast_hours])})")
        self._running = True

        while self._running:
            try:
                now = datetime.now()
                current_hour = now.hour

                # Check if we're at a broadcast hour
                if current_hour in self.broadcast_hours:
                    # Check if we're within the first 2 minutes of the hour (more tolerant window)
                    if now.minute < 2:
                        await self.broadcast_status()
                        # Sleep until the next hour to avoid duplicate broadcasts
                        # Calculate seconds until next hour
                        seconds_until_next_hour = 3600 - (now.minute * 60 + now.second)
                        await asyncio.sleep(seconds_until_next_hour)
                        continue

                # Sleep for 30 seconds before checking again
                await asyncio.sleep(30)

            except Exception as e:
                logger.error(f"❌ Error in scheduled broadcast loop: {e}", exc_info=True)
                await asyncio.sleep(60)  # Wait a minute before retrying

    def stop(self):
        """Stop the broadcast scheduler."""
        self._running = False
        logger.info("🛑 Stopping broadcast scheduler")
