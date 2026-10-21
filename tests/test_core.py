"""Hardware-free checks for parsing, validation and tray icon rendering."""

import unittest

from devices import has_precision_driver, model_for
from driver_backend import DEFAULTS, validate_settings
import tray


class DeviceTests(unittest.TestCase):
    def test_model_from_bluetooth_hardware_id(self):
        device = {"InstanceId": r"HID\{00001124-0000-1000-8000-00805F9B34FB}_VID&0001004C_PID&0324&COL01\B&1"}
        self.assertEqual(model_for(device), "Magic Trackpad (USB-C)")

    def test_other_apple_device_is_not_a_trackpad(self):
        self.assertIsNone(model_for({"InstanceId": r"BTHENUM\{0000110B}_VID&0001004C_PID&2024\A&1"}))

    def test_precision_driver_detected_from_filter(self):
        self.assertTrue(has_precision_driver([{"LowerFilters": ["AmtPtpHidFilter"]}]))
        self.assertFalse(has_precision_driver([{"Service": "HidBth", "Stack": [r"\Driver\HidBth"]}]))


class SettingsTests(unittest.TestCase):
    def test_defaults_are_valid(self):
        self.assertEqual(validate_settings(DEFAULTS.copy()), DEFAULTS)

    def test_both_thresholds_rejected(self):
        with self.assertRaises(ValueError):
            validate_settings({**DEFAULTS, "StopPressure": 40, "StopSize": 40})

    def test_unknown_option_rejected(self):
        with self.assertRaises(ValueError):
            validate_settings({**DEFAULTS, "Extra": 1})


class TrayIconTests(unittest.TestCase):
    def test_colors_follow_battery_level(self):
        self.assertEqual(tray.battery_color(None, 20), tray.GRAY)
        self.assertEqual(tray.battery_color(20, 20), tray.RED)
        self.assertEqual(tray.battery_color(35, 20), tray.AMBER)
        self.assertEqual(tray.battery_color(80, 20), tray.GREEN)

    def test_render_fits_every_icon_size(self):
        for size in (16, 20, 24, 32, 48):
            for text in ("-", "7", "76", "100"):
                pixels = tray.render_pixels(text, tray.GREEN, size)
                self.assertEqual(len(pixels), size * size * 4)
                self.assertIn(b"\xff\xff\xff\xff", pixels)  # digits were drawn


if __name__ == "__main__":
    unittest.main()
