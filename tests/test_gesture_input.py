"""Output side of gestures: Look up and smart zoom, with all OS calls patched out."""

import unittest
from unittest.mock import patch

from gestures import Action
import gesture_input
from gesture_input import InputSink
import uia


class LookupTests(unittest.TestCase):
    def setUp(self):
        self.sent, self.opened = [], []
        for target, replacement in (("send", self.sent.append), ("open_url", self.opened.append)):
            patcher = patch.object(gesture_input, target, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_lookup_sends_no_input_and_opens_a_definition(self):
        with patch.object(uia, "word_at", return_value="trackpad") as word_at:
            InputSink()._lookup(120, 340)
        word_at.assert_called_once_with(120, 340)
        self.assertEqual(self.sent, [])  # no clicks, no Ctrl+C, no clipboard
        self.assertEqual(self.opened, ["https://www.bing.com/search?q=define%20trackpad"])

    def test_no_word_does_nothing(self):
        with patch.object(uia, "word_at", return_value=None):
            InputSink()._lookup(1, 1)
        self.assertEqual((self.sent, self.opened), ([], []))

    def test_lookup_runs_once_at_a_time_and_never_blocks_other_actions(self):
        sink = InputSink()
        sink.lookup_busy = True
        with patch.object(gesture_input.threading, "Thread") as thread:
            sink.emit(Action("lookup"))
        thread.assert_not_called()
        with patch.object(gesture_input, "shortcut", return_value=True) as shortcut:
            sink.emit(Action("notifications"))
        shortcut.assert_called_once()

    def test_clean_word(self):
        self.assertEqual(uia.clean_word("  “hello,”  "), "hello")
        for rejected in (None, "", "   ", "...", "two\nlines", "x" * 65):
            self.assertIsNone(uia.clean_word(rejected), rejected)


class SmartZoomTests(unittest.TestCase):
    def test_zoom_state_is_tracked_per_window(self):
        sink, sent = InputSink(), []
        windows = iter([101, 202, 101, 202])
        with patch.object(gesture_input.user32, "GetForegroundWindow", side_effect=lambda: next(windows)), \
             patch.object(gesture_input.user32, "IsWindow", return_value=True), \
             patch.object(gesture_input, "shortcut", side_effect=lambda *keys: sent.append(keys) or True):
            for _ in range(4):
                sink.emit(Action("smart_zoom"))
        zoom_in, reset = (gesture_input.VK_CTRL, 0x6B), (gesture_input.VK_CTRL, ord("0"))
        self.assertEqual(sent, [zoom_in, zoom_in, reset, reset])

    def test_closed_windows_are_forgotten(self):
        sink = InputSink()
        sink.zoomed = {101}
        with patch.object(gesture_input.user32, "GetForegroundWindow", return_value=303), \
             patch.object(gesture_input.user32, "IsWindow", return_value=False), \
             patch.object(gesture_input, "shortcut", return_value=True):
            sink.emit(Action("smart_zoom"))
        self.assertEqual(sink.zoomed, {303})


if __name__ == "__main__":
    unittest.main()
