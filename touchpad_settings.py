"""Windows 11 PTP settings, with durable, exact registry rollback.

SPI V1 controls basic options live. Gesture action mappings in
gesture_mapping.json were measured using Settings (see docs/gestures.md).
"""

import argparse
import base64
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import sys
import winreg

from gesture_config import atomic_json, data_dir

KEY = r"Software\Microsoft\Windows\CurrentVersion\PrecisionTouchPad"
SPI_GET, SPI_SET = 0xAE, 0xAF
FLAGS = {"tap": 1 << 2, "two_tap": 1 << 4, "pan": 1 << 7,
         "zoom": 1 << 8, "reverse": 1 << 9}


class TOUCHPAD_PARAMETERS(ctypes.Structure):
    _fields_ = [(name, wintypes.UINT) for name in (
        "versionNumber", "maxSupportedContacts", "legacyTouchpadFeatures",
        "systemFlags", "settingsFlags", "sensitivityLevel", "cursorSpeed",
        "feedbackIntensity", "clickForceSensitivity", "rightClickZoneWidth", "rightClickZoneHeight")]


user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]
user32.SystemParametersInfoW.restype = wintypes.BOOL


def parameters():
    p = TOUCHPAD_PARAMETERS(versionNumber=1)
    if not user32.SystemParametersInfoW(SPI_GET, ctypes.sizeof(p), ctypes.byref(p), 0):
        raise ctypes.WinError(ctypes.get_last_error())
    return p


def set_flags(values):
    p = parameters()
    for key, enabled in values.items():
        mask = FLAGS[key]
        p.settingsFlags = (p.settingsFlags | mask) if enabled else (p.settingsFlags & ~mask)
    if not user32.SystemParametersInfoW(SPI_SET, ctypes.sizeof(p), ctypes.byref(p), 3):
        raise ctypes.WinError(ctypes.get_last_error())
    actual = parameters()
    if any(bool(actual.settingsFlags & FLAGS[k]) != v for k, v in values.items()):
        raise RuntimeError("Windows did not retain the requested touchpad options.")


def registry_snapshot():
    result = {}

    def walk(relative):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY + ("\\"+relative if relative else ""))
        except FileNotFoundError:
            return
        with key:
            children, values, _ = winreg.QueryInfoKey(key)
            result[relative] = {}
            for i in range(values):
                name, value, kind = winreg.EnumValue(key, i)
                if isinstance(value, bytes):
                    value = {"base64": base64.b64encode(value).decode("ascii")}
                result[relative][name] = {"type": kind, "value": value}
            for i in range(children):
                child = winreg.EnumKey(key, i)
                walk(relative+"\\"+child if relative else child)
    walk("")
    return result


def diff(before, after):
    changes = []
    for key in sorted(set(before) | set(after)):
        for name in sorted(set(before.get(key, {})) | set(after.get(key, {}))):
            old, new = before.get(key, {}).get(name), after.get(key, {}).get(name)
            if old != new:
                changes.append({"key": key, "name": name, "before": old, "after": new})
    return changes


def write_value(key, name, item):
    full = KEY + ("\\"+key if key else "")
    if item is None:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, full, 0, winreg.KEY_SET_VALUE) as h:
                winreg.DeleteValue(h, name)
        except FileNotFoundError:
            pass
    else:
        value = item["value"]
        if isinstance(value, dict):
            value = base64.b64decode(value["base64"])
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, full, 0, winreg.KEY_SET_VALUE) as h:
            winreg.SetValueEx(h, name, 0, item["type"], value)


def snapshot():
    p = parameters()
    return {"build": sys.getwindowsversion().build, "registry": registry_snapshot(),
            "flags": {k: bool(p.settingsFlags & v) for k, v in FLAGS.items()},
            "parameters": {name: getattr(p, name) for name, _ in p._fields_}}


WINDOWS_11 = 22000


def mapping():
    """Registry values for Windows' gesture actions (see docs/gestures.md).

    They were measured on one build. Other Windows 11 builds use the same
    values: every write is read back and restorable, and mapping_note() asks
    the user to confirm the result in Settings after signing in.
    """
    path = Path(__file__).with_name("gesture_mapping.json")
    try:
        m = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RuntimeError("Missing gesture_mapping.json.") from None
    if sys.getwindowsversion().build < WINDOWS_11:
        raise RuntimeError("Windows gesture mappings need Windows 11.")
    return m


def mapping_note() -> str:
    """Empty on the measured build; otherwise a hint to verify in Settings."""
    measured, build = mapping().get("build"), sys.getwindowsversion().build
    if measured == build:
        return ""
    return (f" These values were measured on Windows build {measured}; this PC runs {build}, so after signing in "
            "check Settings > Bluetooth & devices > Touchpad > Three- and four-finger gestures.")


