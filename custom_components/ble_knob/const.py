"""Constants for the BLE Knob integration."""

DOMAIN = "ble_knob"

CONF_MAC = "mac"
CONF_NAME = "name"

# Options: keycode mapping
CONF_KEY_ROTATE_LEFT = "key_rotate_left"
CONF_KEY_ROTATE_RIGHT = "key_rotate_right"
CONF_KEY_PRESS = "key_press"
# The VK01 has a hardware "press and turn" layer that emits its own
# keycodes rather than the button + rotation codes together.
CONF_KEY_ROTATE_LEFT_PRESSED = "key_rotate_left_pressed"
CONF_KEY_ROTATE_RIGHT_PRESSED = "key_rotate_right_pressed"

# VK01 factory defaults (Linux evdev keycodes)
DEFAULT_KEY_ROTATE_LEFT = 114   # KEY_VOLUMEDOWN
DEFAULT_KEY_ROTATE_RIGHT = 115  # KEY_VOLUMEUP
DEFAULT_KEY_PRESS = 113         # KEY_MUTE
# Press-and-turn layer (the knob sends these instead of 113 + 114/115).
DEFAULT_KEY_ROTATE_LEFT_PRESSED = 224   # KEY_BRIGHTNESSDOWN
DEFAULT_KEY_ROTATE_RIGHT_PRESSED = 225  # KEY_BRIGHTNESSUP

EVENT_TYPE = "ble_knob_event"

# Base actions, resolved straight from a keycode.
ACTION_ROTATE_LEFT = "rotate_left"
ACTION_ROTATE_RIGHT = "rotate_right"
ACTION_PRESS = "press"
# Press-and-turn actions: from the knob's dedicated keycodes, or from a
# plain rotate arriving while our button-held state is set.
ACTION_ROTATE_LEFT_PRESSED = "rotate_left_pressed"
ACTION_ROTATE_RIGHT_PRESSED = "rotate_right_pressed"

SIGNAL_KNOB_EVENT = "ble_knob_event_{entry_id}"
SIGNAL_AVAILABILITY = "ble_knob_availability_{entry_id}"

# BLE HID service UUID
HID_SERVICE_UUID = "00001812-0000-1000-8000-00805f9b34fb"
