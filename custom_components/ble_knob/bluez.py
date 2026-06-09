"""Pair, trust and connect a BLE HID device through BlueZ over D-Bus."""
from __future__ import annotations

import asyncio
import logging

from dbus_fast import BusType
from dbus_fast.aio import MessageBus
from dbus_fast.service import ServiceInterface, method

_LOGGER = logging.getLogger(__name__)

BLUEZ = "org.bluez"
ADAPTER_PATH = "/org/bluez/hci0"
AGENT_MANAGER_PATH = "/org/bluez"
AGENT_PATH = "/org/bluez/ble_knob_agent"
# "Just Works" pairing: BlueZ never asks for a PIN or passkey, which is
# the only mode a knob with no keypad or display can satisfy.
AGENT_CAPABILITY = "NoInputNoOutput"


def _device_path(mac: str) -> str:
    return f"{ADAPTER_PATH}/dev_{mac.upper().replace(':', '_')}"


class _PairingAgent(ServiceInterface):
    """A minimal ``org.bluez.Agent1`` that accepts Just Works pairing.

    BlueZ refuses to authenticate a new device unless an agent is
    registered to answer the pairing handshake — this is why a bare
    ``Device1.Pair()`` returns *Authentication Failed*. A knob cannot
    display or enter a passkey, so every request is satisfied with the
    "no interaction" answer: confirmations and authorisations return
    (which accepts them) and the unused PIN/passkey requests return
    harmless defaults.
    """

    def __init__(self) -> None:
        super().__init__("org.bluez.Agent1")

    @method()
    def Release(self):  # noqa: N802 - D-Bus method name
        _LOGGER.debug("Pairing agent released")

    @method()
    def RequestPinCode(self, device: "o") -> "s":  # type: ignore[name-defined] # noqa: N802,F821
        return "0000"

    @method()
    def DisplayPinCode(self, device: "o", pincode: "s"):  # type: ignore[name-defined] # noqa: N802,F821
        pass

    @method()
    def RequestPasskey(self, device: "o") -> "u":  # type: ignore[name-defined] # noqa: N802,F821
        return 0

    @method()
    def DisplayPasskey(self, device: "o", passkey: "u", entered: "q"):  # type: ignore[name-defined] # noqa: N802,F821
        pass

    @method()
    def RequestConfirmation(self, device: "o", passkey: "u"):  # type: ignore[name-defined] # noqa: N802,F821
        # Returning without raising accepts the pairing.
        _LOGGER.debug("Auto-confirming pairing for %s", device)

    @method()
    def RequestAuthorization(self, device: "o"):  # type: ignore[name-defined] # noqa: N802,F821
        _LOGGER.debug("Auto-authorising %s", device)

    @method()
    def AuthorizeService(self, device: "o", uuid: "s"):  # type: ignore[name-defined] # noqa: N802,F821
        pass

    @method()
    def Cancel(self):  # noqa: N802 - D-Bus method name
        _LOGGER.debug("Pairing cancelled by BlueZ")


async def _agent_manager(bus: MessageBus):
    """Return the ``org.bluez.AgentManager1`` interface proxy."""
    introspection = await bus.introspect(BLUEZ, AGENT_MANAGER_PATH)
    obj = bus.get_proxy_object(BLUEZ, AGENT_MANAGER_PATH, introspection)
    return obj.get_interface("org.bluez.AgentManager1")


async def _register_agent(bus: MessageBus) -> None:
    """Export and register a Just Works pairing agent on this connection.

    BlueZ routes pairing prompts to the agent registered by the same
    D-Bus connection that calls ``Pair()``, so the agent and the pairing
    call must share one bus. Becoming the default agent is best effort —
    if another integration already holds it, ours is still used for the
    pairing we initiate here.
    """
    bus.export(AGENT_PATH, _PairingAgent())
    manager = await _agent_manager(bus)
    await manager.call_register_agent(AGENT_PATH, AGENT_CAPABILITY)
    try:
        await manager.call_request_default_agent(AGENT_PATH)
    except Exception:  # noqa: BLE001 - another default agent is registered
        _LOGGER.debug("Could not become default pairing agent; continuing")


async def _unregister_agent(bus: MessageBus) -> None:
    """Unregister and unexport the pairing agent. Never raises."""
    try:
        manager = await _agent_manager(bus)
        await manager.call_unregister_agent(AGENT_PATH)
    except Exception:  # noqa: BLE001 - already gone or never registered
        _LOGGER.debug("Pairing agent was not registered")
    finally:
        bus.unexport(AGENT_PATH)


async def pair_and_trust(mac: str, timeout: float = 30.0) -> None:
    """Pair with, trust and connect to the device at `mac`.

    The device must be advertising (in pairing mode) so that BlueZ
    already knows about it. Home Assistant's Bluetooth integration keeps
    a continuous scan running, so this is normally the case.
    """
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    try:
        # A registered agent is required for BlueZ to authenticate a new
        # HID device; without it Pair() fails with "Authentication
        # Failed". Keep it alive for the whole pair/connect sequence.
        await _register_agent(bus)
        try:
            path = _device_path(mac)
            introspection = await bus.introspect(BLUEZ, path)
            obj = bus.get_proxy_object(BLUEZ, path, introspection)
            device = obj.get_interface("org.bluez.Device1")

            paired = await device.get_paired()
            if not paired:
                _LOGGER.debug("Pairing with %s", mac)
                await asyncio.wait_for(device.call_pair(), timeout=timeout)

            # Trusted = BlueZ accepts reconnections from the device when
            # it wakes from sleep, without user interaction. Essential
            # for battery-powered HID remotes.
            await device.set_trusted(True)

            connected = await device.get_connected()
            if not connected:
                _LOGGER.debug("Connecting to %s", mac)
                await asyncio.wait_for(device.call_connect(), timeout=timeout)
        finally:
            await _unregister_agent(bus)
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