def action_changes(profile: str):
    m = mapping()
    if profile not in m.get("profiles", {}):
        raise RuntimeError(f"The '{profile}' mapping has not been measured in Settings.")
    changes = m["profiles"][profile]
    for c in changes:
        if c["key"] or not isinstance(c["name"], str) or c["after"] is None or c["after"]["type"] != winreg.REG_DWORD:
            raise ValueError("Unsupported gesture mapping entry.")
    return changes


def apply_transaction(name: str, flags: dict, changes: list):
    """Retain the first backup through repeated Apply; recover after interruption."""
    path = data_dir() / f"{name}-backup.json"
    if path.exists():
        raise RuntimeError(f"{name} is already applied. Restore previous before applying another profile.")
    before = snapshot()
    record = {"before": before, "flags": list(flags), "changes": changes, "pending": True,
              "activation_logon": logon_id()}
    atomic_json(path, record)  # durable BEFORE mutating Windows
    try:
        for c in changes:
            write_value(c["key"], c["name"], c["after"])
        if flags:
            set_flags(flags)
        after = snapshot()
        for c in changes:
            if after["registry"].get(c["key"], {}).get(c["name"]) != c["after"]:
                raise RuntimeError("Gesture registry read-back did not match.")
        record["changes"] = diff(before["registry"], after["registry"])
        record["pending"] = False
        atomic_json(path, record)
    except Exception:
        restore_transaction(name)
        raise
    return ("Saved and read back. Basic options apply live; sign out/in to activate registry gesture actions."
            + (mapping_note() if changes else ""))


def restore_transaction(name: str):
    path = data_dir() / f"{name}-backup.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    before = record["before"]
    # SPI persists defaults for other options. Include those side effects in
    # rollback, without resetting unrelated settings edited since Apply.
    current = registry_snapshot()
    if record["flags"]:
        set_flags({k: before["flags"][k] for k in record["flags"]})
    side_effects = diff(current, registry_snapshot())
    changes = diff(before["registry"], registry_snapshot()) if record["pending"] else record["changes"]
    touched = {(c["key"], c["name"]) for c in changes + side_effects}
    for key, value in touched:
        original = before["registry"].get(key, {}).get(value) if (key, value) in {(c['key'], c['name']) for c in changes} else current.get(key, {}).get(value)
        write_value(key, value, original)
    # Remove only empty subkeys created by our transaction.
    for key in sorted(set(registry_snapshot()) - set(before["registry"]), key=len, reverse=True):
        if key:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY+"\\"+key) as h:
                    empty = winreg.QueryInfoKey(h)[:2] == (0, 0)
                if empty:
                    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, KEY+"\\"+key)
            except OSError:
                pass
    actual = registry_snapshot()
    if any(actual.get(c["key"], {}).get(c["name"]) != before["registry"].get(c["key"], {}).get(c["name"]) for c in changes):
        raise RuntimeError("Restore read-back failed. Backup retained for recovery.")
    actual_flags = snapshot()["flags"]
    if any(actual_flags[k] != before["flags"][k] for k in record["flags"]):
        raise RuntimeError("Restore SPI read-back failed. Backup retained for recovery.")
    path.unlink()
    return "Previous settings restored and read back. Sign out/in to restore registry gesture actions."


def apply_mac():
    if (data_dir() / "gesture-conflicts-backup.json").exists():
        raise RuntimeError("Turn off custom gestures before changing the Mac preset.")
    # Natural scrolling = fingers and content move together. Microsoft's
    # default (reverse=False) already has this behavior; see docs/gestures.md.
    return apply_transaction("mac-preset", {"tap": True, "two_tap": True, "pan": True, "reverse": False}, action_changes("mac"))


def restore_mac():
    if (data_dir() / "gesture-conflicts-backup.json").exists():
        raise RuntimeError("Turn off custom gestures before restoring the Mac preset.")
    return restore_transaction("mac-preset")


