"""GPL-2.0-or-later. SendInput output; Look up reads text with UI Automation off-thread."""

import ctypes
from ctypes import wintypes
import subprocess
import threading
from urllib.parse import quote

import uia

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
MOVE, LEFT_DOWN, LEFT_UP, RIGHT_DOWN, RIGHT_UP = 1, 2, 4, 8, 16
KEY_UP = 2
VK_CTRL, VK_SHIFT, VK_ALT, VK_WIN = 0x11, 0x10, 0x12, 0x5B
TAG = 0x54504652


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = [("type", wintypes.DWORD), ("data", INPUT_UNION)]


user32 = ctypes.WinDLL("user32", use_last_error=True)
for function, args, result in (
    (user32.SendInput, [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int], wintypes.UINT),
    (user32.GetAsyncKeyState, [ctypes.c_int], ctypes.c_short),
    (user32.GetForegroundWindow, [], wintypes.HWND),
    (user32.IsWindow, [wintypes.HWND], wintypes.BOOL),
    (user32.GetCursorPos, [ctypes.POINTER(wintypes.POINT)], wintypes.BOOL),
):
    function.argtypes, function.restype = args, result


def mouse(flags, dx=0, dy=0):
    return INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(dx, dy, 0, flags, 0, TAG))


def key(vk, up=False):
    return INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(vk, 0, KEY_UP if up else 0, 0, TAG))


def send(events):
    if not events:
        return
    buffer = (INPUT * len(events))(*events)
    sent = user32.SendInput(len(events), buffer, ctypes.sizeof(INPUT))
    if sent != len(events):
        # Release only downs successfully sent in a partial batch.
        cleanup = []
        for event in events[:sent]:
            if event.type == INPUT_KEYBOARD and not event.ki.dwFlags & KEY_UP:
                cleanup.append(key(event.ki.wVk, True))
            elif event.type == INPUT_MOUSE:
                if event.mi.dwFlags & LEFT_DOWN:
                    cleanup.append(mouse(LEFT_UP))
                if event.mi.dwFlags & RIGHT_DOWN:
                    cleanup.append(mouse(RIGHT_UP))
        if cleanup:
            user32.SendInput(len(cleanup), (INPUT * len(cleanup))(*cleanup), ctypes.sizeof(INPUT))
        raise OSError(f"SendInput delivered {sent}/{len(events)} events (possibly UIPI or secure desktop).")


def shortcut(*keys) -> bool:
    if any(user32.GetAsyncKeyState(k) & 0x8000 for k in (VK_CTRL, VK_SHIFT, VK_ALT, VK_WIN, 0x5C)):
        return False  # do not release keys the user is physically holding
    send([key(k) for k in keys] + [key(k, True) for k in reversed(keys)])
    return True


def open_url(url: str) -> None:
    """Open in the user's browser. Handing the URL to Explorer keeps the browser
    out of the tray's elevated (administrator) token."""
    subprocess.Popen(["explorer.exe", url], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def lookup_url(word: str) -> str:
    return "https://www.bing.com/search?q=" + quote("define " + word, safe="")


class InputSink:
    def __init__(self):
        self.left_down = False
        self.scale = 1800
        self.fraction_x = self.fraction_y = 0.0
        self.lookup_busy = False
        self.zoomed: set[int] = set()  # windows smart zoom has zoomed in
        self.closed = threading.Event()
        self.error = None

    def release(self):
        if self.left_down:
            send([mouse(LEFT_UP)])
            self.left_down = False
        self.fraction_x = self.fraction_y = 0.0

    def emit(self, action):
        kind = action.kind
        if kind == "left_up":
            self.release()
            return
        if self.closed.is_set():
            return
        if kind == "left_down":
            if not self.left_down and not user32.GetAsyncKeyState(1) & 0x8000:
                send([mouse(LEFT_DOWN)])
                self.left_down = True
        elif kind == "move" and self.left_down:
            x, y = self.fraction_x + action.dx*self.scale, self.fraction_y + action.dy*self.scale
            dx, dy = int(x), int(y)
            send([mouse(MOVE, dx, dy)])
            self.fraction_x, self.fraction_y = x-dx, y-dy
        elif kind == "right_click":
            send([mouse(RIGHT_DOWN), mouse(RIGHT_UP)])
        elif kind == "lookup":
            point = wintypes.POINT()
            if not self.lookup_busy and user32.GetCursorPos(ctypes.byref(point)):
                self.lookup_busy = True
                threading.Thread(target=self._lookup, args=(point.x, point.y), daemon=True).start()
        elif kind == "smart_zoom":
            self._smart_zoom()
        elif kind in SHORTCUTS:
            shortcut(*SHORTCUTS[kind])

    def _smart_zoom(self):
        # Zoom state is per window: zooming the browser must not make the next
        # double-tap in another app send "reset".
        window = user32.GetForegroundWindow()
        self.zoomed = {handle for handle in self.zoomed if user32.IsWindow(handle)}
        zoomed = window in self.zoomed
        if shortcut(VK_CTRL, ord('0') if zoomed else 0x6B):  # Ctrl+0 resets, Ctrl+numpad-plus zooms in
            if zoomed:
                self.zoomed.discard(window)
            elif window:
                self.zoomed.add(window)

    def _lookup(self, x, y):
        # Reads the word through UI Automation: no clicks, no keystrokes, no
        # clipboard. Password fields and apps without accessible text give None.
        try:
            word = uia.word_at(x, y)
            if word and not self.closed.is_set():
                open_url(lookup_url(word))
        except OSError as error:
            self.error = str(error)
        finally:
            self.lookup_busy = False

    def close(self):
        self.closed.set()
        self.release()


SHORTCUTS = {
    "notifications": (VK_WIN, ord('N')), "start": (VK_CTRL, 0x1B),
    "desktop": (VK_WIN, ord('D')), "task_view": (VK_WIN, 0x09),
    "desktop_left": (VK_CTRL, VK_WIN, 0x25), "desktop_right": (VK_CTRL, VK_WIN, 0x27),
    "screenshot": (VK_WIN, VK_SHIFT, ord('S')),  # Snipping Tool's screen capture overlay
}
