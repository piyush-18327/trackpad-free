"""Tray integration. No settings changes on startup/reload; defaults are off.

The one live change is smart zoom's two-finger tap hold: it is taken only
while the engine is running and released on stop, error, exit or next start.
"""

import queue
import threading
import time

import gesture_config as config
from gestures import DEFAULTS, TOGGLES, Recognizer
from hidraw import RawInputMonitor
from gesture_input import InputSink
import touchpad_settings

STATUS_HEARTBEAT = 30  # seconds; the app treats older status as a stopped tray
FAST, IDLE, OFF = 16, 250, 1000  # tick intervals in milliseconds


class GestureHost:
    def __init__(self, hwnd):
        self.monitor = RawInputMonitor(hwnd)
        self.sink = InputSink()
        self.recognizer = Recognizer()
        self.settings = DEFAULTS.copy()
        self.enabled = False
        self.error = "Custom gestures are off."
        self.actions = 0
        self.last_action = None
        self.responses = queue.SimpleQueue()
        self.loading = False
        self.next_reload = 0
        self.closed = False
        self.four_swipes = False
        self.written_key = None
        self.written_at = 0.0
        self._sync_two_tap(False)  # undo a hold left by a crashed or killed tray

    @property
    def interval(self) -> int:
        """Timer interval: fast only while a gesture could be in progress."""
        if not self.enabled:
            return OFF
        r = self.recognizer
        touched = r.last_frame_time is not None and time.monotonic() - r.last_frame_time < 2
        return FAST if r.dragging or r.pending_tap or touched else IDLE

    def _emit(self, actions):
        for action in actions:
            self.sink.emit(action)
            self.actions += 1
            self.last_action = action.kind

    def _cancel(self):
        self._emit(self.recognizer.cancel())
        self.sink.release()

    def _sync_two_tap(self, hold):
        try:
            if hold:
                touchpad_settings.hold_two_finger_tap()
            else:
                touchpad_settings.release_two_finger_tap()
        except (OSError, ValueError, RuntimeError) as error:
            self.error = f"Two-finger tap setting: {error}"

    def _reload(self):
        self.loading = True
        status = {"enabled": self.enabled, "message": self.error,
                  "reports": self.monitor.reports, "parse_errors": self.monitor.errors,
                  "last_parse_error": self.monitor.last_error, "actions": self.actions,
                  "last_action": self.last_action}
        # Counters change with every touch; rewrite only when the state a user
        # sees changes, plus a heartbeat so the app can tell the tray is alive.
        key = (status["enabled"], status["message"], status["parse_errors"], status["last_parse_error"])

        def worker():
            try:
                settings = config.load()
                active = any(settings[k] for k in TOGGLES)
                ready, note = touchpad_settings.runtime_ready(settings) if active else (False, "Custom gestures are off.")
                four = settings["launchpad"] and (settings["three_finger_drag"] or (config.data_dir()/"mac-preset-backup.json").exists())
                result = settings, ready, note, four
                now = time.time()
                if key != self.written_key or now - self.written_at >= STATUS_HEARTBEAT:
                    config.atomic_json(config.data_dir()/"gesture-status.json", {**status, "updated": now})
                    self.written_key, self.written_at = key, now
            except (OSError, ValueError, RuntimeError, KeyError) as error:
                result = DEFAULTS.copy(), False, str(error), False
            self.responses.put(result)
        threading.Thread(target=worker, daemon=True).start()

    def tick(self):
        if self.closed:
            return
        now = time.monotonic()
        try:
            if not self.responses.empty():
                settings, ready, note, four = self.responses.get()
                self.loading = False
                if settings != self.settings or ready != self.enabled or four != self.four_swipes:
                    self._cancel()
                    self.settings, self.enabled, self.four_swipes = settings, ready, four
                    self.recognizer = Recognizer(settings, four_swipes=four)
                    self.sink.scale = settings["pointer_scale"]
                    if ready and not self.monitor.registered:
                        if not self.monitor.register():
                            raise OSError("Raw Input registration failed.")
                    elif not ready:
                        self.monitor.close()
                self.error = note or "Custom gestures active."
                # Re-checked every second, so something switching the tap back on is undone.
                self._sync_two_tap(self.enabled and self.settings["smart_zoom"])
            if self.enabled:
                self._emit(self.recognizer.tick(now))
            if now >= self.next_reload and not self.loading:
                self.next_reload = now + 1
                self._reload()
        except (OSError, ValueError, RuntimeError) as error:
            self.error = str(error)
            self.enabled = False
            self.recognizer.cancel()
            self.monitor.close()
            self._sync_two_tap(False)
            try:
                self.sink.release()
            except OSError:
                pass  # next timer retries releasing our button
        if not self.enabled and self.sink.left_down:
            try:
                self.sink.release()
            except OSError:
                pass

    def raw_input(self, lparam):
        if not self.enabled:
            return
        try:
            errors = self.monitor.errors
            frames = self.monitor.read(lparam)
            if self.monitor.errors != errors:
                self._cancel()
            for frame in frames:
                self._emit(self.recognizer.feed(frame))
        except (OSError, ValueError, RuntimeError) as error:
            self.error = str(error)
            self.recognizer.cancel()
            try:
                self.sink.release()
            except OSError:
                pass

    def devices_changed(self):
        try:
            self._cancel()
            if self.enabled:
                self.monitor.rediscover()
        except (OSError, ValueError) as error:
            self.error = str(error)

    def close(self):
        self.closed = True
        self.monitor.close()
        self.recognizer.cancel()
        self.sink.close()
        self._sync_two_tap(False)
