"""Base command interface and registry."""
from abc import ABC, abstractmethod
from typing import Dict, Optional, List, Any
import logging

logger = logging.getLogger('meshcore.bot')


class Command(ABC):
    """Base class for all bot commands."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Command name (e.g., 'test', 'ping')."""
        pass

    @property
    @abstractmethod
    def aliases(self) -> List[str]:
        """Command aliases (e.g., ['t'] for test)."""
        pass

    @property
    @abstractmethod
    def help_text(self) -> str:
        """Short help text for this command."""
        pass

    @abstractmethod
    async def execute(self, message: Dict[str, Any], sender_id: str, **kwargs) -> Optional[str]:
        """
        Execute the command.

        Args:
            message: Message dict with metadata
            sender_id: Sender identifier
            **kwargs: Additional context (e.g., meshcore_api, path_utils)

        Returns:
            Response text, or None if no response
        """
        pass

    def matches(self, words: List[str]) -> bool:
        """
        Check if this command matches the given words.

        Args:
            words: List of words from message

        Returns:
            True if command should execute
        """
        triggers = [self.name] + self.aliases
        return any(word in triggers for word in words)


class CommandRegistry:
    """Registry for bot commands."""

    def __init__(self):
        self.commands: Dict[str, Command] = {}

    def register(self, command: Command):
        """Register a command."""
        self.commands[command.name] = command
        logger.debug(f"Registered command: {command.name} (aliases: {command.aliases})")

    def find_command(self, words: List[str]) -> Optional[Command]:
        """
        Find a matching command for the given words.

        Args:
            words: List of words from message

        Returns:
            Matching command, or None
        """
        for command in self.commands.values():
            if command.matches(words):
                return command
        return None

    def get_help(self) -> str:
        """Get help text for all commands."""
        command_names = [cmd.name for cmd in self.commands.values()]
        return f"Commands: {','.join(command_names)} | Or ask me about MeshCore"
