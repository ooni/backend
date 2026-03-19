import json
import hashlib
import requests
from typing import Dict, Any, Optional

def download_and_parse_tor_bridges() -> Dict[str, Dict[str, Any]]:
    """
    Downloads the Tor Expert Bundle pluggable transports configuration
    and parses it into a structured format.
    
    Returns:
        A dictionary mapping bridge identifiers to bridge configuration objects.
        Each bridge object contains: address, fingerprint, name, protocol, and params.
    """
    url = "https://gitlab.torproject.org/tpo/applications/tor-browser-build/-/raw/main/projects/tor-expert-bundle/pt_config.json?ref_type=heads&inline=false"
    
    try:
        # Download the file
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        config = response.json()
    except requests.RequestException as e:
        print(f"Error downloading file: {e}")
        return {}
    
    bridges_output = {}
    
    # Process each bridge type
    for bridge_type, bridge_list in config.get("bridges", {}).items():
        for bridge_line in bridge_list:
            bridge_entry = _parse_bridge_line(bridge_line, bridge_type)
            if bridge_entry:
                # Generate a unique key (hash of the bridge line)
                key = hashlib.sha256(bridge_line.encode()).hexdigest()
                bridges_output[key] = bridge_entry
    
    return bridges_output


def _parse_bridge_line(bridge_line: str, protocol: str) -> Optional[Dict[str, Any]]:
    """
    Parses a single bridge line into a structured format.
    
    Args:
        bridge_line: A single bridge configuration line
        protocol: The protocol type (e.g., 'obfs4', 'snowflake')
    
    Returns:
        A dictionary with bridge configuration or None if parsing fails
    """
    parts = bridge_line.split()
    
    if len(parts) < 2:
        return None
    
    # First part is the transport type (obfs4, snowflake, meek, etc.)
    transport = parts[0]
    # Second part is the address
    address = parts[1]
    
    # Third part is typically the fingerprint (for obfs4, snowflake)
    fingerprint = parts[2] if len(parts) > 2 else None
    
    # Parse remaining parameters
    params = {}
    for part in parts[3:]:
        if '=' in part:
            key, value = part.split('=', 1)
            if key not in params:
                params[key] = []
            params[key].append(value)
    
    return {
        "address": address,
        "fingerprint": fingerprint,
        "name": "",
        "protocol": protocol,
        "params": params if params else None
    }


if __name__ == "__main__":
    bridges = download_and_parse_tor_bridges()
    print(json.dumps(bridges, indent=2))
