"""GPL-2.0-or-later. Read the word under a screen point with UI Automation.

Look up uses this instead of double-click + Ctrl+C: nothing is clicked or
typed, the clipboard is untouched, and password fields are skipped. Apps that
expose no UI Automation text (some terminals, games, images) return None.
Raw COM through ctypes; vtable indices follow UIAutomationClient.h.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import uuid

CLSID_CUIAUTOMATION = "ff48dba4-60ef-4201-aa87-54103eef594e"
IID_IUIAUTOMATION = "30cbe57d-d9d0-452a-ab13-7ac5ac4825ee"
IID_TEXT_PATTERN = "32eba289-3583-42c9-9c59-3b6d9a1e9b6a"
TEXT_PATTERN_ID = 10014
IS_PASSWORD_PROPERTY_ID = 30019
TEXT_UNIT_WORD = 2  # TextUnit_Character=0, Format=1, Word=2, Line=3
VT_BOOL = 11
MAX_ANCESTORS = 6

# Vtable slots (IUnknown takes 0-2).
AUTOMATION_ELEMENT_FROM_POINT, AUTOMATION_CONTROL_VIEW_WALKER = 7, 14
ELEMENT_GET_PROPERTY, ELEMENT_GET_PATTERN_AS = 10, 14
WALKER_GET_PARENT = 3
PATTERN_RANGE_FROM_POINT = 3
RANGE_EXPAND, RANGE_BOUNDING_RECTANGLES, RANGE_GET_TEXT = 6, 10, 12


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]


class VARIANT(ctypes.Structure):
    _fields_ = [("vt", wintypes.USHORT), ("reserved", wintypes.USHORT * 3), ("value", ctypes.c_ulonglong),
                ("extra", ctypes.c_ulonglong)]


ole32 = ctypes.WinDLL("ole32", use_last_error=True)
oleaut32 = ctypes.WinDLL("oleaut32", use_last_error=True)
for function, argtypes, restype in (
    (ole32.CoInitializeEx, [ctypes.c_void_p, wintypes.DWORD], ctypes.c_long),
    (ole32.CoUninitialize, [], None),
    (ole32.CoCreateInstance, [ctypes.POINTER(GUID), ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)], ctypes.HRESULT),
    (oleaut32.SysFreeString, [ctypes.c_void_p], None),
    (oleaut32.VariantClear, [ctypes.POINTER(VARIANT)], ctypes.HRESULT),
    (oleaut32.SafeArrayGetUBound, [ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(wintypes.LONG)], ctypes.HRESULT),
    (oleaut32.SafeArrayAccessData, [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)], ctypes.HRESULT),
    (oleaut32.SafeArrayUnaccessData, [ctypes.c_void_p], ctypes.HRESULT),
    (oleaut32.SafeArrayDestroy, [ctypes.c_void_p], ctypes.HRESULT),
):
    function.argtypes, function.restype = argtypes, restype


def _guid(text: str) -> GUID:
    return GUID.from_buffer_copy(uuid.UUID(text).bytes_le)


def _call(interface: ctypes.c_void_p, slot: int, argtypes: list, *args) -> None:
    """Call a COM method; ctypes.HRESULT raises OSError on failure."""
    vtable = ctypes.cast(interface, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, *argtypes)(vtable[slot])(interface, *args)


def _release(interface: ctypes.c_void_p) -> None:
    if interface and interface.value:
        vtable = ctypes.cast(interface, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)(vtable[2])(interface)


def _is_password(element: ctypes.c_void_p) -> bool:
    value = VARIANT()
    _call(element, ELEMENT_GET_PROPERTY, [ctypes.c_int, ctypes.POINTER(VARIANT)], IS_PASSWORD_PROPERTY_ID, ctypes.byref(value))
    try:
        return value.vt == VT_BOOL and value.value & 0xFFFF != 0
    finally:
        oleaut32.VariantClear(ctypes.byref(value))


def _covers(text_range: ctypes.c_void_p, x: int, y: int) -> bool:
    """True when one of the word's bounding rectangles contains the point."""
    array = ctypes.c_void_p()
    _call(text_range, RANGE_BOUNDING_RECTANGLES, [ctypes.POINTER(ctypes.c_void_p)], ctypes.byref(array))
    if not array.value:
        return False
    try:
        upper, data = wintypes.LONG(), ctypes.c_void_p()
        oleaut32.SafeArrayGetUBound(array, 1, ctypes.byref(upper))
        oleaut32.SafeArrayAccessData(array, ctypes.byref(data))
        try:
            values = ctypes.cast(data, ctypes.POINTER(ctypes.c_double))
            for index in range(0, upper.value + 1 - 3, 4):  # left, top, width, height
                left, top, width, height = (values[index + offset] for offset in range(4))
                if left - 2 <= x <= left + width + 2 and top - 2 <= y <= top + height + 2:
                    return True
            return False
        finally:
            oleaut32.SafeArrayUnaccessData(array)
    finally:
        oleaut32.SafeArrayDestroy(array)


