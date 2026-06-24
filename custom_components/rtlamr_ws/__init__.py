"""
RTLAMR WebSocket Integration for Home Assistant.

Consumes meter readings from the rtlamr-ws Go add-on via WebSocket
and exposes them as sensors with automatic discovery.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any

import aiohttp
import async_timeout
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONF_WS_URL,
    DOMAIN,
    PLATFORMS,
    RECONNECT_DELAY,
    signal_new_sensor,
    signal_update,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


def _parse_message(payload: str) -> dict[str, Any] | None:
    """Parse a WebSocket message and extract meter reading."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        _LOGGER.debug("Ignoring non-JSON payload: %s", payload[:100])
        return None

    if not isinstance(data, dict):
        return None

    meter_id = data.get("meter_id") or data.get("id")
    reading = data.get("reading")

    if meter_id is None or reading is None:
        _LOGGER.debug("Message missing meter_id or reading: %s", data)
        return None

    return {
        "meter_id": str(meter_id),
        "reading": reading,
        "attributes": data.get("attributes", {}),
        "last_seen": data.get("lastseen") or data.get("last_seen"),
    }


def _update_state(hass: HomeAssistant, entry_id: str, msg: dict[str, Any]) -> None:
    """Process a meter reading and dispatch to sensors."""
    meter_id = msg.get("meter_id", "")
    if not meter_id:
        return

    entry_data = hass.data[DOMAIN].get(entry_id, {})
    readings = entry_data.get("readings", {})
    sensors = entry_data.get("sensors", set())

    readings[meter_id] = msg
    is_new = meter_id not in sensors

    if is_new:
        _LOGGER.info("Discovered new meter: %s", meter_id)
        sensors.add(meter_id)
        async_dispatcher_send(hass, signal_new_sensor(entry_id), meter_id)

    async_dispatcher_send(hass, signal_update(entry_id), meter_id)


async def _listen_ws(
    hass: HomeAssistant,
    entry_id: str,
    ws_url: str,
    stop_event: asyncio.Event,
) -> None:
    """Persistent WebSocket listener loop with auto-reconnect."""
    import websockets  # Lazy import to not slow HA startup

    while not stop_event.is_set():
        try:
            async with websockets.connect(ws_url) as websocket:
                _LOGGER.info("Connected to RTLAMR WebSocket at %s", ws_url)

                async for message in websocket:
                    parsed = _parse_message(message)
                    if parsed:
                        _update_state(hass, entry_id, parsed)

        except asyncio.CancelledError:
            raise
        except websockets.exceptions.ConnectionClosedOK as err:
            _LOGGER.info("WebSocket closed cleanly (code=%s)", err.code)
        except websockets.exceptions.ConnectionClosedError as err:
            _LOGGER.warning(
                "WebSocket closed unexpectedly (code=%s, reason=%s)",
                err.code,
                err.reason,
            )
        except Exception as err:
            _LOGGER.warning("WebSocket connection error: %s", err)

        if stop_event.is_set():
            break

        _LOGGER.debug("Reconnecting in %s seconds...", RECONNECT_DELAY)
        await asyncio.sleep(RECONNECT_DELAY)


async def _check_health(
    ws_url: str, attempts: int = 5, delay: float = 2.0
) -> bool:
    """Check if the add-on is reachable via its HTTP health endpoint.

    Retries a few times before giving up so a transient startup race — Home
    Assistant loading this integration before the add-on's HTTP server is
    listening — does not surface as a spurious warning. Each failed attempt is
    logged at debug; the caller decides what to do once all attempts fail.
    """
    http_url = ws_url.replace("wss://", "https://").replace("ws://", "http://")
    base_url = http_url.rsplit("/", 1)[0]
    health_url = f"{base_url}/health"

    async with aiohttp.ClientSession() as session:
        for attempt in range(1, attempts + 1):
            try:
                async with async_timeout.timeout(5):
                    async with session.get(health_url) as resp:
                        if resp.status == 200:
                            return True
                        _LOGGER.debug(
                            "Health check %s returned HTTP %s (attempt %d/%d)",
                            health_url,
                            resp.status,
                            attempt,
                            attempts,
                        )
            except Exception as err:  # noqa: BLE001 - probe is best-effort
                _LOGGER.debug(
                    "Health check attempt %d/%d failed: %s",
                    attempt,
                    attempts,
                    err,
                )
            if attempt < attempts:
                await asyncio.sleep(delay)
    return False


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration from YAML (not used)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a config entry."""
    ws_url: str = entry.data.get(CONF_WS_URL) or entry.options.get(CONF_WS_URL)

    if not ws_url:
        raise ConfigEntryNotReady("WebSocket URL not configured")

    # Check if add-on is reachable (non-blocking warning)
    if not await _check_health(ws_url):
        _LOGGER.warning(
            "Add-on health check failed at %s - will retry in background", ws_url
        )

    stop_event = asyncio.Event()

    hass.data.setdefault(DOMAIN, {})
    entry_data: dict[str, Any] = {
        "readings": {},
        "sensors": set(),
    }
    hass.data[DOMAIN][entry.entry_id] = entry_data

    # Start WebSocket listener task
    task = hass.loop.create_task(_listen_ws(hass, entry.entry_id, ws_url, stop_event))

    # Store runtime info
    hass.data[DOMAIN]["runtime"] = {
        "stop_event": stop_event,
        "task": task,
    }

    async def _stop_ws(event: Any) -> None:
        stop_event.set()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _stop_ws)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    _LOGGER.info("RTLAMR WebSocket integration started (url=%s)", ws_url)
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when it changed."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    runtime = hass.data.get(DOMAIN, {}).get("runtime")
    if runtime:
        runtime["stop_event"].set()
        runtime["task"].cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await runtime["task"]

    hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
