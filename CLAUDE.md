# CLAUDE.md

Guidance for LLM-assisted development of this repository. Read this fully
before making changes.

## What this project is

A Home Assistant **custom integration** (HACS-distributable, domain
`ble_knob`) that pairs BLE HID rotary knobs — built for the Anticater VK01,
but generic to any Bluetooth knob presenting as a keyboard — and exposes
rotation/press as HA event entities.

It is NOT a Home Assistant add-on (no Dockerfile, no Supervisor config).
Do not introduce add-on packaging.

## Architecture

The data path, end to end:

```
Knob (BLE HID peripheral)
  │  pairs/bonds via BlueZ (host OS)
  ▼
BlueZ exposes a Linux input device  /dev/input/eventN  (uniq == BT MAC)
  │  read with python-evdev, async_read_loop()
  ▼
KnobListener (__init__.py)  — one background task per config entry
  │  filters EV_KEY, value==1 (key_down only)
  │  maps keycode → action via entry.options
  ├─► hass.bus.async_fire("ble_knob_event", payload)      # raw, for users
  └─► dispatcher SIGNAL_KNOB_EVENT.format(entry_id=...)   # for entities
        ▼
      event.py — two EventEntity per knob (rotation, button)
```

Pairing path (config_flow.py → bluez.py):

```
HA Bluetooth integration sees HID advertisement (service UUID 1812)
  → async_step_bluetooth (auto) or async_step_user (manual pick)
  → bluez.pair_and_trust(mac): D-Bus calls on org.bluez.Device1
      Pair() → set Trusted=True → Connect()
  → config entry created with MAC + default keymap in options
```

### File map

| File | Responsibility |
|---|---|
| `custom_components/ble_knob/__init__.py` | Entry setup/unload, `KnobListener` (evdev read loop + reconnect), device registry |
| `bluez.py` | All D-Bus/BlueZ interaction: pair, trust, connect, is_paired, remove |
| `config_flow.py` | Discovery (bluetooth + manual), pairing step, options flow (keymap) |
| `event.py` | The two `EventEntity` classes, availability via dispatcher |
| `device_trigger.py` | Device automation triggers (rotate_left/right, press), delegating to the `ble_knob_event` bus event |
| `const.py` | Domain, conf keys, default keycodes, signal templates |
| `manifest.json` | Bluetooth matcher (`service_uuid` 1812), requirement `evdev` |
| `strings.json` / `translations/en.json` | Flow UI text — keep these two files identical |

## Key design decisions (do not silently reverse)

1. **Rotation is key_down only** (`event.value == 1`). Knob detents
   arrive as down+up pairs; reacting to both would double every event.
   The **button**, by contrast, is tracked across its full down/up
   lifecycle (`_handle_button`) so the gesture layer can tell a tap from
   a hold and notice a turn made while it is held. The button is
   classified on **release**: tap → `press`, held past
   `long_press_ms` → `long_press`, and a turn during the hold marks
   `_combo_consumed` so the release fires nothing (the turn already
   emitted `rotate_*_pressed`). This assumes the knob keeps the button
   *held down* while pressed; a momentary button that taps instantly
   makes only `press`/`rotate_*` reachable.
2. **Device matched by `dev.uniq == MAC`**, not by `/dev/input/eventN`
   path or name. Event numbers shuffle across reconnects; names collide
   when running multiple identical knobs.
3. **Two delivery channels on purpose**: bus event (`ble_knob_event`)
   for user-facing discovery/debugging and power users; dispatcher for
   the entities. Keep both in sync if the payload changes.
4. **Options hold the keymap**, data holds identity (MAC, name). Options
   changes trigger a full entry reload via the update listener — cheap
   and correct, don't optimise it away.
5. **`trust` during pairing is essential.** Without `Trusted=True`,
   battery-powered HID devices cannot reconnect after sleeping. If
   pairing code is refactored, this must survive.
6. **Reconnect loop is poll-based** (5 s rescan of `/dev/input` when the
   device is gone). A udev/pyudev monitor would be more elegant — see
   Backlog — but the poll is simple and proven. Don't replace it without
   testing on HA OS.

## Hard constraints from the runtime

- Runs inside the HA container on HA OS. It has: D-Bus access to host
  BlueZ (the core `bluetooth` integration relies on this), and
  `/dev/input` visibility. It does NOT have: arbitrary host shell, udev
  rule installation, root on the host.
- `dbus-fast` ships with HA core — use it, do not add `dbus-python` or
  `pydbus`. `evdev` is the only pip requirement; keep requirements
  minimal, HACS installs them via manifest only.
