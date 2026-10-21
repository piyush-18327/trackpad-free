"""Read-only Windows Plug and Play discovery, independent of device names."""

from __future__ import annotations

import base64
import json
import re
import subprocess

MODELS = {"030e": "Magic Trackpad (original)", "0265": "Magic Trackpad (Lightning)", "0324": "Magic Trackpad (USB-C)"}
APPLE_ID = re.compile(r"VID(?:_05AC|&000205AC|&0001004C|_0001004C)(?=[&_\\]|$)", re.I)
PRODUCT_ID = re.compile(r"PID[&_](030e|0265|0324)(?=[&_\\]|$)", re.I)

POWERSHELL = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$all = @(Get-PnpDevice -PresentOnly)
$candidates = @($all | Where-Object {
    ($_.InstanceId -match 'VID(_05AC|&000205AC|&0001004C|_0001004C)' -and
     $_.InstanceId -match 'PID[&_](030e|0265|0324)') -or
    $_.FriendlyName -match 'trackpad'
})
$rows = @($candidates | ForEach-Object {
    $d = $_
    $properties = @{}
    Get-PnpDeviceProperty -InstanceId $d.InstanceId -ErrorAction SilentlyContinue |
        ForEach-Object { $properties[$_.KeyName] = $_.Data }
    [pscustomobject]@{
        FriendlyName = $d.FriendlyName
        InstanceId = $d.InstanceId
        Class = $d.Class
        Status = $d.Status
        HardwareIds = @($properties['DEVPKEY_Device_HardwareIds'])
        ContainerId = [string]$properties['DEVPKEY_Device_ContainerId']
        Parent = $properties['DEVPKEY_Device_Parent']
        Service = $properties['DEVPKEY_Device_Service']
        DriverProvider = $properties['DEVPKEY_Device_DriverProvider']
        DriverVersion = $properties['DEVPKEY_Device_DriverVersion']
        DriverInf = $properties['DEVPKEY_Device_DriverInfPath']
        LowerFilters = @($properties['DEVPKEY_Device_LowerFilters'])
        Stack = @($properties['DEVPKEY_Device_Stack'])
    }
})
ConvertTo-Json -InputObject $rows -Depth 5 -Compress
"""


def model_for(device: dict) -> str | None:
    identifiers = [device.get("InstanceId") or "", *(device.get("HardwareIds") or [])]
    for identifier in identifiers:
        if not identifier or not APPLE_ID.search(identifier):
            continue
        match = PRODUCT_ID.search(identifier)
        if match:
            return MODELS[match[1].lower()]
    return None


def has_precision_driver(devices: list[dict]) -> bool:
    for device in devices:
        # Check the service/stack/filter, not the friendly name or provider alone.
        evidence = [device.get("Service"), *(device.get("Stack") or []), *(device.get("LowerFilters") or [])]
        if any("amtptphidfilter" in str(value).lower() for value in evidence):
            return True
    return False


def find_trackpads() -> list[dict]:
    command = base64.b64encode(POWERSHELL.encode("utf-16le")).decode("ascii")
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", command],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Windows device discovery failed.")
    devices = json.loads(result.stdout.lstrip("\ufeff") or "[]")
    if isinstance(devices, dict):
        devices = [devices]
    if not isinstance(devices, list):
        raise RuntimeError("Unexpected Windows device discovery response.")
    for device in devices:
        device["Model"] = model_for(device)
    return devices
