"""Configuration management for MeshCore bot."""
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Settings:
    """Bot configuration from environment variables."""

    # MeshCore device
    serial_port: str

    # AWS Bedrock
    aws_region: str
    aws_profile: Optional[str]
    bedrock_model_id: str

    # Bot identity
    bot_name: str
    trigger_word: str

    # Discord integration
    discord_webhook_url: Optional[str]
    discord_bot_token: Optional[str]
    discord_channel_id: Optional[int]

    # HTTP API
    api_enabled: bool
    api_host: str
    api_port: int

    @classmethod
    def from_env(cls) -> 'Settings':
        """Load settings from environment variables."""
        discord_channel_id = os.getenv('DISCORD_CHANNEL_ID')

        return cls(
            # MeshCore
            serial_port=os.getenv('MESHCORE_SERIAL_PORT', '/dev/ttyUSB0'),

            # AWS
            aws_region=os.getenv('AWS_REGION', 'us-east-1'),
            aws_profile=os.getenv('AWS_PROFILE'),
            bedrock_model_id=os.getenv(
                'BEDROCK_MODEL_ID',
                'us.anthropic.claude-3-5-haiku-20241022-v1:0'
            ),

            # Bot
            bot_name=os.getenv('BOT_NAME', 'Jeff'),
            trigger_word=os.getenv('TRIGGER_WORD', '@jeff'),

            # Discord
            discord_webhook_url=os.getenv('DISCORD_WEBHOOK_URL'),
            discord_bot_token=os.getenv('DISCORD_BOT_TOKEN'),
            discord_channel_id=int(discord_channel_id) if discord_channel_id else None,

            # API
            api_enabled=os.getenv('API_ENABLED', 'true').lower() == 'true',
            api_host=os.getenv('API_HOST', 'localhost'),
            api_port=int(os.getenv('API_PORT', '8080'))
        )
