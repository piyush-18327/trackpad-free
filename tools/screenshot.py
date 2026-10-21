"""Capture README screenshots of every page using demo data (no real device IDs).

    python tools/screenshot.py --theme light
    python tools/screenshot.py --theme dark

The window opens for a few seconds, each page is captured with PrintWindow,
and the window closes again. Standard library only.
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import re
import struct
import sys
import time
import zlib

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEMO_ID = r"HID\{00001124-0000-1000-8000-00805F9B34FB}_VID&0001004C_PID&0324"
DEMO = {
    "devices": [
        {"FriendlyName": "Apple Multi-touch Trackpad HID Filter", "InstanceId": DEMO_ID + r"&COL01\0&DEMO&0&0000",
         "Class": "HIDClass", "Status": "OK", "Service": "mshidkmdf", "DriverProvider": "Bingxing Wang, Vito Plantamura",
         "DriverVersion": "2026.3982.1.1000", "LowerFilters": ["AmtPtpHidFilter"], "Model": "Magic Trackpad (USB-C)"},
        {"FriendlyName": "HID-compliant touch pad", "InstanceId": DEMO_ID + r"&COL01&COL01\0&DEMO&0&0000",
         "Class": "HIDClass", "Status": "OK", "Service": None, "DriverProvider": "Microsoft",
         "DriverVersion": "10.0.26100.9711", "LowerFilters": [None], "Model": "Magic Trackpad (USB-C)"},
    ],
    "precision_driver": True,
    "driver": {"admin": True, "battery": 76, "driver_available": True, "error": None},
    "tray_task": True,
}


class RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG), ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD), ("colors", wintypes.DWORD * 3)]


user32, gdi32, dwmapi = ctypes.WinDLL("user32"), ctypes.WinDLL("gdi32"), ctypes.WinDLL("dwmapi")
for function, argtypes, restype in (
    (user32.GetParent, [wintypes.HWND], wintypes.HWND),
    (user32.GetWindowRect, [wintypes.HWND, ctypes.POINTER(RECT)], wintypes.BOOL),
    (user32.GetDC, [wintypes.HWND], wintypes.HDC),
    (user32.ReleaseDC, [wintypes.HWND, wintypes.HDC], ctypes.c_int),
    (user32.PrintWindow, [wintypes.HWND, wintypes.HDC, wintypes.UINT], wintypes.BOOL),
    (gdi32.CreateCompatibleDC, [wintypes.HDC], wintypes.HDC),
    (gdi32.CreateCompatibleBitmap, [wintypes.HDC, ctypes.c_int, ctypes.c_int], wintypes.HBITMAP),
    (gdi32.SelectObject, [wintypes.HDC, wintypes.HGDIOBJ], wintypes.HGDIOBJ),
    (gdi32.GetDIBits, [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, ctypes.c_void_p, ctypes.POINTER(BITMAPINFO), wintypes.UINT], ctypes.c_int),
    (gdi32.DeleteObject, [wintypes.HGDIOBJ], wintypes.BOOL),
    (gdi32.DeleteDC, [wintypes.HDC], wintypes.BOOL),
    (dwmapi.DwmGetWindowAttribute, [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD], ctypes.c_long),
):
    function.argtypes, function.restype = argtypes, restype


def capture(hwnd: int) -> tuple[bytes, int, int]:
    """RGB pixels of the window's visible frame (without the invisible resize border)."""
    window, frame = RECT(), RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(window))
    if dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(frame), ctypes.sizeof(frame)):  # DWMWA_EXTENDED_FRAME_BOUNDS
        frame = window
    width, height = window.right - window.left, window.bottom - window.top
    screen = user32.GetDC(None)
    memory = gdi32.CreateCompatibleDC(screen)
    bitmap = gdi32.CreateCompatibleBitmap(screen, width, height)
    previous = gdi32.SelectObject(memory, bitmap)
    user32.PrintWindow(hwnd, memory, 2)  # PW_RENDERFULLCONTENT
    info = BITMAPINFO(biSize=40, biWidth=width, biHeight=-height, biPlanes=1, biBitCount=32)
    pixels = (ctypes.c_ubyte * (width * height * 4))()
    gdi32.GetDIBits(memory, bitmap, 0, height, pixels, ctypes.byref(info), 0)
    gdi32.SelectObject(memory, previous)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(memory)
    user32.ReleaseDC(None, screen)

    left, top = frame.left - window.left, frame.top - window.top
    crop_width, crop_height = frame.right - frame.left, frame.bottom - frame.top
    data, rows = bytes(pixels), []
    for y in range(top, top + crop_height):
        start = (y * width + left) * 4
        bgra = data[start:start + crop_width * 4]
        rgb = bytearray(crop_width * 3)
        rgb[0::3], rgb[1::3], rgb[2::3] = bgra[2::4], bgra[1::4], bgra[0::4]
        rows.append(b"\0" + bytes(rgb))
    return b"".join(rows), crop_width, crop_height


def write_png(path: Path, rows: bytes, width: int, height: int) -> None:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def settle(app, seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.update()
        time.sleep(0.02)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--theme", choices=("light", "dark"), default="light")
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "screenshots")
    args = parser.parse_args()
    os.environ["TRACKPADFREE_THEME"] = args.theme

    from app import TrackpadApp
    from driver_backend import DEFAULTS

    app = TrackpadApp(auto_scan=False)
    try:
        app.geometry("+40+40")
        app.admin = True  # show the settings page in its usable state
        demo = {**DEMO, "driver": {**DEMO["driver"], "settings": DEFAULTS.copy()}}
        settle(app, 0.5)
        app._show_snapshot(demo)
        app.notice.configure(text="Updated · 2 trackpad-related Windows interfaces found.")
        args.out.mkdir(parents=True, exist_ok=True)
        hwnd = user32.GetParent(app.winfo_id())
        for entry in app.tabs._pages:
            app.tabs.select(entry["page"])
            settle(app, 0.6)
            slug = re.sub(r"[^a-z0-9]+", "-", entry["text"].lower()).strip("-")
            path = args.out / f"{args.theme}-{slug}.png"
            write_png(path, *capture(hwnd))
            print(path)
    finally:
        app.destroy()


if __name__ == "__main__":
    main()