- Never block the event loop. evdev enumeration (`_find_input_device`)
  runs in the executor; keep it that way. `async_read_loop()` is async.
- Assume BlueZ ≥ 5.66 (HA OS ships current BlueZ). Adapter is hardcoded
  `hci0` in `bluez.py` (`ADAPTER_PATH`) — known limitation.

## Conventions

- Follow Home Assistant core style: full type hints, `from __future__
  import annotations`, `_attr_*` entity attributes, `has_entity_name`.
- Config flow strings live in BOTH `strings.json` and
  `translations/en.json`. Edit both or CI/hassfest complains.
- Bump `version` in `manifest.json` on every behavioural change
  (semver: patch for fixes, minor for features).
- British English in user-facing text and docs; code identifiers in
  standard US-English HA vocabulary (`color`, etc.) where HA core does.
- Log levels: `info` for attach/detach of hardware, `debug` for
  D-Bus/loop chatter, `error` only for things a user must act on.

## Testing

There is currently no test suite (the integration was written blind,
without hardware). When adding tests:

- Use `pytest-homeassistant-custom-component`. Add it to
  `requirements_dev.txt`, never to the manifest.
- Priority order for coverage:
  1. `config_flow` — discovery filtering (HID UUID), already-configured
     abort, pairing failure abort. Mock `bluez.pair_and_trust`.
  2. `KnobListener._handle_keycode` — keymap resolution, payload shape.
  3. Options flow → reload behaviour.
- `bluez.py` and the evdev loop need hardware or heavy mocking; treat
  them as integration-test territory and keep them thin so unit-testable
  logic lives elsewhere.

Manual smoke test on real hardware (the actual acceptance test):
1. Fresh HA OS on a Pi with onboard BT, install via HACS custom repo.
2. Knob in pairing mode → appears in Discovered → confirm → entities exist.
3. Rotate both directions and press → check Developer Tools → Events for
   `ble_knob_event` and the event entities updating.
4. Leave the knob idle 5+ minutes, touch it → it must recover without a
   restart (watch for the rescan log line).
5. Reboot the Pi → knob must reconnect with no flow re-run.

## Known weak points (check these first when debugging)

- **Pairing agent**: `bluez.py` registers a `NoInputNoOutput`
  `org.bluez.Agent1` on the pairing connection so BlueZ can authenticate
  the device — without it `Pair()` fails with *Authentication Failed*.
  This handles "Just Works" pairing only; a device that demands an
  out-of-band passkey or a PIN typed on a keypad still can't pair (the
  agent returns defaults rather than prompting). Symptom if it regresses:
  Pair() returns *Authentication Failed* / *Page Timeout*.
- **`uniq` field**: some kernels/drivers leave `dev.uniq` empty for BLE
  HID devices. Fallback strategy if hit: match on `dev.name` +
  phys/bus type, or read the MAC from sysfs.
- **Multiple HA Bluetooth proxies**: discovery via an ESPHome proxy will
  surface devices the local BlueZ cannot pair with (the knob must be in
  range of the Pi itself). Consider filtering discovery to local-adapter
  sources (`info.source`).

## Backlog (sensible next features, in rough order)

1. GitHub Actions: hassfest + HACS validation workflows (see
   `.github/workflows/validate.yml` if present). — **done**
2. Test suite per the Testing section.
3. ~~Long-press~~ — **done**: hold duration is measured in
   `_handle_button`, exposing `long_press` plus the `rotate_*_pressed`
   hold-and-turn gestures. A fire-at-threshold timer (so a long press
   registers without waiting for release) is a possible refinement.
4. Velocity: count detents per rolling window and attach a `speed`
   attribute to rotation events, enabling acceleration-style dimming.
5. Configurable Bluetooth adapter (replace hardcoded `hci0`).
6. Battery level via BLE Battery Service (0x180F) GATT read — would make
   the knob a proper first-class device. Use `bleak` through HA's
   `bluetooth` helpers, never a raw socket.
7. udev-based hotplug detection to replace the 5 s rescan poll.

## Things an LLM should NOT do here

- Don't convert this to an add-on, AppDaemon app, or pyscript.
- Don't add YAML configuration; this integration is config-entry only.
- Don't catch broad exceptions around the evdev read loop in a way that
  swallows `CancelledError` — unload relies on cancellation propagating.
- Don't write to `entry.data` for keymap changes; keymap lives in
  `entry.options`.
- Don't add dependencies beyond `evdev` without strong justification.
- Don't invent VK01 protocol details. It is a standard HID keyboard;
  everything device-specific is just "which keycodes is it sending",
  which the user discovers at runtime.
