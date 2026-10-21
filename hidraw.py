"""Raw Input access to a Precision Touchpad's multitouch contacts.

The MagicTrackpad2ForWindows driver exposes the trackpad as a Windows
Precision Touchpad top-level collection (usage page 0x0D, usage 0x05), so the
contacts can be read with the Raw Input API and parsed with the HID parsing
library (hid.dll) instead of guessing the report layout.

Only the ctypes standard library is used. Nothing here changes system state:
registering for raw input is additive and never consumes the device.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import time

from gestures import Contact, Frame

WM_INPUT = 0x00FF
RID_INPUT, RID_HEADER = 0x10000003, 0x10000005
RIDI_DEVICEINFO, RIDI_PREPARSEDDATA = 0x2000000B, 0x20000005
RIM_TYPEHID = 2
RIDEV_INPUTSINK = 0x00000100
RIDEV_DEVNOTIFY = 0x00002000
WM_INPUT_DEVICE_CHANGE = 0x00FE
UINT_ERROR = 0xFFFFFFFF
HIDP_STATUS_SUCCESS = 0x00110000
HIDP_INPUT = 0

USAGE_PAGE_GENERIC = 0x01
USAGE_PAGE_DIGITIZER = 0x0D
USAGE_TOUCH_PAD = 0x05
USAGE_X, USAGE_Y = 0x30, 0x31
USAGE_CONTACT_ID = 0x51
USAGE_CONTACT_COUNT = 0x54
USAGE_SCAN_TIME = 0x56
USAGE_TIP_SWITCH = 0x42
USAGE_CONFIDENCE = 0x47
USAGE_PRESSURE = 0x30

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", wintypes.USHORT), ("usUsage", wintypes.USHORT),
                ("dwFlags", wintypes.DWORD), ("hwndTarget", wintypes.HWND)]


class RAWINPUTDEVICELIST(ctypes.Structure):
    _fields_ = [("hDevice", wintypes.HANDLE), ("dwType", wintypes.DWORD)]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [("dwType", wintypes.DWORD), ("dwSize", wintypes.DWORD),
                ("hDevice", wintypes.HANDLE), ("wParam", wintypes.WPARAM)]


class HIDP_CAPS(ctypes.Structure):
    _fields_ = [("Usage", wintypes.USHORT), ("UsagePage", wintypes.USHORT),
                ("InputReportByteLength", wintypes.USHORT), ("OutputReportByteLength", wintypes.USHORT),
                ("FeatureReportByteLength", wintypes.USHORT), ("Reserved", wintypes.USHORT * 17),
                ("NumberLinkCollectionNodes", wintypes.USHORT), ("NumberInputButtonCaps", wintypes.USHORT),
                ("NumberInputValueCaps", wintypes.USHORT), ("NumberInputDataIndices", wintypes.USHORT),
                ("NumberOutputButtonCaps", wintypes.USHORT), ("NumberOutputValueCaps", wintypes.USHORT),
                ("NumberOutputDataIndices", wintypes.USHORT), ("NumberFeatureButtonCaps", wintypes.USHORT),
                ("NumberFeatureValueCaps", wintypes.USHORT), ("NumberFeatureDataIndices", wintypes.USHORT)]


class HIDP_VALUE_CAPS(ctypes.Structure):
    _fields_ = [("UsagePage", wintypes.USHORT), ("ReportID", ctypes.c_ubyte), ("IsAlias", ctypes.c_ubyte),
                ("BitField", wintypes.USHORT), ("LinkCollection", wintypes.USHORT),
                ("LinkUsage", wintypes.USHORT), ("LinkUsagePage", wintypes.USHORT),
                ("IsRange", ctypes.c_ubyte), ("IsStringRange", ctypes.c_ubyte),
                ("IsDesignatorRange", ctypes.c_ubyte), ("IsAbsolute", ctypes.c_ubyte),
                ("HasNull", ctypes.c_ubyte), ("Reserved", ctypes.c_ubyte),
                ("BitSize", wintypes.USHORT), ("ReportCount", wintypes.USHORT),
                ("Reserved2", wintypes.USHORT * 5), ("UnitsExp", wintypes.ULONG), ("Units", wintypes.ULONG),
                ("LogicalMin", wintypes.LONG), ("LogicalMax", wintypes.LONG),
                ("PhysicalMin", wintypes.LONG), ("PhysicalMax", wintypes.LONG),
                ("Range", wintypes.USHORT * 8)]


user32 = ctypes.WinDLL("user32", use_last_error=True)
hid = ctypes.WinDLL("hid", use_last_error=True)
for function, argtypes, restype in (
    (user32.RegisterRawInputDevices, [ctypes.POINTER(RAWINPUTDEVICE), wintypes.UINT, wintypes.UINT], wintypes.BOOL),
    (user32.GetRawInputData, [wintypes.HANDLE, wintypes.UINT, ctypes.c_void_p, ctypes.POINTER(wintypes.UINT), wintypes.UINT], wintypes.UINT),
    (user32.GetRawInputDeviceList, [ctypes.POINTER(RAWINPUTDEVICELIST), ctypes.POINTER(wintypes.UINT), wintypes.UINT], wintypes.UINT),
    (user32.GetRawInputDeviceInfoW, [wintypes.HANDLE, wintypes.UINT, ctypes.c_void_p, ctypes.POINTER(wintypes.UINT)], wintypes.UINT),
    (hid.HidP_GetCaps, [ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS)], ctypes.c_long),
    (hid.HidP_GetValueCaps, [ctypes.c_int, ctypes.POINTER(HIDP_VALUE_CAPS), ctypes.POINTER(wintypes.USHORT), ctypes.c_void_p], ctypes.c_long),
    (hid.HidP_GetUsageValue, [ctypes.c_int, wintypes.USHORT, wintypes.USHORT, wintypes.USHORT, ctypes.POINTER(wintypes.ULONG), ctypes.c_void_p, ctypes.c_char_p, wintypes.ULONG], ctypes.c_long),
    (hid.HidP_GetUsages, [ctypes.c_int, wintypes.USHORT, wintypes.USHORT, ctypes.POINTER(wintypes.USHORT), ctypes.POINTER(wintypes.ULONG), ctypes.c_void_p, ctypes.c_char_p, wintypes.ULONG], ctypes.c_long),
):
    function.argtypes, function.restype = argtypes, restype


class TouchpadParser:
    """Turns raw HID reports into contacts, using the device's own descriptors."""

    def __init__(self, preparsed, report_id: int | None = None) -> None:
        # Own the ctypes buffer, not just its address. HID parser pointers must
        # stay valid for the lifetime of this parser (including after GC).
        self.preparsed = preparsed
        self.report_id = report_id
        self.links: list[int] = []
        self.axes = {}
        self.last_scan = None
        self._read_value_caps()

    def _read_value_caps(self) -> None:
        caps = HIDP_CAPS()
        if hid.HidP_GetCaps(self.preparsed, ctypes.byref(caps)) != HIDP_STATUS_SUCCESS:
            raise OSError("HidP_GetCaps failed for the touchpad.")
        self.report_length = caps.InputReportByteLength
        length = wintypes.USHORT(caps.NumberInputValueCaps)
        if not length.value:
            raise ValueError("Touchpad has no input value capabilities.")
        value_caps = (HIDP_VALUE_CAPS * length.value)()
        if hid.HidP_GetValueCaps(HIDP_INPUT, value_caps, ctypes.byref(length), self.preparsed) != HIDP_STATUS_SUCCESS:
            raise OSError("HidP_GetValueCaps failed.")
        links: set[int] = set()
        reports = {item.ReportID for item in value_caps[:length.value]
                   if item.UsagePage == USAGE_PAGE_DIGITIZER and item.Range[0] == USAGE_CONTACT_COUNT}
        if self.report_id is None:
            if len(reports) != 1:
                raise ValueError("Ambiguous contact report ID.")
            self.report_id = reports.pop()
        for item in value_caps[:length.value]:
            if item.ReportID != self.report_id:
                continue
            usages = range(item.Range[0], item.Range[1]+1) if item.IsRange else [item.Range[0]]
            for usage in usages:
                if item.UsagePage == USAGE_PAGE_DIGITIZER and usage == USAGE_CONTACT_ID:
                    links.add(item.LinkCollection)
                if item.UsagePage == USAGE_PAGE_GENERIC and usage in (USAGE_X, USAGE_Y):
                    self.axes[(item.LinkCollection, usage)] = (item.LogicalMin, item.LogicalMax, item.BitSize)
        # Link collection 0 holds device-level values; contacts live in 1..N.
        self.links = sorted(links)
        for link in self.links:
            for usage in (USAGE_X, USAGE_Y):
                low, high, _ = self.axes[(link, usage)]
                if high <= low:
                    raise ValueError("Invalid coordinate range.")

    def _value(self, report: bytes, page: int, link: int, usage: int) -> int | None:
        value = wintypes.ULONG(0)
        status = hid.HidP_GetUsageValue(HIDP_INPUT, page, link, usage, ctypes.byref(value),
                                        self.preparsed, report, len(report))
        if status != HIDP_STATUS_SUCCESS:
            return None
        return value.value

    def _usages(self, report: bytes, link: int, page=USAGE_PAGE_DIGITIZER) -> set[int]:
        usages = (wintypes.USHORT * 32)()
        length = wintypes.ULONG(len(usages))
        status = hid.HidP_GetUsages(HIDP_INPUT, page, link, usages, ctypes.byref(length),
                                    self.preparsed, report, len(report))
        if status != HIDP_STATUS_SUCCESS:
            raise ValueError(f"HidP_GetUsages failed: {status & UINT_ERROR:#x}")
        return set(usages[:length.value])

    def _coordinate(self, raw: int, link: int, usage: int) -> float:
        low, high, bits = self.axes[(link, usage)]
        if low < 0 and raw & (1 << (bits-1)):
            raw -= 1 << bits
        if not low <= raw <= high:
            raise ValueError("Contact coordinate outside descriptor range.")
        return (raw-low) / (high-low)

    def parse(self, report: bytes, now=None, device=0) -> Frame | None:
        """None means irrelevant/duplicate; an empty Frame is a real lift.

        This driver reports a complete parallel frame. Incomplete/hybrid
        reports are rejected rather than misinterpreted as finger lifts.
        """
        if not report or report[0] != self.report_id:
            return None
        if len(report) != self.report_length:
            raise ValueError("Truncated or oversized HID report.")
        count = self._value(report, USAGE_PAGE_DIGITIZER, 0, USAGE_CONTACT_COUNT)
        scan = self._value(report, USAGE_PAGE_DIGITIZER, 0, USAGE_SCAN_TIME)
        if count is None or scan is None or count > len(self.links):
            raise ValueError("Missing/incomplete contact frame.")
        if scan == self.last_scan:
            return None
        contacts: list[Contact] = []
        for link in self.links:
            pressed = self._usages(report, link)
            if USAGE_TIP_SWITCH not in pressed:
                continue
            contact_id = self._value(report, USAGE_PAGE_DIGITIZER, link, USAGE_CONTACT_ID)
            x = self._value(report, USAGE_PAGE_GENERIC, link, USAGE_X)
            y = self._value(report, USAGE_PAGE_GENERIC, link, USAGE_Y)
            if contact_id is None or x is None or y is None:
                raise ValueError("Missing contact values.")
            contacts.append(Contact(
                id=contact_id,
                x=self._coordinate(x, link, USAGE_X),
                y=self._coordinate(y, link, USAGE_Y),
                tip=True,
                confidence=USAGE_CONFIDENCE in pressed,
            ))
        if len(contacts) > count or len({c.id for c in contacts}) != len(contacts):
            raise ValueError("Inconsistent contact count/identifiers.")
        self.last_scan = scan
        return Frame(time.monotonic() if now is None else now, tuple(sorted(contacts, key=lambda c: c.id)),
                     device, scan, 1 in self._usages(report, 0, 9))

    def contact_count(self, report: bytes) -> int | None:
        return self._value(report, USAGE_PAGE_DIGITIZER, 0, USAGE_CONTACT_COUNT)


