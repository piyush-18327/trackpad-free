"""How entry points are launched from source and from TrackpadFree.exe."""

import sys
import unittest
from unittest.mock import patch

import runtime
import trackpadfree


class RuntimeTests(unittest.TestCase):
    def test_source_runs_scripts_with_python(self):
        command = runtime.command("tray", windowed=True)
        self.assertTrue(command[1].endswith("tray.py"))
        self.assertTrue(command[0].lower().endswith(("pythonw.exe", "python.exe")))

    def test_exe_relaunches_itself(self):
        with patch.object(runtime, "FROZEN", True), patch.object(runtime.sys, "executable", r"C:\Apps\TrackpadFree.exe"):
            self.assertEqual(runtime.command("driver-helper", "--apply", "{}"),
                             [r"C:\Apps\TrackpadFree.exe", "--run=driver-helper", "--apply", "{}"])
            self.assertEqual(runtime.interpreter(windowed=True), r"C:\Apps\TrackpadFree.exe")

    def test_unknown_entry_is_refused(self):
        with self.assertRaises(ValueError):
            runtime.command("nonsense")


class ExeEntryTests(unittest.TestCase):
    def test_run_flag_selects_the_entry_and_keeps_its_arguments(self):
        seen = []
        with patch.object(sys, "argv", ["TrackpadFree.exe", "--run=driver-helper", "--apply", "{}"]), \
             patch("driver_backend.main", lambda: seen.append(list(sys.argv))):
            trackpadfree.main()
        self.assertEqual(seen, [["TrackpadFree.exe", "--apply", "{}"]])

    def test_no_flag_opens_the_app(self):
        seen = []
        with patch.object(sys, "argv", ["TrackpadFree.exe"]), patch("app.main", lambda: seen.append("app")):
            trackpadfree.main()
        self.assertEqual(seen, ["app"])

    def test_unknown_entry_exits(self):
        with patch.object(sys, "argv", ["TrackpadFree.exe", "--run=nonsense"]):
            with self.assertRaises(SystemExit):
                trackpadfree.main()


if __name__ == "__main__":
    unittest.main()
