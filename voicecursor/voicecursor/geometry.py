"""Screen-space rectangles, used by the grid navigator."""

from __future__ import annotations

from dataclasses import dataclass


def _split(origin: int, size: int, n: int) -> list[int]:
    """n+1 boundaries splitting [origin, origin+size) into n parts as evenly
    as possible. Rounding (not floor) spreads the leftover pixels across the
    parts instead of dumping them all in the last one, and the first/last
    boundaries land exactly on origin and origin+size."""
    return [origin + round(i * size / n) for i in range(n + 1)]


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    @property
    def center(self) -> tuple[int, int]:
        return self.left + self.width // 2, self.top + self.height // 2

    def subdivide(self, rows: int, cols: int) -> list["Rect"]:
        """Split into rows*cols cells, in reading order (left-to-right,
        top-to-bottom). Cells share exact boundaries: no gaps, no overlap."""
        xs = _split(self.left, self.width, cols)
        ys = _split(self.top, self.height, rows)
        return [
            Rect(xs[c], ys[r], xs[c + 1] - xs[c], ys[r + 1] - ys[r])
            for r in range(rows)
            for c in range(cols)
        ]