def _preparsed_for(handle: int):
    """Return the preparsed data pointer for a raw input device.

    The buffer is kept alive by the caller so the pointer stays valid.
    """
    size = wintypes.UINT(0)
    if user32.GetRawInputDeviceInfoW(handle, RIDI_PREPARSEDDATA, None, ctypes.byref(size)) == UINT_ERROR:
        raise ctypes.WinError(ctypes.get_last_error())
    if not 0 < size.value <= 1024 * 1024:
        raise ValueError("Invalid preparsed-data size.")
    buffer = ctypes.create_string_buffer(size.value)
    if user32.GetRawInputDeviceInfoW(handle, RIDI_PREPARSEDDATA, buffer, ctypes.byref(size)) == UINT_ERROR:
        raise ctypes.WinError(ctypes.get_last_error())
    return buffer


def list_touchpads() -> list[dict]:
    """Return the raw input devices that expose a touch pad top-level collection."""
    count = wintypes.UINT(0)
    if user32.GetRawInputDeviceList(None, ctypes.byref(count), ctypes.sizeof(RAWINPUTDEVICELIST)) == UINT_ERROR:
        raise ctypes.WinError(ctypes.get_last_error())
    if not count.value:
        return []
    devices = (RAWINPUTDEVICELIST * count.value)()
    received = user32.GetRawInputDeviceList(devices, ctypes.byref(count), ctypes.sizeof(RAWINPUTDEVICELIST))
    if received == UINT_ERROR:
        raise ctypes.WinError(ctypes.get_last_error())
    found: list[dict] = []
    for index in range(received):
        handle = devices[index].hDevice
        size = wintypes.UINT(32)
        buffer = ctypes.create_string_buffer(32)
        ctypes.memmove(buffer, (32).to_bytes(4, "little"), 4)
        if user32.GetRawInputDeviceInfoW(handle, RIDI_DEVICEINFO, buffer, ctypes.byref(size)) == UINT_ERROR:
            continue
        raw = bytes(buffer.raw)
        if int.from_bytes(raw[4:8], "little") != RIM_TYPEHID:
            continue
        usage_page = int.from_bytes(raw[20:22], "little")
        usage = int.from_bytes(raw[22:24], "little")
        if usage_page != USAGE_PAGE_DIGITIZER or usage != USAGE_TOUCH_PAD:
            continue
        # The upstream PTP filter uses synthetic VID 8910. Also require the
        # Apple hardware path so another vendor's PID cannot select a device.
        name_size = wintypes.UINT(0)
        user32.GetRawInputDeviceInfoW(handle, 0x20000007, None, ctypes.byref(name_size))
        if not 0 < name_size.value < 32768:
            continue
        name = ctypes.create_unicode_buffer(name_size.value + 1)
        if user32.GetRawInputDeviceInfoW(handle, 0x20000007, name, ctypes.byref(name_size)) == UINT_ERROR:
            continue
        path = name.value.lower()
        if not ("vid&0001004c_pid&0324" in path or "vid_05ac&pid_0324" in path):
            continue
        found.append({
            "handle": handle,
            "vendor_id": int.from_bytes(raw[8:12], "little"),
            "product_id": int.from_bytes(raw[12:16], "little"),
            "path": name.value,
        })
    return found


