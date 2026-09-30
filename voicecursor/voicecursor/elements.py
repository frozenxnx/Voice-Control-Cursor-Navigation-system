"""UI Automation element discovery (Windows only).

Kept separate from labels.py so the reading-order/labelling logic stays
pure Python and testable without Windows or the `uiautomation` package.
Nothing in this module is imported at package-load time by anything else -
it's only reached from Controller._labels_enter(), so the rest of the app
works fine even if `uiautomation` isn't installed (e.g. in tests, or on a
platform other than Windows).
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass

from .geometry import Rect

log = logging.getLogger(__name__)

# Control types worth labelling: things a person would plausibly want to
# click or type into. Anything else (plain text, panes, images...) is noise
# that would clutter the overlay and isn't actionable anyway.
_INTERACTIVE_TYPES = {
    "ButtonControl", "HyperlinkControl", "CheckBoxControl", "RadioButtonControl",
    "ComboBoxControl", "EditControl", "ListItemControl", "MenuItemControl",
    "TabItemControl", "TreeItemControl", "SliderControl", "SplitButtonControl",
}


@dataclass(frozen=True)
class ElementInfo:
    """One clickable thing found on screen. Platform-independent shape, so
    tests can construct these directly without touching real UI Automation."""

    name: str
    control_type: str
    rect: Rect


def find_actionable_elements(max_elements: int = 60, max_depth: int = 8) -> list[ElementInfo]:
    """Walk the foreground window's UI Automation tree and return the
    visible, enabled, interactive controls in it.

    Scoped to just the foreground window (not the whole desktop) and capped
    in both depth and count, because walking a full UIA tree is slow -
    an unscoped walk can take seconds on a complex app and make the overlay
    feel broken rather than instant.
    """
    if sys.platform != "win32":
        raise RuntimeError("find_actionable_elements is only available on Windows")
    try:
        import uiautomation as auto
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise RuntimeError(
            "the 'uiautomation' package is not installed: pip install uiautomation") from exc

    root = auto.GetForegroundControl()
    if root is None:
        log.warning("no foreground window found")
        return []

    found: list[ElementInfo] = []

    def walk(control, depth: int) -> None:
        if len(found) >= max_elements or depth > max_depth:
            return
        try:
            children = control.GetChildren()
        except Exception:  # noqa: BLE001 - a single bad control shouldn't abort the scan
            log.debug("failed to enumerate children of a control", exc_info=True)
            return
        for child in children:
            if len(found) >= max_elements:
                return
            _maybe_add(child, found)
            walk(child, depth + 1)

    _maybe_add(root, found)
    walk(root, 0)
    return found


def _maybe_add(control, found: list[ElementInfo]) -> None:
    try:
        if control.ControlTypeName not in _INTERACTIVE_TYPES:
            return
        if not control.IsEnabled:
            return
        b = control.BoundingRectangle  # (left, top, right, bottom); empty if offscreen/hidden
        width, height = b.right - b.left, b.bottom - b.top
        if width <= 0 or height <= 0:
            return
        found.append(ElementInfo(
            name=(control.Name or "").strip(),
            control_type=control.ControlTypeName,
            rect=Rect(b.left, b.top, width, height)))
    except Exception:  # noqa: BLE001 - a single bad control shouldn't abort the scan
        log.debug("failed to inspect a control", exc_info=True)
