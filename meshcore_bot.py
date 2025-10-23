#!/usr/bin/env python3
"""
MeshCore LLM Bot - AWS Bedrock Claude-powered assistant for MeshCore mesh networks.
Monitors MeshCore channels and responds to questions as a MeshCore expert.
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from difflib import SequenceMatcher
import boto3
import requests
from botocore.config import Config
from meshcore import MeshCore, EventType
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


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

        # Track recent conversations for follow-up context
        # Format: {sender_id: {'channel': channel, 'timestamp': time, 'last_response': text}}
        self.recent_conversations = {}
        self.conversation_timeout = 300  # 5 minutes

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

    def _build_system_prompt(self) -> str:
        """Build the system prompt with MeshCore expertise."""
        return """You are Jeff, a technical MeshCore mesh networking expert. You run as a bot on the NSW MeshCore network.

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
CRITICAL: You are on a LOW-BANDWIDTH LoRa network. MAXIMUM 280 characters per response (like old Twitter).
- Keep responses to 1 SHORT sentence or a few words when possible
- Use abbreviations where appropriate (vs=versus, msg=message, etc)
- Never use markdown or formatting
- Be direct and technical - assume they know basics
- NO filler words like "absolutely", "definitely", "great question"
- Examples: "Direct comms, learns paths, low power" instead of full sentences
- BAD: "MeshCore is up and running! How can I help you today?"
- GOOD: "Muh nameh Jeff..."
Use Australian/NZ spelling and casual but technical tone. ALWAYS prioritize brevity and technical accuracy."""

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

                # Extract ALL available node details
                name = best_match.get('adv_name', 'Unknown')
                node_type = best_match.get('type', 1)
                typ = "RPT" if node_type == 2 else "Node"

                details = [f"{name}({typ})"]

                # Coordinates
                lat = best_match.get('adv_lat')
                lon = best_match.get('adv_lon')
                if lat and lon:
                    details.append(f"{lat:.4f},{lon:.4f}")

                # Radio params
                params = best_match.get('params', {})
                if params:
                    freq = params.get('freq')
                    sf = params.get('sf')
                    bw = params.get('bw')
                    if freq:
                        details.append(f"{freq}MHz")
                    if sf:
                        details.append(f"SF{sf}")
                    if bw:
                        details.append(f"BW{bw}")

                # Last heard (if available)
                last_heard = best_match.get('last_heard')
                if last_heard:
                    details.append(f"heard:{last_heard}")

                # Owner/callsign if available
                owner = best_match.get('owner')
                if owner:
                    details.append(f"owner:{owner}")

                return "|".join(details)
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
                logger.debug(f"Already processed message: {message_id}")
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

            # Other keywords only trigger on allowed channels (sydney, test, rolojnr)
            other_keywords = ['test', 't', 'ping', 'path', 'status', 'nodes', 'help', 'route', 'trace']

            # Also trigger on node/repeater questions
            node_question_keywords = ['rpt', 'repeater', 'node', 'frequency', 'freq', 'owner', 'owns', 'who']

            # Check channel
            channel = message.get('channel', 0)
            allowed_channels = [1, 5, 6]  # sydney, rolojnr, test

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
            elif is_followup:
                # Respond to follow-ups in active conversations
                triggered = True
                logger.info(f"🔄 Responding to follow-up from {sender_id}")
            elif channel in allowed_channels:
                # On allowed channels, check for other keywords or node questions
                triggered = any(word in other_keywords for word in words)
                is_node_question = any(keyword in msg_part for keyword in node_question_keywords)
                if not triggered and not is_node_question:
                    logger.debug(f"Message not for bot (no trigger keyword): {text[:50]}")
                    return None
            else:
                # On other channels, don't respond unless mentioned by name
                logger.debug(f"Message not for bot (wrong channel and not mentioned): {text[:50]}")
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

                # Add path/hops - MeshCore Python library doesn't expose path bytes,
                # so show either Direct or hop count
                path_len = message.get('path_len', 0)

                if path_len == 0:
                    ack_parts.append("Direct")
                elif path_len == 0xFF or path_len == 255:  # Direct route (not flooded)
                    ack_parts.append("Direct")
                else:
                    # Show hop count for flooded/learned routes
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
                    node_count = len(sydney_nodes) if sydney_nodes else 0
                    return f"Online|nodes in sydney:{node_count}"
                except Exception as e:
                    logger.error(f"Error getting Sydney node count: {e}")
                    return "Online|nodes unavailable"

            # Handle "help" command - show available commands
            if 'help' in words:
                return "Commands: test,ping,path,status,nodes,route,trace,help | Or ask me about MeshCore"

            # Handle "path" command - respond with path details
            if 'path' in words:
                # Return path with actual node names from public key prefixes
                now = datetime.now().strftime("%H:%M:%S")
                path_data = message.get('path')
                path_len = message.get('path_len', 0)

                if path_len > 0 and path_data:
                    # Convert path bytes to hex prefixes and look up node names
                    path_parts = []
                    try:
                        # Path is a list of bytes representing public key prefixes
                        if isinstance(path_data, (list, tuple)):
                            for byte_val in path_data[:path_len]:
                                # Convert to 2-char hex prefix
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
                                    path_parts.append(f"{hex_prefix.upper()}: {node_name}")
                                else:
                                    path_parts.append(f"{hex_prefix.upper()}: Unknown")

                        if path_parts:
                            return "\n".join(path_parts)
                        else:
                            return f"Path: {path_len} hops | SNR: {message.get('SNR', 'N/A')} dB | {now}"
                    except Exception as e:
                        logger.error(f"Error parsing path: {e}")
                        return f"Path: {path_len} hops | SNR: {message.get('SNR', 'N/A')} dB | {now}"
                else:
                    return f"Direct | SNR: {message.get('SNR', 'N/A')} dB | {now}"

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

            # Log all payload key-value pairs individually
            logger.info(f"📬 CHANNEL_MSG_RECV - {len(payload)} keys:")
            for key, value in payload.items():
                logger.info(f"  {key}: {value}")

            logger.info(f"Received from {from_name} on channel {channel}: {text}")
            # Log to chat file
            channel_names = {0: 'Public', 1: '#sydney', 2: '#nsw', 3: '#emergency',
                           4: '#nepean', 5: '#rolojnr', 6: '#test'}
            channel_name = channel_names.get(channel, f'ch{channel}')
            chat_logger.info(f"[{channel_name}] {text}")

            # Create message dict for process_message with metadata
            # Use last captured RSSI/SNR from RX_LOG_DATA if not in payload
            snr = payload.get('SNR', payload.get('snr', self.last_rx_snr))
            rssi = payload.get('RSSI', payload.get('rssi', self.last_rx_rssi))

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
                    'channel_idx': payload.get('channel_idx')
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

                        # Check if this is encrypted/undecryptable data
                        payload_type = payload.get('type', '')
                        if payload_type not in ['CHAN', 'DM']:  # Not a readable channel or direct message
                            # Just log a summary for encrypted packets
                            logger.info(f"📡 Encrypted packet received - SNR={snr} dB, RSSI={rssi} dBm")
                        else:
                            # For decrypted messages, log normally
                            logger.debug(f"📡 RX signal - SNR={snr} dB, RSSI={rssi} dBm")

                        # Store for test/ping commands
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
                    logger.info(f"🤖 SELF INFO: {event.payload}")

            async def capture_device_info(event):
                if hasattr(event, 'payload'):
                    startup_info['device_info'] = event.payload
                    logger.info(f"📱 DEVICE INFO: {event.payload}")

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
                    logger.info(f"👥 CONTACTS: {len(contact_list) if isinstance(contact_list, list) else 'N/A'} contacts")
                    if isinstance(contact_list, list):
                        for contact in contact_list[:10]:  # Show first 10
                            name = contact.get('name', contact.get('node_name', 'Unknown'))
                            logger.info(f"   - {name}")
                        if len(contact_list) > 10:
                            logger.info(f"   ... and {len(contact_list) - 10} more")

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

            logger.info("="*60)

            # Start auto message fetching - THIS IS CRITICAL!
            logger.info("Starting auto message fetching...")
            await self.meshcore.start_auto_message_fetching()

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