class RawInputMonitor:
    """Receives touchpad reports for a window and hands back parsed contacts."""

    def __init__(self, window: int) -> None:
        self.window = window
        self.parsers: dict[int, TouchpadParser] = {}
        self.errors = 0
        self.last_error = None
        self.reports = 0
        self.registered = False

    def rediscover(self) -> None:
        """Refresh parsers after a device arrives or leaves."""
        self._discover()

    def _discover(self) -> None:
        devices = list_touchpads()
        handles = {device["handle"] for device in devices}
        self.parsers = {h: p for h, p in self.parsers.items() if h in handles}
        for device in devices:
            handle = device["handle"]
            if handle in self.parsers:
                continue
            try:
                parser = TouchpadParser(_preparsed_for(handle))
            except (OSError, ValueError, KeyError) as error:
                self.last_error = str(error)
                continue
            if parser.links:
                self.parsers[handle] = parser

    def register(self) -> bool:
        registration = RAWINPUTDEVICE(USAGE_PAGE_DIGITIZER, USAGE_TOUCH_PAD, RIDEV_INPUTSINK | RIDEV_DEVNOTIFY, self.window)
        if not user32.RegisterRawInputDevices(ctypes.byref(registration), 1, ctypes.sizeof(RAWINPUTDEVICE)):
            return False
        self._discover()
        self.registered = True
        return True

    def close(self):
        if self.registered:
            registration = RAWINPUTDEVICE(USAGE_PAGE_DIGITIZER, USAGE_TOUCH_PAD, 1, None)
            user32.RegisterRawInputDevices(ctypes.byref(registration), 1, ctypes.sizeof(RAWINPUTDEVICE))
            self.registered = False
        self.parsers.clear()

    def read(self, message_param: int) -> list[Frame]:
        """Return every frame, including lifts; failures never swallow WM_INPUT."""
        try:
            return self._read(message_param)
        except (OSError, ValueError, KeyError) as error:
            self.errors += 1
            self.last_error = str(error)
            return []

    def _read(self, message_param: int) -> list[Frame]:
        size = wintypes.UINT(0)
        header_size = ctypes.sizeof(RAWINPUTHEADER)
        if user32.GetRawInputData(message_param, RID_INPUT, None, ctypes.byref(size), header_size) == UINT_ERROR:
            raise ctypes.WinError(ctypes.get_last_error())
        if not header_size + 8 <= size.value <= 1024*1024:
            raise ValueError("Invalid RAWINPUT size.")
        buffer = ctypes.create_string_buffer(size.value)
        if user32.GetRawInputData(message_param, RID_INPUT, buffer, ctypes.byref(size), header_size) == UINT_ERROR:
            raise ctypes.WinError(ctypes.get_last_error())
        raw = bytes(buffer.raw[:size.value])
        header = RAWINPUTHEADER.from_buffer_copy(raw)
        if header.dwType != RIM_TYPEHID:
            return []
        handle = header.hDevice
        parser = self.parsers.get(handle)
        if parser is None:
            return []
        size_hid = int.from_bytes(raw[header_size:header_size+4], "little")
        count = int.from_bytes(raw[header_size+4:header_size+8], "little")
        if not size_hid or count * size_hid > len(raw)-header_size-8:
            raise ValueError("Invalid RAWHID batch length.")
        frames = []
        for index in range(count):
            start = header_size + 8 + index * size_hid
            report = raw[start:start + size_hid]
            frame = parser.parse(report, device=handle)
            self.reports += 1
            if frame is not None:
                frames.append(frame)
        return frames
