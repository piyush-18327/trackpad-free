"""Trackpad Free tray icon: battery percentage in the notification area.

Started at sign-in by the elevated scheduled task from Install-Tray.ps1, so the
upstream driver's admin-only battery interface works without a UAC prompt.
Uses only the Windows API through ctypes, like the rest of the project.
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from pathlib import Path
import subprocess
import sys
import threading

from driver_backend import run_helper as backend

ROOT = Path(__file__).resolve().parent
PYTHONW = str(Path(sys.executable).with_name("pythonw.exe"))
TASK = r"\TrackpadFree\Trackpad Free Tray"

WM_DESTROY, WM_CLOSE, WM_TIMER, WM_NULL = 0x0002, 0x0010, 0x0113, 0x0000
WM_LBUTTONDBLCLK, WM_RBUTTONUP = 0x0203, 0x0205
WM_TRAY, WM_RESULT = 0x8001, 0x8002
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 0x01, 0x02, 0x04, 0x10
NIIF_INFO, NIIF_WARNING = 0x01, 0x02
MF_STRING, MF_GRAYED, MF_SEPARATOR = 0x0000, 0x0001, 0x0800
TPM_RIGHTBUTTON, TPM_NONOTIFY, TPM_RETURNCMD = 0x0002, 0x0080, 0x0100
MENU_REFRESH, MENU_OPEN, MENU_EXIT = 1, 2, 3
ERROR_ALREADY_EXISTS = 183

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

# 3x5 pixel digits; the icon scales them by whole pixels so they stay crisp.
FONT = {
    "0": "111101101101111", "1": "010110010010111", "2": "111001111100111",
    "3": "111001111001111", "4": "101101111001001", "5": "111100111001111",
    "6": "111100111101111", "7": "111001001001001", "8": "111101111101111",
    "9": "111101111001111", "-": "000000111000000",
}
GREEN, AMBER, RED, GRAY = (0x1E, 0x8E, 0x3E), (0xC7, 0x77, 0x00), (0xD9, 0x30, 0x25), (0x6B, 0x72, 0x80)


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT), ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128), ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256), ("uVersion", wintypes.UINT), ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD), ("guidItem", GUID), ("hBalloonIcon", wintypes.HICON),
    ]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD),
    ]


class ICONINFO(ctypes.Structure):
    _fields_ = [("fIcon", wintypes.BOOL), ("xHotspot", wintypes.DWORD), ("yHotspot", wintypes.DWORD),
                ("hbmMask", wintypes.HBITMAP), ("hbmColor", wintypes.HBITMAP)]


user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
for function, argtypes, restype in (
    (user32.DefWindowProcW, [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM], LRESULT),
    (user32.RegisterClassW, [ctypes.POINTER(WNDCLASSW)], wintypes.ATOM),
    (user32.CreateWindowExW, [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                              ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p], wintypes.HWND),
    (user32.RegisterWindowMessageW, [wintypes.LPCWSTR], wintypes.UINT),
    (user32.ChangeWindowMessageFilterEx, [wintypes.HWND, wintypes.UINT, wintypes.DWORD, ctypes.c_void_p], wintypes.BOOL),
    (user32.SetTimer, [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, ctypes.c_void_p], ctypes.c_size_t),
    (user32.PostMessageW, [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM], wintypes.BOOL),
    (user32.GetMessageW, [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT], wintypes.BOOL),
    (user32.TranslateMessage, [ctypes.POINTER(wintypes.MSG)], wintypes.BOOL),
    (user32.DispatchMessageW, [ctypes.POINTER(wintypes.MSG)], LRESULT),
    (user32.CreatePopupMenu, [], wintypes.HMENU),
    (user32.AppendMenuW, [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR], wintypes.BOOL),
    (user32.TrackPopupMenu, [wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, ctypes.c_void_p], wintypes.BOOL),
    (user32.DestroyMenu, [wintypes.HMENU], wintypes.BOOL),
    (user32.SetForegroundWindow, [wintypes.HWND], wintypes.BOOL),
    (user32.GetCursorPos, [ctypes.POINTER(wintypes.POINT)], wintypes.BOOL),
    (user32.DestroyWindow, [wintypes.HWND], wintypes.BOOL),
    (user32.CreateIconIndirect, [ctypes.POINTER(ICONINFO)], wintypes.HICON),
    (user32.DestroyIcon, [wintypes.HICON], wintypes.BOOL),
    (gdi32.CreateDIBSection, [wintypes.HDC, ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD], wintypes.HBITMAP),
    (gdi32.CreateBitmap, [ctypes.c_int, ctypes.c_int, wintypes.UINT, wintypes.UINT, ctypes.c_void_p], wintypes.HBITMAP),
    (gdi32.DeleteObject, [wintypes.HGDIOBJ], wintypes.BOOL),
    (shell32.Shell_NotifyIconW, [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)], wintypes.BOOL),
    (kernel32.GetModuleHandleW, [wintypes.LPCWSTR], wintypes.HMODULE),
    (kernel32.CreateMutexW, [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE),
):
    function.argtypes, function.restype = argtypes, restype


def battery_color(level: int | None, low: int) -> tuple[int, int, int]:
    if level is None:
        return GRAY
    return RED if level <= low else AMBER if level < 50 else GREEN


def render_pixels(text: str, color: tuple[int, int, int], size: int) -> bytes:
    """Top-down BGRA pixels: a rounded colored square with white digits."""
    pixels = bytearray(size * size * 4)
    radius = max(2, size // 6)
    for y in range(size):
        for x in range(size):
            dx = max(radius - x, 0, x - (size - 1 - radius))
            dy = max(radius - y, 0, y - (size - 1 - radius))
            if dx * dx + dy * dy <= radius * radius:
                pixels[(y * size + x) * 4:(y * size + x + 1) * 4] = bytes((color[2], color[1], color[0], 255))
    units = 4 * len(text) - 1
    scale = max(1, min((size - 2) // units, (size - 2) // 5))
    left, top = (size - units * scale) // 2, (size - 5 * scale) // 2
    for index, character in enumerate(text):
        for bit, on in enumerate(FONT[character]):
            if on == "0":
                continue
            column, row = bit % 3, bit // 3
            for py in range(scale):
                for px in range(scale):
                    x = left + (index * 4 + column) * scale + px
                    y = top + row * scale + py
                    pixels[(y * size + x) * 4:(y * size + x + 1) * 4] = b"\xff\xff\xff\xff"
    return bytes(pixels)


def make_icon(text: str, color: tuple[int, int, int]) -> int:
    size = user32.GetSystemMetrics(49) or 16  # SM_CXSMICON follows display scaling
    header = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), size, -size, 1, 32, 0)
    bits = ctypes.c_void_p()
    color_bitmap = gdi32.CreateDIBSection(None, ctypes.byref(header), 0, ctypes.byref(bits), None, 0)
    if not color_bitmap:
        raise ctypes.WinError(ctypes.get_last_error())
    pixels = render_pixels(text, color, size)
    ctypes.memmove(bits, pixels, len(pixels))
    mask = (ctypes.c_ubyte * (((size + 15) // 16) * 2 * size))()
    mask_bitmap = gdi32.CreateBitmap(size, size, 1, 1, mask)
    info = ICONINFO(True, 0, 0, mask_bitmap, color_bitmap)
    icon = user32.CreateIconIndirect(ctypes.byref(info))
    gdi32.DeleteObject(color_bitmap)
    gdi32.DeleteObject(mask_bitmap)
    if not icon:
        raise ctypes.WinError(ctypes.get_last_error())
    return icon


def task_installed() -> bool:
    result = subprocess.run(["schtasks.exe", "/query", "/tn", TASK], capture_output=True,
                            timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return result.returncode == 0


def start_task() -> None:
    """Start the elevated tray through Task Scheduler; no UAC prompt once installed."""
    result = subprocess.run(["schtasks.exe", "/run", "/tn", TASK], capture_output=True, text=True,
                            errors="replace", timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Could not start the tray task.")


class Tray:
    def __init__(self, low: int, interval: int) -> None:
        self.low, self.interval = low, interval
        self.level: int | None = None
        self.error: str | None = "Reading battery…"
        self.result: dict | None = None
        self.polling = False
        self.warned_low = self.warned_critical = False
        self.icon = 0
        self.taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")
        self.proc = WNDPROC(self._window_proc)  # keep a reference for the lifetime of the window
        instance = kernel32.GetModuleHandleW(None)
        window_class = WNDCLASSW(lpfnWndProc=self.proc, hInstance=instance, lpszClassName="TrackpadFreeTray")
        user32.RegisterClassW(ctypes.byref(window_class))
        self.hwnd = user32.CreateWindowExW(0, "TrackpadFreeTray", "Trackpad Free", 0, 0, 0, 0, 0, None, None, instance, None)
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        # When elevated, let the non-elevated Explorer reach this window.
        for message in (WM_TRAY, self.taskbar_created):
            user32.ChangeWindowMessageFilterEx(self.hwnd, message, 1, None)
        self._notify(NIM_ADD)
        user32.SetTimer(self.hwnd, 1, interval * 1000, None)
        self.poll()

    def _data(self, flags: int) -> NOTIFYICONDATAW:
        data = NOTIFYICONDATAW(cbSize=ctypes.sizeof(NOTIFYICONDATAW), hWnd=self.hwnd, uID=1,
                               uFlags=flags, uCallbackMessage=WM_TRAY)
        return data

    def _tooltip(self) -> str:
        if self.level is not None:
            return f"Magic Trackpad battery: {self.level}%"
        return f"Magic Trackpad battery: unavailable\n{self.error or ''}"[:127]

    def _notify(self, action: int) -> None:
        old, self.icon = self.icon, make_icon("-" if self.level is None else str(self.level), battery_color(self.level, self.low))
        data = self._data(NIF_MESSAGE | NIF_ICON | NIF_TIP)
        data.hIcon, data.szTip = self.icon, self._tooltip()
        shell32.Shell_NotifyIconW(action, ctypes.byref(data))
        if old:
            user32.DestroyIcon(old)

    def _balloon(self, title: str, text: str, flags: int) -> None:
        data = self._data(NIF_INFO)
        data.szInfoTitle, data.szInfo, data.dwInfoFlags = title[:63], text[:255], flags
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(data))

    def poll(self) -> None:
        if self.polling:
            return
        self.polling = True

        def worker() -> None:
            try:
                self.result = backend()
            except Exception as error:  # reported in the tooltip; the next poll retries
                self.result = {"battery": None, "error": str(error)}
            user32.PostMessageW(self.hwnd, WM_RESULT, 0, 0)

        threading.Thread(target=worker, daemon=True).start()

    def _show_result(self) -> None:
        self.polling = False
        result = self.result or {}
        self.level, self.error = result.get("battery"), result.get("error")
        if self.level is None and result.get("admin") is False:
            self.error = "Needs admin rights: use Set up tray icon in Trackpad Free."
        self._notify(NIM_MODIFY)
        if self.level is None:
            return
        if self.level > self.low + 5:
            self.warned_low = self.warned_critical = False
        elif self.level <= min(10, self.low) and not self.warned_critical:
            self.warned_low = self.warned_critical = True
            self._balloon("Magic Trackpad battery very low", f"{self.level}% left. Charge it now with a USB-C cable.", NIIF_WARNING)
        elif self.level <= self.low and not self.warned_low:
            self.warned_low = True
            self._balloon("Magic Trackpad battery low", f"{self.level}% left. Charge it soon.", NIIF_WARNING)

    def _menu(self) -> None:
        menu = user32.CreatePopupMenu()
        label = f"Battery: {self.level}%" if self.level is not None else "Battery: unavailable"
        user32.AppendMenuW(menu, MF_STRING | MF_GRAYED, 0, label)
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, MENU_REFRESH, "Refresh now")
        user32.AppendMenuW(menu, MF_STRING, MENU_OPEN, "Open Trackpad Free")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, MENU_EXIT, "Exit tray icon")
        point = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(point))
        user32.SetForegroundWindow(self.hwnd)  # lets the menu close when clicking elsewhere
        command = user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_NONOTIFY | TPM_RETURNCMD, point.x, point.y, 0, self.hwnd, None)
        user32.PostMessageW(self.hwnd, WM_NULL, 0, 0)
        user32.DestroyMenu(menu)
        if command == MENU_REFRESH:
            self.poll()
        elif command == MENU_OPEN:
            self.open_app()
        elif command == MENU_EXIT:
            user32.DestroyWindow(self.hwnd)

    def open_app(self) -> None:
        # Launched from the elevated tray, the app inherits admin rights too.
        subprocess.Popen([PYTHONW if Path(PYTHONW).exists() else sys.executable, str(ROOT / "app.py")], cwd=ROOT)

    def _window_proc(self, hwnd: int, message: int, wparam: int, lparam: int) -> int:
        if message == WM_TRAY:
            if lparam == WM_RBUTTONUP:
                self._menu()
            elif lparam == WM_LBUTTONDBLCLK:
                self.open_app()
            return 0
        if message == WM_RESULT:
            self._show_result()
            return 0
        if message == WM_TIMER:
            self.poll()
            return 0
        if message == self.taskbar_created:  # Explorer restarted
            self._notify(NIM_ADD)
            return 0
        if message == WM_CLOSE:
            user32.DestroyWindow(hwnd)
            return 0
        if message == WM_DESTROY:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._data(0)))
            if self.icon:
                user32.DestroyIcon(self.icon)
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, message, wparam, lparam)

    def run(self) -> None:
        message = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--low", type=int, default=20, help="Warn at or below this battery percentage (default 20)")
    parser.add_argument("--interval", type=int, default=300, help="Seconds between battery readings (default 300)")
    args = parser.parse_args()
    if not 1 <= args.low <= 99 or args.interval < 30:
        parser.error("--low must be 1-99 and --interval at least 30 seconds.")
    mutex = kernel32.CreateMutexW(None, False, "Local\\TrackpadFreeTray")
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        sys.exit(0)  # already running
    Tray(args.low, args.interval).run()
