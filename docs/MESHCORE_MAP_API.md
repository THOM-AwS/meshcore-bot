# MeshCore Map API

This document describes how to interact with the official MeshCore Map API to register and update nodes.

## API Endpoint

**Base URL:** `https://map.meshcore.dev/api/v1`

## Endpoints

### GET /nodes
Retrieve all nodes registered on the map.

**Request:**
```bash
curl https://map.meshcore.dev/api/v1/nodes
```

**Response:**
```json
[
  {
    "public_key": "abc123...",
    "adv_name": "Node Name",
    "adv_lat": -33.8688,
    "adv_lon": 151.2093,
    "type": 2,
    "last_advert": "2025-10-26T10:00:00Z",
    "params": {
      "freq": 915.8,
      "sf": 11
    },
    ...
  }
]
```

### POST /nodes
Register or update a node on the map.

**Request:**
```bash
curl -X POST https://map.meshcore.dev/api/v1/nodes \
  -H "Content-Type: application/json" \
  -d '{
    "links": ["meshcore://616263313233..."],
    "radio": {}
  }'
```

**Parameters:**
- `links` (required): Array of meshcore:// links (contact QR code data)
- `radio` (optional): Radio configuration object

**Response:**
```json
{
  "message": "Node registered successfully"
}
```

Or on error:
```json
{
  "error": "Invalid meshcore link format"
}
```

## MeshCore Link Format

The `meshcore://` link is a custom URI scheme containing hex-encoded contact card data.

**Format:** `meshcore://{hex(card_data)}`

This is the same data encoded in contact QR codes used for sharing node information between devices.

### How to Get Your MeshCore Link

**From MeshCore App:**
1. For BLE Companion radios:
   - Tap 3-dot menu (top right)
   - Tap "Internet Map"
   - Tap 3-dot menu again
   - Choose "Add me to the Map"

2. For Repeaters/Room Servers:
   - Go to Contact List
   - Tap 3-dot next to the node
   - Tap "Share"
   - Tap "Upload to Internet Map"

**Programmatically:**
- The link can be generated from node's SELF_INFO contact card data
- Contact card contains: public key, advertised name, location, etc.
- Encode as hex and prefix with `meshcore://`

## Python Implementation Example

```python
import requests

class MeshCoreMapAPI:
    BASE_URL = "https://map.meshcore.dev/api/v1"

    def get_nodes(self):
        """Fetch all nodes from the map."""
        response = requests.get(f"{self.BASE_URL}/nodes", timeout=10)
        response.raise_for_status()
        return response.json()

    def register_node(self, meshcore_link):
        """Register a node on the map.

        Args:
            meshcore_link: MeshCore link (e.g., "meshcore://abc123...")

        Returns:
            Response message from API
        """
        if not meshcore_link.startswith('meshcore://'):
            raise ValueError("Invalid meshcore link format")

        payload = {
            "links": [meshcore_link],
            "radio": {}
        }

        response = requests.post(
            f"{self.BASE_URL}/nodes",
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=10
        )
        response.raise_for_status()
        return response.json()
```

## Removing Nodes

To remove a node from the map:
- Use the same companion (same public key) that added the node
- Follow the app's "Remove from Map" flow
- This ensures only the node owner can remove it

## Additional Resources

- **Official Map:** https://map.meshcore.dev/
- **Map Frontend Source:** https://github.com/meshcore-dev/map.meshcore.dev
- **MeshCore Documentation:** https://github.com/meshcore-dev/MeshCore
- **MeshCore FAQ:** https://github.com/meshcore-dev/MeshCore/blob/main/docs/faq.md

## Notes

- The API uses the same contact card format as QR codes
- Nodes can only be updated/removed by the same public key that registered them
- The map is public - all registered nodes are visible
- Location data (lat/lon) is optional but recommended for map display
- Node type: 1 = Companion, 2 = Repeater
