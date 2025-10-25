"""Help command - shows available commands."""
from typing import Dict, Optional, List, Any
from .base import Command


class HelpCommand(Command):
    """Help command - shows available commands."""

    @property
    def name(self) -> str:
        return "help"

    @property
    def aliases(self) -> List[str]:
        return []

    @property
    def help_text(self) -> str:
        return "Show this help message"

    async def execute(self, message: Dict[str, Any], sender_id: str, **kwargs) -> Optional[str]:
        """
        Execute help command.

        Args:
            message: Message dict (not used)
            sender_id: Sender identifier (not used)
            **kwargs: May include 'registry' for dynamic command list

        Returns:
            Help message string
        """
        registry = kwargs.get('registry')

        if registry:
            return registry.get_help()
        else:
            # Fallback static help
            return "Commands: test,ping,path,status,nodes,route,trace,help | Or ask me about MeshCore"
