<p align="center">
  <img src="assets/icon-128.png" width="96" height="96" alt="Trackpad Free icon">
</p>

<h1 align="center">Trackpad Free</h1>

<p align="center">
  A free, open-source Windows companion for the Apple Magic Trackpad:<br>
  precision-touchpad gestures, battery in the tray and click settings, with no subscription.
</p>

<p align="center">
  <img alt="Windows 11" src="https://img.shields.io/badge/Windows-11-0a64d6">
  <img alt="Python 3.10+" src="https://img.shields.io/badge/Python-3.10%2B-3776ab">
  <img alt="License: GPL-2.0-or-later" src="https://img.shields.io/badge/License-GPL--2.0--or--later-1a7f37">
  <img alt="No dependencies" src="https://img.shields.io/badge/dependencies-none-5e6875">
</p>

<p align="center">
  <img src="docs/screenshots/light-my-trackpad.png" width="760" alt="Trackpad Free showing the trackpad, battery level and tray status">
</p>

Trackpad Free starts with the **USB-C Magic Trackpad over Bluetooth**
(PID 0324) and aims for the features of paid utilities (gestures, battery
display, a settings app) without a subscription.

## Screenshots

| Light | Dark |
| --- | --- |
| ![Click and precision settings](docs/screenshots/light-click-precision.png) | ![My trackpad page in dark mode](docs/screenshots/dark-my-trackpad.png) |
| ![Mac gestures](docs/screenshots/light-gestures.png) | ![Mac gestures in dark mode](docs/screenshots/dark-gestures.png) |
| ![Driver setup](docs/screenshots/light-driver-setup.png) | ![Click and precision settings in dark mode](docs/screenshots/dark-click-precision.png) |

## Download

1. Install **Python 3.10 or newer** from
   [python.org](https://www.python.org/downloads/windows/) (keep *tcl/tk and
   IDLE* selected), or run `winget install Python.Python.3.12`.
2. Download `TrackpadFree-vX.Y.Z.zip` from the
   [latest release](../../releases/latest) and extract it to a folder only you
   can write to, for example `%LOCALAPPDATA%\TrackpadFree`.
3. Double-click `Start-TrackpadFree.cmd`, then follow the setup below.

## What works today

| Feature | Status |
| --- | --- |
| Detect the trackpad by hardware ID (not display name) | ✅ |
| Windows Precision Touchpad gestures (2-finger scroll, pinch, 3/4-finger) | ✅ via the precision driver |
| Battery percentage over Bluetooth | ✅ once driver installed (tray icon, or app as admin) |
| Tray icon with battery %, low-battery alerts at 20% and 10% | ✅ one-time admin setup, then no prompts |
| Mac preset for Windows' own gestures (Task View, show desktop, switch desktops) | ✅ restorable; swipe changes need sign-out/in |
| Mac gestures: three-finger drag, smart zoom, Notification Center edge swipe, Launchpad pinch, Look up, five-finger double-tap screenshot | ✅ opt-in, run by the tray — see [docs/gestures.md](docs/gestures.md) |
| Click strength / silent clicking | ✅ once driver installed (admin) |
| Palm rejection, near-finger rejection options | ✅ once driver installed (admin) |
| Pointer-speed, tap-to-click, scroll direction, gesture assignment | ✅ handled by Windows Settings (link in the app) |
| Light / Dark / Match Windows appearance | ✅ sidebar → Appearance; switches instantly and is remembered |
| USB-C wired connection | not yet tested |
| Exact Magic Utilities feature parity | not established — see THIRD_PARTY.md |

## How to set it up

1. **Start the app**: double-click `Start-TrackpadFree.cmd` (or `python app.py`).
2. Open the **Driver setup** tab → **1. Prepare driver**. This downloads the
   pinned, Microsoft-signed `MagicTrackpad2ForWindows` v2.2 package plus its
   GPL source and verifies the SHA-256 checksum.
3. Click **2. Install driver** and accept the UAC prompt. The installer
   re-verifies the Microsoft signature before running `pnputil`.
4. Reconnect the trackpad (toggle Bluetooth or the trackpad power switch),
   click **Refresh**.
5. On **My trackpad**, click **Set up tray icon** and accept the UAC prompt
   once. This registers a sign-in task (`\TrackpadFree\Trackpad Free Tray`)
   that starts `tray.py` with highest privileges, so the battery appears in
   the notification area at every sign-in without another prompt. Right-click
   the icon to refresh, open the app (already elevated) or exit.
