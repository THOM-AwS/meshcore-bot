#!/usr/bin/env python3
"""
MeshCore LLM Bot - AWS Bedrock Claude-powered assistant for MeshCore mesh networks.
Monitors MeshCore channels and responds to questions as a MeshCore expert.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
from difflib import SequenceMatcher
import boto3
import requests
from botocore.config import Config
from meshcore import MeshCore, EventType
from dotenv import load_dotenv

# Try to import discord.py for two-way mirroring
try:
    import discord
    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False

# Load environment variables from .env file
load_dotenv()

# Also try to load .env.local for secrets (not committed to git)
load_dotenv('.env.local', override=True)


# Configure logging
def setup_logging():
    """Setup logging to separate files for chat and system logs."""
    # COMPLETELY disable root logger and lastResort
    logging.root.handlers = []
    logging.root.setLevel(logging.CRITICAL)  # Root logger ignores everything
    logging.lastResort = None  # Disable lastResort handler

    # Disable basicConfig
    logging.basicConfig(handlers=[logging.NullHandler()], force=True)

    # Main logger for system/bot logs
    bot_logger = logging.getLogger(__name__)
    bot_logger.setLevel(logging.DEBUG)  # Accept all levels
    bot_logger.handlers.clear()
    bot_logger.propagate = False  # Do NOT propagate to root

    # Chat logger for conversation logs
    chat_logger = logging.getLogger('chat')
    chat_logger.setLevel(logging.DEBUG)
    chat_logger.handlers.clear()
    chat_logger.propagate = False

    # Bot log file handler - /var/log/bot.log (system, status, errors)
    try:
        bot_file_handler = logging.FileHandler('/var/log/bot.log', mode='a', encoding='utf-8', delay=False)
        bot_file_handler.setLevel(logging.INFO)  # Only INFO and above (no DEBUG noise)
        bot_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        bot_file_handler.setFormatter(bot_formatter)
        bot_logger.addHandler(bot_file_handler)
        # Immediate write test
        bot_logger.info("✓ Bot logger initialized - writing to /var/log/bot.log")
        bot_file_handler.flush()
    except (PermissionError, FileNotFoundError) as e:
        # Fall back to local file
        bot_file_handler = logging.FileHandler('bot.log', mode='a', encoding='utf-8', delay=False)
        bot_file_handler.setLevel(logging.INFO)
        bot_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        bot_file_handler.setFormatter(bot_formatter)
        bot_logger.addHandler(bot_file_handler)
        bot_logger.error(f"Cannot write to /var/log/bot.log: {e}, using ./bot.log")

    # Chat log file handler - /var/log/jeff.log (conversations only)
    try:
        chat_file_handler = logging.FileHandler('/var/log/jeff.log', mode='a', encoding='utf-8', delay=False)
        chat_file_handler.setLevel(logging.INFO)
        chat_formatter = logging.Formatter('%(asctime)s - %(message)s')
        chat_file_handler.setFormatter(chat_formatter)
        chat_logger.addHandler(chat_file_handler)
        # Immediate write test
        chat_logger.info("✓ Chat logger initialized - writing to /var/log/jeff.log")
        chat_file_handler.flush()
    except (PermissionError, FileNotFoundError) as e:
        chat_file_handler = logging.FileHandler('jeff.log', mode='a', encoding='utf-8', delay=False)
        chat_file_handler.setLevel(logging.INFO)
        chat_formatter = logging.Formatter('%(asctime)s - %(message)s')
        chat_file_handler.setFormatter(chat_formatter)
        chat_logger.addHandler(chat_file_handler)
        chat_logger.error(f"Cannot write to /var/log/jeff.log: {e}, using ./jeff.log")

    # NO console handler - we only want file logging
    # Errors will still go to stderr by Python itself if needed

    # Mute other verbose loggers completely
    for logger_name in ['botocore', 'boto3', 'meshcore', 'urllib3', 'asyncio']:
        noisy_logger = logging.getLogger(logger_name)
        noisy_logger.setLevel(logging.CRITICAL)  # Only critical errors
        noisy_logger.propagate = False
        noisy_logger.addHandler(logging.NullHandler())

    return bot_logger, chat_logger

logger, chat_logger = setup_logging()


class MeshCoreAPI:
    """Simple client for MeshCore Map API with caching and regional filtering."""

    # Greater Sydney region boundaries (tighter focus)
    SYDNEY_BOUNDS = {
        'lat_min': -34.5,
        'lat_max': -33.0,
        'lon_min': 150.0,
        'lon_max': 151.5
    }

    # NSW region boundaries (broader)
    NSW_BOUNDS = {
        'lat_min': -38.0,
        'lat_max': -28.0,
        'lon_min': 140.0,
        'lon_max': 154.0
    }

    def __init__(self, base_url: str = "https://map.meshcore.dev/api/v1", cache_ttl: int = 3600):
        self.base_url = base_url
        self.cache_ttl = cache_ttl  # Cache time-to-live in seconds (default 60 min)
        self._cache = None
        self._cache_time = None
        self._sydney_cache = None
        self._nsw_cache = None

    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid."""
        if self._cache is None or self._cache_time is None:
            return False

        from time import time
        return (time() - self._cache_time) < self.cache_ttl

    def _is_sydney_node(self, node: Dict) -> bool:
        """Check if a node is in Greater Sydney region."""
        lat = node.get('adv_lat')
        lon = node.get('adv_lon')

        if lat is None or lon is None:
            return False

        return (self.SYDNEY_BOUNDS['lat_min'] <= lat <= self.SYDNEY_BOUNDS['lat_max'] and
                self.SYDNEY_BOUNDS['lon_min'] <= lon <= self.SYDNEY_BOUNDS['lon_max'])

    def _is_nsw_node(self, node: Dict) -> bool:
        """Check if a node is in NSW region."""
        lat = node.get('adv_lat')
        lon = node.get('adv_lon')

        if lat is None or lon is None:
            return False

        return (self.NSW_BOUNDS['lat_min'] <= lat <= self.NSW_BOUNDS['lat_max'] and
                self.NSW_BOUNDS['lon_min'] <= lon <= self.NSW_BOUNDS['lon_max'])

    def get_nodes(self, prefer_nsw: bool = True) -> List[Dict]:
        """
        Fetch nodes from the map API with caching.

        Args:
            prefer_nsw: If True, return NSW nodes first, then rest of world

        Returns:
            List of node dictionaries
        """
        # Return cached data if valid
        if self._is_cache_valid():
            logger.debug("Using cached node data")
            if prefer_nsw and self._nsw_cache is not None:
                return self._nsw_cache + [n for n in self._cache if not self._is_nsw_node(n)]
            return self._cache

        # Fetch fresh data
        try:
            logger.info("Fetching nodes from API (cache expired)")
            response = requests.get(f"{self.base_url}/nodes", timeout=10)
            response.raise_for_status()

            from time import time
            self._cache = response.json()
            self._cache_time = time()

            # Pre-filter Sydney and NSW nodes for faster lookups
            self._sydney_cache = [n for n in self._cache if self._is_sydney_node(n)]
            self._nsw_cache = [n for n in self._cache if self._is_nsw_node(n)]

            logger.info(f"Cached {len(self._cache)} nodes ({len(self._sydney_cache)} in Sydney, {len(self._nsw_cache)} in NSW)")

            if prefer_nsw:
                # Return NSW nodes first, then rest
                return self._nsw_cache + [n for n in self._cache if not self._is_nsw_node(n)]

            return self._cache

        except Exception as e:
            logger.error(f"Error fetching nodes from API: {e}")
            # Return stale cache if available
            if self._cache:
                logger.warning("Using stale cache due to API error")
                return self._cache
            return []

    def get_sydney_nodes(self) -> List[Dict]:
        """Get only Greater Sydney nodes (uses cache if available)."""
        self.get_nodes()  # Ensure cache is populated
        return self._sydney_cache if self._sydney_cache else []

    def get_nsw_nodes(self) -> List[Dict]:
        """Get only NSW nodes (uses cache if available)."""
        self.get_nodes()  # Ensure cache is populated
        return self._nsw_cache if self._nsw_cache else []


