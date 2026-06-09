"""Constants for the BLE Knob integration."""

DOMAIN = "ble_knob"

CONF_MAC = "mac"
CONF_NAME = "name"

# Options: keycode mapping
CONF_KEY_ROTATE_LEFT = "key_rotate_left"
CONF_KEY_ROTATE_RIGHT = "key_rotate_right"
CONF_KEY_PRESS = "key_press"

# VK01 factory defaults (Linux evdev keycodes)
DEFAULT_KEY_ROTATE_LEFT = 114   # KEY_VOLUMEDOWN
DEFAULT_KEY_ROTATE_RIGHT = 115  # KEY_VOLUMEUP
DEFAULT_KEY_PRESS = 113         # KEY_MUTE

EVENT_TYPE = "ble_knob_event"

ACTION_ROTATE_LEFT = "rotate_left"
ACTION_ROTATE_RIGHT = "rotate_right"
ACTION_PRESS = "press"

SIGNAL_KNOB_EVENT = "ble_knob_event_{entry_id}"
SIGNAL_AVAILABILITY = "ble_knob_availability_{entry_id}"

# BLE HID service UUID
HID_SERVICE_UUID = "00001812-0000-1000-8000-00805f9b34fb"
