"""Event entities for the BLE Knob."""
from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ACTION_PRESS,
    ACTION_ROTATE_LEFT,
    ACTION_ROTATE_RIGHT,
    CONF_MAC,
    CONF_NAME,
    DOMAIN,
    SIGNAL_AVAILABILITY,
    SIGNAL_KNOB_EVENT,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(
        [
            KnobEventEntity(
                entry,
                key="rotation",
                name="Rotation",
                event_types=[ACTION_ROTATE_LEFT, ACTION_ROTATE_RIGHT],
                icon="mdi:rotate-360",
            ),
            KnobEventEntity(
                entry,
                key="button",
                name="Button",
                event_types=[ACTION_PRESS],
                icon="mdi:gesture-tap-button",
            ),
        ]
    )


class KnobEventEntity(EventEntity):
    """Fires when the knob rotates or is pressed."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        entry: ConfigEntry,
        key: str,
        name: str,
        event_types: list[str],
        icon: str,
    ) -> None:
        self._entry = entry
        self._attr_name = name
        self._attr_icon = icon
        self._attr_event_types = event_types
        self._attr_unique_id = f"{entry.data[CONF_MAC]}_{key}"
        self._attr_available = False
        self._attr_device_info = DeviceInfo(
            connections={(dr.CONNECTION_BLUETOOTH, entry.data[CONF_MAC])},
            name=entry.data.get(CONF_NAME, "BLE Knob"),
            manufacturer="Anticater",
            model="VK01",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_KNOB_EVENT.format(entry_id=self._entry.entry_id),
                self._handle_event,
            )
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_AVAILABILITY.format(entry_id=self._entry.entry_id),
                self._handle_availability,
            )
        )

    @callback
    def _handle_event(self, payload: dict) -> None:
        action = payload.get("action")
        if action in self.event_types:
            self._trigger_event(action, {"keycode": payload.get("keycode")})
            self.async_write_ha_state()

    @callback
    def _handle_availability(self, available: bool) -> None:
        self._attr_available = available
        self.async_write_ha_state()
