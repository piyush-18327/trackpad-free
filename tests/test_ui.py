"""Window smoke tests and icon checks; skipped where Tk cannot open a window."""

import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

import gesture_config
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


class ThemeModeTests(unittest.TestCase):
    def test_initial_mode_precedence(self):
        with patch.dict(os.environ, {"TRACKPADFREE_THEME": ""}):
            self.assertEqual(ui.initial_mode(None), "system")
            self.assertEqual(ui.initial_mode("dark"), "dark")
            self.assertEqual(ui.initial_mode("purple"), "system")
        with patch.dict(os.environ, {"TRACKPADFREE_THEME": "light"}):
            self.assertEqual(ui.initial_mode("dark"), "light")  # screenshots force a theme


class WindowTests(unittest.TestCase):
    def setUp(self):
        # Never read or write the real %APPDATA% preferences, and ignore a forced theme.
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.data = Path(folder.name)
        for patcher in (patch.object(gesture_config, "data_dir", lambda: self.data),
                        patch.dict(os.environ, {"TRACKPADFREE_THEME": ""})):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.app = self.open_app()

    def open_app(self):
        from app import TrackpadApp
        try:
            app = TrackpadApp(auto_scan=False)
        except tk.TclError as error:
            self.skipTest(f"Tk cannot open a window here: {error}")
        app.withdraw()
        return app

    def tearDown(self):
        self.app.destroy()

    def colors(self):
        item = self.app.tabs._pages[0]["item"]
        return (ttk.Style(self.app).lookup("TFrame", "background"), self.app.tabs.canvas.cget("background"),
                self.app.diagnostics.cget("background"), self.app.battery_gauge.cget("background"),
                item.label.cget("foreground"))

    def test_theme_switches_live(self):
        for mode, palette in (("dark", ui.DARK), ("light", ui.LIGHT), ("dark", ui.DARK)):
            self.app.set_theme(mode)
            self.app.update()
            self.assertEqual(self.colors(), (palette["window"], palette["window"], palette["code_bg"],
                                             palette["window"], palette["text"]), mode)
            self.assertEqual(self.app.theme_choice.get(), ui_label(mode))

    def test_choice_is_remembered_for_next_start(self):
        self.app.set_theme("dark")
        self.assertEqual(json.loads((self.data / "app.json").read_text(encoding="utf-8")), {"theme": "dark"})
        self.app.destroy()
        self.app = self.open_app()
        self.assertEqual((self.app.theme.mode, self.app.theme.dark), ("dark", True))
        self.assertEqual(self.app.theme_choice.get(), "Dark")

    def test_match_windows_follows_windows(self):
        self.app.set_theme("system")
        for windows_dark, palette in ((True, ui.DARK), (False, ui.LIGHT)):
            with patch.object(ui, "windows_prefers_dark", return_value=windows_dark):
                self.app._follow_windows_theme()
            self.app.update()
            self.assertEqual(self.colors()[0], palette["window"])

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


def ui_label(mode):
    from app import THEME_LABELS
    return THEME_LABELS[mode]


if __name__ == "__main__":
    unittest.main()
