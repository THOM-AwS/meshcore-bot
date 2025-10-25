"""MeshCore Map API client with regional filtering and caching."""
import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta, timezone
import requests

logger = logging.getLogger('meshcore.bot')


class MeshCoreAPI:
    """
    Client for MeshCore Map API with Sydney/NSW regional filtering and caching.

    API: https://map.meshcore.dev/api/v1/nodes
    """

    # Greater Sydney bounding box
    SYDNEY_BOUNDS = {
        'lat_min': -34.5,
        'lat_max': -33.0,
        'lon_min': 150.0,
        'lon_max': 151.5
    }

    # NSW bounding box (larger region)
    NSW_BOUNDS = {
        'lat_min': -37.5,
        'lat_max': -28.0,
        'lon_min': 141.0,
        'lon_max': 154.0
    }

    def __init__(self, base_url: str = "https://map.meshcore.dev/api/v1", cache_ttl: int = 3600):
        """
        Initialize API client.

        Args:
            base_url: API base URL
            cache_ttl: Cache time-to-live in seconds (default: 60 minutes)
        """
        self.base_url = base_url
        self.cache_ttl = cache_ttl
        self._cache: Optional[List[Dict]] = None
        self._cache_time: Optional[float] = None
        self._sydney_cache: Optional[List[Dict]] = None
        self._nsw_cache: Optional[List[Dict]] = None

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
                return self._nsw_cache + [n for n in self._cache if not self._is_nsw_node(n)]

            return self._cache

        except Exception as e:
            logger.error(f"Error fetching nodes from API: {e}")
            # Return stale cache if available
            if self._cache:
                logger.warning("Returning stale cache due to API error")
                return self._cache
            return []

    def get_sydney_nodes(self) -> List[Dict]:
        """Get all nodes in Greater Sydney region."""
        if self._is_cache_valid() and self._sydney_cache is not None:
            return self._sydney_cache

        # Refresh cache
        self.get_nodes()
        return self._sydney_cache or []

    def get_nsw_nodes(self) -> List[Dict]:
        """Get all nodes in NSW region."""
        if self._is_cache_valid() and self._nsw_cache is not None:
            return self._nsw_cache

        # Refresh cache
        self.get_nodes()
        return self._nsw_cache or []

    def filter_nodes_by_days(self, nodes: List[Dict], days: int = 7) -> List[Dict]:
        """
        Filter nodes seen in the last N days.

        Args:
            nodes: List of node dictionaries
            days: Number of days to look back

        Returns:
            Filtered list of active nodes
        """
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
