# Mac-style gestures

Windows Precision Touchpad already handles pointer movement, two-finger
scrolling, pinch-to-zoom and the basic three- and four-finger swipes. Trackpad
Free adds the Mac gestures Windows lacks, and a **Mac preset** that sets
Windows' own gestures to behave like a Mac.

## How the gesture engine works

- The tray (`tray.py`) registers for Raw Input from the trackpad's precision
  touchpad collection (usage page 0x0D, usage 0x05) and parses each report
  with the HID parser in `hid.dll` (`hidraw.py`). Windows still receives every
  report; nothing is consumed or blocked.
- `gestures.py` is a pure state machine that turns contact frames into
  actions, unit-tested with synthetic frames (`tests/test_gestures.py`).
- `gesture_input.py` performs the actions with `SendInput`. It is in the
  elevated tray process, so it also reaches elevated windows.
- Every gesture is off until you enable it on the **Gestures** page and click
  **Save**. The tray reloads the saved preferences within a second.

| Gesture | Motion | Action | Windows setting it needs |
| --- | --- | --- | --- |
| Three-finger drag | Three fingers down and move promptly; lift to release (0.5 s grace to reposition) | Left-button drag | Three-finger swipes and tap set to *Nothing*; Mac swipes move to four fingers |
| Smart zoom | Two-finger double-tap | Ctrl+Plus, then Ctrl+0 on the next double-tap in the same window | Windows' two-finger tap is taken over while the tray runs (see below) |
| Notification Center | Two fingers swipe in from the right edge | Win+N | None |
| Launchpad | Four-finger pinch / spread | Start / show desktop | Four-finger swipes set to *Nothing* (the engine supplies Mac swipes when needed) |
| Look up | Three-finger tap | Opens Bing with "define *word*" for the word under the pointer | Three-finger tap set to *Nothing* |
| Screenshot | Five-finger double-tap (second lift within 0.6 s of the first) | Win+Shift+S: Windows' snipping overlay | None (Windows has no five-finger gestures) |

### Look up

Look up reads the word under the pointer through Windows accessibility (UI
Automation, `uia.py`): `ElementFromPoint`, the element's `TextPattern`,
`RangeFromPoint` and `ExpandToEnclosingUnit(TextUnit_Word)`. Nothing is
clicked or typed and the clipboard is never touched, so it is safe over File
Explorer, the desktop and terminals. Password fields are skipped, and a tap
on blank space does nothing. Apps that don't expose their text through UI
Automation (some games, canvases or older apps) also do nothing. The word is
sent to Bing only when you perform the gesture, and the browser is opened
through Explorer so it never inherits the tray's administrator rights.

### Smart zoom and two-finger tap

To tell a single two-finger tap (right-click) from a double-tap (zoom), the
engine must own two-finger taps. While the tray engine is running with smart
zoom on, it turns off Windows' own two-finger tap and right-clicks itself
after the double-tap window (0.35 s), or immediately if the next touch turns
into a scroll. Your original setting is saved first in
`%APPDATA%\TrackpadFree\two-finger-tap-hold.json` and restored when smart zoom
is turned off, when the engine stops or hits an error, when the tray exits,
and the next time the tray starts after a crash. Turning smart zoom off and
clicking **Save** in the app restores it too, even if the tray is not running.

## Windows settings the app changes

All changes go through one transaction in `touchpad_settings.py`: the
previous values are written to a backup file in `%APPDATA%\TrackpadFree`
**before** anything changes, every write is read back, and **Restore
previous** (or turning the gestures off and saving) puts back exactly what
was there, without overwriting settings you changed later.

- **Basic options** use `SystemParametersInfo(SPI_SETTOUCHPADPARAMETERS)` and
  apply immediately: tap to click, two-finger tap for right-click and
  two-finger scrolling. The Mac preset leaves the scrolling direction at
  Windows' default, where content moves with your fingers as on a Mac.
- **Three- and four-finger gesture actions** are registry values under
  `HKCU\Software\Microsoft\Windows\CurrentVersion\PrecisionTouchPad`. Windows
  reads them at sign-in, so they need a sign-out and sign-in. The engine waits
  for that before it starts injecting.

### Measured registry values

`gesture_mapping.json` holds the values. They were measured on **Windows 11
25H2, build 26200, on 2026-10-21**, by changing one control at a time in
Settings > Bluetooth & devices > Touchpad through UI Automation
(`tools/settings_controls.ps1`) and diffing the registry before and after
(`tools/calibrate_settings.py`).

Per-direction actions (`ThreeFingerUp`, `ThreeFingerDown`, `ThreeFingerLeft`,
`ThreeFingerRight`, and the same for `FourFinger…`), as recorded for each
Settings choice:

| Value | Settings choice |
| --- | --- |
| 0 | Nothing |
| 1 | Switch apps |
| 2 | Task view |
| 3 | Show desktop |
| 4 | Switch desktops |

Swipe presets (`ThreeFingerSlideEnabled`, `FourFingerSlideEnabled`):

| Value | Settings choice |
| --- | --- |
| 0 | Nothing |
| 1 | Switch apps and show desktop |
| 2 | Switch desktops and show desktop |
| 65535 | Custom (set per direction in Advanced gestures) |

`ThreeFingerTapEnabled` = 0 corresponds to *Nothing* for the three-finger tap.

The Mac preset writes up = Task view (2), down = Show desktop (3), left and
right = Switch desktops (4), with the matching preset value 2.

### Other Windows builds

The same values are used on every Windows 11 build (22000 and later). On a
build other than 26200 the app says so after saving and asks you to check
Settings > Bluetooth & devices > Touchpad after signing in. Because every
write is read back and the backup restores the exact previous values, a
mismatch is easy to undo. Windows 10 is not supported.

## Measuring a new Windows build

To confirm or correct the values on another build, open Settings > Bluetooth
& devices > Touchpad and, for each control, run:

```
python tools/calibrate_settings.py <profile> <AutomationId> "<Settings choice>" [--group "<group name>"]
```

Each run changes one control, prints the registry diff, and records it with
the before/after snapshots in `%APPDATA%\TrackpadFree\gesture-calibration.json`.
The app does not read that file: each entry covers a single control, so
combine the diffs into the profiles in `gesture_mapping.json` and open a pull
request with the evidence. `tools/settings_controls.ps1` with no arguments
lists the AutomationIds of the visible Touchpad controls.

## Diagnostics

`python tools/gesture_probe.py --seconds 10 --output capture.json` records raw
contact frames for a few seconds without injecting anything or changing
settings, and shows what the recogniser would have done. The tray writes its
current state to `%APPDATA%\TrackpadFree\gesture-status.json` whenever it
changes, and at least every 30 seconds.
