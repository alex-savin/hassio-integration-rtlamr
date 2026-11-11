"""
Sensor entities fed by readings from the Go add-on.
"""

from __future__ import annotations

from typing import Any

import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, signal_new_sensor, signal_update

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities) -> None:
    """Set up sensor entities for this entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    sensors: dict[str, RtlamrSensor] = {}

    @callback
    def handle_new_sensor(meter_id: str) -> None:
        if meter_id in sensors:
            _LOGGER.debug("Sensor for meter %s already exists", meter_id)
            return
        _LOGGER.debug("Creating sensor for meter %s", meter_id)
        sensor = RtlamrSensor(hass, entry.entry_id, meter_id)
        sensors[meter_id] = sensor
        async_add_entities([sensor], update_before_add=True)
        _LOGGER.info("Added sensor: %s", sensor.name)

    # Add any meters we already have state for
    for meter_id in data.get("readings", {}):
        handle_new_sensor(meter_id)

    # Subscribe to new sensor discovery
    unsub = async_dispatcher_connect(
        hass, signal_new_sensor(entry.entry_id), handle_new_sensor
    )
    entry.async_on_unload(unsub)


class RtlamrSensor(RestoreEntity, SensorEntity):
    """Represents a meter reading as a sensor."""

    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, entry_id: str, meter_id: str) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._meter_id = meter_id

        # Get meter name from first reading if available
        domain_data = hass.data[DOMAIN].get(entry_id, {})
        reading = domain_data.get("readings", {}).get(meter_id, {})
        meter_name = reading.get("attributes", {}).get("meter_name", "Unknown")

        self._attr_unique_id = f"{DOMAIN}_{meter_id}"
        self._attr_has_entity_name = False
        self._attr_name = f"{meter_name.title()} Meter ({meter_id})"
        self._unsub_update = None

    async def async_added_to_hass(self) -> None:
        """Restore previous state and subscribe to updates."""
        await super().async_added_to_hass()
        _LOGGER.debug("Sensor %s added to Home Assistant", self._meter_id)

        # Restore previous state if available
        if (last_state := await self.async_get_last_state()) is not None:
            _LOGGER.debug(
                "Restoring previous state for %s: %s %s",
                self._meter_id,
                last_state.state,
                last_state.attributes.get("unit_of_measurement")
                if last_state.attributes
                else "",
            )
            self._attr_native_value = last_state.state
            if last_state.attributes:
                self._attr_native_unit_of_measurement = last_state.attributes.get(
                    "unit_of_measurement"
                )
                device_class = last_state.attributes.get("device_class")
                if device_class and device_class != "none":
                    self._attr_device_class = device_class
                state_class = last_state.attributes.get("state_class")
                if state_class:
                    self._attr_state_class = state_class
        else:
            _LOGGER.debug("No previous state to restore for %s", self._meter_id)

        @callback
        def handle_update(meter_id: str) -> None:
            if meter_id != self._meter_id:
                return
            _LOGGER.debug("Updating sensor %s", self._meter_id)
            self._apply_state()
            self.async_write_ha_state()

        self._apply_state()
        self._unsub_update = async_dispatcher_connect(
            self._hass, signal_update(self._entry_id), handle_update
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub_update:
            self._unsub_update()
            self._unsub_update = None

    def _get_reading(self) -> dict[str, Any] | None:
        domain_data = self._hass.data[DOMAIN].get(self._entry_id, {})
        return domain_data.get("readings", {}).get(self._meter_id)

    def _apply_state(self) -> None:
        reading = self._get_reading()
        if not reading:
            _LOGGER.debug("No reading available for %s", self._meter_id)
            return

        attributes = reading.get("attributes", {}) or {}
        last_seen = reading.get("last_seen")
        value = reading.get("reading")

        _LOGGER.debug(
            "Applying state for %s: value=%s, attributes=%s",
            self._meter_id,
            value,
            attributes,
        )

        # Preferred name from attributes, fallback to meter id
        name = attributes.get("name") or attributes.get("friendly_name")
        if name:
            self._attr_name = name

        # Ensure value is numeric - try to convert strings to float
        if isinstance(value, str):
            try:
                # Remove any invalid characters and convert
                original_value = value
                value = float(value.replace("<nil>", "0").replace("<nil.>", "0"))
                if original_value != str(value):
                    _LOGGER.debug(
                        "Converted string value '%s' to float %s", original_value, value
                    )
            except (ValueError, AttributeError) as err:
                _LOGGER.warning(
                    "Failed to convert value '%s' to float for %s: %s",
                    value,
                    self._meter_id,
                    err,
                )
                value = None

        self._attr_native_value = value

        # Set unit of measurement from meter config
        unit = attributes.get("unit_of_measurement")
        if unit:
            self._attr_native_unit_of_measurement = unit
            _LOGGER.debug("Set unit for %s: %s", self._meter_id, unit)

        # Set device class from meter config (if provided)
        device_class = attributes.get("device_class")
        if device_class and device_class != "none":
            self._attr_device_class = device_class
            _LOGGER.debug("Set device_class for %s: %s", self._meter_id, device_class)

        # Set state class from meter config (if provided)
        state_class = attributes.get("state_class")
        if state_class:
            self._attr_state_class = state_class
            _LOGGER.debug("Set state_class for %s: %s", self._meter_id, state_class)

        extra_attrs = dict(attributes)
        if last_seen:
            extra_attrs["last_seen"] = last_seen
        self._attr_extra_state_attributes = extra_attrs

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._meter_id)},
            "name": self._attr_name,
            "manufacturer": "RTLAMR",
            "model": "Meter",
        }
