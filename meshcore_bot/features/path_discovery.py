"""Path discovery functionality for MeshCore."""
import asyncio
import logging
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger('meshcore.bot')


class PathDiscovery:
    """
    Manages path discovery for MeshCore contacts.

    Uses CMD_SEND_PATH_DISCOVERY_REQ (0x34) firmware command for reliable
    path discovery with complete hop data.
    """

    def __init__(self, meshcore):
        """
        Initialize path discovery.

        Args:
            meshcore: MeshCore instance
        """
        self.meshcore = meshcore

    async def discover_path_to_contact(
        self,
        contact_name: str,
        timeout: float = 30.0
    ) -> Optional[Dict[str, Any]]:
        """
        Discover the routing path to a contact using proper firmware command.

        This method:
        1. Finds contact by name
        2. Sends CMD_SEND_PATH_DISCOVERY_REQ (0x34)
        3. Waits for PATH_RESPONSE event
        4. Returns complete path data including hop-by-hop route

        Args:
            contact_name: Name of the contact
            timeout: Maximum time to wait for path discovery (seconds)

        Returns:
            Dict with discovery results:
            {
                'success': bool,
                'contact_name': str,
                'pubkey': str,
                'out_path_len': int,       # Hops TO contact
                'out_path': str,           # Hex string of route TO contact
                'out_path_hops': list,     # List of node hashes
                'in_path_len': int,        # Hops FROM contact
                'in_path': str,            # Hex string of route FROM contact
                'in_path_hops': list,      # List of node hashes
                'timestamp': str
            }
            Or on failure:
            {
                'success': False,
                'error': str,
                'contact_name': str
            }
        """
        # Find contact by name
        contact = self._find_contact_by_name(contact_name)
        if not contact:
            logger.warning(f"❌ Contact '{contact_name}' not found")
            return {
                'success': False,
                'error': 'Contact not found',
                'contact_name': contact_name
            }

        pubkey = contact.get('public_key', '')
        if not pubkey or len(pubkey) < 64:
            logger.warning(f"❌ Contact '{contact_name}' has invalid public key")
            return {
                'success': False,
                'error': 'Invalid public key',
                'contact_name': contact_name
            }

        logger.info(f"🔍 Starting path discovery for {contact_name}")
        logger.info(f"   Public key: {pubkey[:16]}...")

        # Check current path status
        current_path_len = contact.get('out_path_len', -1)
        logger.info(f"   Current out_path_len: {current_path_len}")

        try:
            # Send path discovery request using proper command
            CMD_SEND_PATH_DISCOVERY_REQ = 0x34

            pubkey_bytes = bytes.fromhex(pubkey[:64])
            cmd_frame = bytearray([CMD_SEND_PATH_DISCOVERY_REQ, 0x00])
            cmd_frame.extend(pubkey_bytes)

            logger.info(f"📤 Sending path discovery request...")
            logger.debug(f"   Command: {cmd_frame.hex()}")

            # Wait for PATH_RESPONSE event
            from meshcore import EventType

            # Send command (will get RESP_CODE_SENT immediately)
            send_response = await self.meshcore.commands.send(
                bytes(cmd_frame),
                expected_events=[EventType.MSG_SENT, EventType.ERROR],
                timeout=5.0
            )

            if send_response.type == EventType.ERROR:
                error_msg = send_response.payload.get('message', 'Unknown error')
                logger.error(f"❌ Failed to send command: {error_msg}")
                return {
                    'success': False,
                    'error': f'Send failed: {error_msg}',
                    'contact_name': contact_name
                }

            logger.info(f"📤 Command sent, waiting for path response...")

            # Now wait for PATH_DISCOVERY_RESPONSE push (0x8D)
            response = await self.meshcore.dispatcher.wait_for_event(
                EventType.PATH_RESPONSE,
                timeout=timeout
            )

            if not response:
                logger.warning(f"⏱️  Timeout waiting for PATH_RESPONSE")
                raise asyncio.TimeoutError()

            logger.info(f"📥 Path response received!")

            if response.type == EventType.PATH_RESPONSE:
                payload = response.payload

                # Extract path data
                pubkey_pre = payload.get('pubkey_pre', '')
                out_path_len = payload.get('out_path_len', 0)
                out_path_hex = payload.get('out_path', '')
                in_path_len = payload.get('in_path_len', 0)
                in_path_hex = payload.get('in_path', '')

                # Parse hops (1 byte per hop)
                out_path_hops = []
                in_path_hops = []

                if out_path_hex:
                    out_path_bytes = bytes.fromhex(out_path_hex)
                    out_path_hops = [f"{b:02x}" for b in out_path_bytes[:out_path_len]]

                if in_path_hex:
                    in_path_bytes = bytes.fromhex(in_path_hex)
                    in_path_hops = [f"{b:02x}" for b in in_path_bytes[:in_path_len]]

                logger.info(f"✅ Path discovery successful!")
                logger.info(f"   Out path (TO {contact_name}): {out_path_len} hops")
                if out_path_hops:
                    logger.info(f"      Hops: {' -> '.join(out_path_hops)}")
                logger.info(f"   In path (FROM {contact_name}): {in_path_len} hops")
                if in_path_hops:
                    logger.info(f"      Hops: {' -> '.join(in_path_hops)}")

                # Refresh contacts to get updated out_path
                await self.meshcore.commands.get_contacts()

                return {
                    'success': True,
                    'contact_name': contact_name,
                    'pubkey': pubkey,
                    'old_path_len': current_path_len,
                    'out_path_len': out_path_len,
                    'out_path': out_path_hex,
                    'out_path_hops': out_path_hops,
                    'in_path_len': in_path_len,
                    'in_path': in_path_hex,
                    'in_path_hops': in_path_hops,
                    'timestamp': datetime.now().isoformat()
                }

            elif response.type == EventType.ERROR:
                error_msg = response.payload.get('message', 'Unknown error')
                logger.error(f"❌ Path discovery failed: {error_msg}")
                print(f"DEBUG: Got ERROR response, payload={response.payload}")
                return {
                    'success': False,
                    'error': error_msg,
                    'contact_name': contact_name
                }

            else:
                logger.warning(f"⚠️  Unexpected response type: {response.type}")
                return {
                    'success': False,
                    'error': f'Unexpected response: {response.type}',
                    'contact_name': contact_name
                }

        except asyncio.TimeoutError:
            logger.warning(f"⏱️  Path discovery timed out for {contact_name}")
            return {
                'success': False,
                'error': f'Timeout after {timeout}s',
                'contact_name': contact_name,
                'old_path_len': current_path_len
            }

        except Exception as e:
            logger.error(f"❌ Path discovery error: {e}", exc_info=True)
            print(f"DEBUG: Exception type: {type(e)}")
            print(f"DEBUG: Exception: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e),
                'contact_name': contact_name
            }

    def _find_contact_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Find a contact by name.

        Args:
            name: Contact name to search for

        Returns:
            Contact dict or None if not found
        """
        if not hasattr(self.meshcore, 'contacts'):
            return None

        contacts = self.meshcore.contacts
        name_lower = name.lower()

        for pubkey, contact in contacts.items():
            contact_name = contact.get('adv_name', '').lower()
            if contact_name == name_lower or name_lower in contact_name:
                return contact

        return None

    async def discover_paths_batch(
        self,
        contact_names: list,
        delay_between: float = 2.0,
        timeout_per_contact: float = 30.0
    ) -> Dict[str, Dict[str, Any]]:
        """
        Discover paths to multiple contacts sequentially.

        Args:
            contact_names: List of contact names
            delay_between: Delay between discoveries (seconds)
            timeout_per_contact: Timeout for each discovery

        Returns:
            Dict mapping contact name to discovery result
        """
        results = {}

        for i, name in enumerate(contact_names):
            logger.info(f"🔍 Discovering path {i+1}/{len(contact_names)}: {name}")

            result = await self.discover_path_to_contact(name, timeout_per_contact)
            results[name] = result

            # Delay between discoveries to avoid flooding
            if i < len(contact_names) - 1:
                logger.info(f"⏸️  Waiting {delay_between}s before next discovery...")
                await asyncio.sleep(delay_between)

        # Summary
        success_count = sum(1 for r in results.values() if r.get('success'))
        logger.info(f"📊 Path discovery complete: {success_count}/{len(contact_names)} successful")

        return results

    def get_contacts_without_paths(self, limit: int = 10) -> list:
        """
        Get list of contacts that don't have paths.

        Args:
            limit: Maximum number of contacts to return

        Returns:
            List of contact names without paths
        """
        if not hasattr(self.meshcore, 'contacts'):
            return []

        contacts_without_paths = []

        for pubkey, contact in self.meshcore.contacts.items():
            out_path_len = contact.get('out_path_len', -1)
            if out_path_len < 0:
                name = contact.get('adv_name', 'Unknown')
                contacts_without_paths.append(name)

                if len(contacts_without_paths) >= limit:
                    break

        return contacts_without_paths

    async def get_node_name_from_hash(
        self,
        node_hash: str,
        contacts: Optional[Dict] = None
    ) -> str:
        """
        Look up a node's name from its 1-byte hash.

        Args:
            node_hash: 2-char hex string (1 byte)
            contacts: Optional contacts dict

        Returns:
            Node name or "?" if not found
        """
        try:
            if contacts is None:
                contacts_result = await self.meshcore.commands.get_contacts()
                from meshcore import EventType
                if contacts_result.type != EventType.CONTACTS:
                    return "?"
                contacts = contacts_result.payload

            # Match by hash prefix
            for key, contact in contacts.items():
                # Try both the 'public_key' field and the key itself
                pubkey = contact.get('public_key', key)
                if not pubkey:
                    continue

                # Normalize to hex string for consistent comparison
                if isinstance(pubkey, bytes):
                    pubkey_hex = pubkey.hex()
                else:
                    pubkey_hex = pubkey

                # Check if pubkey starts with the hash we're looking for
                if pubkey_hex.startswith(node_hash):
                    return contact.get('adv_name', '?')

            return "?"

        except Exception as e:
            logger.debug(f"Error looking up node name: {e}")
            return "?"
