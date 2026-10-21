"""Trackpad Free: Windows companion for a Bluetooth Magic Trackpad."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
import webbrowser

from devices import find_trackpads, has_precision_driver
from driver_backend import DEFAULTS, FEEDBACK, PYTHON, is_admin, run_helper as backend
from driver_package import PACKAGE_DIR, RELEASE, prepare_package
import tray
import ui
import gesture_config
import touchpad_settings
from gestures import DEFAULTS as GESTURE_DEFAULTS, TOGGLES, validate as validate_gestures
from version import __version__

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
GESTURE_STATUS_STALE = 75  # seconds; the tray rewrites its status at least every 30 s


def snapshot() -> dict:
    devices = find_trackpads()
    try:
        driver = backend()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        driver = {"admin": is_admin(), "battery": None, "driver_available": False, "error": str(error)}
    try:
        tray_task = tray.task_installed()
    except (OSError, subprocess.SubprocessError):
        tray_task = False
    try:
        gesture_status = json.loads((gesture_config.data_dir()/"gesture-status.json").read_text(encoding="utf-8"))
        stale = time.time() - gesture_status.get("updated", 0) > GESTURE_STATUS_STALE
    except (OSError, ValueError):
        gesture_status, stale = {}, True
    if stale:
        gesture_status["message"] = "The tray isn't running, so custom gestures are paused. Start the tray to use them."
        if touchpad_settings.two_finger_tap_held():
            gesture_status["message"] += " Two-finger tap right-click stays off until the tray starts, or until you turn smart zoom off and Save."
    return {"devices": devices, "precision_driver": has_precision_driver(devices), "driver": driver, "tray_task": tray_task, "gestures": gesture_status}


def elevate(executable: str, arguments: list[str]) -> None:
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    shell.ShellExecuteW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_int]
    shell.ShellExecuteW.restype = ctypes.c_void_p
    result = shell.ShellExecuteW(None, "runas", executable, subprocess.list2cmdline(arguments), str(ROOT), 1)
    if not result or result <= 32:
        raise OSError("The administrator request was cancelled or could not be started.")


class TrackpadApp(tk.Tk):
    def __init__(self, auto_scan: bool = True) -> None:
        ui.enable_dpi_awareness()
        super().__init__()
        self.title("Trackpad Free")
        self.theme = ui.Theme(self)
        px = ui.px
        self.geometry(f"{px(1040)}x{px(760)}")
        self.minsize(px(860), px(560))
        self.messages: queue.Queue = queue.Queue()
        self.busy = False
        self.last_snapshot: dict = {}
        self.settings_loaded = False
        self.loaded_settings = DEFAULTS.copy()
        self.admin = is_admin()
        self.icons = ui.load_icons(self, ASSETS)
        if self.icons:
            self.iconphoto(True, *(self.icons[size] for size in sorted(self.icons, reverse=True)))

        # NavBook keeps the ttk.Notebook API (add/select), so pages are added as before.
        self.tabs = ui.NavBook(self, self.theme, brand_icon=self._icon(32), version=__version__)
        self.tabs.pack(fill="both", expand=True)
        self.overview = ttk.Frame(self.tabs)
        self.settings_tab = ttk.Frame(self.tabs)
        self.gesture_tab = ttk.Frame(self.tabs)
        self.setup_tab = ttk.Frame(self.tabs)
        self.diagnostics_tab = ttk.Frame(self.tabs)
        pages = (
            (self.overview, "My trackpad", "Battery, connection and tray alerts at a glance."),
            (self.settings_tab, "Click & precision", "Haptic click strength and pointer rejection, applied by the driver."),
            (self.gesture_tab, "Gestures", "Mac-style actions, recognized locally by the tray. Off until you enable them."),
            (self.setup_tab, "Driver setup", "Install the free, Microsoft-signed precision touchpad driver."),
            (self.diagnostics_tab, "Diagnostics", "What Windows reports about your trackpad and its driver."),
        )
        for frame, label, subtitle in pages:
            self.tabs.add(frame, text=label, subtitle=subtitle)
        self._build_overview()
        self._build_settings()
        self._build_gestures()
        self._build_setup()
        self._build_diagnostics()

        footer = self.tabs.footer
        self.refresh_button = ttk.Button(footer, text="Refresh", command=self.scan)
        self.refresh_button.pack(side="right")
        self.notice = ui.WrapLabel(footer, text="Ready to scan.", style="Muted.TLabel")
        self.notice.pack(side="left", fill="x", expand=True)
        self.busy_bar = ttk.Progressbar(footer, mode="indeterminate", length=px(96), style="Busy.Horizontal.TProgressbar")
        self.side_battery = ttk.Label(self.tabs.sidebar_footer, text="Battery  —", style="SidebarMuted.TLabel")
        self.side_battery.pack(anchor="w")
        self.after(10, lambda: self.theme.style_titlebar(self))
        self.after(100, self._drain)
        if auto_scan:
            self.after(200, self.scan)
            self.after(60000, self._auto_refresh)

    def _icon(self, size: int) -> tk.PhotoImage | None:
        """The smallest pre-rendered icon at least `size` design pixels wide."""
        fitting = [available for available in self.icons if available >= ui.px(size)]
        if fitting:
            return self.icons[min(fitting)]
        return self.icons[max(self.icons)] if self.icons else None

    def _build_overview(self) -> None:
        page, px = self.overview, ui.px
        hero = ui.Card(page, padding=px(20))
        hero.pack(fill="x")
        hero_icon = self._icon(64)
        if hero_icon is not None:
            ttk.Label(hero, image=hero_icon).pack(side="left", anchor="n", padx=(0, px(18)))
        info = ttk.Frame(hero)
        info.pack(side="left", fill="x", expand=True)
        self.device_name = ttk.Label(info, text="Looking for your trackpad…", style="Hero.TLabel")
        self.device_name.pack(anchor="w")
        pills = ttk.Frame(info)
        pills.pack(anchor="w", pady=(px(8), px(8)))
        self.pill_connection = ttk.Label(pills, text="Scanning", style="Neutral.Pill.TLabel")
        self.pill_connection.pack(side="left")
        self.pill_driver = ttk.Label(pills, text="Checking driver", style="Neutral.Pill.TLabel")
        self.pill_driver.pack(side="left", padx=(px(6), 0))
        self.device_status = ui.WrapLabel(info, text="", style="Muted.TLabel")
        self.device_status.pack(fill="x")

        row = ttk.Frame(page)
        row.pack(fill="x", pady=(px(16), 0))
        row.columnconfigure((0, 1), weight=1, uniform="cards")
        battery = ui.Card(row, title="Battery")
        battery.grid(row=0, column=0, sticky="nsew", padx=(0, px(8)))
        reading = ttk.Frame(battery)
        reading.pack(fill="x", pady=(px(10), px(8)))
        self.battery = ttk.Label(reading, text="—", style="Battery.TLabel")
        self.battery.pack(side="left")
        self.battery_gauge = ui.BatteryGauge(reading, self.theme)
        self.battery_gauge.pack(side="right")
        self.battery_note = ui.WrapLabel(battery, text="Waiting for the Bluetooth driver.", style="Muted.TLabel")
        self.battery_note.pack(fill="x")

        tray_card = ui.Card(row, title="Tray icon & alerts")
        tray_card.grid(row=0, column=1, sticky="nsew", padx=(px(8), 0))
        status_row = ttk.Frame(tray_card)
        status_row.pack(fill="x", pady=(px(10), px(8)))
        self.pill_tray = ttk.Label(status_row, text="Checking", style="Neutral.Pill.TLabel")
        self.pill_tray.pack(side="left")
        # Low-emphasis action beside the status, so the button row always fits.
        self.tray_remove = ttk.Button(status_row, text="Remove", style="Link.TButton", state="disabled", command=lambda: self.tray_setup(True))
        self.tray_remove.pack(side="right")
        self.tray_note = ui.WrapLabel(tray_card, text="Checking tray setup…", style="Muted.TLabel")
        self.tray_note.pack(fill="x")
        tray_actions = ttk.Frame(tray_card)
        tray_actions.pack(fill="x", pady=(px(14), 0))
        self.tray_setup_button = ttk.Button(tray_actions, text="Set up tray icon", style="Accent.TButton", command=lambda: self.tray_setup(False))
        self.tray_setup_button.pack(side="left")
        self.tray_start = ttk.Button(tray_actions, text="Start now", state="disabled", command=self.tray_run)
        self.tray_start.pack(side="left", padx=px(8))

        layout = {"stacked": None}

        def reflow(event: tk.Event) -> None:
            # Side by side when there is room, stacked in narrow windows.
            stacked = event.width < px(620)
            if stacked == layout["stacked"]:
                return
            layout["stacked"] = stacked
            battery.grid_configure(row=0, column=0, columnspan=2 if stacked else 1, padx=0 if stacked else (0, px(8)))
            tray_card.grid_configure(row=1 if stacked else 0, column=0 if stacked else 1, columnspan=2 if stacked else 1,
                                     padx=0 if stacked else (px(8), 0), pady=(px(16), 0) if stacked else 0)

        row.bind("<Configure>", reflow)

        # Gesture features can add their controls to this card.
        self.gestures_card = ui.Card(page, title="Gestures", subtitle="Windows Precision Touchpad handles two-finger scrolling, pinch-to-zoom, taps, and three- and four-finger swipes once the driver is installed.")
        self.gestures_card.pack(fill="x", pady=(px(16), 0))
        ttk.Button(self.gestures_card, text="Open Windows gesture settings", command=lambda: self._open("ms-settings:devices-touchpad")).pack(anchor="w", pady=(px(14), 0))
        preset = ttk.Frame(self.gestures_card)
        preset.pack(fill="x", pady=(px(10), 0))
        self.mac_button = ttk.Button(preset, text="Apply Mac preset", command=lambda: self.mac_preset(False))
        self.mac_button.pack(side="left")
        self.mac_restore = ttk.Button(preset, text="Restore previous", command=lambda: self.mac_preset(True))
        self.mac_restore.pack(side="left", padx=px(8))
        ui.WrapLabel(self.gestures_card, text="Natural scroll, taps and right-click; three-finger Task View / desktop / desktop switching. Basic options apply live. Swipe mappings need sign-out/in. Applies to all precision touchpads for this user.", style="Small.TLabel").pack(fill="x", pady=(px(8), 0))

        actions = ttk.Frame(page)
        actions.pack(fill="x", pady=(px(16), 0))
        ttk.Button(actions, text="Bluetooth settings", command=lambda: self._open("ms-settings:bluetooth")).pack(side="left")
        if not self.admin:
            ttk.Button(actions, text="Open as administrator", command=self.restart_elevated).pack(side="left", padx=px(8))

    def _build_settings(self) -> None:
        page, px = self.settings_tab, ui.px
        self.settings_note = ui.WrapLabel(page, text="Install the Bluetooth driver to enable these settings.", style="Muted.TLabel")
        self.settings_note.pack(fill="x", pady=(0, px(14)))
        self.click_enabled = tk.BooleanVar(value=True)
        self.strength = tk.StringVar(value="Medium")
        self.silent = tk.BooleanVar(value=False)
        self.ignore_button = tk.BooleanVar(value=True)
        self.ignore_hover = tk.BooleanVar(value=True)
        self.palm = tk.BooleanVar(value=True)
        self.stop_mode = tk.StringVar(value="On physical click")
        self.threshold = tk.StringVar(value="40")

        click = ui.Card(page, title="Physical click & haptic feedback", subtitle="How strongly the trackpad clicks under your finger.")
        click.pack(fill="x")
        ttk.Checkbutton(click, text="Enable physical clicking", variable=self.click_enabled).pack(anchor="w", pady=(px(12), px(6)))
        ttk.Label(click, text="Click strength", style="Strong.TLabel").pack(anchor="w", pady=(px(6), px(4)))
        strengths = ttk.Frame(click)
        strengths.pack(anchor="w")
        for name in FEEDBACK:
            ttk.Radiobutton(strengths, text=name, value=name, variable=self.strength).pack(side="left", padx=(0, px(18)))
        # Selected only when the driver holds values this form cannot express.
        ttk.Radiobutton(strengths, text="Custom", value="Custom (unchanged)", variable=self.strength, state="disabled").pack(side="left")
        ttk.Checkbutton(click, text="Silent clicking (Light, Medium and Firm)", variable=self.silent).pack(anchor="w", pady=(px(10), 0))

        precision = ui.Card(page, title="Pointer precision", subtitle="Keep the pointer steady while you click or rest your hand.")
        precision.pack(fill="x", pady=(px(16), 0))
        checks = ttk.Frame(precision)
        checks.pack(fill="x", pady=(px(10), 0))
        for variable, label in ((self.ignore_button, "Ignore the finger resting on the physical button"), (self.ignore_hover, "Ignore near-surface and hovering fingers"), (self.palm, "Palm rejection")):
            ttk.Checkbutton(checks, variable=variable, text=label).pack(anchor="w", pady=px(2))
        row = ttk.Frame(precision)
        row.pack(fill="x", pady=(px(12), 0))
        ttk.Label(row, text="Stop pointer movement", style="Strong.TLabel").pack(side="left")
        ttk.Combobox(row, textvariable=self.stop_mode, values=["On physical click", "Never", "Pressure threshold", "Contact size threshold"], state="readonly", width=23).pack(side="left", padx=px(12))
        self.threshold_box = ttk.Spinbox(row, textvariable=self.threshold, from_=0, to=255, width=5)
        self.threshold_box.pack(side="left")
        ui.WrapLabel(precision, text="The threshold (0–255) is used only in pressure or contact-size mode.", style="Small.TLabel").pack(fill="x", pady=(px(8), 0))
        self.stop_mode.trace_add("write", lambda *_: self._sync_threshold())
        self._sync_threshold()

        actions = ttk.Frame(page)
        actions.pack(fill="x", pady=(px(16), 0))
        self.apply_button = ttk.Button(actions, text="Apply to trackpad", style="Accent.TButton", state="disabled", command=self.apply)
        self.apply_button.pack(side="left")
        ttk.Button(actions, text="Restore defaults", command=lambda: self._load_settings(DEFAULTS)).pack(side="left", padx=px(8))
        ui.WrapLabel(page, text="These settings apply to the whole driver. Pointer speed, tap-to-click, scrolling direction and gesture assignments are in Windows gesture settings.", style="Small.TLabel").pack(fill="x", pady=(px(14), 0))

    def _sync_threshold(self) -> None:
        uses_threshold = self.stop_mode.get() in ("Pressure threshold", "Contact size threshold")
        self.threshold_box.configure(state="normal" if uses_threshold else "disabled")

    def _build_gestures(self):
        px, page = ui.px, self.gesture_tab
        try:
            values = gesture_config.load()
            note = "Each gesture is opt-in. The tray reloads saved preferences within one second."
        except (OSError, ValueError) as error:
            values = GESTURE_DEFAULTS.copy()
            note = f"Could not load gesture preferences: {error}. Gestures are off."
        self.gesture_vars = {k: tk.BooleanVar(value=values[k]) for k in TOGGLES}
        self.gesture_values = values
        self.gesture_status = ui.WrapLabel(page, text=note, style="Muted.TLabel")
        self.gesture_status.pack(fill="x", pady=(0, px(12)))
        card = ui.Card(page, title="Extra gestures", subtitle="Raw contacts are read from your USB-C trackpad. Windows keeps ordinary pointer movement and two-finger scrolling.")
        card.pack(fill="x")
        labels = {
            "three_finger_drag": "Three-finger drag — move promptly to pick up; lift to release",
            "smart_zoom": "Smart zoom — two-finger double-tap: Ctrl+Plus / Ctrl+0",
            "notification_center": "Notification Center — two fingers swipe inward from right edge",
            "launchpad": "Launchpad — four-finger pinch: Start; spread: desktop",
            "lookup": "Look up — three-finger tap: define the word under the pointer on Bing",
        }
        for name, label in labels.items():
            ttk.Checkbutton(card, text=label, variable=self.gesture_vars[name]).pack(anchor="w", pady=px(4))
        ui.WrapLabel(card, text="Look up reads the word through Windows accessibility (UI Automation): nothing is clicked or typed, the clipboard is untouched, and password fields are skipped. Apps that don't expose their text do nothing. Smart zoom delays a single two-finger tap's right-click to tell it apart from a double-tap; while the tray runs it takes over Windows' two-finger tap and gives it back when it stops. The physical two-finger click stays native.", style="Small.TLabel").pack(fill="x", pady=(px(8), 0))
        tuning = ui.Card(page, title="Timing & sensitivity")
        tuning.pack(fill="x", pady=(px(16), 0))
        self.gesture_numbers = {}
        for name, label in (("drag_release_delay", "Drag release grace (seconds)"), ("tap_max_time", "Maximum tap duration (seconds)"), ("tap_max_movement", "Maximum tap movement (surface fraction)"), ("edge_width", "Right-edge width (surface fraction)"), ("pointer_scale", "Drag pointer travel (pixels / surface)")):
            row = ttk.Frame(tuning)
            row.pack(fill="x", pady=px(3))
            ttk.Label(row, text=label).pack(side="left")
            variable = tk.StringVar(value=str(values[name]))
            self.gesture_numbers[name] = variable
            ttk.Entry(row, textvariable=variable, width=10).pack(side="right")
        ui.WrapLabel(tuning, text="0.025 = 2.5% of the surface; default drag grace is 0.5 s. A slow three-finger rest never starts a drag.", style="Small.TLabel").pack(fill="x", pady=(px(8), 0))
        conflict = ui.Card(page, title="Windows gesture conflicts")
        conflict.pack(fill="x", pady=(px(16), 0))
        ui.WrapLabel(conflict, text="Three-finger drag sets Windows' three-finger actions to Nothing and moves Mac swipes to four fingers. Look up disables Windows' three-finger tap. Launchpad disables native four-finger swipes; this engine supplies Mac swipes when the Mac preset or three-finger drag is enabled. Registry changes require sign-out/in; the engine waits before injecting. Turn features off and Save to restore their previous Windows settings.", style="Muted.TLabel").pack(fill="x")
        actions = ttk.Frame(page)
        actions.pack(fill="x", pady=px(16))
        self.gesture_save = ttk.Button(actions, text="Save gestures", style="Accent.TButton", command=self.save_gestures)
        self.gesture_save.pack(side="left")
        ttk.Button(actions, text="Turn all off in form", command=lambda: [v.set(False) for v in self.gesture_vars.values()]).pack(side="left", padx=px(8))

    def mac_preset(self, restore):
        if self.busy:
            return
        text = ("Restore the Windows touchpad settings saved before Apply Mac preset? Swipe changes need sign-out/in."
                if restore else "Apply natural scrolling, tap-to-click and two-finger right-click, with three-finger Task View / show desktop / switch desktops? Your previous settings will be saved. Swipe changes need sign-out/in.")
        if not messagebox.askokcancel("Windows touchpad settings", text, parent=self):
            return
        self._work("Restoring touchpad settings…" if restore else "Applying Mac preset…",
                   touchpad_settings.restore_mac if restore else touchpad_settings.apply_mac,
                   lambda message: self.notice.configure(text=message))

    def save_gestures(self):
        if self.busy:
            return
        try:
            values = {**self.gesture_values, **{k:v.get() for k,v in self.gesture_vars.items()},
                      **{k:float(v.get()) for k,v in self.gesture_numbers.items()}}
            values = validate_gestures(values)
        except ValueError as error:
            messagebox.showerror("Invalid gesture setting", str(error), parent=self)
            return
        if not messagebox.askokcancel("Save gestures & Windows conflicts", "Save these gestures and adjust or restore Windows tap/swipe actions as described above? New registry swipe mappings require sign-out/in. Look up sends the word under the pointer to Bing when you perform the gesture.", parent=self):
            return
        def done(message):
            self.gesture_values = values
            self.notice.configure(text=message)
            self.gesture_status.configure(text=message)
        self._work("Saving gestures and Windows conflict settings…", lambda: touchpad_settings.configure_gestures(values), done)

    def _build_setup(self) -> None:
        page, px = self.setup_tab, ui.px
        intro = ui.Card(page, title="MagicTrackpad2ForWindows v2.2", subtitle="Free, open-source driver by Bingxing Wang and Vito Plantamura. Microsoft-signed Windows 11 package for the USB-C Magic Trackpad (PID 0324) over Bluetooth.")
        intro.pack(fill="x")
        self.pill_setup = ttk.Label(intro, text="Checking", style="Neutral.Pill.TLabel")
        self.pill_setup.pack(anchor="w", pady=(px(12), 0))

        steps = ui.Card(page, title="Install in three steps")
        steps.pack(fill="x", pady=(px(16), 0))
        for number, (title, text) in enumerate((
            ("Prepare", "Downloads the signed driver and its matching open-source code, then verifies the pinned SHA-256 checksum."),
            ("Install", "Asks for administrator access once, re-checks the Microsoft signature and installs the driver with pnputil."),
            ("Reconnect", "Switch the trackpad off and on (or toggle Bluetooth), then click Refresh."),
        ), start=1):
            step = ttk.Frame(steps)
            step.pack(fill="x", pady=(px(12), 0))
            ttk.Label(step, text=str(number), style="Step.TLabel").pack(side="left", anchor="n", padx=(0, px(12)))
            body = ttk.Frame(step)
            body.pack(side="left", fill="x", expand=True)
            ttk.Label(body, text=title, style="Strong.TLabel").pack(anchor="w")
            ui.WrapLabel(body, text=text, style="Muted.TLabel").pack(fill="x")
        self.package_note = ui.WrapLabel(steps, text="Package downloaded." if PACKAGE_DIR.exists() else "Package not downloaded yet.", style="Small.TLabel")
        self.package_note.pack(fill="x", pady=(px(14), 0))
        actions = ttk.Frame(steps)
        actions.pack(fill="x", pady=(px(12), 0))
        self.prepare_button = ttk.Button(actions, text="1. Prepare driver", style="Accent.TButton", command=self.prepare)
        self.prepare_button.pack(side="left")
        self.install_button = ttk.Button(actions, text="2. Install driver", command=self.install)
        self.install_button.pack(side="left", padx=px(8))
        ttk.Button(actions, text="Installation log", command=self.show_install_log).pack(side="left")

        about = ui.Card(page, title="How it fits together", subtitle="Trackpad Free is the companion app; the upstream driver provides multitouch. The driver's battery and settings interface is limited to administrators, which the tray icon handles after a one-time setup. Feature parity with Magic Utilities has not been established.")
        about.pack(fill="x", pady=(px(16), 0))
        links = ttk.Frame(about)
        links.pack(fill="x", pady=(px(14), 0))
        ttk.Button(links, text="Upstream release & instructions", command=lambda: webbrowser.open(RELEASE)).pack(side="left")
        ttk.Button(links, text="Licenses & credits", command=lambda: self._open(str(ROOT / "THIRD_PARTY.md"))).pack(side="left", padx=px(8))

    def _update_setup_state(self, precision: bool) -> None:
        downloaded = PACKAGE_DIR.exists()
        if precision:
            ui.set_pill(self.pill_setup, "good", "Installed and active")
        elif downloaded:
            ui.set_pill(self.pill_setup, "warn", "Downloaded, ready to install")
        else:
            ui.set_pill(self.pill_setup, "neutral", "Not installed")
        self.prepare_button.configure(style="Accent.TButton" if not (downloaded or precision) else "TButton")
        self.install_button.configure(style="Accent.TButton" if downloaded and not precision else "TButton")

    def _build_diagnostics(self) -> None:
        page, px, c = self.diagnostics_tab, ui.px, self.theme.c
        box = ttk.Frame(page, style="Card.TFrame", padding=1)
        box.pack(fill="both", expand=True)
        self.diagnostics = tk.Text(box, font=(self.theme.mono_family, 9), wrap="word", height=24, state="disabled",
                                   background=c["code_bg"], foreground=c["text"], insertbackground=c["text"],
                                   selectbackground=c["accent"], selectforeground=c["accent_text"],
                                   relief="flat", borderwidth=0, highlightthickness=0, padx=px(14), pady=px(12))
        scrollbar = ttk.Scrollbar(box, orient="vertical", command=self.diagnostics.yview)
        self.diagnostics.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.diagnostics.pack(side="left", fill="both", expand=True)
        actions = ttk.Frame(page)
        actions.pack(fill="x", pady=(px(12), 0))
        ttk.Button(actions, text="Copy diagnostics", command=self.copy_diagnostics).pack(side="left")
        ttk.Label(actions, text="Includes device identifiers; review before posting publicly.", style="Small.TLabel").pack(side="left", padx=px(12))

    def _open(self, target: str) -> None:
        try:
            os.startfile(target)
        except OSError as error:
            messagebox.showerror("Could not open", str(error), parent=self)

    def _work(self, label: str, operation, finished) -> None:
        if self.busy:
            return
        self.busy = True
        self.notice.configure(text=label)
        self.busy_bar.pack(side="right", padx=(0, ui.px(12)), before=self.notice)
        self.busy_bar.start(12)
        for button in (self.refresh_button, self.apply_button, self.prepare_button, self.install_button, self.mac_button, self.mac_restore, self.gesture_save):
            button.configure(state="disabled")

        def worker() -> None:
            try:
                self.messages.put((finished, operation(), None))
            except Exception as error:
                self.messages.put((finished, None, str(error)))

        threading.Thread(target=worker, daemon=True).start()

    def _drain(self) -> None:
        try:
            finished, result, error = self.messages.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            self.busy_bar.stop()
            self.busy_bar.pack_forget()
            for button in (self.refresh_button, self.prepare_button, self.install_button, self.mac_button, self.mac_restore, self.gesture_save):
                button.configure(state="normal")
            if error:
                self.notice.configure(text=f"Operation failed: {error}")
            else:
                finished(result)
            self._update_apply()
        self.after(100, self._drain)

    def _auto_refresh(self) -> None:
        if not self.busy:
            self.scan()
        self.after(60000, self._auto_refresh)

    def scan(self) -> None:
        self._work("Reading Windows device and Bluetooth driver status…", snapshot, self._show_snapshot)

    def _show_snapshot(self, data: dict) -> None:
        self.last_snapshot = data
        devices, driver = data["devices"], data["driver"]
        models = sorted({device["Model"] for device in devices if device.get("Model")})
        level = driver.get("battery")
        installed = data.get("tray_task", False)
        if models:
            self.device_name.configure(text=" / ".join(models))
            detail = "Multitouch gestures are handled by Windows Precision Touchpad." if data["precision_driver"] else "Working as a basic mouse. Install the precision driver for multitouch gestures."
            # Windows lists paired devices even when they are off; a battery reading proves a live link.
            ui.set_pill(self.pill_connection, "good" if level is not None else "neutral", "Connected" if level is not None else "Paired")
        elif devices:
            self.device_name.configure(text="Trackpad-named device found")
            detail = "Hardware model not confirmed. See Diagnostics for identifiers."
            ui.set_pill(self.pill_connection, "warn", "Model unconfirmed")
        else:
            self.device_name.configure(text="No Magic Trackpad found")
            detail = "Turn on the trackpad and connect it in Windows Bluetooth settings."
            ui.set_pill(self.pill_connection, "bad", "Not found")
        if data["precision_driver"]:
            ui.set_pill(self.pill_driver, "good", "Precision driver active")
        elif models:
            ui.set_pill(self.pill_driver, "warn", "Basic mouse mode")
        else:
            ui.set_pill(self.pill_driver, "neutral", "Driver not detected")
        self.device_status.configure(text=detail)

        self.battery.configure(text=f"{level}%" if level is not None else "—")
        self.battery_gauge.set(level)
        note = "Live reading from the Bluetooth driver."
        if level is None:
            note = driver.get("error") or "No battery reading available."
            if installed and not self.admin:
                note = "Shown in the tray icon. Open Trackpad Free from the tray icon to see it here too."
        self.battery_note.configure(text=note)
        self.side_battery.configure(text=f"Battery  {level}%" if level is not None else "Battery  —")
        if driver.get("settings") and not self.settings_loaded:
            self._load_settings(driver["settings"])
            self.settings_loaded = True

        ui.set_pill(self.pill_tray, "good" if installed else "neutral", "Starts at sign-in" if installed else "Not set up")
        self.tray_note.configure(text="Shows the battery in the notification area without a UAC prompt, and warns at 20% and 10%." if installed else "One administrator prompt now; afterwards the battery icon starts at every sign-in and warns at 20% and 10%.")
        self.tray_setup_button.configure(text="Set up again" if installed else "Set up tray icon", style="TButton" if installed else "Accent.TButton")
        for button in (self.tray_start, self.tray_remove):
            button.configure(state="normal" if installed else "disabled")
        self._update_setup_state(data["precision_driver"])
        if data.get("gestures"):
            self.gesture_status.configure(text=data["gestures"].get("message", "No gesture status yet."))
        self._set_diagnostics(json.dumps(data, indent=2, ensure_ascii=False))
        self.notice.configure(text=f"Updated · {len(devices)} trackpad-related Windows interfaces found.")
        self._update_apply()

    def _update_apply(self) -> None:
        driver = self.last_snapshot.get("driver", {})
        available = self.admin and driver.get("driver_available", False)
        self.apply_button.configure(state="normal" if available and not self.busy else "disabled")
        note = "Settings apply to the upstream Bluetooth driver. Changes in this form are saved only on Apply."
        if not available:
            note = driver.get("error") or "Install the Bluetooth driver, then open this app as administrator."
        self.settings_note.configure(text=note)

    def _load_settings(self, values: dict) -> None:
        self.loaded_settings = {**DEFAULTS, **values}
        values = self.loaded_settings
        self.click_enabled.set(not values["ButtonDisabled"])
        self.strength.set("Custom (unchanged)")
        self.silent.set(False)
        for name, (click, release) in FEEDBACK.items():
            if (values["FeedbackClick"], values["FeedbackRelease"]) == (click, release):
                self.strength.set(name)
                break
            if name != "Maximum" and (values["FeedbackClick"], values["FeedbackRelease"]) == (click & 255, release & 255):
                self.strength.set(name)
                self.silent.set(True)
                break
        if values["ButtonDisabled"]:
            self.strength.set("Medium")
        self.ignore_button.set(bool(values["IgnoreButtonFinger"]))
        self.ignore_hover.set(bool(values["IgnoreNearFingers"]))
        self.palm.set(bool(values["PalmRejection"]))
        if values["StopPressure"] == 0:
            self.stop_mode.set("On physical click")
        elif values["StopPressure"] != -1:
            self.stop_mode.set("Pressure threshold")
            self.threshold.set(str(values["StopPressure"]))
        elif values["StopSize"] != -1:
            self.stop_mode.set("Contact size threshold")
            self.threshold.set(str(values["StopSize"]))
        else:
            self.stop_mode.set("Never")

    def _form_settings(self) -> dict:
        values = self.loaded_settings.copy()
        values["ButtonDisabled"] = int(not self.click_enabled.get())
        if not self.click_enabled.get():
            values["FeedbackClick"], values["FeedbackRelease"] = 0, 0
        elif self.strength.get() in FEEDBACK:
            click, release = FEEDBACK[self.strength.get()]
            if self.silent.get() and self.strength.get() != "Maximum":
                click, release = click & 255, release & 255
            values["FeedbackClick"], values["FeedbackRelease"] = click, release
        values["IgnoreButtonFinger"] = int(self.ignore_button.get())
        values["IgnoreNearFingers"] = int(self.ignore_hover.get())
        values["PalmRejection"] = int(self.palm.get())
        values["StopPressure"], values["StopSize"] = -1, -1
        mode = self.stop_mode.get()
        if mode == "On physical click":
            values["StopPressure"] = 0
        elif mode in ("Pressure threshold", "Contact size threshold"):
            threshold = int(self.threshold.get())
            if not 0 <= threshold <= 255:
                raise ValueError("Threshold must be between 0 and 255.")
            values["StopPressure" if mode == "Pressure threshold" else "StopSize"] = threshold
        return values

    def apply(self) -> None:
        try:
            settings = self._form_settings()
        except ValueError as error:
            messagebox.showerror("Invalid settings", str(error), parent=self)
            return

        def finished(result: dict) -> None:
            self.loaded_settings = settings
            self.notice.configure(text=result["message"])

        self._work("Applying Bluetooth driver settings…", lambda: backend(settings), finished)

    def prepare(self) -> None:
        def finished(path: Path) -> None:
            self.package_note.configure(text=f"Verified package ready: {path}")
            self.notice.configure(text="Driver downloaded and SHA-256 verified. Ready to install.")
            self._update_setup_state(self.last_snapshot.get("precision_driver", False))
        self._work("Downloading and verifying the signed driver and its source…", prepare_package, finished)

    def install(self) -> None:
        if not PACKAGE_DIR.exists():
            self.notice.configure(text="Prepare the driver package first.")
            return
        try:
            elevate("powershell.exe", ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "Install-Driver.ps1"), "-Python", PYTHON])
        except OSError as error:
            self.notice.configure(text=str(error))
            return
        self.notice.configure(text="Installer started. Read the installation log, then reconnect the trackpad and Refresh.")

    def tray_setup(self, remove: bool) -> None:
        user = f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}"
        arguments = ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "Install-Tray.ps1"),
                     "-User", user, "-Pythonw", str(Path(PYTHON).with_name("pythonw.exe"))]
        try:
            elevate("powershell.exe", arguments + (["-Remove"] if remove else []))
        except OSError as error:
            self.notice.configure(text=str(error))
            return
        self.notice.configure(text="Tray setup started. Click Refresh once it finishes; details are in tray-install.log.")

    def tray_run(self) -> None:
        try:
            tray.start_task()
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            self.notice.configure(text=f"Could not start the tray: {error}")
            return
        self.notice.configure(text="Tray icon started. Look for the battery percentage in the notification area.")

    def show_install_log(self) -> None:
        path = ROOT / "driver-install.log"
        if not path.exists():
            self.notice.configure(text="No installation log yet. Install the prepared driver first.")
            return
        self._set_diagnostics(path.read_text(encoding="utf-8-sig"))
        self.tabs.select(self.diagnostics_tab)

    def destroy(self) -> None:
        # Cancel the polling timers so they do not fire into a destroyed window.
        for job in self.tk.splitlist(self.tk.call("after", "info")):
            self.after_cancel(job)
        super().destroy()

    def restart_elevated(self) -> None:
        try:
            elevate(PYTHON, [str(ROOT / "app.py")])
        except OSError as error:
            self.notice.configure(text=str(error))
            return
        self.destroy()

    def _set_diagnostics(self, text: str) -> None:
        self.diagnostics.configure(state="normal")
        self.diagnostics.delete("1.0", tk.END)
        self.diagnostics.insert("1.0", text)
        self.diagnostics.configure(state="disabled")

    def copy_diagnostics(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.diagnostics.get("1.0", "end-1c"))
        self.notice.configure(text="Diagnostics copied. Device identifiers are included.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagnose", action="store_true", help="Print device/driver status and exit")
    args = parser.parse_args()
    if args.diagnose:
        print(json.dumps(snapshot(), indent=2, ensure_ascii=True))
    else:
        TrackpadApp().mainloop()
