"""Tray gesture host: timer cadence and status writes, with Windows calls patched out."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import gesture_config
import gesture_host
import touchpad_settings


class ImmediateThread:
    def __init__(self, target, daemon=None):
        self.target = target

    def start(self):
        self.target()


class HostTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.writes = []
        for owner, target, replacement in (
            (gesture_config, "data_dir", lambda: Path(folder.name)),
            (touchpad_settings, "release_two_finger_tap", lambda: None),
            (touchpad_settings, "hold_two_finger_tap", lambda: None),
            (gesture_config, "atomic_json", lambda path, data: self.writes.append(data)),
            (gesture_host.threading, "Thread", ImmediateThread),
        ):
            p = patch.object(owner, target, replacement); p.start(); self.addCleanup(p.stop)
        self.host = gesture_host.GestureHost(hwnd=0)

    def test_timer_is_slow_unless_a_gesture_may_be_in_progress(self):
        self.assertEqual(self.host.interval, gesture_host.OFF)
        self.host.enabled = True
        self.assertEqual(self.host.interval, gesture_host.IDLE)
        self.host.recognizer.dragging = True
        self.assertEqual(self.host.interval, gesture_host.FAST)

    def test_status_is_written_on_change_and_heartbeat_only(self):
        for _ in range(5):
            self.host._reload()
        self.assertEqual(len(self.writes), 1)
        self.host.monitor.reports += 100  # touches alone do not rewrite the file
        self.host._reload()
        self.assertEqual(len(self.writes), 1)
        self.host.error = "Raw Input registration failed."
        self.host._reload()
        self.assertEqual(len(self.writes), 2)
        self.host.written_at -= gesture_host.STATUS_HEARTBEAT
        self.host._reload()
        self.assertEqual(len(self.writes), 3)


if __name__ == "__main__":
    unittest.main()