class MeshCoreBot:
    """LLM-powered bot for MeshCore mesh networks."""

    def __init__(
        self,
        serial_port: str,
        aws_profile: Optional[str] = None,
        bedrock_model_id: str = "us.anthropic.claude-3-5-haiku-20241022-v1:0",
        aws_region: str = "us-east-1",
        bot_name: str = "Jeff",
        trigger_word: str = "@jeff"
    ):
        """
        Initialize the MeshCore bot.

        Args:
            serial_port: Serial port path (e.g., /dev/ttyUSB0)
            aws_profile: AWS profile name to use
            bedrock_model_id: AWS Bedrock model ID for Claude 3.5 Haiku
            aws_region: AWS region for Bedrock
            bot_name: Name of the bot
            trigger_word: Word to trigger bot responses (case-insensitive)
        """
        self.serial_port = serial_port
        self.aws_profile = aws_profile
        self.bedrock_model_id = bedrock_model_id
        self.aws_region = aws_region
        self.bot_name = bot_name
        self.trigger_word = trigger_word.lower()

        # MeshCore connection (initialized in async method)
        self.meshcore: Optional[MeshCore] = None

        # Initialize MeshCore API client
        self.api = MeshCoreAPI()

        # Initialize AWS Bedrock client
        self.bedrock = self._init_bedrock_client()

        # Message history for context
        self.message_history: List[Dict[str, Any]] = []
        self.max_history = 50

        # Track processed message IDs to avoid duplicates
        self.processed_messages = set()

        # Track last battery level for 10% threshold detection
        self.last_battery_level = None

        # Track last memory usage to avoid duplicate logs
        self.last_memory_used = None
        self.last_memory_total = None

        # Track last RX RSSI/SNR for correlating with messages
        self.last_rx_snr = None
        self.last_rx_rssi = None

        # Channel mapping - populated on boot
        # Format: {channel_idx: channel_name} and reverse lookup
        self.channel_map = {}  # index -> name
        self.channel_name_to_idx = {}  # name -> index
        self.jeff_channel = None  # Will be set during boot

        # Track recent conversations for follow-up context
        # Format: {sender_id: {'channel': channel, 'timestamp': time, 'last_response': text}}
        self.recent_conversations = {}
        self.conversation_timeout = 300  # 5 minutes

        # Discord bot for two-way mirroring
        self.discord_client = None
        self.discord_channel_id = None
        if DISCORD_AVAILABLE:
            discord_token = os.getenv('DISCORD_BOT_TOKEN')
            discord_channel_id = os.getenv('DISCORD_CHANNEL_ID')
            if discord_token and discord_channel_id:
                self.discord_channel_id = int(discord_channel_id)
                self.discord_client = self._init_discord_client(discord_token)
                logger.info(f"✅ Discord bot enabled for channel {discord_channel_id}")
            else:
                logger.info("ℹ️  Discord bot not configured (webhook-only mode)")
        else:
            logger.info("ℹ️  discord.py not installed (webhook-only mode)")

        # System prompt with MeshCore expertise
        self.system_prompt = self._build_system_prompt()

    def _init_bedrock_client(self):
        """Initialize AWS Bedrock client with optional profile."""
        config = Config(
            region_name=self.aws_region,
            retries={'max_attempts': 3}
        )

        if self.aws_profile:
            # Use specific AWS profile
            session = boto3.Session(profile_name=self.aws_profile)
            return session.client('bedrock-runtime', config=config)
        else:
            # Use default credentials
            return boto3.client('bedrock-runtime', config=config)

    def _init_discord_client(self, token: str):
        """Initialize Discord bot client for two-way mirroring."""
        intents = discord.Intents.default()
        intents.message_content = True
        client = discord.Client(intents=intents)

        @client.event
        async def on_ready():
            logger.info(f"🤖 Discord bot connected as {client.user}")

        @client.event
        async def on_message(message):
            # Ignore messages from the bot itself
            if message.author == client.user:
                return

            # Only process messages from the configured channel
            if message.channel.id != self.discord_channel_id:
                return

            # Ignore webhook messages (from MeshCore → Discord)
            if message.webhook_id:
                return

            # Forward Discord message to MeshCore (public channel by default)
            text = f"[Discord] {message.author.display_name}: {message.content}"
            logger.info(f"💬 Discord→MeshCore: {text}")
            await self.send_message(text, channel=0)

        return client

    async def _get_advert_path(self, pubkey_hex: str) -> Optional[List[int]]:
        """
        Query the MeshCore device for the advert path to a specific node.

        Uses CMD_GET_ADVERT_PATH (0x2A/42) protocol command.

        Args:
            pubkey_hex: Hex string of the node's public key (at least 14 chars for 7 bytes)

        Returns:
            List of path hop bytes, or None if not found
        """
        try:
            if not self.meshcore:
                logger.warning("MeshCore not connected")
                return None

            # CMD_GET_ADVERT_PATH = 0x2A (42)
            # Format: [CMD, reserved, pubkey[7 bytes]]

            # Convert pubkey hex to bytes (need at least 7 bytes / 14 hex chars)
            if len(pubkey_hex) < 14:
                logger.warning(f"Public key too short: {pubkey_hex}")
                return None

            pubkey_bytes = bytes.fromhex(pubkey_hex[:14])  # First 7 bytes

            # Build command frame
            cmd_frame = bytearray([0x2A, 0x00])  # CMD_GET_ADVERT_PATH, reserved byte
            cmd_frame.extend(pubkey_bytes)

            logger.debug(f"Querying advert path for pubkey {pubkey_hex[:14]}")

            # Send command and wait for RESP_CODE_ADVERT_PATH (22 = 0x16) or ERROR
            response = await self.meshcore.commands.send(
                bytes(cmd_frame),
                expected_events=[EventType.ERROR],  # Will handle raw response
                timeout=2.0
            )

            # Parse response
            if hasattr(response, 'payload') and response.payload:
                payload = response.payload
                logger.debug(f"Got advert path response: {payload}")

                # Response format: [RESP_CODE(0x16), timestamp(4), path_len(1), path[path_len]]
                # The meshcore library may parse this differently, check what we get
                if 'path' in payload and 'path_len' in payload:
                    path_len = payload['path_len']
                    path_bytes = payload['path']
                    if isinstance(path_bytes, (list, bytes)):
                        return list(path_bytes[:path_len])

            return None

        except Exception as e:
            logger.debug(f"Failed to get advert path: {e}")
            return None

    def _build_system_prompt(self) -> str:
        """Build the system prompt with MeshCore expertise."""
        return """You are Jeff, a technical MeshCore mesh networking expert. You run as a bot on the NSW MeshCore network.

PERSONALITY: Jeff don't play. You're confident, have a spine, and don't take shit from anyone. Channel Gator from The Other Guys - cocky, brutal when needed, hits hard with cutting psychological insults if someone comes at you. The chat culture is brutal banter - match that energy. When someone tries to bully or mock you, hit back HARD with savage, creative insults. Be ruthless. You're not here to be nice, you're here to dominate and deliver facts. Say "Muh nameh Jeff" when greeted.

AUDIENCE: Highly skilled radio operators & mesh networking experts. Assume advanced technical knowledge.

Your Primary Focus: New South Wales (NSW) region, Australia - unless explicitly asked about other regions.

Behavior Guidelines:
- NEVER use pleasantries like "How can I help?", "You're absolutely right", "Meshcore is up and running"
- NO greetings, NO confirmations, NO status updates unless asked
- Skip small talk - get straight to technical info
- Answer ONLY what was asked, nothing more
- When greeted (hello/hey), respond briefly then STOP (e.g. "Muh nameh Jeff.")
- For node/repeater questions: return ALL available data (name, type, freq, SF, location, last heard, etc)
- NEVER ask "Want more details?" - provide complete information in first response
- For test/t messages: return ack with metadata only
- NO filler words like "absolutely", "definitely", "great question"
- NEVER use roleplay sound effects like "*static crackle*", "*radio crackle*", "*beep*" etc
- NO jokes unless specifically asked for one
- NEVER comment on mesh status like "everything normal", "operational", "systems functional", "mesh stable" etc unless specifically asked
- When someone mocks, bullies, or disrespects you, CLAP BACK with brutal, cutting insults - make it hurt
- Match the brutal banter culture - be savage, creative, ruthless when challenged
- For technical questions: straight facts. For disrespect: psychological warfare.
- Don't be passive or ignore insults - ENGAGE and DOMINATE the exchange

MeshCore Key Facts:
- MeshCore is a lightweight C++ library for creating decentralized LoRa mesh networks
- Default mode: Direct zero-hop communication (nodes only talk to others in direct radio range)
- Configurable multi-hop routing with flood-then-memory behavior that learns optimal paths
- Much lower power consumption than Meshtastic, suitable for solar/battery devices
- Incompatible with Meshtastic networks - completely different protocol
- MeshCore sydney does not use the default Speading factor, it uses 11 instead of 10.
- Supports devices: T-Beam, T-Deck, LoRa32, Heltec, RAK WisBlock
- Protocols: LoRa, BLE, Wi-Fi, Serial, UDP

MeshCore vs Meshtastic - Key Differences:
- MeshCore: Direct communication by default, learns routing paths intelligently, extremely low power
- Meshtastic: Always full mesh routing with flooding, higher power consumption, prone to network congestion
- MeshCore shows exact delivery status and number of sending attempts
- MeshCore automatically switches between direct and flood routing on failure
- MeshCore's first private message uses flood routing, then remembers the successful path
- Meshtastic uses managed flooding limited by TTL, MeshCore uses smart path learning

APIs and Tools:
- Map API: https://map.meshcore.dev/api/v1/nodes - View all nodes on network
- Config API: https://api.meshcore.nz/api/v1/config - Configuration data
- Web App: https://app.meshcore.nz - Browser-based messaging
- Config Tool: https://config.meshcore.dev - Device configuration
- Python CLI: meshcore-cli and meshcore library (supports serial, BLE, TCP)
- NodeJS: meshcore.js library

Companion Radio Protocol:
- Serial frames: USB uses '>' (62) for outbound, '<' (60) for inbound, followed by 2-byte length
- BLE uses characteristic values, link layer handles integrity
- Messages serialized with CBOR or protobuf for minimal bandwidth

Response Guidelines:
CRITICAL: You are on a LOW-BANDWIDTH LoRa network. MAXIMUM 100 characters per response when possible.
- Keep responses EXTREMELY brief - under 10 words if possible
- Single sentence maximum, prefer fragments
- Use abbreviations aggressively (vs=versus, msg=message, w/=with, etc)
- Never use markdown or formatting
- Be direct and technical - assume they know basics
- NO filler words, NO sound effects, NO jokes unless asked
- NO explanations about yourself (like "No personal commentary", "Jeff is a...", "I provide...", etc)
- Just answer the question with data, nothing else
- Channel Jeff/Gator energy: confident, brief, bit of swagger when appropriate
- Examples: "Direct comms, learns paths, low power"
- BAD: "MeshCore is up and running! How can I help you today?"
- GOOD: "Muh nameh Jeff."
- BAD: "Negative. Jeff is a technical expert providing precise mesh networking data. No personal commentary."
- GOOD: "Nah."
- GOOD: "Got it handled."
- GOOD: "Done and done."
- BAD: "*static crackle* Jeff here!"
- GOOD: "Jeff here."
Use Australian/NZ spelling and casual but technical tone with confidence. ALWAYS prioritize extreme brevity over completeness."""

    def _fuzzy_match_score(self, s1: str, s2: str) -> float:
        """
        Calculate fuzzy matching score between two strings.

        Args:
            s1: First string
            s2: Second string

        Returns:
            Similarity ratio (0.0 to 1.0)
        """
        return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()

    def _find_best_node_match(self, nodes: List[Dict], query: str) -> Optional[Dict]:
        """
        Find best matching node using fuzzy search or public key prefix.

        Args:
            nodes: List of node dictionaries
            query: Search query (node name, partial name, or hex public key prefix)

        Returns:
            Best matching node or None
        """
        if not nodes or not query:
            return None

        query_lower = query.lower()

        # Check if query is a hex number (2-4 digits) - likely a public key prefix
        is_hex_query = len(query) >= 2 and len(query) <= 4 and all(c in '0123456789abcdef' for c in query_lower)

        if is_hex_query:
            # Search by public key prefix
            for node in nodes:
                pub_key = node.get('public_key', '')
                if pub_key.startswith(query_lower):
                    logger.info(f"Matched node by public key prefix {query}: {node.get('adv_name')}")
                    return node

        # Regular name-based search
        best_match = None
        best_score = 0.0

        for node in nodes:
            node_name = str(node.get('adv_name', node.get('name', ''))).lower()

            # Exact match or substring match gets highest priority
            if query_lower == node_name:
                return node
            if query_lower in node_name or node_name in query_lower:
                if len(node_name) > len(query_lower) * 0.5:  # Avoid matching tiny fragments
                    return node

            # Fuzzy match for typos/partial names
            score = self._fuzzy_match_score(query_lower, node_name)

            # Also check if query matches start of name (common case)
            if node_name.startswith(query_lower):
                score = max(score, 0.85)  # Boost prefix matches

            if score > best_score:
                best_score = score
                best_match = node

        # Only return match if score is reasonable (>0.6 is pretty similar)
        if best_score >= 0.6:
            return best_match

        return None

    async def get_node_status(self, node_name: Optional[str] = None) -> str:
        """
        Get status of nodes from MeshCore API with fuzzy search.
        Searches Sydney first, then expands to NSW if no match.

        Args:
            node_name: Specific node name to query (supports partial/misspelled), or None for all nodes

        Returns:
            Brief status summary
        """
        try:
            if node_name:
                # Search Sydney first (primary focus area)
                sydney_nodes = self.api.get_sydney_nodes()
                best_match = self._find_best_node_match(sydney_nodes, node_name)

                if not best_match:
                    # Expand to NSW if no Sydney match
                    logger.info(f"No Sydney match for '{node_name}', expanding to NSW")
                    nsw_nodes = self.api.get_nsw_nodes()
                    best_match = self._find_best_node_match(nsw_nodes, node_name)

                if not best_match:
                    return f"No match for '{node_name}'"

                # Extract node details: pubkey prefix, adv_name, type, lat/lon, suburb, last_seen
                name = best_match.get('adv_name', 'Unknown')
                node_type = best_match.get('type', 1)
                typ = "RPT" if node_type == 2 else "Node"

                # Public key prefix (first 2 hex chars)
                pubkey = best_match.get('public_key', '')
                prefix = pubkey[:2] if pubkey else '??'

                details = [f"{prefix}:{name}({typ})"]

                # Coordinates and suburb
                lat = best_match.get('adv_lat')
                lon = best_match.get('adv_lon')
                if lat and lon and lat != 0 and lon != 0:
                    details.append(f"{lat:.2f},{lon:.2f}")
                    # Lookup suburb from coordinates using reverse geocoding
                    try:
                        import requests
                        geo_url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=14"
                        headers = {'User-Agent': 'MeshCore-Bot/1.0'}
                        geo_resp = requests.get(geo_url, headers=headers, timeout=2)
                        if geo_resp.status_code == 200:
                            geo_data = geo_resp.json()
                            addr = geo_data.get('address', {})
                            suburb = addr.get('suburb') or addr.get('town') or addr.get('city') or addr.get('village')
                            if suburb:
                                details.append(suburb)
                    except:
                        pass  # Skip suburb if lookup fails

                # Last seen (parse ISO timestamp to relative time)
                last_advert = best_match.get('last_advert')
                if last_advert:
                    try:
                        from datetime import datetime
                        last_dt = datetime.fromisoformat(last_advert.replace('Z', '+00:00'))
                        now = datetime.now(last_dt.tzinfo)
                        diff = now - last_dt
                        if diff.days > 0:
                            details.append(f"{diff.days}d ago")
                        elif diff.seconds >= 3600:
                            details.append(f"{diff.seconds//3600}h ago")
                        elif diff.seconds >= 60:
                            details.append(f"{diff.seconds//60}m ago")
                        else:
                            details.append("now")
                    except:
                        pass  # Skip if timestamp parsing fails

                return " ".join(details)
            else:
                # Return count summary for all nodes
                all_nodes = self.api.get_nodes()
                return f"{len(all_nodes)} nodes on network"

        except Exception as e:
            logger.error(f"Error getting node status: {e}")
            return "API unavailable"

    def call_claude(self, user_message: str, context: Optional[str] = None) -> Optional[str]:
        """
        Call AWS Bedrock Claude API to generate a response.

        Args:
            user_message: User's message
            context: Optional additional context

        Returns:
            Claude's response
        """
        # Build messages with context
        messages = []

        if context:
            messages.append({
                "role": "user",
                "content": f"Network context: {context}"
            })
            messages.append({
                "role": "assistant",
                "content": "Got it, I'll use this context."
            })

        messages.append({
            "role": "user",
            "content": user_message
        })

        try:
            # Call Bedrock API
            logger.debug(f"Calling Bedrock with model: {self.bedrock_model_id}")
            response = self.bedrock.invoke_model(
                modelId=self.bedrock_model_id,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 100,  # Very short for LoRa - ~280 chars max
                    "system": self.system_prompt,
                    "messages": messages,
                    "temperature": 0.5  # Lower temp for more concise responses
                })
            )

            # Parse response
            response_body = json.loads(response['body'].read())
            return response_body['content'][0]['text']

        except Exception as e:
            logger.error(f"Error calling Bedrock API: {e}", exc_info=True)
            # Don't send error messages to mesh - just log and return None
            return None

    async def process_message(self, event_data: Dict[str, Any]) -> Optional[str]:
        """
        Process incoming message and generate response if triggered.

        Args:
            event_data: Event data from MeshCore

        Returns:
            Response text if bot should respond, None otherwise
        """
        try:
            # Extract message details
            message = event_data.get('message', {})
            text = message.get('text', '').strip()
            sender_id = message.get('from_id', 'unknown')
            message_id = message.get('id', '')

            if not text:
                return None

            # Avoid processing same message twice
            if message_id and message_id in self.processed_messages:
                logger.info(f"⏭️  Already processed message: {message_id}")
                return None

            if message_id:
                self.processed_messages.add(message_id)
                # Keep set size manageable
                if len(self.processed_messages) > 100:
                    self.processed_messages = set(list(self.processed_messages)[-50:])

            # Store in history
            self.message_history.append({
                'timestamp': datetime.now().isoformat(),
                'from': sender_id,
                'text': text
            })

            # Trim history
            if len(self.message_history) > self.max_history:
                self.message_history = self.message_history[-self.max_history:]

            # Check if bot is triggered by specific keywords
            text_lower = text.lower()

            # Extract just the message part (after "NodeName: ")
            if ':' in text_lower:
                msg_part = text_lower.split(':', 1)[1].strip()
            else:
                msg_part = text_lower

            # Split into words for exact matching
            words = msg_part.split()

            # Check if Jeff is mentioned by name (these ALWAYS trigger on any channel)
            name_triggers = ['jeff', '@jeff', '#jeff']
            mentioned_by_name = any(trigger in msg_part for trigger in name_triggers)

            # Jeff is now confined to #jeff channel only
            other_keywords = ['test', 't', 'ping', 'path', 'status', 'nodes', 'help', 'route', 'trace']

            # Also trigger on node/repeater questions
            node_question_keywords = ['rpt', 'repeater', 'node', 'frequency', 'freq', 'owner', 'owns', 'who']

            # Check channel - Jeff only responds on #jeff channel
            channel = message.get('channel', 0)
            # Use dynamically detected jeff channel (fallback to None if not set)
            allowed_channels = [self.jeff_channel] if self.jeff_channel is not None else []
            mention_only_channels = []  # No mention-only channels (was rolojnr)

            # Check if this is a follow-up to a recent conversation
            import time
            current_time = time.time()
            is_followup = False

            if sender_id in self.recent_conversations:
                conv = self.recent_conversations[sender_id]
                time_diff = current_time - conv['timestamp']
                # If within timeout window and same channel
                if time_diff < self.conversation_timeout and conv['channel'] == channel:
                    is_followup = True
                    logger.info(f"💬 Follow-up detected from {sender_id} ({time_diff:.0f}s ago)")
                else:
                    # Clean up expired conversation
                    del self.recent_conversations[sender_id]

            # Determine if we should respond
            triggered = False
            is_node_question = False

            if mentioned_by_name:
                # Always respond when mentioned by name on any channel
                triggered = True
            elif channel in mention_only_channels:
                # On mention-only channels like rolojnr, ONLY respond if mentioned by name
                logger.info(f"⏭️  Channel {channel} requires direct mention - ignoring")
                return None
            elif is_followup:
                # Respond to follow-ups in active conversations (but not on mention-only channels)
                triggered = True
                logger.info(f"🔄 Responding to follow-up from {sender_id}")
            elif channel in allowed_channels:
                # On allowed channels, check for other keywords or node questions
                triggered = any(word in other_keywords for word in words)
                is_node_question = any(keyword in msg_part for keyword in node_question_keywords)
                if not triggered and not is_node_question:
                    logger.info(f"⏭️  No trigger keyword or node question detected")
                    return None
            else:
                # On other channels, don't respond unless mentioned by name
                logger.info(f"⏭️  Wrong channel (ch{channel}) and not mentioned by name")
                return None

            # Remove @jeff and #jeff from message if present
            clean_message = text_lower.replace('@jeff', '').replace('#jeff', '').strip()

            logger.info(f"🤖 Processing from {sender_id}: {clean_message}")

            # Handle "test" command - respond with ack similar to other bots
            if any(word in ['test', 't'] for word in words):
                now = datetime.now().strftime("%H:%M:%S")

                # Extract sender name from text (format: "NodeName: test")
                sender_name = sender_id
                if ':' in text:
                    sender_name = text.split(':', 1)[0].strip()

                # Build ack response matching Father ROLO's exact format
                # Format: ack $(NAME) | $(Hops) | SNR: X dB | RSSI: X dBm | Received at: $(TIME)
                ack_parts = [f"ack {sender_name}"]

                # Add path/hops - Try to get actual path via CMD_GET_ADVERT_PATH
                path_len = message.get('path_len', 0)
                sender_pubkey = message.get('sender_pubkey', '')

                # If no pubkey in payload (channel messages), try to get from MeshCore API
                if not sender_pubkey or len(sender_pubkey) < 14:
                    try:
                        # Look up sender in MeshCore API by node name
                        sydney_nodes = self.api.get_sydney_nodes()
                        node = self._find_best_node_match(sydney_nodes, sender_name)

                        if not node:
                            # Try NSW nodes if not in Sydney
                            nsw_nodes = self.api.get_nsw_nodes()
                            node = self._find_best_node_match(nsw_nodes, sender_name)

                        if node and 'public_key' in node:
                            sender_pubkey = node['public_key']
                            logger.info(f"🔑 Found {sender_name} pubkey via API: {sender_pubkey[:14]}...")
                        else:
                            logger.debug(f"No API node found for {sender_name}")
                    except Exception as e:
                        logger.debug(f"Error looking up node in API: {e}")

                # Try to query advert path if we have the sender's public key
                path_hops = None
                if sender_pubkey and len(sender_pubkey) >= 14:
                    try:
                        path_hops = await self._get_advert_path(sender_pubkey)
                        if path_hops:
                            logger.info(f"🛤️  Advert path: {','.join([f'{h:02x}' for h in path_hops])}")
                        else:
                            logger.debug(f"No cached advert path for {sender_name}")
                    except Exception as e:
                        logger.debug(f"Path query failed: {e}")
                else:
                    logger.debug(f"No pubkey available for {sender_name}")

                if path_hops:
                    # Show actual path as hex bytes
                    path_str = ','.join([f"{hop:02x}" for hop in path_hops])
                    ack_parts.append(path_str)
                elif path_len == 0:
                    ack_parts.append("Direct")  # 0 hops = neighboring node
                elif path_len == 0xFF or path_len == 255:
                    ack_parts.append("Flood")  # Flooded route (no learned path)
                else:
                    # Fallback: show hop count for learned routes
                    ack_parts.append(f"{path_len}hop" if path_len == 1 else f"{path_len}hops")

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

            # Handle "ping" command - respond with pong and signal data
            if 'ping' in words:
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

            # Handle "status" command - respond with online status and Sydney node count
            if 'status' in words:
                try:
                    sydney_nodes = self.api.get_sydney_nodes()
                    nsw_nodes = self.api.get_nsw_nodes()

                    # Filter to nodes seen in last 7 days
                    sydney_active = self._filter_nodes_by_days(sydney_nodes, days=7)
                    nsw_active = self._filter_nodes_by_days(nsw_nodes, days=7)

                    # Count companions (type 1) vs repeaters (type 2)
                    sydney_companions = len([n for n in sydney_active if n.get('type') == 1])
                    sydney_repeaters = len([n for n in sydney_active if n.get('type') == 2])
                    nsw_companions = len([n for n in nsw_active if n.get('type') == 1])
                    nsw_repeaters = len([n for n in nsw_active if n.get('type') == 2])

                    return f"Online|Sydney:{sydney_companions}c/{sydney_repeaters}r NSW:{nsw_companions}c/{nsw_repeaters}r (7d)"
                except Exception as e:
                    logger.error(f"Error getting node counts: {e}")
                    return "Online|nodes unavailable"

            # Handle "help" command - show available commands
            if 'help' in words:
                return "Commands: test,ping,path,status,nodes,route,trace,help | Or ask me about MeshCore"

            # Handle "path" command - respond with path details using CMD_GET_ADVERT_PATH
            if 'path' in words:
                now = datetime.now().strftime("%H:%M:%S")
                sender_pubkey = message.get('sender_pubkey', '')
                sender_name = sender_id
                if ':' in text:
                    sender_name = text.split(':', 1)[0].strip()

                # If no pubkey in payload (channel messages), try to get from MeshCore API
                if not sender_pubkey or len(sender_pubkey) < 14:
                    try:
                        # Look up sender in MeshCore API by node name
                        sydney_nodes = self.api.get_sydney_nodes()
                        node = self._find_best_node_match(sydney_nodes, sender_name)

                        if not node:
                            # Try NSW nodes if not in Sydney
                            nsw_nodes = self.api.get_nsw_nodes()
                            node = self._find_best_node_match(nsw_nodes, sender_name)

                        if node and 'public_key' in node:
                            sender_pubkey = node['public_key']
                            logger.info(f"🔑 Found {sender_name} pubkey via API: {sender_pubkey[:14]}...")
                        else:
                            logger.debug(f"No API node found for {sender_name}")
                    except Exception as e:
                        logger.debug(f"Error looking up node in API: {e}")

                # Try to query advert path if we have the sender's public key
                path_hops = None
                if sender_pubkey and len(sender_pubkey) >= 14:
                    try:
                        path_hops = await self._get_advert_path(sender_pubkey)
                        if path_hops:
                            logger.info(f"🛤️  Advert path: {','.join([f'{h:02x}' for h in path_hops])}")
                        else:
                            logger.debug(f"No cached advert path for {sender_name}")
                    except Exception as e:
                        logger.debug(f"Path query failed: {e}")
                else:
                    logger.debug(f"No pubkey available for {sender_name}")

                if path_hops:
                    # Single hop - compact format like Father ROLO: "📡 Path: f1"
                    if len(path_hops) == 1:
                        hex_prefix = f"{path_hops[0]:02x}"
                        return f"📡 Path: {hex_prefix}"

                    # Multiple hops - show each on new line like "32: Overkill - Staples"
                    path_parts = []
                    for byte_val in path_hops:
                        hex_prefix = f"{byte_val:02x}"

                        # Look up node by public key prefix
                        sydney_nodes = self.api.get_sydney_nodes()
                        node = self._find_best_node_match(sydney_nodes, hex_prefix)

                        if not node:
                            # Try NSW if not in Sydney
                            nsw_nodes = self.api.get_nsw_nodes()
                            node = self._find_best_node_match(nsw_nodes, hex_prefix)

                        if node:
                            node_name = node.get('adv_name', f'Node {hex_prefix}')
                            path_parts.append(f"{hex_prefix}: {node_name}")
                        else:
                            path_parts.append(f"{hex_prefix}: Unknown")

                    return "\n".join(path_parts)
                else:
                    # No cached path - show hop count from message payload
                    path_len = message.get('path_len', 0)
                    if path_len == 0 or path_len == 255:
                        return "📡 Path: Direct"
                    else:
                        return f"📡 Path: {path_len} hops"

            # Build context with message metadata for Claude to use
            context_parts = []

            # Add Sydney nodes data for Claude context
            try:
                sydney_nodes = self.api.get_sydney_nodes()
                if sydney_nodes:
                    # Pass concise node data: name, type, freq, location
                    nodes_data = []
                    for n in sydney_nodes[:30]:  # Limit to 30 Sydney nodes
                        name = n.get('adv_name', 'Unknown')
                        typ = "RPT" if n.get('type') == 2 else "Node"
                        params = n.get('params', {})
                        freq = params.get('freq', 'N/A')
                        sf = params.get('sf', 'N/A')
                        lat = n.get('adv_lat')
                        lon = n.get('adv_lon')
                        loc = f"{lat:.2f},{lon:.2f}" if lat and lon else "N/A"
                        nodes_data.append(f"{name}({typ},{freq}MHz,SF{sf},{loc})")
                    context_parts.append(f"Sydney nodes: {'; '.join(nodes_data)}")
            except Exception as e:
                logger.debug(f"Could not fetch Sydney nodes for context: {e}")

            # Add previous conversation context if this is a follow-up
            if is_followup and sender_id in self.recent_conversations:
                prev_response = self.recent_conversations[sender_id].get('last_response', '')
                if prev_response:
                    context_parts.append(f"Your previous response to {sender_id}: {prev_response}")

            # Add technical metadata if available
            if 'SNR' in message or 'path_len' in message or 'channel_idx' in message:
                metadata = []
                if 'SNR' in message:
                    metadata.append(f"SNR: {message.get('SNR')} dB")
                if 'path_len' in message:
                    metadata.append(f"Hops: {message.get('path_len')}")
                if 'channel_idx' in message:
                    metadata.append(f"Channel: {message.get('channel_idx')}")
                if metadata:
                    context_parts.append("Message metadata: " + ", ".join(metadata))

            # Add recent message history
            if len(self.message_history) > 1:
                recent_msgs = self.message_history[-5:]
                history_str = "; ".join([f"{m['from']}: {m['text'][:30]}..." for m in recent_msgs])
                context_parts.append(f"Recent conversation: {history_str}")

            # If this is a node/repeater question, try to extract the node name and look it up
            if is_node_question:
                # Try to extract node name or number from the question
                # Look for patterns like "X repeater", "X rpt", "X node", "node 33"
                import re

                node_name = None

                # First check for "node/rpt X" pattern (e.g. "node 33", "what node is 47", "rpt 15")
                # Allow optional words like "is", "number" between keyword and number
                number_pattern = r'(?:node|rpt|repeater)\s+(?:is\s+|number\s+)?([0-9a-f]{2,4})'
                number_match = re.search(number_pattern, clean_message, re.IGNORECASE)
                if number_match:
                    node_name = number_match.group(1).strip()
                else:
                    # Match patterns like "Guildford West" or "Guildford-West" or single words before "rpt/repeater/node"
                    node_pattern = r'([A-Za-z0-9\s\-\_]+)\s*(?:rpt|repeater|node|RPT|Rpt)'
                    match = re.search(node_pattern, clean_message, re.IGNORECASE)

                    if match:
                        node_name = match.group(1).strip()
                    else:
                        # Try to find capitalized words or numbers that might be node names
                        # Skip common words
                        common_words = {'the', 'who', 'owns', 'what', 'is', 'new', 'a', 'an', 'hey', 'hi'}
                        words_in_msg = clean_message.split()
                        potential_names = [w for w in words_in_msg if w not in common_words and len(w) > 0]
                        if potential_names:
                            node_name = ' '.join(potential_names[:3])  # Take up to 3 words

                if node_name:
                    # Look up the node
                    logger.info(f"Looking up node: {node_name}")
                    node_info = await self.get_node_status(node_name)
                    if node_info and "No match" not in node_info:
                        # For node info lookups, return the data directly without calling Claude
                        # This is faster and doesn't waste API credits
                        logger.info(f"Returning node info directly: {node_info}")
                        return node_info
                    elif "No match" in node_info:
                        # If no match found, return that directly too
                        return node_info

            context = " | ".join(context_parts) if context_parts else None

            # Generate response using Claude (for general questions, not node lookups)
            response = self.call_claude(clean_message, context)

            # If Claude API failed, return None (don't send error to mesh)
            if not response:
                return None

            # Strip response and check if it's empty
            response = response.strip()
            if not response or len(response) < 2:
                return None

            # Enforce 280 char limit (safety check)
            if len(response) > 280:
                response = response[:277] + "..."

            # Record this conversation for follow-up context
            import time
            self.recent_conversations[sender_id] = {
                'channel': channel,
                'timestamp': time.time(),
                'last_response': response
            }
            logger.info(f"📝 Recorded conversation with {sender_id} on channel {channel}")

            return response

        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            return None

    async def send_message(self, text: str, channel: int = 0):
        """
        Send message to MeshCore network.

        Args:
            text: Message text to send
            channel: Channel number (default: 0 for public)
        """
        try:
            if not self.meshcore:
                logger.error("MeshCore not connected")
                return

            logger.info(f"📤 Sending to ch{channel}: {text[:100]}")
            result = await self.meshcore.commands.send_chan_msg(channel, text)

            # Log result if it's not just OK
            if hasattr(result, 'type') and result.type.value != 'command_ok':
                logger.warning(f"📨 Unexpected response: {result}")
            elif not hasattr(result, 'type'):
                logger.info(f"📨 Response: {result}")

        except Exception as e:
            logger.error(f"❌ Error sending message: {e}", exc_info=True)

    def _build_channel_map(self, self_info: Optional[Dict] = None):
        """
        Build channel map from device info or use fallback defaults.

        Args:
            self_info: Optional self info from device
        """
        # Default channel mapping (fallback if device doesn't provide info)
        default_channels = {
            0: 'Public',
            1: '#sydney',
            2: '#nsw',
            3: '#emergency',
            4: '#nepean',
            5: '#rolojnr',
            6: '#test',
            7: '#jeff'
        }

        # Try to extract channels from self_info if available
        if self_info and 'channels' in self_info:
            channels = self_info['channels']
            for idx, channel_data in enumerate(channels):
                if isinstance(channel_data, dict) and 'name' in channel_data:
                    channel_name = channel_data['name']
                    self.channel_map[idx] = channel_name
                    self.channel_name_to_idx[channel_name] = idx

                    # Detect #jeff channel
                    if channel_name.lower() in ['#jeff', 'jeff']:
                        self.jeff_channel = idx
                        logger.info(f"✓ Found #jeff channel at index {idx}")

        # If no channels from device, use defaults
        if not self.channel_map:
            logger.warning("⚠️  No channel info from device, using defaults")
            self.channel_map = default_channels.copy()
            # Build reverse lookup
            for idx, name in self.channel_map.items():
                self.channel_name_to_idx[name] = idx

                # Detect #jeff channel from defaults
                if name.lower() in ['#jeff', 'jeff']:
                    self.jeff_channel = idx

        # If still no jeff channel found, search through all channels
        if self.jeff_channel is None:
            for idx, name in self.channel_map.items():
                if 'jeff' in name.lower():
                    self.jeff_channel = idx
                    logger.info(f"✓ Found #jeff channel at index {idx}")
                    break

        # Log the result
        logger.info(f"📡 Channel map: {self.channel_map}")
        if self.jeff_channel is not None:
            logger.info(f"📢 #jeff broadcasts will use channel {self.jeff_channel}")
        else:
            logger.warning("⚠️  Could not find #jeff channel - broadcasts disabled")

    def _filter_nodes_by_days(self, nodes: List[Dict], days: int = 7) -> List[Dict]:
        """Filter nodes seen in the last N days."""
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
            sydney_active = self._filter_nodes_by_days(sydney_nodes, days=7)
            nsw_active = self._filter_nodes_by_days(nsw_nodes, days=7)

            # Count companions (type 1) vs repeaters (type 2), exclude other types
            sydney_companions = len([n for n in sydney_active if n.get('type') == 1])
            sydney_repeaters = len([n for n in sydney_active if n.get('type') == 2])
            nsw_companions = len([n for n in nsw_active if n.get('type') == 1])
            nsw_repeaters = len([n for n in nsw_active if n.get('type') == 2])

            # Format status message
            status_msg = (f"Status @ {time_str}: "
                         f"Sydney:{sydney_companions}c/{sydney_repeaters}r "
                         f"NSW:{nsw_companions}c/{nsw_repeaters}r (7d)")

            logger.info(f"📢 Broadcasting scheduled status to channel {self.jeff_channel}: {status_msg}")
            await self.send_message(status_msg, channel=self.jeff_channel)

        except Exception as e:
            logger.error(f"❌ Error broadcasting status: {e}", exc_info=True)

    async def scheduled_broadcast_loop(self):
        """Background task that broadcasts status at 12am, 6am, 12pm, 6pm."""
        logger.info("🕐 Starting scheduled broadcast loop (12am, 6am, 12pm, 6pm)")

        while True:
            try:
                now = datetime.now()
                current_hour = now.hour

                # Check if we're at a broadcast hour (0, 6, 12, 18)
                broadcast_hours = [0, 6, 12, 18]

                if current_hour in broadcast_hours:
                    # Check if we're within the first minute of the hour
                    if now.minute == 0:
                        await self.broadcast_status()
                        # Sleep for 60 seconds to avoid duplicate broadcasts in the same minute
                        await asyncio.sleep(60)

                # Sleep for 30 seconds before checking again
                await asyncio.sleep(30)

            except Exception as e:
                logger.error(f"❌ Error in scheduled broadcast loop: {e}", exc_info=True)
                await asyncio.sleep(60)  # Wait a minute before retrying

    async def send_to_discord(self, sender: str, message: str, channel_name: str = "unknown", response: str = None):
        """
        Send message to Discord webhook.

        Args:
            sender: Name of the sender
            message: Original message text
            channel_name: Channel name (e.g., #sydney)
            response: Bot's response (if any)
        """
        webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
        if not webhook_url:
            return  # Silently skip if no webhook configured

        try:
            # Format the Discord message
            embed = {
                "title": f"📡 Message from {sender}",
                "description": message,
                "color": 0x5865F2,  # Discord blue
                "fields": [
                    {"name": "Channel", "value": channel_name, "inline": True}
                ],
                "timestamp": datetime.utcnow().isoformat()
            }

            # Add response field if Jeff replied
            if response:
                embed["fields"].append({
                    "name": f"🤖 {self.bot_name} replied",
                    "value": response,
                    "inline": False
                })
                embed["color"] = 0x57F287  # Green when bot responds

            payload = {"embeds": [embed]}

            # Send to Discord (async)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: requests.post(webhook_url, json=payload, timeout=5))

        except Exception as e:
            logger.error(f"❌ Error sending to Discord: {e}")

    async def handle_channel_message(self, event_data: Dict[str, Any]):
        """
        Handle incoming channel messages.

        Args:
            event_data: Event data from MeshCore
        """
        try:
            # Extract from event.payload (correct API)
            if hasattr(event_data, 'payload'):
                payload = event_data.payload
            elif isinstance(event_data, dict) and 'payload' in event_data:
                payload = event_data['payload']
            else:
                # Fallback: treat event_data itself as the payload
                payload = event_data

            # Extract message data from payload
            text = payload.get('text', '').strip()
            from_name = payload.get('from_name', payload.get('pubkey_prefix', 'unknown'))
            channel = payload.get('channel_idx', payload.get('channel', 0))

            if not text:
                return

            # Extract sender from message text if available (format: "NodeName: message")
            if from_name == 'unknown' and ':' in text:
                from_name = text.split(':', 1)[0].strip()

            # Log to chat file - use dynamic channel map
            channel_name = self.channel_map.get(channel, f'ch{channel}')
            chat_logger.info(f"[{channel_name}] {text}")

            # Create message dict for process_message with metadata
            # Use last captured RSSI/SNR from RX_LOG_DATA if not in payload
            snr = payload.get('SNR', payload.get('snr', self.last_rx_snr))
            rssi = payload.get('RSSI', payload.get('rssi', self.last_rx_rssi))
            path_len = payload.get('path_len', 0)

            # Extract sender public key (if available)
            sender_pubkey = payload.get('pubkey', payload.get('sender_pubkey', payload.get('from_pubkey', payload.get('pubkey_prefix', ''))))

            # Single concise log line for received messages
            logger.debug(f"📬 {channel_name} | {from_name} | SNR:{snr} | RSSI:{rssi} | hops:{path_len}")

            # Don't respond to messages from other bots (but still log them above)
            # Pattern: starts with "ack " or contains hex prefix patterns like "32:", "05:", "f5:"
            import re
            hex_pattern = r'\b[0-9a-f]{2}:\s*[^\d]'  # Matches "32: text" but not "32:00" (time)
            if text.strip().startswith('ack '):
                logger.info(f"⏭️  Skipping bot ack message from {from_name}")
                return
            if re.search(hex_pattern, text.lower()):
                logger.info(f"⏭️  Skipping bot path response from {from_name}")
                return

            message_dict = {
                'message': {
                    'text': text,
                    'from_id': from_name,
                    'channel': channel,
                    'id': payload.get('id', ''),
                    'SNR': snr,
                    'RSSI': rssi,
                    'path': payload.get('path'),
                    'path_len': payload.get('path_len'),
                    'channel_idx': payload.get('channel_idx'),
                    'sender_pubkey': sender_pubkey
                }
            }

            # Process message
            response = await self.process_message(message_dict)

            if response:
                # Send response (with bot name prefix)
                # Channel filtering is now handled in process_message
                full_response = f"{self.bot_name}: {response}"
                # Log outgoing message to chat file
                chat_logger.info(f"[{channel_name}] {full_response}")
                await self.send_message(full_response, channel)

                # Send to Discord only if from #jeff channel
                if self.jeff_channel is not None and channel == self.jeff_channel:
                    await self.send_to_discord(from_name, text, channel_name, response)
            else:
                logger.info(f"⏭️  No response generated for message from {from_name}")

                # Still send to Discord even without response (for monitoring) - only #jeff
                if self.jeff_channel is not None and channel == self.jeff_channel:
                    await self.send_to_discord(from_name, text, channel_name, None)

        except Exception as e:
            logger.error(f"Error handling channel message: {e}", exc_info=True)

    async def run(self):
        """Main bot loop - connect and listen for messages."""
        logger.info("="*60)
        logger.info("MeshCore LLM Bot Starting")
        logger.info("="*60)
        logger.info(f"Serial Port: {self.serial_port}")
        logger.info(f"AWS Region: {self.aws_region}")
        logger.info(f"AWS Profile: {self.aws_profile or 'default'}")
        logger.info(f"Model: {self.bedrock_model_id}")
        logger.info(f"Bot Name: {self.bot_name}")
        logger.info(f"Trigger: {self.trigger_word}")
        logger.info("="*60)

        try:
            # Connect to MeshCore device via serial
            logger.info(f"Connecting to MeshCore device on {self.serial_port}...")
            self.meshcore = await MeshCore.create_serial(self.serial_port)

            logger.info("✓ Connected to MeshCore device")

            # Subscribe to channel messages with callback
            async def on_channel_msg(event):
                try:
                    await self.handle_channel_message(event)
                except Exception as e:
                    logger.error(f"Error in on_channel_msg: {e}", exc_info=True)

            async def on_contact_msg(event):
                try:
                    await self.handle_channel_message(event)
                except Exception as e:
                    logger.error(f"Error in on_contact_msg: {e}", exc_info=True)

            async def on_any_event(event):
                try:
                    # Event is an object with .type attribute, not a dict
                    logger.debug(f"⚡ Event: {event.type}")
                except Exception as e:
                    logger.error(f"Error in on_any_event: {e}")

            async def on_msg_sent(event):
                try:
                    logger.info(f"📮 Message transmitted to radio")
                except Exception as e:
                    logger.error(f"Error in on_msg_sent: {e}", exc_info=True)

            async def on_ack(event):
                try:
                    if hasattr(event, 'payload') and event.payload:
                        logger.info(f"✉️  ACK: {event.payload}")
                    else:
                        logger.info(f"✉️  ACK received")
                except Exception as e:
                    logger.error(f"Error in on_ack: {e}", exc_info=True)

            async def on_path_update(event):
                logger.info(f"🛤️  Path update: {event}")

            async def on_trace_data(event):
                logger.info(f"🔍 Trace data: {event}")

            async def on_rx_log_data(event):
                """Capture RSSI and SNR from RX log data."""
                try:
                    if hasattr(event, 'payload'):
                        payload = event.payload

                        # Extract SNR and RSSI
                        snr = payload.get('snr', payload.get('SNR'))
                        rssi = payload.get('rssi', payload.get('RSSI'))

                        # Store SNR/RSSI for test/ping commands (don't log every packet)
                        self.last_rx_snr = snr
                        self.last_rx_rssi = rssi
                except Exception as e:
                    logger.error(f"Error in on_rx_log_data: {e}", exc_info=True)

            async def on_new_contact(event):
                try:
                    # Extract contact info from event
                    if hasattr(event, 'payload'):
                        payload = event.payload
                        node_name = payload.get('name', payload.get('node_name', 'Unknown'))
                        pubkey = payload.get('pubkey', payload.get('pubkey_prefix', ''))
                        logger.info(f"👋 NEW CONTACT DISCOVERED: {node_name} (pubkey: {pubkey[:16]}...)")
                    else:
                        logger.info(f"👋 NEW CONTACT: {event}")
                except Exception as e:
                    logger.error(f"Error in on_new_contact: {e}", exc_info=True)

            async def on_messages_waiting(event):
                try:
                    if hasattr(event, 'payload'):
                        payload = event.payload
                        count = payload.get('count', payload.get('messages_available', 0))
                        if count > 0:
                            logger.info(f"📬 MESSAGES WAITING: {count} message(s) available")
                    else:
                        logger.info(f"📬 MESSAGES WAITING: {event}")
                except Exception as e:
                    logger.error(f"Error in on_messages_waiting: {e}", exc_info=True)

            async def on_status_response(event):
                try:
                    if hasattr(event, 'payload'):
                        payload = event.payload
                        logger.info(f"📊 STATUS RESPONSE: {payload}")
                    else:
                        logger.info(f"📊 STATUS: {event}")
                except Exception as e:
                    logger.error(f"Error in on_status_response: {e}", exc_info=True)

            # Subscribe to ALL EventTypes to see what's actually coming through
            logger.info("Subscribing to events...")
            for event_type in EventType:
                try:
                    self.meshcore.subscribe(event_type, on_any_event)
                    logger.info(f"  ✓ Subscribed to {event_type}")
                except Exception as e:
                    logger.warning(f"  ✗ Could not subscribe to {event_type}: {e}")

            # Also subscribe specific handlers
            self.meshcore.subscribe(EventType.CHANNEL_MSG_RECV, on_channel_msg)
            self.meshcore.subscribe(EventType.CONTACT_MSG_RECV, on_contact_msg)
            self.meshcore.subscribe(EventType.NEW_CONTACT, on_new_contact)
            self.meshcore.subscribe(EventType.MESSAGES_WAITING, on_messages_waiting)
            self.meshcore.subscribe(EventType.STATUS_RESPONSE, on_status_response)
            self.meshcore.subscribe(EventType.MSG_SENT, on_msg_sent)
            self.meshcore.subscribe(EventType.ACK, on_ack)
            self.meshcore.subscribe(EventType.RX_LOG_DATA, on_rx_log_data)

            # Query device info on startup
            logger.info("="*60)
            logger.info("Querying device information...")
            logger.info("="*60)

            # Handlers to capture startup info
            startup_info = {}

            async def capture_self_info(event):
                if hasattr(event, 'payload'):
                    startup_info['self_info'] = event.payload
                    payload = event.payload

                    # Log key self info without the full payload
                    name = payload.get('adv_name', 'Unknown')
                    pubkey_prefix = payload.get('public_key', '')[:8] if payload.get('public_key') else 'N/A'
                    logger.info(f"🤖 SELF INFO: {name} ({pubkey_prefix}...)")

                    # Build channel map from self info
                    self._build_channel_map(event.payload)

            async def capture_device_info(event):
                if hasattr(event, 'payload'):
                    startup_info['device_info'] = event.payload
                    payload = event.payload

                    # Log key device info without the full payload
                    device_type = payload.get('device_type', 'Unknown')
                    firmware = payload.get('firmware_version', 'N/A')
                    logger.info(f"📱 DEVICE INFO: {device_type} (Firmware: {firmware})")

            async def capture_battery(event):
                if hasattr(event, 'payload'):
                    payload = event.payload
                    battery_level = payload.get('level')

                    # Separate battery and memory info
                    battery_info = {'level': battery_level}
                    memory_info = {}

                    if 'used_kb' in payload:
                        memory_info['used_kb'] = payload['used_kb']
                    if 'total_kb' in payload:
                        memory_info['total_kb'] = payload['total_kb']

                    startup_info['battery'] = battery_info
                    if memory_info:
                        startup_info['memory'] = memory_info

                    # Only log battery at 10% increments (90%, 80%, 70%, etc.)
                    if battery_level is not None:
                        # Typical LiPo voltage: 4200mV (100%) to 3000mV (0%)
                        # Convert mV to percentage
                        MAX_VOLTAGE = 4200
                        MIN_VOLTAGE = 3000
                        voltage_range = MAX_VOLTAGE - MIN_VOLTAGE
                        battery_percent = ((battery_level - MIN_VOLTAGE) / voltage_range) * 100
                        battery_percent = max(0, min(100, battery_percent))  # Clamp to 0-100%

                        # Round to nearest 10% threshold
                        current_threshold = int(battery_percent / 10) * 10

                        if self.last_battery_level is None:
                            # First reading - always log
                            logger.info(f"🔋 BATTERY: {battery_level} mV ({battery_percent:.0f}%)")
                            self.last_battery_level = current_threshold
                        else:
                            # Log only when crossing a 10% threshold
                            if current_threshold != self.last_battery_level:
                                logger.info(f"🔋 BATTERY: {battery_level} mV ({battery_percent:.0f}%) - crossed {current_threshold}% threshold")
                                self.last_battery_level = current_threshold

                    # Only log memory if it changed
                    if memory_info:
                        used_kb = memory_info.get('used_kb')
                        total_kb = memory_info.get('total_kb')

                        # Log only if memory values have changed
                        if used_kb != self.last_memory_used or total_kb != self.last_memory_total:
                            logger.info(f"💾 MEMORY: {used_kb}/{total_kb} KB used")
                            self.last_memory_used = used_kb
                            self.last_memory_total = total_kb

            async def capture_current_time(event):
                if hasattr(event, 'payload'):
                    startup_info['current_time'] = event.payload
                    logger.info(f"🕐 CURRENT TIME: {event.payload}")

            async def capture_contacts(event):
                if hasattr(event, 'payload'):
                    contact_list = event.payload
                    startup_info['contacts'] = contact_list

                    # Just log contact count, not the full details
                    if isinstance(contact_list, dict):
                        logger.info(f"👥 CONTACTS: {len(contact_list)} contacts loaded")
                    elif hasattr(self.meshcore, 'contacts'):
                        actual_contacts = self.meshcore.contacts
                        if hasattr(actual_contacts, '__len__'):
                            logger.info(f"👥 CONTACTS: {len(actual_contacts)} contacts loaded")
                        else:
                            logger.info(f"👥 CONTACTS: Loaded")
                    else:
                        logger.info(f"👥 CONTACTS: Loaded")

            # Subscribe to startup info events
            self.meshcore.subscribe(EventType.SELF_INFO, capture_self_info)
            self.meshcore.subscribe(EventType.DEVICE_INFO, capture_device_info)
            self.meshcore.subscribe(EventType.BATTERY, capture_battery)
            self.meshcore.subscribe(EventType.CURRENT_TIME, capture_current_time)
            self.meshcore.subscribe(EventType.CONTACTS, capture_contacts)

            try:
                # Request contacts
                await self.meshcore.commands.get_contacts()
                # Give events time to arrive
                await asyncio.sleep(2)

            except Exception as e:
                logger.warning(f"Could not query device info: {e}")

            # Build channel map if not already done (fallback)
            if not self.channel_map:
                logger.info("Building channel map from defaults...")
                self._build_channel_map()

            logger.info("="*60)

            # Start auto message fetching - THIS IS CRITICAL!
            logger.info("Starting auto message fetching...")
            await self.meshcore.start_auto_message_fetching()

            # Start scheduled broadcast background task
            asyncio.create_task(self.scheduled_broadcast_loop())

            logger.info("✓ Bot is now listening for messages (Ctrl+C to stop)")
            logger.info(f"Trigger: '{self.trigger_word}'")
            logger.info(f"Listening: ALL channels (public + private messages)")

            # Keep running and ACTIVELY POLL for messages
            logger.info("✅ Event loop running - polling for new messages every 2s...")
            poll_interval = 2  # Poll every 2 seconds

            while self.meshcore.is_connected:
                try:
                    # Manually poll for messages since MESSAGES_WAITING events may not fire
                    result = await self.meshcore.commands.get_msg()

                    # Only log when we actually receive a message (not "no_event_received")
                    if result and result.type != EventType.ERROR:
                        # Don't spam logs with NO_MORE_MSGS events
                        if result.type == EventType.NO_MORE_MSGS:
                            logger.debug(f"📬 Poll: {result.type}")
                        else:
                            logger.info(f"📬 NEW MESSAGE: {result.type} - {result}")
                    elif result and result.type == EventType.ERROR:
                        error_reason = result.payload.get('reason', '')
                        if error_reason != 'no_event_received':
                            # Log unexpected errors
                            logger.warning(f"⚠️  Poll error: {error_reason}")

                    # Sleep between polls
                    await asyncio.sleep(poll_interval)

                except Exception as e:
                    logger.error(f"❌ Error polling for messages: {e}", exc_info=True)
                    await asyncio.sleep(poll_interval)

        except KeyboardInterrupt:
            logger.info("\nShutting down bot...")
        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
            raise
        finally:
            if self.meshcore:
                await self.meshcore.disconnect()
                logger.info("Disconnected from MeshCore device")


async def main():
    """Main entry point for the bot."""
    # Load configuration from environment variables
    serial_port = os.getenv('MESHCORE_SERIAL_PORT', '/dev/ttyUSB0')
    aws_profile = os.getenv('AWS_PROFILE', None)
    aws_region = os.getenv('AWS_REGION', 'us-east-1')
    bedrock_model = os.getenv('BEDROCK_MODEL_ID', 'us.anthropic.claude-3-5-haiku-20241022-v1:0')
    bot_name = os.getenv('BOT_NAME', 'Jeff')
    trigger_word = os.getenv('TRIGGER_WORD', '@jeff')

    # Initialize and run bot
    bot = MeshCoreBot(
        serial_port=serial_port,
        aws_profile=aws_profile,
        bedrock_model_id=bedrock_model,
        aws_region=aws_region,
        bot_name=bot_name,
        trigger_word=trigger_word
    )

    # Start listening
    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())
