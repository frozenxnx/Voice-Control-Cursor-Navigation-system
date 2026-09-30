"""Recursive numbered-grid cursor navigation ("grid" -> "five" -> "click")."""

from __future__ import annotations

from .geometry import Rect


class GridSelector:
    """Tracks the zoom history for one grid session.

    `current` starts as the full bounds and shrinks by one cell each time
    `select` is called; `back` undoes the most recent selection. Cells are
    numbered 1..rows*cols in reading order (left-to-right, top-to-bottom).
    """

    def __init__(self, bounds: Rect, rows: int = 3, cols: int = 3) -> None:
        if rows < 1 or cols < 1:
            raise ValueError("rows and cols must be positive")
        self.rows = rows
        self.cols = cols
        self._history: list[Rect] = [bounds]

    @property
    def current(self) -> Rect:
        return self._history[-1]

    @property
    def depth(self) -> int:
        """Number of selections made so far (0 = still at the full bounds)."""
        return len(self._history) - 1

    @property
    def cells(self) -> list[Rect]:
        return self.current.subdivide(self.rows, self.cols)

    def select(self, n: int) -> Rect:
        """Zoom into cell `n` (1-based, reading order). Returns the new
        current rect."""
        count = self.rows * self.cols
        if not 1 <= n <= count:
            raise ValueError(f"cell number must be between 1 and {count}, got {n}")
        self._history.append(self.cells[n - 1])
        return self.current

    def back(self) -> bool:
        """Undo the most recent selection. Returns False (and does nothing)
        if already at the root, so the caller can decide to exit instead."""
        if self.depth == 0:
            return False
        self._history.pop()
        return True
