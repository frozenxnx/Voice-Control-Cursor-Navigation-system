"""Screen-size detection, isolated so the grid navigator can be tested
without a real display."""

from __future__ import annotations

import logging
import sys

from .geometry import Rect

log = logging.getLogger(__name__)


def virtual_screen_rect() -> Rect:
    """Bounding box of *all* monitors combined, in physical pixels.

    Requires DPI awareness to already be enabled (see mouse_windows.
    enable_dpi_awareness), or the values are Windows' virtualised, wrong
    coordinates on any scaled display.
    """
    if sys.platform == "win32":
        import ctypes
        user32 = ctypes.windll.user32
        SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
        SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79
        left = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        top = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        width = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        height = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
        if width > 0 and height > 0:
            return Rect(left, top, width, height)
        log.warning("GetSystemMetrics returned an empty virtual screen; using a fallback size")

    try:  # best-effort for development off Windows
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        w, h = root.winfo_screenwidth(), root.winfo_screenheight()
        root.destroy()
        return Rect(0, 0, w, h)
    except Exception:  # noqa: BLE001 - no display available either
        log.warning("Could not detect screen size; defaulting to 1920x1080")
        return Rect(0, 0, 1920, 1080)