def clean_word(text: str | None) -> str | None:
    """Trim spacing and punctuation; reject empty, multi-line or overlong results."""
    if not text:
        return None
    word = text.strip().strip(".,;:!?\"'()[]{}<>«»“”‘’").strip()
    if not word or len(word) > 64 or any(character in word for character in "\r\n\t"):
        return None
    return word if any(character.isalnum() for character in word) else None


def word_at(x: int, y: int) -> str | None:
    """The word under screen point (x, y), or None. Sends no input."""
    initialized = ole32.CoInitializeEx(None, 0x2) >= 0  # apartment-threaded; S_FALSE also needs CoUninitialize
    automation, walker, element, pattern, text_range = (ctypes.c_void_p() for _ in range(5))
    try:
        ole32.CoCreateInstance(ctypes.byref(_guid(CLSID_CUIAUTOMATION)), None, 1,  # CLSCTX_INPROC_SERVER
                               ctypes.byref(_guid(IID_IUIAUTOMATION)), ctypes.byref(automation))
        _call(automation, AUTOMATION_ELEMENT_FROM_POINT, [wintypes.POINT, ctypes.POINTER(ctypes.c_void_p)],
              wintypes.POINT(x, y), ctypes.byref(element))
        _call(automation, AUTOMATION_CONTROL_VIEW_WALKER, [ctypes.POINTER(ctypes.c_void_p)], ctypes.byref(walker))
        text_iid = _guid(IID_TEXT_PATTERN)
        for _ in range(MAX_ANCESTORS):
            if not element.value or _is_password(element):
                return None
            _call(element, ELEMENT_GET_PATTERN_AS, [ctypes.c_int, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)],
                  TEXT_PATTERN_ID, ctypes.byref(text_iid), ctypes.byref(pattern))
            if pattern.value:
                break
            parent = ctypes.c_void_p()
            _call(walker, WALKER_GET_PARENT, [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)], element, ctypes.byref(parent))
            _release(element)
            element = parent
        if not pattern.value:
            return None
        _call(pattern, PATTERN_RANGE_FROM_POINT, [wintypes.POINT, ctypes.POINTER(ctypes.c_void_p)],
              wintypes.POINT(x, y), ctypes.byref(text_range))
        _call(text_range, RANGE_EXPAND, [ctypes.c_int], TEXT_UNIT_WORD)
        if not _covers(text_range, x, y):
            return None  # blank area: RangeFromPoint snaps to the nearest text
        text = ctypes.c_void_p()
        _call(text_range, RANGE_GET_TEXT, [ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)], 80, ctypes.byref(text))
        try:
            return clean_word(ctypes.wstring_at(text.value) if text.value else None)
        finally:
            oleaut32.SysFreeString(text)
    except OSError:
        return None  # the app does not expose text here, or it went away
    finally:
        for interface in (text_range, pattern, element, walker, automation):
            _release(interface)
        if initialized:
            ole32.CoUninitialize()
