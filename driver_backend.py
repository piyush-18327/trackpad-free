"""Bluetooth IPC client for MagicTrackpad2ForWindows v2.2.

This runs as a bounded subprocess so a slow driver request cannot hang the UI.
Interface references and upstream attribution are in THIRD_PARTY.md.
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import winreg

PYTHON = str(Path(sys.executable).with_name("python.exe"))
if not Path(PYTHON).exists():
    PYTHON = sys.executable
DEVICE = r"\\.\AmtPtpControlDeviceUm"
REGISTRY_KEY = r"SYSTEM\CurrentControlSet\Services\AmtPtpHidFilter\Parameters"
IOCTL_RELOAD = (0x22 << 16) | (0x800 << 2)
IOCTL_BATTERY = (0x22 << 16) | (0x801 << 2)

DEFAULTS = {
    "ButtonDisabled": 0, "FeedbackClick": 0x060617, "FeedbackRelease": 0x000014,
    "StopPressure": 0, "StopSize": -1, "IgnoreButtonFinger": 1,
    "IgnoreNearFingers": 1, "PalmRejection": 1,
}
FEEDBACK = {"Light": (0x040415, 0x000010), "Medium": (0x060617, 0x000014), "Firm": (0x08081E, 0x020218), "Maximum": (0xFFFFFF, 0xFFFFFF)}


def is_admin() -> bool:
    return bool(ctypes.windll.shell32.IsUserAnAdmin())


def validate_settings(settings: dict) -> dict[str, int]:
    if set(settings) != set(DEFAULTS):
        raise ValueError("The settings must contain exactly the supported Bluetooth driver options.")
    for name, value in settings.items():
        if type(value) is not int:
            raise ValueError(f"{name} must be an integer.")
        if name in ("FeedbackClick", "FeedbackRelease"):
            valid = 0 <= value <= 0xFFFFFF
        elif name in ("StopPressure", "StopSize"):
            valid = -1 <= value <= 255
        else:
            valid = value in (0, 1)
        if not valid:
            raise ValueError(f"Invalid value for {name}.")
    if settings["StopPressure"] != -1 and settings["StopSize"] != -1:
        raise ValueError("Select either a pressure threshold or a contact-size threshold.")
    return settings


def read_settings() -> dict[str, int]:
    values = DEFAULTS.copy()
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, REGISTRY_KEY, 0, winreg.KEY_READ)
    except FileNotFoundError:
        return values
    with key:
        for name in values:
            try:
                value, kind = winreg.QueryValueEx(key, name)
            except FileNotFoundError:
                continue
            if kind == winreg.REG_DWORD:
                values[name] = -1 if name in ("StopPressure", "StopSize") and value == 0xFFFFFFFF else value
    return values


class BluetoothDriver:
    def __init__(self) -> None:
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        self.kernel.CreateFileW.restype = wintypes.HANDLE
        self.kernel.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        self.kernel.DeviceIoControl.restype = wintypes.BOOL
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL
        self.handle = self.kernel.CreateFileW(DEVICE, 0xC0000000, 3, None, 3, 0, None)
        if self.handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())

    def __enter__(self) -> BluetoothDriver:
        return self

    def __exit__(self, *_: object) -> None:
        self.kernel.CloseHandle(self.handle)

    def request(self, code: int, expect_battery: bool = False) -> int | None:
        output, returned = wintypes.DWORD(), wintypes.DWORD()
        success = self.kernel.DeviceIoControl(
            self.handle, code, None, 0,
            ctypes.byref(output) if expect_battery else None,
            ctypes.sizeof(output) if expect_battery else 0, ctypes.byref(returned), None,
        )
        if not success:
            raise ctypes.WinError(ctypes.get_last_error())
        if expect_battery:
            if returned.value != 4 or output.value > 100:
                raise ValueError("The driver did not return a valid battery percentage.")
            return output.value
        return None


def status() -> dict:
    result = {"admin": is_admin(), "battery": None, "settings": read_settings(), "driver_available": False, "error": None}
    try:
        with BluetoothDriver() as driver:
            result["driver_available"] = True
            result["battery"] = driver.request(IOCTL_BATTERY, True)
    except (OSError, ValueError) as error:
        code = getattr(error, "winerror", None)
        if code in (2, 3):
            result["error"] = "The Bluetooth precision driver is not loaded. Install it, then reconnect the trackpad."
        elif code == 5:
            result["error"] = "Open Trackpad Free as administrator to read battery and change driver settings."
        else:
            result["error"] = f"Battery unavailable: {error}"
    return result


def apply_settings(settings: dict) -> dict:
    validate_settings(settings)
    if not is_admin():
        raise PermissionError("Open Trackpad Free as administrator to apply driver settings.")
    # Opening the driver's control device first avoids creating settings for an
    # unavailable driver. Windows owns gesture preferences separately.
    with BluetoothDriver() as driver:
        with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, REGISTRY_KEY, 0, winreg.KEY_WRITE) as key:
            for name, value in settings.items():
                winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, value & 0xFFFFFFFF)
        try:
            driver.request(IOCTL_RELOAD)
        except OSError as error:
            return {"saved": True, "applied": False, "message": f"Settings saved. Reconnect the trackpad to load them. Driver response: {error}"}
    return {"saved": True, "applied": True, "message": "Bluetooth click and precision settings applied."}


def run_helper(settings: dict | None = None) -> dict:
    """Run this module as a subprocess with a timeout and return its JSON."""
    command = [PYTHON, str(Path(__file__).resolve())]
    if settings is not None:
        command += ["--apply", json.dumps(settings)]
    result = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    if not result.stdout.strip():
        raise RuntimeError(result.stderr.strip() or "The driver helper returned no response.")
    data = json.loads(result.stdout)
    if result.returncode:
        raise RuntimeError(data.get("error", "The driver request failed."))
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", metavar="JSON", help="Apply settings; requires administrator rights")
    parser.add_argument("--apply-file", metavar="PATH", help="Apply settings read from a JSON file")
    args = parser.parse_args()
    try:
        if args.apply_file:
            with open(args.apply_file, encoding="utf-8") as handle:
                print(json.dumps(apply_settings(json.load(handle))))
        elif args.apply:
            print(json.dumps(apply_settings(json.loads(args.apply))))
        else:
            print(json.dumps(status()))
    except (OSError, ValueError, TypeError) as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(1)
