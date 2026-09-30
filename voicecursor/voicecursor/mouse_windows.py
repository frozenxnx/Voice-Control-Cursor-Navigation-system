"""Windows mouse backend (ctypes; no third-party dependencies).

Design notes
------------
* Cursor *movement* uses GetCursorPos/SetCursorPos rather than relative
  SendInput(MOUSEEVENTF_MOVE). Relative moves are subject to "Enhance pointer
  precision" acceleration, so "move left 200" would not be 200 pixels.
* Clicks and wheel events go through SendInput, batched into a single call so
  a double-click's down/up pairs arrive back-to-back.
* The process is made DPI-aware *before* any coordinates are read; otherwise
  positions are virtualised and wrong on scaled displays.
* UIPI: input cannot be injected into windows running elevated unless this
  process is elevated too. Windows does not report that failure reliably.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes

log = logging.getLogger(__name__)

INPUT_MOUSE = 0
_DOWN = {"left": 0x0002, "right": 0x0008, "middle": 0x0020}  # MOUSEEVENTF_*DOWN
_UP = {"left": 0x0004, "right": 0x0010, "middle": 0x0040}    # MOUSEEVENTF_*UP
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
WHEEL_DELTA = 120

ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):  # unused for now; keeps the union's size right
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUT_UNION)]


def _mouse_event(flags: int, data: int = 0) -> INPUT:
    inp = INPUT(type=INPUT_MOUSE)
    inp.mi = MOUSEINPUT(0, 0, data & 0xFFFFFFFF, flags, 0, 0)  # mask: wheel deltas are signed
    return inp


def enable_dpi_awareness() -> None:
    """Per-monitor DPI awareness; falls back to system-wide on old Windows."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            log.warning("Could not enable DPI awareness; coordinates may be off on scaled displays")


class WindowsMouse:
    def __init__(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("WindowsMouse is only available on Windows")
        enable_dpi_awareness()
        u = ctypes.WinDLL("user32", use_last_error=True)
        u.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
        u.SendInput.restype = wintypes.UINT
        u.GetCursorPos.argtypes = (ctypes.POINTER(wintypes.POINT),)
        u.GetCursorPos.restype = wintypes.BOOL
        u.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
        u.SetCursorPos.restype = wintypes.BOOL
        self._user32 = u

    # -- MouseBackend interface ------------------------------------------
    def move_rel(self, dx: int, dy: int) -> None:
        pt = wintypes.POINT()
        if not self._user32.GetCursorPos(ctypes.byref(pt)):
            raise ctypes.WinError(ctypes.get_last_error())
        self._user32.SetCursorPos(pt.x + dx, pt.y + dy)

    def move_to(self, x: int, y: int) -> None:
        if not self._user32.SetCursorPos(x, y):
            raise ctypes.WinError(ctypes.get_last_error())

    def click(self, button: str = "left", count: int = 1) -> None:
        events: list[INPUT] = []
        for _ in range(count):
            events.append(_mouse_event(_DOWN[button]))
            events.append(_mouse_event(_UP[button]))
        self._send(events)

    def button_down(self, button: str = "left") -> None:
        self._send([_mouse_event(_DOWN[button])])

    def button_up(self, button: str = "left") -> None:
        self._send([_mouse_event(_UP[button])])

    def scroll(self, vertical: int = 0, horizontal: int = 0) -> None:
        events = []
        if vertical:
            events.append(_mouse_event(MOUSEEVENTF_WHEEL, vertical * WHEEL_DELTA))
        if horizontal:
            events.append(_mouse_event(MOUSEEVENTF_HWHEEL, horizontal * WHEEL_DELTA))
        self._send(events)

    # -- internals ---------------------------------------------------------
    def _send(self, events: list[INPUT]) -> None:
        if not events:
            return
        array = (INPUT * len(events))(*events)
        sent = self._user32.SendInput(len(events), array, ctypes.sizeof(INPUT))
        if sent != len(events):
            log.warning(
                "SendInput injected %d of %d events (blocked by UIPI? "
                "Try running this process as administrator.)", sent, len(events))
