"""Config flow for BLE Knob: discover, pair, and map keys."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback

from .bluez import pair_and_trust
from .const import (
    CONF_KEY_PRESS,
    CONF_KEY_ROTATE_LEFT,
    CONF_KEY_ROTATE_LEFT_PRESSED,
    CONF_KEY_ROTATE_RIGHT,
    CONF_KEY_ROTATE_RIGHT_PRESSED,
    CONF_MAC,
    CONF_NAME,
    DEFAULT_KEY_PRESS,
    DEFAULT_KEY_ROTATE_LEFT,
    DEFAULT_KEY_ROTATE_LEFT_PRESSED,
    DEFAULT_KEY_ROTATE_RIGHT,
    DEFAULT_KEY_ROTATE_RIGHT_PRESSED,
    DOMAIN,
    HID_SERVICE_UUID,
)

_LOGGER = logging.getLogger(__name__)


def _is_hid(info: BluetoothServiceInfoBleak) -> bool:
    return HID_SERVICE_UUID in (info.service_uuids or [])


class BleKnobConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle discovery and pairing."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery: BluetoothServiceInfoBleak | None = None

    # -- Automatic discovery (knob in pairing mode, advertising HID) -------

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery = discovery_info
        self.context["title_placeholders"] = {
            "name": discovery_info.name or discovery_info.address
        }
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._discovery is not None
        if user_input is not None:
            return await self._async_pair(self._discovery)
        return self.async_show_form(
            step_id="confirm",
            description_placeholders={
                "name": self._discovery.name or self._discovery.address,
                "address": self._discovery.address,
            },
        )

    # -- Manual: pick from currently visible HID devices --------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        candidates = {
            info.address: info
            for info in bluetooth.async_discovered_service_info(self.hass)
            if _is_hid(info)
        }
        # Filter out already-configured devices
        configured = self._async_current_ids()
        candidates = {
            addr: info for addr, info in candidates.items() if addr not in configured
        }

        if user_input is not None:
            self._discovery = candidates[user_input[CONF_MAC]]
            await self.async_set_unique_id(self._discovery.address)
            self._abort_if_unique_id_configured()
            return await self._async_pair(self._discovery)

        if not candidates:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MAC): vol.In(
                        {
                            addr: f"{info.name or 'Unknown'} ({addr})"
                            for addr, info in candidates.items()
                        }
                    )
                }
            ),
        )

    # -- Pairing -------------------------------------------------------------

    async def _async_pair(
        self, info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        try:
            await pair_and_trust(info.address)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Pairing with %s failed: %s", info.address, err)
            return self.async_abort(reason="pairing_failed")

        return self.async_create_entry(
            title=info.name or info.address,
            data={
                CONF_MAC: info.address,
                CONF_NAME: info.name or info.address,
            },
            options={
                CONF_KEY_ROTATE_LEFT: DEFAULT_KEY_ROTATE_LEFT,
                CONF_KEY_ROTATE_RIGHT: DEFAULT_KEY_ROTATE_RIGHT,
                CONF_KEY_PRESS: DEFAULT_KEY_PRESS,
                CONF_KEY_ROTATE_LEFT_PRESSED: DEFAULT_KEY_ROTATE_LEFT_PRESSED,
                CONF_KEY_ROTATE_RIGHT_PRESSED: DEFAULT_KEY_ROTATE_RIGHT_PRESSED,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> "BleKnobOptionsFlow":
        return BleKnobOptionsFlow()


class BleKnobOptionsFlow(OptionsFlow):
    """Remap evdev keycodes to knob actions.

    Tip: fire the knob and watch the `ble_knob_event` bus event in
    Developer Tools to read off the keycodes it actually sends.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        opts = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_KEY_ROTATE_LEFT,
                        default=opts.get(
                            CONF_KEY_ROTATE_LEFT, DEFAULT_KEY_ROTATE_LEFT
                        ),
                    ): vol.Coerce(int),
                    vol.Required(
                        CONF_KEY_ROTATE_RIGHT,
                        default=opts.get(
                            CONF_KEY_ROTATE_RIGHT, DEFAULT_KEY_ROTATE_RIGHT
                        ),
                    ): vol.Coerce(int),
                    vol.Required(
                        CONF_KEY_PRESS,
                        default=opts.get(CONF_KEY_PRESS, DEFAULT_KEY_PRESS),
                    ): vol.Coerce(int),
                    vol.Required(
                        CONF_KEY_ROTATE_LEFT_PRESSED,
                        default=opts.get(
                            CONF_KEY_ROTATE_LEFT_PRESSED,
                            DEFAULT_KEY_ROTATE_LEFT_PRESSED,
                        ),
                    ): vol.Coerce(int),
                    vol.Required(
                        CONF_KEY_ROTATE_RIGHT_PRESSED,
                        default=opts.get(
                            CONF_KEY_ROTATE_RIGHT_PRESSED,
                            DEFAULT_KEY_ROTATE_RIGHT_PRESSED,
                        ),
                    ): vol.Coerce(int),
                }
            ),
        )
