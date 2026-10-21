"""Explicit Settings calibration, to run only with the user's permission.

Each command makes one UI change, captures before/after, and records the
registry diff as evidence in %APPDATA%\\TrackpadFree\\gesture-calibration.json.
The app does not read that file: each entry covers one Settings control, so a
contributor combines the printed diffs into a profile in gesture_mapping.json
(see docs/gestures.md). No registry action identifiers are assumed.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gesture_config import atomic_json, data_dir
import touchpad_settings as ptp

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("profile")
parser.add_argument("control")
parser.add_argument("choice")
parser.add_argument("--group", default="")
args = parser.parse_args()
before = ptp.snapshot()
script = Path(__file__).with_name("settings_controls.ps1")
process = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(script),
                          "-Id", args.control, "-Action", "choose", "-Value", args.choice,
                          "-Group", args.group],
                         capture_output=True, timeout=15)
if process.returncode:
    sys.exit(process.stderr.decode(errors="replace"))
after = ptp.snapshot()
changes = ptp.diff(before["registry"], after["registry"])
if not changes:
    sys.exit("No diff: choose a different option first, then repeat.")
path = data_dir() / "gesture-calibration.json"
calibration = json.loads(path.read_text()) if path.exists() else {}
if calibration.get("build") != after["build"]:
    calibration = {"build": after["build"], "profiles": {}, "evidence": {}}  # never mix Windows builds
calibration["profiles"][args.profile] = changes
calibration["evidence"][args.profile] = {"control": args.control, "choice": args.choice, "before": before, "after": after}
atomic_json(path, calibration)
print(json.dumps(changes, indent=2))
print(f"Recorded for build {after['build']} in {path}. Combine the diffs into gesture_mapping.json to use them.", file=sys.stderr)
