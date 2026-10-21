# Third-party components, credits, and licenses

Trackpad Free is an independent, free, open-source companion application. It does
**not** use any code, branding, or assets from Magic Utilities (magicutilities.net)
or Trackpad++.

## Driver backend: MagicTrackpad2ForWindows v2.2

- Project: https://github.com/vitoplantamura/MagicTrackpad2ForWindows
- Authors: Bingxing Wang (imbushuo) and Vito Plantamura, with contributors
- License: GPL-2.0 (full text: `drivers/v2.2/UPSTREAM-LICENSE.txt`, also
  `MagicTrackpad2ForWindows-v2.2-source.zip` in the driver package directory)
- Distribution: the Windows 11 driver archive is pinned by SHA-256 in
  `driver_package.py` and is signed by the *Microsoft Windows Hardware
  Compatibility Publisher* (verified before installation by
  `Install-Driver.ps1`).

What it provides: Windows Precision Touchpad multitouch and gestures over
Bluetooth for the USB-C Magic Trackpad (PID 0324), battery report access, and
haptic/click configuration via a control device.

Trackpad Free interacts with this driver only through its documented public
interface:

- Control device: `\\.\AmtPtpControlDeviceUm`
- IOCTLs: `IOCTL_RELOAD_SETTINGS` (0x222000) and `IOCTL_GET_BATTERY` (0x222004),
  matching `CtlCode(FILE_DEVICE_UNKNOWN, 0x800/0x801, METHOD_BUFFERED, FILE_ANY_ACCESS)`
- Settings registry key:
  `HKLM\SYSTEM\CurrentControlSet\Services\AmtPtpHidFilter\Parameters`
  (the same key the upstream control panel writes)

If you redistribute this project with the driver package included, GPL-2.0
requires you to ship the corresponding upstream source
(`MagicTrackpad2ForWindows-v2.2-source.zip`) and license texts, as
`driver_package.py` does automatically.

## Protocol documentation

The multitouch report layout used by the upstream driver is documented in the
Linux kernel driver `drivers/hid/hid-magicmouse.c` (GPL-2.0), which describes
report `0x31` for Bluetooth Magic Trackpads and identifies the 2024 USB-C
model as Bluetooth version `0x314`.

## Windows APIs

Device discovery uses the built-in PowerShell `Get-PnpDevice` /
`Get-PnpDeviceProperty` cmdlets. Nothing is installed for discovery.
