"""
Constants for the RTLAMR WebSocket custom integration.
"""

from homeassistant.const import Platform

VERSION = "1.0.0"
DOMAIN = "rtlamr_ws"
PLATFORMS = [Platform.SENSOR]
DEFAULT_WS_URL = "ws://homeassistant.local:8080/ws"
DEFAULT_TITLE = "RTLAMR WebSocket"

CONF_WS_URL = "websocket_url"

# Reconnection delay in seconds
RECONNECT_DELAY = 10


def signal_new_sensor(entry_id: str) -> str:
    """Signal name for newly discovered sensors."""
    return f"{DOMAIN}_new_sensor_{entry_id}"


def signal_update(entry_id: str) -> str:
    """Signal name for sensor updates."""
    return f"{DOMAIN}_update_{entry_id}"
