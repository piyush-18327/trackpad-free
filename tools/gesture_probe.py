"""Bounded read-only raw contact probe. Never calls SendInput or changes settings.

python tools/gesture_probe.py --seconds 10 --output capture.json
The optional JSON contains normalized frames, useful for replaying regressions.
"""

import argparse
from collections import Counter
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dataclasses import asdict
from gestures import Recognizer, TOGGLES
from hidraw import RawInputMonitor, WM_INPUT
from tray import user32, kernel32, WNDCLASSW, WNDPROC


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 0 < args.seconds <= 90:
        parser.error("--seconds must be between 0 and 90.")
    user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
    user32.PeekMessageW.restype = wintypes.BOOL
    user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
    user32.UnregisterClassW.restype = wintypes.BOOL
    monitor = None
    frames, actions = [], []
    recognizer = Recognizer({k:True for k in TOGGLES})
    started = time.monotonic()

    def window_proc(hwnd, msg, wp, lp):
        if msg == WM_INPUT and monitor:
            for frame in monitor.read(lp):
                frames.append(asdict(frame))
                actions.extend(asdict(a) for a in recognizer.feed(frame))
        return user32.DefWindowProcW(hwnd,msg,wp,lp)

    callback = WNDPROC(window_proc)
    instance = kernel32.GetModuleHandleW(None)
    klass = WNDCLASSW(lpfnWndProc=callback,hInstance=instance,lpszClassName="TrackpadFreeGestureProbe")
    if not user32.RegisterClassW(ctypes.byref(klass)):
        raise ctypes.WinError(ctypes.get_last_error())
    hwnd = user32.CreateWindowExW(0,klass.lpszClassName,"Read-only contact probe",0,0,0,0,0,None,None,instance,None)
    try:
        if not hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        monitor = RawInputMonitor(hwnd)
        if not monitor.register():
            raise ctypes.WinError(ctypes.get_last_error())
        print(f"Monitoring {len(monitor.parsers)} USB-C trackpad(s) for {args.seconds:g}s. No input injection.",flush=True)
        message = wintypes.MSG()
        deadline = time.monotonic()+args.seconds
        while time.monotonic() < deadline:
            # Bound batch size too, so a constantly busy queue cannot prevent exit.
            for _ in range(64):
                if not user32.PeekMessageW(ctypes.byref(message),None,0,0,1):
                    break
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
            actions.extend(asdict(a) for a in recognizer.tick(time.monotonic()))
            time.sleep(.002)
        summary = {"reports":monitor.reports,"frames":len(frames),"parse_errors":monitor.errors,
                   "last_error":monitor.last_error,"contact_counts":dict(Counter(len(f['contacts']) for f in frames)),
                   "recognized_actions":dict(Counter(a['kind'] for a in actions))}
        if args.output:
            args.output.write_text(json.dumps({"summary":summary,"frames":frames,"actions":actions},indent=2),encoding="utf-8")
        print(json.dumps(summary,indent=2))
    finally:
        if monitor:
            monitor.close()
        if hwnd:
            user32.DestroyWindow(hwnd)
        user32.UnregisterClassW(klass.lpszClassName,instance)


if __name__ == "__main__":
    main()
