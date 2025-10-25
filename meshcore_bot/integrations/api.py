"""HTTP API server for sending commands to running bot."""
import logging
from typing import Optional
from aiohttp import web
import json

logger = logging.getLogger('meshcore.bot')


class CommandAPI:
    """HTTP API for sending commands to the bot without interrupting it."""

    def __init__(self, bot, host: str = 'localhost', port: int = 8080):
        """
        Initialize command API.

        Args:
            bot: Reference to the bot instance
            host: Host to bind to
            port: Port to listen on
        """
        self.bot = bot
        self.host = host
        self.port = port
        self.app = web.Application()
        self.runner: Optional[web.AppRunner] = None

        # Setup routes
        self.app.router.add_post('/send', self.send_handler)
        self.app.router.add_get('/status', self.status_handler)
        self.app.router.add_get('/health', self.health_handler)

    async def send_handler(self, request: web.Request) -> web.Response:
        """
        Handle send message requests.

        POST /send
        Body: {"message": "text", "channel": 7}
        """
        try:
            data = await request.json()
            message = data.get('message')
            channel = data.get('channel', 7)  # Default to #jeff

            if not message:
                return web.json_response(
                    {'status': 'error', 'message': 'Message is required'},
                    status=400
                )

            logger.info(f"🔌 API request: Send to ch{channel}: {message}")

            # Send via bot's send_message method
            await self.bot.send_message(message, channel)

            return web.json_response({
                'status': 'ok',
                'message': message,
                'channel': channel
            })

        except json.JSONDecodeError:
            return web.json_response(
                {'status': 'error', 'message': 'Invalid JSON'},
                status=400
            )
        except Exception as e:
            logger.error(f"API send error: {e}", exc_info=True)
            return web.json_response(
                {'status': 'error', 'message': str(e)},
                status=500
            )

    async def status_handler(self, request: web.Request) -> web.Response:
        """
        Get bot status.

        GET /status
        """
        return web.json_response({
            'status': 'ok',
            'bot_name': self.bot.bot_name,
            'connected': self.bot.meshcore is not None and self.bot.meshcore.is_connected,
            'channels': self.bot.channel_map
        })

    async def health_handler(self, request: web.Request) -> web.Response:
        """
        Health check endpoint.

        GET /health
        """
        return web.json_response({'status': 'healthy'})

    async def start(self):
        """Start the API server."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()

        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()

        logger.info(f"📡 HTTP API listening on http://{self.host}:{self.port}")
        logger.info(f"   POST /send - Send message to mesh")
        logger.info(f"   GET /status - Get bot status")
        logger.info(f"   GET /health - Health check")

    async def stop(self):
        """Stop the API server."""
        if self.runner:
            await self.runner.cleanup()
            logger.info("📡 HTTP API stopped")
