"""BLE Knob integration: pairs a BLE HID rotary knob and exposes its events."""
from __future__ import annotations

import asyncio
import logging

import evdev

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .bluez import remove_device
from .const import (
    ACTION_PRESS,
    ACTION_ROTATE_LEFT,
    ACTION_ROTATE_LEFT_PRESSED,
    ACTION_ROTATE_RIGHT,
    ACTION_ROTATE_RIGHT_PRESSED,
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
    EVENT_TYPE,
    SIGNAL_AVAILABILITY,
    SIGNAL_KNOB_EVENT,
)

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["event"]

RESCAN_INTERVAL = 5.0  # seconds between /dev/input scans while disconnected


def _find_input_device(mac: str) -> evdev.InputDevice | None:
    """Locate the evdev input device whose uniq field matches the BT MAC."""
    mac_lower = mac.lower()
    for path in evdev.list_devices():
        try:
            dev = evdev.InputDevice(path)
        except OSError:
            continue
        if (dev.uniq or "").lower() == mac_lower:
            return dev
        dev.close()
    return None


class KnobListener:
    """Owns the evdev read loop for one knob, reconnecting as it sleeps/wakes."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.mac: str = entry.data[CONF_MAC]
        self._task: asyncio.Task | None = None
        self._stopping = False
        # Gesture state. `_button_down` tracks whether the button is
        # currently held; `_combo_consumed` marks that a turn happened
        # during the current hold, so the release fires no plain press.
        self._button_down = False
        self._combo_consumed = False

    @property
    def _press_keycode(self) -> int:
        return self.entry.options.get(CONF_KEY_PRESS, DEFAULT_KEY_PRESS)

    @property
    def _button_held(self) -> bool:
        return self._button_down

    def start(self) -> None:
        self._task = self.entry.async_create_background_task(
            self.hass, self._run(), name=f"ble_knob_{self.mac}"
        )

    async def stop(self) -> None:
        self._stopping = True
        if self._task:
            self._task.cancel()

    def _set_available(self, available: bool) -> None:
        async_dispatcher_send(
            self.hass,
            SIGNAL_AVAILABILITY.format(entry_id=self.entry.entry_id),
            available,
        )

    async def _run(self) -> None:
        while not self._stopping:
            dev = await self.hass.async_add_executor_job(
                _find_input_device, self.mac
            )
            if dev is None:
                self._set_available(False)
                await asyncio.sleep(RESCAN_INTERVAL)
                continue

            _LOGGER.info("Knob %s attached at %s", self.mac, dev.path)
            # Drop any half-finished gesture from before a sleep/reconnect.
            self._button_down = False
            self._combo_consumed = False
            self._set_available(True)
            try:
                async for event in dev.async_read_loop():
                    if event.type != evdev.ecodes.EV_KEY:
                        continue
                    self._handle_key_event(event.code, event.value)
            except (OSError, asyncio.CancelledError):
                if self._stopping:
                    raise
                _LOGGER.debug("Knob %s detached (sleep?), rescanning", self.mac)
            finally:
                try:
                    dev.close()
                except OSError:
                    pass
            self._set_available(False)

    def _handle_key_event(self, keycode: int, value: int) -> None:
        """Route a raw evdev key event into a knob gesture.

        The button is tracked across its full down/up lifecycle so we can
        notice a turn made while it is held. Rotations (and any unmapped
        key) fire on key_down only, matching the down/up pairs the knob
        emits per detent.
        """
        opts = self.entry.options

        if keycode == opts.get(CONF_KEY_PRESS, DEFAULT_KEY_PRESS):
            self._handle_button(value)
            return

        if value != 1:  # rotation/unknown: key_down only
            return

        # The knob's hardware press-and-turn layer sends dedicated
        # keycodes; check those first. Otherwise a plain rotation becomes
        # a "pressed" variant only if our own button-held state says so.
        if keycode == opts.get(
            CONF_KEY_ROTATE_LEFT_PRESSED, DEFAULT_KEY_ROTATE_LEFT_PRESSED
        ):
            action = ACTION_ROTATE_LEFT_PRESSED
        elif keycode == opts.get(
            CONF_KEY_ROTATE_RIGHT_PRESSED, DEFAULT_KEY_ROTATE_RIGHT_PRESSED
        ):
            action = ACTION_ROTATE_RIGHT_PRESSED
        elif keycode == opts.get(CONF_KEY_ROTATE_LEFT, DEFAULT_KEY_ROTATE_LEFT):
            action = (
                ACTION_ROTATE_LEFT_PRESSED if self._button_held else ACTION_ROTATE_LEFT
            )
        elif keycode == opts.get(CONF_KEY_ROTATE_RIGHT, DEFAULT_KEY_ROTATE_RIGHT):
            action = (
                ACTION_ROTATE_RIGHT_PRESSED if self._button_held else ACTION_ROTATE_RIGHT
            )
        else:
            action = None  # unmapped keycode: still emitted for discovery

        if self._button_held and action in (
            ACTION_ROTATE_LEFT_PRESSED,
            ACTION_ROTATE_RIGHT_PRESSED,
        ):
            # A turn during the hold: the upcoming release is part of this
            # combo, not a separate press.
            self._combo_consumed = True

        self._emit(action, keycode)

    def _handle_button(self, value: int) -> None:
        """Fire a press on release, unless the hold was a turn combo."""
        if value == 1:  # down
            self._button_down = True
            self._combo_consumed = False
            return
        if value != 0:  # autorepeat (2): still held, nothing to decide
            return

        # Released.
        was_down = self._button_down
        self._button_down = False
        if not was_down:
            return  # release with no matching press (e.g. across reconnect)
        if self._combo_consumed:
            self._combo_consumed = False
            return  # already expressed as a rotate-while-pressed gesture
        self._emit(ACTION_PRESS, self._press_keycode)

    def _emit(self, action: str | None, keycode: int) -> None:
        payload = {
            "entry_id": self.entry.entry_id,
            "mac": self.mac,
            "name": self.entry.data.get(CONF_NAME),
            "keycode": keycode,
            "action": action,
        }
        # Bus event: usable in automations even without the entities
        self.hass.bus.async_fire(EVENT_TYPE, payload)
        # Dispatcher: drives the event entities
        async_dispatcher_send(
            self.hass,
            SIGNAL_KNOB_EVENT.format(entry_id=self.entry.entry_id),
            payload,
        )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a knob from a config entry."""
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={(dr.CONNECTION_BLUETOOTH, entry.data[CONF_MAC])},
        name=entry.data.get(CONF_NAME, "BLE Knob"),
        manufacturer="Anticater",
        model="VK01",
    )

    listener = KnobListener(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = listener

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    listener.start()

    entry.async_on_unload(entry.add_update_listener(_update_listener))
    return True


async def _update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload on options change (keymap edits)."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    listener: KnobListener = hass.data[DOMAIN].pop(entry.entry_id)
    await listener.stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Unpair from BlueZ when the integration is deleted."""
    await remove_device(entry.data[CONF_MAC])
