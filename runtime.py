"""Where Trackpad Free runs from, and how it starts its own entry points.

From source, each entry point is a script next to this file, started with the
same Python. As the PyInstaller executable (tools/build_exe.py), the exe
relaunches itself with --run=<entry>: bundled read-only files are unpacked to
sys._MEIPASS, and writable files (driver downloads, logs) go to
%LOCALAPPDATA%\\TrackpadFree, because the unpacked folder is deleted on exit.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

FROZEN = bool(getattr(sys, "frozen", False))
SOURCE = Path(__file__).resolve().parent
RESOURCES = Path(getattr(sys, "_MEIPASS", SOURCE))  # assets, scripts, mapping: read-only
HOME = (Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "TrackpadFree") if FROZEN else SOURCE  # writable

SCRIPTS = {"app": "app.py", "tray": "tray.py", "driver-helper": "driver_backend.py", "driver-package": "driver_package.py"}


def interpreter(windowed: bool = False) -> str:
    """The program that runs an entry point: the exe itself, or python/pythonw."""
    if FROZEN:
        return sys.executable
    candidate = Path(sys.executable).with_name("pythonw.exe" if windowed else "python.exe")
    return str(candidate) if candidate.exists() else sys.executable


def entry_args(entry: str) -> list[str]:
    """What follows the interpreter to start `entry`."""
    if entry not in SCRIPTS:
        raise ValueError(f"Unknown entry point: {entry}")
    return [f"--run={entry}"] if FROZEN else [str(SOURCE / SCRIPTS[entry])]


def command(entry: str, *args: str, windowed: bool = False) -> list[str]:
    return [interpreter(windowed), *entry_args(entry), *args]


def home() -> Path:
    """The writable folder, created on first use."""
    HOME.mkdir(parents=True, exist_ok=True)
    return HOME
