# Security policy

Trackpad Free installs a kernel driver package and, optionally, a scheduled
task that runs with administrator rights, so security reports are taken
seriously.

## Reporting a vulnerability

Please report privately through **GitHub → Security → Report a vulnerability**
on this repository, not in a public issue. Include what an attacker could do,
the steps to reproduce, and the Trackpad Free version (shown in the sidebar).

## What is in scope

- `Install-Driver.ps1` and `driver_package.py`: download, SHA-256 pinning,
  archive extraction and Microsoft signature verification.
- `Install-Tray.ps1` and `tray.py`: the elevated sign-in task.
- `driver_backend.py`: the IOCTL and registry interface to the driver.

## Known design trade-offs

- The tray task runs `tray.py` from the install folder with highest
  privileges. Anyone who can write to that folder can run code as an
  administrator, so install Trackpad Free in a folder only you can write to
  (for example under `%LOCALAPPDATA%`), and use **Remove** before moving it.
- Bugs in the multitouch driver itself belong to the upstream
  [MagicTrackpad2ForWindows](https://github.com/vitoplantamura/MagicTrackpad2ForWindows) project.
