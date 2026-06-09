"""Pair, trust and connect a BLE HID device through BlueZ over D-Bus."""
from __future__ import annotations

import asyncio
import logging

from dbus_fast import BusType
from dbus_fast.aio import MessageBus

_LOGGER = logging.getLogger(__name__)

BLUEZ = "org.bluez"
ADAPTER_PATH = "/org/bluez/hci0"


def _device_path(mac: str) -> str:
    return f"{ADAPTER_PATH}/dev_{mac.upper().replace(':', '_')}"


async def pair_and_trust(mac: str, timeout: float = 30.0) -> None:
    """Pair with, trust and connect to the device at `mac`.

    The device must be advertising (in pairing mode) so that BlueZ
    already knows about it. Home Assistant's Bluetooth integration keeps
    a continuous scan running, so this is normally the case.
    """
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    try:
        path = _device_path(mac)
        introspection = await bus.introspect(BLUEZ, path)
        obj = bus.get_proxy_object(BLUEZ, path, introspection)
        device = obj.get_interface("org.bluez.Device1")

        paired = await device.get_paired()
        if not paired:
            _LOGGER.debug("Pairing with %s", mac)
            await asyncio.wait_for(device.call_pair(), timeout=timeout)

        # Trusted = BlueZ accepts reconnections from the device when it
        # wakes from sleep, without user interaction. Essential for
        # battery-powered HID remotes.
        await device.set_trusted(True)

        connected = await device.get_connected()
        if not connected:
            _LOGGER.debug("Connecting to %s", mac)
            await asyncio.wait_for(device.call_connect(), timeout=timeout)
    finally:
        bus.disconnect()


async def is_paired(mac: str) -> bool:
    """Return True if BlueZ already has this device paired."""
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    try:
        path = _device_path(mac)
        introspection = await bus.introspect(BLUEZ, path)
        obj = bus.get_proxy_object(BLUEZ, path, introspection)
        device = obj.get_interface("org.bluez.Device1")
        return bool(await device.get_paired())
    except Exception:  # noqa: BLE001 - device unknown to BlueZ
        return False
    finally:
        bus.disconnect()


async def remove_device(mac: str) -> None:
    """Unpair: remove the device from the BlueZ adapter."""
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    try:
        introspection = await bus.introspect(BLUEZ, ADAPTER_PATH)
        obj = bus.get_proxy_object(BLUEZ, ADAPTER_PATH, introspection)
        adapter = obj.get_interface("org.bluez.Adapter1")
        await adapter.call_remove_device(_device_path(mac))
    except Exception:  # noqa: BLE001 - already gone
        _LOGGER.debug("Device %s was not registered with BlueZ", mac)
    finally:
        bus.disconnect()
