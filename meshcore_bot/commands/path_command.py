"""Path command - shows routing path with suburbs."""
from typing import Dict, Optional, List, Any
from .base import Command


class PathCommand(Command):
    """Path command - shows compact routing path with suburbs."""

    @property
    def name(self) -> str:
        return "path"

    @property
    def aliases(self) -> List[str]:
        return ["route", "trace"]

    @property
    def help_text(self) -> str:
        return "Show routing path"

    async def execute(self, message: Dict[str, Any], sender_id: str, **kwargs) -> Optional[str]:
        """
        Execute path command.

        Args:
            message: Message dict with path info
            sender_id: Sender identifier
            **kwargs: Must include 'path_utils'

        Returns:
            Compact path string
        """
        path_utils = kwargs.get('path_utils')

        if not path_utils:
            return f"{sender_id} -> YOU"

        compact_path = await path_utils.get_compact_path(message, sender_id)
        return compact_path
