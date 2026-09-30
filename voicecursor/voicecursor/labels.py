"""Numbering and selecting clickable elements ("show numbers" -> "click fourteen").

Pure Python, no platform dependency - element discovery itself lives in
elements.py (Windows-only); this module just assigns numbers and looks
selections back up, so it's fully unit-testable with fabricated elements.
"""

from __future__ import annotations

from dataclasses import dataclass

from .elements import ElementInfo
from .geometry import Rect


@dataclass(frozen=True)
class Labeled:
    """One numbered, clickable element, ready for the overlay to draw and
    the controller to click."""

    label: int
    name: str
    rect: Rect


def _nearly_equal(a: Rect, b: Rect, tol: int = 4) -> bool:
    """True if two rects are the same clickable spot for practical purposes.
    A tolerance rather than exact equality, since duplicates from UI
    Automation (an icon vs. its wrapping button, say) are sometimes off by a
    pixel or two rather than pixel-identical."""
    return (abs(a.left - b.left) <= tol and abs(a.top - b.top) <= tol and
            abs(a.width - b.width) <= tol and abs(a.height - b.height) <= tol)


def _dedupe(elements: list[ElementInfo]) -> list[ElementInfo]:
    """Drop near-duplicate bounding boxes.

    A common UI Automation artefact: an icon and its wrapping button (or a
    button and a redundant automation peer) often report almost identical
    rects, which shows up as two numbered badges stacked on top of each
    other. When a duplicate is found, the copy with a non-empty accessible
    name wins, since that's the more useful one to click and to display.
    Keeps first-seen order otherwise, so numbering stays stable.
    """
    kept: list[ElementInfo] = []
    for el in elements:
        dup = next((i for i, k in enumerate(kept) if _nearly_equal(el.rect, k.rect)), None)
        if dup is None:
            kept.append(el)
        elif not kept[dup].name and el.name:
            kept[dup] = el  # prefer the named copy, keep its original slot
    return kept


def assign_labels(elements: list[ElementInfo]) -> list[Labeled]:
    """Number elements in reading order (top-to-bottom, then left-to-right),
    starting at 1, after removing near-duplicate bounding boxes. Reading
    order - rather than, say, tree order - is what makes the numbers
    predictable to a person looking at the screen."""
    deduped = _dedupe(elements)
    ordered = sorted(deduped, key=lambda e: (e.rect.top, e.rect.left))
    return [Labeled(i, e.name, e.rect) for i, e in enumerate(ordered, start=1)]


class LabelSelector:
    """Holds one label session: the numbered elements currently on screen."""

    def __init__(self, elements: list[Labeled]) -> None:
        self._by_label = {e.label: e for e in elements}

    @property
    def items(self) -> list[Labeled]:
        return sorted(self._by_label.values(), key=lambda e: e.label)

    def get(self, n: int) -> Labeled | None:
        return self._by_label.get(n)