6. For click settings without the tray, use **Open as administrator**.
7. Optional Mac gestures: on **My trackpad**, **Apply Mac preset** sets
   Windows' own three-finger gestures like a Mac. On the **Gestures** page,
   tick the gestures you want and click **Save**. Gestures that change
   Windows' three- or four-finger actions take effect after you sign out and
   back in; the tray must be running. Details and the exact Windows settings
   changed are in [docs/gestures.md](docs/gestures.md).

The tray task runs `tray.py` from this folder with administrator rights, so
anyone who can edit this folder can run code as administrator. Keep it in a
folder only you can write to, and use **Remove** before moving or deleting it.

Requirements: Windows 11 (AMD64/ARM64), Python 3.10+, trackpad paired over
Bluetooth. Do **not** install Magic Utilities or Trackpad++ alongside this —
only one precision driver can claim the device.

## Files

- `app.py` — Tkinter companion app (overview, settings, driver setup, diagnostics)
- `ui.py` — Windows 11-style theme (light/dark, high-DPI), sidebar, cards, battery gauge
- `version.py` — the app version; release tags are `v<version>`
- `assets/` — app icon in every Windows size (generated by `tools/make_icons.py`)
- `devices.py` — name-independent Plug and Play discovery
- `driver_backend.py` — battery/settings client for the upstream driver
- `driver_package.py` — pinned download + SHA-256 + path-safe extraction
- `Install-Driver.ps1` — elevated installer with signature verification
- `tray.py` — dependency-free notification-area icon (battery %, low alerts) that also hosts the gesture engine
- `gestures.py` — pure gesture recogniser (contact frames in, actions out)
- `hidraw.py` — Raw Input + HID parsing of the trackpad's multitouch contacts
- `gesture_host.py`, `gesture_input.py`, `gesture_config.py` — tray integration, `SendInput` output, saved preferences
- `uia.py` — UI Automation word lookup for the Look up gesture (no input sent)
- `touchpad_settings.py`, `gesture_mapping.json` — restorable Windows touchpad settings (Mac preset, gesture conflicts)
- `Install-Tray.ps1` — registers or removes the elevated sign-in task for the tray
- `tests/` — hardware-free unit tests, run by GitHub Actions on Windows
- `tools/` — icon generator and README screenshot capture (demo data only)
- `THIRD_PARTY.md` — credits, licenses, and the exact driver interfaces used

## Uninstall

1. In the app, **My trackpad → Tray icon & alerts → Remove** deletes the
   sign-in task.
2. Remove the driver: Device Manager → Human Interface Devices → *Apple
   Multi-touch Trackpad HID Filter* → Uninstall device, with *Attempt to
   remove the driver for this device* ticked. Or, in an administrator
   terminal, find the `AmtPtpDevice.inf` entry with `pnputil /enum-drivers`
   and run `pnputil /delete-driver oemNN.inf /uninstall`.
3. Delete the Trackpad Free folder.

## Development

No third-party Python packages are needed. Run the tests with:

```
python -m unittest discover -s tests
```

The driver package (`drivers/`) is downloaded on demand and is not committed;
logs and local scratch files are ignored too. See
[CONTRIBUTING.md](CONTRIBUTING.md) for UI conventions, screenshots and
releases, and [SECURITY.md](SECURITY.md) to report a vulnerability.

## Troubleshooting

- **App says driver not loaded**: run the install step, then reconnect the
  trackpad. Check `driver-install.log`.
- **Battery shows “—”**: the upstream control device is restricted to
  administrators; set up the tray icon or restart Trackpad Free as administrator.
- **Tray icon missing**: click **Start tray now**, or check `tray-install.log`.
- **Mac gestures do nothing**: the Gestures page shows the tray's status. If
  it asks you to sign out and in, do that once; if it says the tray isn't
  running, start it from **My trackpad**. Look up only works in apps that
  expose their text to Windows accessibility.
- **Two-finger tap stopped right-clicking**: smart zoom takes over two-finger
  taps while the tray runs. Start the tray, or turn smart zoom off and click
  **Save** to give the tap back to Windows.
- **Conflicting gesture behavior**: uninstall Magic Utilities / Trackpad++ /
  the 2021 Apple Boot Camp driver first (Device Manager → Human Interface
  Devices → uninstall with driver software), then reinstall this driver.

This project is independent and does not use Magic Utilities code.

## License

Trackpad Free is licensed under the GNU General Public License v2.0 or later
(`GPL-2.0-or-later`), matching the upstream MagicTrackpad2ForWindows driver.
See [LICENSE](LICENSE) and [THIRD_PARTY.md](THIRD_PARTY.md).