def logon_id():
    """Authentication LUID distinguishes a new sign-in from a process restart."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel.GetCurrentProcess.argtypes, kernel.GetCurrentProcess.restype = [], wintypes.HANDLE
    kernel.CloseHandle.argtypes, kernel.CloseHandle.restype = [wintypes.HANDLE], wintypes.BOOL
    advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi.OpenProcessToken.restype = wintypes.BOOL
    advapi.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    advapi.GetTokenInformation.restype = wintypes.BOOL
    token, size = wintypes.HANDLE(), wintypes.DWORD()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        data = ctypes.create_string_buffer(56)
        if not advapi.GetTokenInformation(token, 10, data, len(data), ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        return data.raw[8:16].hex()
    finally:
        kernel.CloseHandle(token)


TWO_TAP_HOLD = "two-finger-tap-hold.json"


def native_two_tap() -> bool:
    return bool(parameters().settingsFlags & FLAGS["two_tap"])


def hold_two_finger_tap() -> None:
    """Smart zoom owns two-finger taps while the tray engine runs.

    The user's setting is saved before Windows' own two-finger tap is turned
    off, so release_two_finger_tap() can put it back even after a crash.
    Calling it again re-asserts the hold if something switched the tap back on.
    """
    path = data_dir() / TWO_TAP_HOLD
    if not path.exists():
        atomic_json(path, {"two_tap": native_two_tap()})
    if native_two_tap():
        set_flags({"two_tap": False})


def release_two_finger_tap() -> None:
    path = data_dir() / TWO_TAP_HOLD
    if not path.exists():
        return
    original = json.loads(path.read_text(encoding="utf-8")).get("two_tap", True)
    if native_two_tap() != original:
        set_flags({"two_tap": original})
    path.unlink()


def two_finger_tap_held() -> bool:
    return (data_dir() / TWO_TAP_HOLD).exists()


def conflict_plan(settings):
    # Smart zoom's two-finger tap is held live by the tray (hold_two_finger_tap),
    # not saved here, so right-click survives when the tray is not running.
    flags, changes = {}, []
    if settings["three_finger_drag"]:
        changes += action_changes("three_none") + action_changes("three_tap_none")
        changes += action_changes("four_none" if settings["launchpad"] else "four_mac")
    elif settings["lookup"]:
        changes += action_changes("three_tap_none")
    if settings["launchpad"] and not settings["three_finger_drag"]:
        changes += action_changes("four_none")
    return flags, changes


def configure_gestures(settings):
    """Called by the explicit Save button, never by tray reload/startup."""
    from gesture_config import load, save
    from gestures import validate
    settings = validate(settings)
    previous = load()
    if not settings["smart_zoom"]:
        release_two_finger_tap()  # also covers a tray that stopped while holding it
    flags, changes = conflict_plan(settings)
    old_flags, old_changes = conflict_plan(previous)
    backup = data_dir() / "gesture-conflicts-backup.json"
    if (flags, changes) == (old_flags, old_changes) and (backup.exists() or not(flags or changes)):
        save(settings)
        return "Gesture preferences saved. The tray reloads them within one second."
    if backup.exists():
        restore_transaction("gesture-conflicts")
    try:
        if flags or changes:
            apply_transaction("gesture-conflicts", flags, changes)
        save(settings)
    except Exception:
        if backup.exists():
            restore_transaction("gesture-conflicts")
        if old_flags or old_changes:
            apply_transaction("gesture-conflicts", old_flags, old_changes)
        raise
    return ("Saved. Sign out/in to activate the three-/four-finger mapping. The engine waits until then." + mapping_note()
            if changes or old_changes else "Saved and read back. The tray reloads within one second.")


def runtime_ready(settings):
    """Never inject on top of unactivated Windows gesture overrides."""
    flags, changes = conflict_plan(settings)
    if not (flags or changes):
        return True, ""
    path = data_dir() / "gesture-conflicts-backup.json"
    if not path.exists():
        return False, "Save gesture settings in the app to prepare Windows conflict settings."
    record = json.loads(path.read_text(encoding="utf-8"))
    if record["pending"]:
        return False, "An interrupted settings change needs Restore previous."
    current = registry_snapshot()
    if any(current.get(c["key"], {}).get(c["name"]) != c["after"] for c in changes):
        return False, "Windows gesture actions changed. Turn custom gestures off and on again."
    p = parameters()
    if any(bool(p.settingsFlags & FLAGS[k]) != value for k, value in flags.items()):
        return False, "Windows tap settings conflict. Turn custom gestures off and on again."
    if changes and record["activation_logon"] == logon_id():
        return False, "Sign out/in once to activate Windows gesture mappings."
    return True, ""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["read", "capture", "diff", "apply", "restore"])
    parser.add_argument("path", nargs="?", type=Path)
    args = parser.parse_args()
    if args.operation == "read":
        print(json.dumps(snapshot(), indent=2))
    elif args.operation == "capture":
        atomic_json(args.path, snapshot())
    elif args.operation == "diff":
        print(json.dumps(diff(json.loads(args.path.read_text())["registry"], registry_snapshot()), indent=2))
    else:
        print(apply_mac() if args.operation == "apply" else restore_mac())
