#!/usr/bin/env python3
"""
MeshCore packet decoder for extracting path information from RF data
"""

from typing import Optional, Dict, List
import logging
from .enums import RouteType, PayloadType, PayloadVersion

logger = logging.getLogger(__name__)


class PacketDecoder:
    """Decodes MeshCore packets to extract routing path information"""

    def decode_meshcore_packet(self, raw_hex: str, payload_hex: str = None) -> Optional[Dict]:
        """
        Decode a MeshCore packet from raw hex data - matches Packet.cpp exactly

        Args:
            raw_hex: Raw packet data as hex string (may be RF data or direct MeshCore packet)
            payload_hex: Optional extracted payload hex string (preferred over raw_hex)

        Returns:
            Decoded packet information with path_nodes list or None if parsing fails
        """
        try:
            # Use payload_hex if provided (this is the actual MeshCore packet)
            if payload_hex:
                logger.debug("Using provided payload_hex for decoding")
                hex_data = payload_hex
            elif raw_hex:
                logger.debug("Using raw_hex for decoding")
                hex_data = raw_hex
            else:
                logger.debug("No packet data provided for decoding")
                return None

            # Remove 0x prefix if present
            if hex_data.startswith('0x'):
                hex_data = hex_data[2:]

            byte_data = bytes.fromhex(hex_data)

            # Validate minimum packet size
            if len(byte_data) < 2:
                logger.error(f"Packet too short: {len(byte_data)} bytes")
                return None

            header = byte_data[0]

            # Extract route type
            route_type = RouteType(header & 0x03)
            has_transport = route_type in [RouteType.TRANSPORT_FLOOD, RouteType.TRANSPORT_DIRECT]

            # Calculate path length offset based on presence of transport codes
            offset = 1
            if has_transport:
                offset += 4

            # Check if we have enough data for path_len
            if len(byte_data) <= offset:
                logger.error(f"Packet too short for path_len at offset {offset}: {len(byte_data)} bytes")
                return None

            path_len = byte_data[offset]
            offset += 1

            # Check if we have enough data for the full path
            if len(byte_data) < offset + path_len:
                logger.error(f"Packet too short for path (need {offset + path_len}, have {len(byte_data)})")
                return None

            # Extract path
            path_bytes = byte_data[offset:offset + path_len]
            offset += path_len

            # Remaining data is payload
            payload = byte_data[offset:]

            # Extract payload version (bits 6-7)
            payload_version = PayloadVersion((header >> 6) & 0x03)

            # Only accept VER_1 (version 0)
            if payload_version != PayloadVersion.VER_1:
                logger.warning(f"Encountered an unknown packet version. Version: {payload_version.value} RAW: {hex_data}")
                return None

            # Extract payload type (bits 2-5)
            payload_type = PayloadType((header >> 2) & 0x0F)

            # Convert path to list of hex values
            path_hex = path_bytes.hex()
            path_values = []
            i = 0
            while i < len(path_hex):
                path_values.append(path_hex[i:i+2])
                i += 2

            # Process path based on packet type
            path_info = self._process_packet_path(
                path_bytes,
                payload,
                route_type,
                payload_type
            )

            # Extract transport codes if present (only for TRANSPORT_FLOOD and TRANSPORT_DIRECT)
            transport_codes = None
            if has_transport and len(byte_data) >= 5:  # header(1) + transport(4)
                transport_bytes = byte_data[1:5]
                transport_codes = {
                    'code1': int.from_bytes(transport_bytes[0:2], byteorder='little'),
                    'code2': int.from_bytes(transport_bytes[2:4], byteorder='little'),
                    'hex': transport_bytes.hex()
                }

            packet_info = {
                'header': f"0x{header:02x}",
                # Raw values for backward compatibility
                'route_type': route_type.value,
                'route_type_name': route_type.name,
                'payload_type': payload_type.value,
                'payload_type_name': payload_type.name,
                'payload_version': payload_version.value,
                # Enum objects for improved type safety
                'route_type_enum': route_type,
                'payload_type_enum': payload_type,
                'payload_version_enum': payload_version,
                # Transport and path information
                'has_transport_codes': has_transport,
                'transport_codes': transport_codes,
                'transport_size': 4 if has_transport else 0,
                'path_len': path_len,
                'path_info': path_info,
                'path_nodes': path_values,  # This is what we need for test/path commands!
                'path_hex': path_hex,
                'payload_hex': payload.hex(),
                'payload_bytes': len(payload)
            }

            return packet_info

        except Exception as e:
            # Log as ERROR not DEBUG so we can see what's failing
            logger.error(f"Error decoding packet: {e}", exc_info=True)
            if 'hex_data' in locals():
                logger.error(f"Failed packet hex: {hex_data}")
            return None

    def _process_packet_path(self, path_bytes: bytes, payload: bytes, route_type: RouteType, payload_type: PayloadType) -> Dict:
        """
        Process path bytes based on packet type.

        Args:
            path_bytes: Raw path bytes
            payload: Payload bytes (needed for TRACE packets)
            route_type: Route type from header
            payload_type: Payload type from header

        Returns:
            dict: Processed path information
        """
        try:
            # Convert path bytes to hex node IDs
            path_nodes = [f"{b:02x}" for b in path_bytes]

            # Special handling for TRACE packets
            if payload_type == PayloadType.TRACE:
                # In TRACE packets, path field contains SNR data
                snr_values = []
                for b in path_bytes:
                    # Convert SNR byte to dB (signed value)
                    snr_db = (b - 256) / 4 if b > 127 else b / 4
                    snr_values.append(snr_db)

                return {
                    'type': 'trace',
                    'snr_data': snr_values,
                    'snr_path': path_nodes,  # SNR data as hex for reference
                    'path': [],  # No actual routing path for TRACE packets
                    'description': f"TRACE packet with {len(snr_values)} SNR readings (path contains SNR data, not routing info)"
                }

            # Regular packets - determine path type based on route type
            is_direct = route_type in [RouteType.DIRECT, RouteType.TRANSPORT_DIRECT]

            if is_direct:
                # Direct routing: path contains routing instructions
                # Bytes are stripped at each hop
                return {
                    'type': 'routing_instructions',
                    'path': path_nodes,
                    'meaning': 'bytes_stripped_at_each_hop',
                    'description': f"Direct route via {','.join(path_nodes)} ({len(path_nodes)} hops)"
                }
            else:
                # Flood routing: path contains historical route
                # Bytes are added as packet floods through network
                return {
                    'type': 'historical_route',
                    'path': path_nodes,
                    'meaning': 'bytes_added_as_packet_floods',
                    'description': f"Flooded through {','.join(path_nodes)} ({len(path_nodes)} hops)"
                }

        except Exception as e:
            logger.error(f"Error processing packet path: {e}")
            # Return basic path info as fallback
            path_nodes = [f"{b:02x}" for b in path_bytes]
            return {
                'type': 'unknown',
                'path': path_nodes,
                'description': f"Path: {','.join(path_nodes)}"
            }
