"""Logging configuration for MeshCore bot."""
import logging
import sys
from pathlib import Path


# Chat logger for message history
chat_logger = logging.getLogger('meshcore.chat')


def setup_logging(bot_log_file: str = '/var/log/bot.log',
                  chat_log_file: str = '/var/log/jeff.log') -> logging.Logger:
    """
    Setup logging to separate files for chat and system logs.

    Returns:
        Main bot logger
    """
    # COMPLETELY disable root logger and lastResort
    logging.root.handlers = []
    logging.root.setLevel(logging.CRITICAL)
    logging.lastResort = None
    logging.basicConfig(handlers=[logging.NullHandler()], force=True)

    # Main logger for system/bot logs
    bot_logger = logging.getLogger('meshcore.bot')
    bot_logger.setLevel(logging.DEBUG)
    bot_logger.handlers.clear()
    bot_logger.propagate = False

    # Format with timestamp
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    # File handler for bot logs
    try:
        bot_handler = logging.FileHandler(bot_log_file)
        bot_handler.setFormatter(formatter)
        bot_logger.addHandler(bot_handler)
    except PermissionError:
        # Fallback to local file if can't write to /var/log
        fallback_file = Path.home() / 'bot.log'
        bot_handler = logging.FileHandler(fallback_file)
        bot_handler.setFormatter(formatter)
        bot_logger.addHandler(bot_handler)
        bot_logger.warning(f"Using fallback log file: {fallback_file}")

    # Console handler for development
    if sys.stdout.isatty():
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        bot_logger.addHandler(console_handler)

    # Chat logger for message history
    chat_logger.setLevel(logging.INFO)
    chat_logger.handlers.clear()
    chat_logger.propagate = False

    # Simple format for chat logs (no timestamp prefix, messages add their own)
    chat_formatter = logging.Formatter('%(message)s')

    try:
        chat_handler = logging.FileHandler(chat_log_file)
        chat_handler.setFormatter(chat_formatter)
        chat_logger.addHandler(chat_handler)
    except PermissionError:
        fallback_file = Path.home() / 'jeff.log'
        chat_handler = logging.FileHandler(fallback_file)
        chat_handler.setFormatter(chat_formatter)
        chat_logger.addHandler(chat_handler)

    # Silence noisy libraries
    logging.getLogger('meshcore').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('botocore').setLevel(logging.WARNING)
    logging.getLogger('discord').setLevel(logging.WARNING)
    logging.getLogger('aiohttp').setLevel(logging.WARNING)

    bot_logger.info("✓ Bot logger initialized - writing to " + bot_log_file)
    chat_logger.info("✓ Chat logger initialized - writing to " + chat_log_file)

    return bot_logger
