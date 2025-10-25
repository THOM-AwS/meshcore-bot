"""Path utilities for MeshCore routing information."""
import logging
from typing import Optional, List, Dict
from meshcore import EventType

logger = logging.getLogger('meshcore.bot')


class PathUtils:
    """Utilities for working with MeshCore routing paths."""

    def __init__(self, meshcore_client, meshcore_api):
        """
        Initialize path utilities.

        Args:
            meshcore_client: MeshCore client instance
            meshcore_api: MeshCoreAPI instance for node lookups
        """
        self.meshcore = meshcore_client
        self.api = meshcore_api

    async def get_advert_path(self, pubkey_hex: str) -> Optional[List[int]]:
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

    async def get_node_name_from_hash(self, node_hash_bytes: bytes, contacts: Optional[Dict] = None) -> str:
        """
        Look up a node's name from its hash.

        Args:
            node_hash_bytes: Hash bytes to search for
            contacts: Optional contacts dict (will query if not provided)

        Returns:
            Node name or "??" if not found
        """
        try:
            if contacts is None:
                contacts_result = await self.meshcore.commands.get_contacts()
                if contacts_result.type != EventType.CONTACTS:
                    return "??"
                contacts = contacts_result.payload

            for key, contact in contacts.items():
                pubkey = contact.get('public_key', '')
                if not pubkey:
                    continue

                # Handle both hex string and bytes
                pubkey_bytes = bytes.fromhex(pubkey) if isinstance(pubkey, str) else pubkey

                # Check if pubkey starts with node_hash_bytes
                if pubkey_bytes[:len(node_hash_bytes)] == node_hash_bytes:
                    return contact.get('adv_name', '??')

                # Also check hex string comparison
                if isinstance(pubkey, str) and pubkey[:len(node_hash_bytes)*2] == node_hash_bytes.hex():
                    return contact.get('adv_name', '??')

            return "??"

        except Exception as e:
            logger.debug(f"Error looking up node name: {e}")
            return "??"

    async def get_path_for_test(self, message: Dict, sender_id: str) -> str:
        """
        Get path hops in hex format for test command (like Father ROLO).
        Returns format like: "43,36,49,f5" or "Direct" or "3hops"
        """
        try:
            sender_prefix = message.get('pubkey_prefix', '')
            path_len_msg = message.get('path_len', 0)

            # Direct connection (path_len = 255)
            if path_len_msg == 255 or path_len_msg == 0:
                return "Direct"

            # Get all contacts
            contacts_result = await self.meshcore.commands.get_contacts()
            if contacts_result.type != EventType.CONTACTS:
                return f"{path_len_msg}hops"

            contacts = contacts_result.payload

            # Find sender contact
            sender_contact = None
            sender_pubkey = message.get('sender_pubkey', '')

            for key, contact in contacts.items():
                contact_pubkey = contact.get('public_key', '')
                # Match by pubkey prefix (first 12 hex chars = 6 bytes)
                if contact_pubkey[:12] == sender_prefix:
                    sender_contact = contact
                    break
                # Also try matching full pubkey if available
                if sender_pubkey and contact_pubkey == sender_pubkey:
                    sender_contact = contact
                    break

            if not sender_contact:
                return f"{path_len_msg}hops"

            # Get path from contact
            out_path = sender_contact.get('out_path', b'')
            out_path_len = sender_contact.get('out_path_len', -1)

            if out_path_len <= 0:
                return f"{path_len_msg}hops"

            # Build path string as hex bytes (like Father ROLO)
            path_hops = []
            bytes_per_hop = 8 if out_path_len * 8 <= len(out_path) else 6

            for i in range(out_path_len):
                start = i * bytes_per_hop
                end = start + bytes_per_hop
                if end > len(out_path):
                    break

                node_hash = out_path[start:end]
                hash_hex = node_hash.hex()[:2]  # First 2 hex chars (1 byte)
                path_hops.append(hash_hex)

            if path_hops:
                return ",".join(path_hops)
            else:
                return f"{path_len_msg}hops"

        except Exception as e:
            logger.error(f"Error getting path for test: {e}", exc_info=True)
            return f"{message.get('path_len', 0)}hops"

    async def get_compact_path(self, message: Dict, sender_id: str) -> str:
        """
        Get compact path in hash:name format with suburbs, sender to receiver.

        Args:
            message: Message dict with path info
            sender_id: Sender identifier

        Returns:
            Path string like "a1:Bob Pyrmont -> 3f:Tower Chatswood -> YOU"
        """
        try:
            sender_prefix = message.get('pubkey_prefix', '')
            path_len_msg = message.get('path_len', 0)

            # Get all contacts
            contacts_result = await self.meshcore.commands.get_contacts()
            if contacts_result.type != EventType.CONTACTS:
                return f"{sender_prefix[:2]}:{sender_id} -> YOU"

            contacts = contacts_result.payload

            # Load API nodes for suburb lookups
            sydney_nodes = self.api.get_sydney_nodes()
            nsw_nodes = self.api.get_nsw_nodes()
            all_nodes = sydney_nodes + nsw_nodes

            # Find sender contact
            sender_contact = None
            sender_pubkey = message.get('sender_pubkey', '')

            for key, contact in contacts.items():
                contact_pubkey = contact.get('public_key', '')
                # Match by pubkey prefix (first 12 hex chars = 6 bytes)
                if contact_pubkey[:12] == sender_prefix:
                    sender_contact = contact
                    break
                # Also try matching full pubkey if available
                if sender_pubkey and contact_pubkey == sender_pubkey:
                    sender_contact = contact
                    break

            if not sender_contact:
                return f"{sender_prefix[:2]}:{sender_id} -> YOU"

            sender_name = sender_contact.get('adv_name', sender_id)
            sender_hash = sender_contact.get('public_key', '')[:2]

            # Look up sender suburb from API
            sender_suburb = self._get_node_suburb(sender_contact.get('public_key', ''), all_nodes)
            sender_part = f"{sender_hash}:{sender_name} {sender_suburb}".strip()

            # Direct connection (path_len = 255)
            if path_len_msg == 255 or path_len_msg == 0:
                return f"{sender_part} -> YOU"

            # Get path from contact
            out_path = sender_contact.get('out_path', b'')
            out_path_len = sender_contact.get('out_path_len', -1)

            if out_path_len <= 0:
                return f"{sender_part} -> YOU"

            # Build path string
            path_parts = [sender_part]

            # Parse intermediate nodes (8 bytes per hop for full hash, 6 for short)
            bytes_per_hop = 8 if out_path_len * 8 <= len(out_path) else 6

            for i in range(out_path_len):
                start = i * bytes_per_hop
                end = start + bytes_per_hop
                if end > len(out_path):
                    break

                node_hash = out_path[start:end]
                node_name = await self.get_node_name_from_hash(node_hash, contacts)
                hash_prefix = node_hash.hex()[:2]

                # Find full pubkey for this hop to lookup suburb
                hop_pubkey = None
                for key, contact in contacts.items():
                    contact_pubkey = contact.get('public_key', '')
                    if contact_pubkey.startswith(node_hash.hex()):
                        hop_pubkey = contact_pubkey
                        break

                suburb = self._get_node_suburb(hop_pubkey, all_nodes) if hop_pubkey else ""
                node_part = f"{hash_prefix}:{node_name} {suburb}".strip()
                path_parts.append(node_part)

            path_parts.append("YOU")

            return " -> ".join(path_parts)

        except Exception as e:
            logger.error(f"Error building compact path: {e}", exc_info=True)
            return f"{sender_id} -> YOU"

    def _get_node_suburb(self, pubkey: str, nodes: list) -> str:
        """Look up suburb from API nodes based on public key."""
        if not pubkey or not nodes:
            return ""

        for node in nodes:
            if node.get('public_key') == pubkey:
                location = node.get('location', {})
                if isinstance(location, dict):
                    suburb = location.get('suburb', '')
                    if suburb:
                        return suburb
        return ""
