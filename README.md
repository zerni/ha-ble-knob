# BLE Knob (Anticater VK01) for Home Assistant

A HACS custom integration that pairs BLE HID rotary knobs (built for the
Anticater VK01, works with any Bluetooth knob that presents as a keyboard)
directly from the Home Assistant UI, and exposes rotation and press as
**event entities** you can use in automations. No `bluetoothctl`, no
`keyboard_remote` YAML.

## What it does

- **Discovery**: knobs advertising the Bluetooth HID service (UUID `1812`)
  while in pairing mode are auto-discovered and offered for setup, like any
  other Bluetooth device in HA.
- **Pairing**: the config flow pairs, trusts and connects the knob through
  BlueZ over D-Bus. Trusting means the knob reconnects on its own every time
  it wakes from battery-saving sleep.
- **Input handling**: a background task attaches to the knob's evdev input
  device (matched by Bluetooth MAC) and survives the knob's sleep/wake
  cycles, rescanning every 5 seconds while it is away.
- **Entities**: each knob gets a device with two event entities:
  - `event.<knob>_rotation` (event types `rotate_left`, `rotate_right`)
  - `event.<knob>_button` (event type `press`)
- **Key mapping**: integration options let you remap the three evdev
  keycodes if you've customised the knob in the Anticater app. Every raw
  keypress is also fired on the bus as `ble_knob_event` (with `keycode`),
  so you can discover codes in Developer Tools → Events.

## Requirements

- Home Assistant OS or Supervised on hardware with a Bluetooth adapter
  managed by BlueZ (e.g. Raspberry Pi 3/4/5 onboard Bluetooth), with the
  built-in Bluetooth integration enabled.
- Container installs work if the container has D-Bus access to the host
  BlueZ and `/dev/input` mounted.

## Install

1. HACS → Integrations → ⋮ → Custom repositories → add this repo as type
   *Integration*.
2. Install **BLE Knob (Anticater VK01)**, restart Home Assistant.
3. Wake the knob and put it in Bluetooth pairing mode. It should appear
   under Settings → Devices & Services → Discovered. Otherwise: Add
   Integration → *BLE Knob* and pick it from the list.
4. Confirm pairing. Done.

## Example automation: dim Hue lights

```yaml
- alias: Knob dims living room
  triggers:
    - trigger: state
      entity_id: event.vk01_rotation
  actions:
    - choose:
        - conditions: >
            {{ trigger.to_state.attributes.event_type == 'rotate_right' }}
          sequence:
            - action: light.turn_on
              target:
                entity_id: light.living_room
              data:
                brightness_step_pct: 10
                transition: 0.3
        - conditions: >
            {{ trigger.to_state.attributes.event_type == 'rotate_left' }}
          sequence:
            - action: light.turn_on
              target:
                entity_id: light.living_room
              data:
                brightness_step_pct: -10
                transition: 0.3

- alias: Knob press toggles living room
  triggers:
    - trigger: state
      entity_id: event.vk01_button
  actions:
    - action: light.toggle
      target:
        entity_id: light.living_room
```

## Device triggers

In the automation editor you can also pick the knob under **Device** and
choose one of its built-in triggers — *Knob rotated left*, *Knob rotated
right* or *Knob pressed* — without touching YAML or the event entities.
These fire from the same `ble_knob_event` and are scoped to the
individual knob, so multiple knobs never cross-fire.

## Custom keycodes

If you've remapped the knob in the Anticater desktop app, open the
integration's **Configure** dialog and enter the Linux evdev keycodes for
each action. To find them, listen to `ble_knob_event` in Developer Tools →
Events and operate the knob. Factory defaults: 115 (volume up) = rotate
right, 114 (volume down) = rotate left, 113 (mute) = press.

If you run several knobs, give each one distinct keycodes in the Anticater
app (e.g. F13–F24, evdev codes 183–194) so their events never clash.

## Known limitations

- **First-touch lag**: the knob sleeps aggressively to save battery and
  takes ~1 s to reconnect. The first click after idle may be swallowed.
  This is hardware behaviour; no integration can fix it.
- One Bluetooth adapter (`hci0`) is assumed. Multi-adapter setups would
  need the adapter path made configurable in `bluez.py`.
- Pairing requires the knob to be visible to BlueZ at that moment — wake
  it just before confirming the flow.

## License

Released under the **GNU General Public License v3.0** — see
[`LICENSE`](LICENSE). You're free to use, study, share and modify this
integration, but any distributed copy or derivative must also be released
under the GPL-3.0 and keep this notice. It cannot be folded into closed-
source software.
