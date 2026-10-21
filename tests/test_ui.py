"""Window smoke tests and icon checks; skipped where Tk cannot open a window."""

from pathlib import Path
import struct
import sys
import tkinter as tk
from tkinter import ttk
import unittest

import ui

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import make_icons  # noqa: E402

DEMO = {
    "devices": [{"FriendlyName": "Apple Multi-touch Trackpad HID Filter", "Status": "OK",
                 "InstanceId": r"HID\{00001124-0000-1000-8000-00805F9B34FB}_VID&0001004C_PID&0324&COL01\0&DEMO",
                 "LowerFilters": ["AmtPtpHidFilter"], "Model": "Magic Trackpad (USB-C)"}],
    "precision_driver": True,
    "driver": {"admin": False, "battery": 15, "driver_available": False, "error": None},
    "tray_task": True,
}


class BatteryKindTests(unittest.TestCase):
    def test_thresholds_match_the_tray_icon(self):
        self.assertEqual(ui.battery_kind(None), "neutral")
        self.assertEqual(ui.battery_kind(20), "bad")
        self.assertEqual(ui.battery_kind(21), "warn")
        self.assertEqual(ui.battery_kind(49), "warn")
        self.assertEqual(ui.battery_kind(50), "good")


class IconTests(unittest.TestCase):
    def test_png_header_and_size(self):
        data = make_icons.png(make_icons.icon_rgba(16), 16)
        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(struct.unpack(">II", data[16:24]), (16, 16))

    def test_ico_directory_lists_every_image(self):
        images = {size: make_icons.png(make_icons.icon_rgba(size), size) for size in (16, 32)}
        data = make_icons.ico(images)
        self.assertEqual(struct.unpack("<HHH", data[:6]), (0, 1, 2))

    def test_committed_assets_exist(self):
        for size in make_icons.SIZES:
            self.assertTrue((ROOT / "assets" / f"icon-{size}.png").is_file(), size)
        self.assertTrue((ROOT / "assets" / "icon.ico").is_file())


class WindowTests(unittest.TestCase):
    def setUp(self):
        from app import TrackpadApp
        try:
            self.app = TrackpadApp(auto_scan=False)
        except tk.TclError as error:
            self.skipTest(f"Tk cannot open a window here: {error}")
        self.app.withdraw()

    def tearDown(self):
        self.app.destroy()

    def test_demo_snapshot_fills_every_page(self):
        self.app._show_snapshot(DEMO)
        self.app.update()
        self.assertEqual(self.app.battery.cget("text"), "15%")
        self.assertEqual(self.app.pill_connection.cget("text"), "Connected")
        self.assertEqual(self.app.pill_driver.cget("text"), "Precision driver active")
        self.assertEqual(self.app.pill_tray.cget("text"), "Starts at sign-in")
        self.assertEqual(str(self.app.tray_start.cget("state")), "normal")
        for page in self.app.tabs.tabs():
            self.app.tabs.select(page)
            self.app.update()

    def test_new_pages_use_the_notebook_api(self):
        page = ttk.Frame(self.app.tabs, padding=18)
        self.app.tabs.add(page, text="Gestures")
        ttk.Checkbutton(page, text="Three-finger drag").pack(anchor="w")
        self.app.tabs.select(page)
        self.app.update()
        self.assertEqual(self.app.tabs.select(), str(page))
        self.assertEqual(self.app.tabs.title.cget("text"), "Gestures")
        self.assertIn(str(page), self.app.tabs.tabs())


if __name__ == "__main__":
    unittest.main()
