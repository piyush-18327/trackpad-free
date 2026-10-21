"""Entry point of the Windows executable built by tools/build_exe.py.

TrackpadFree.exe opens the app. The app and the tray relaunch the same exe
with --run=<entry> for the parts that used to be separate scripts.
"""

from __future__ import annotations

import ctypes
import msvcrt
import os
import sys


def attach_std_streams() -> None:
    """A windowed exe starts with sys.stdout/stderr set to None. The driver
    helpers report JSON on stdout to the app (and to Install-Driver.ps1), so
    connect the streams to whatever handles the parent passed in."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetStdHandle.restype = ctypes.c_void_p
    for name, handle_id in (("stdout", -11), ("stderr", -12)):
        if getattr(sys, name) is not None:
            continue
        handle = kernel32.GetStdHandle(handle_id)
        if not handle or handle == ctypes.c_void_p(-1).value:
            continue
        try:
            descriptor = msvcrt.open_osfhandle(handle, os.O_WRONLY)
            setattr(sys, name, open(descriptor, "w", encoding="utf-8", errors="replace", buffering=1))
        except OSError:
            continue


def main() -> None:
    entry = "app"
    if len(sys.argv) > 1 and sys.argv[1].startswith("--run="):
        entry = sys.argv.pop(1).split("=", 1)[1]
    attach_std_streams()
    # Static imports, so PyInstaller bundles every entry point.
    if entry == "app":
        from app import main as run
    elif entry == "tray":
        from tray import main as run
    elif entry == "driver-helper":
        from driver_backend import main as run
    elif entry == "driver-package":
        from driver_package import main as run
    else:
        sys.exit(f"Unknown entry point: {entry}")
    run()


if __name__ == "__main__":
    main()
