"""
Config flow for RTLAMR WebSocket integration with connectivity validation.
"""

from __future__ import annotations

import aiohttp
import async_timeout
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    CONF_WS_URL,
    DEFAULT_TITLE,
    DEFAULT_WS_URL,
    DOMAIN,
)


def _http_base(ws_url: str) -> str:
    """Convert WebSocket URL to HTTP base URL."""
    http_url = ws_url.replace("wss://", "https://").replace("ws://", "http://")
    return http_url.rsplit("/", 1)[0]


class RtlamrConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the integration."""

    VERSION = 1

    async def _check_connectivity(self, ws_url: str) -> bool:
        """Check if the add-on is reachable."""
        base = _http_base(ws_url)
        health_url = f"{base}/health"

        try:
            async with aiohttp.ClientSession() as session:
                async with async_timeout.timeout(5):
                    async with session.get(health_url) as resp:
                        return resp.status == 200
        except Exception:
            return False

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}

        if user_input is not None:
            ws_url = user_input[CONF_WS_URL]

            # Validate connectivity
            if not await self._check_connectivity(ws_url):
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=DEFAULT_TITLE, data=user_input)

        data_schema = vol.Schema(
            {
                vol.Required(CONF_WS_URL, default=DEFAULT_WS_URL): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "default_url": DEFAULT_WS_URL,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return RtlamrOptionsFlow()


class RtlamrOptionsFlow(config_entries.OptionsFlow):
    """Handle options for an existing entry."""

    async def _check_connectivity(self, ws_url: str) -> bool:
        """Check if the add-on is reachable."""
        base = _http_base(ws_url)
        health_url = f"{base}/health"

        try:
            async with aiohttp.ClientSession() as session:
                async with async_timeout.timeout(5):
                    async with session.get(health_url) as resp:
                        return resp.status == 200
        except Exception:
            return False

    async def async_step_init(self, user_input=None):
        errors: dict[str, str] = {}

        if user_input is not None:
            ws_url = user_input[CONF_WS_URL]

            # Validate connectivity
            if not await self._check_connectivity(ws_url):
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title="", data=user_input)

        # Get current config from options first, fall back to data
        current_config = self.config_entry.options or self.config_entry.data
        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_WS_URL, default=current_config.get(CONF_WS_URL, DEFAULT_WS_URL)
                ): str,
            }
        )

        return self.async_show_form(
            step_id="init", data_schema=data_schema, errors=errors
        )
