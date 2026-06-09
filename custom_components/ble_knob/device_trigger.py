"""Device automation triggers for the BLE Knob.

Exposes the knob's rotation and press as Home Assistant *device triggers*
so they appear in the automation editor's "Device" trigger picker. Each
trigger is wired to the ``ble_knob_event`` bus event (fired in
``__init__.py``), filtered to this knob's MAC and the chosen action.
"""
from __future__ import annotations

import voluptuous as vol

from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.components.homeassistant.triggers import event as event_trigger
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_PLATFORM,
    CONF_TYPE,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType

from .const import (
    ACTION_LONG_PRESS,
    ACTION_PRESS,
    ACTION_ROTATE_LEFT,
    ACTION_ROTATE_LEFT_PRESSED,
    ACTION_ROTATE_RIGHT,
    ACTION_ROTATE_RIGHT_PRESSED,
    DOMAIN,
    EVENT_TYPE,
)

TRIGGER_TYPES = {
    ACTION_ROTATE_LEFT,
    ACTION_ROTATE_RIGHT,
    ACTION_PRESS,
    ACTION_LONG_PRESS,
    ACTION_ROTATE_LEFT_PRESSED,
    ACTION_ROTATE_RIGHT_PRESSED,
}

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES),
    }
)


def _device_mac(hass: HomeAssistant, device_id: str) -> str | None:
    """Return the Bluetooth MAC recorded for this device, if any."""
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        return None
    for conn_type, conn_value in device.connections:
        if conn_type == dr.CONNECTION_BLUETOOTH:
            return conn_value
    return None


async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, str]]:
    """List the device triggers for a BLE Knob device."""
    return [
        {
            CONF_PLATFORM: "device",
            CONF_DEVICE_ID: device_id,
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: trigger_type,
        }
        for trigger_type in TRIGGER_TYPES
    ]


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a device trigger by listening for the matching knob event."""
    event_data = {"action": config[CONF_TYPE]}
    # Scope the trigger to this specific knob so several knobs don't
    # cross-fire. The MAC is the device's Bluetooth connection value,
    # which matches the `mac` field of every ble_knob_event payload.
    mac = _device_mac(hass, config[CONF_DEVICE_ID])
    if mac is not None:
        event_data["mac"] = mac

    event_config = event_trigger.TRIGGER_SCHEMA(
        {
            event_trigger.CONF_PLATFORM: "event",
            event_trigger.CONF_EVENT_TYPE: EVENT_TYPE,
            event_trigger.CONF_EVENT_DATA: event_data,
        }
    )
    return await event_trigger.async_attach_trigger(
        hass, event_config, action, trigger_info, platform_type="device"
    )
