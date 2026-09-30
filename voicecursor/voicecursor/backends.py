"""Mouse backend interface plus a dry-run implementation for development."""

from __future__ import annotations

import logging
from typing import Protocol

log = logging.getLogger(__name__)


class MouseBackend(Protocol):
    def move_rel(self, dx: int, dy: int) -> None: ...
    def move_to(self, x: int, y: int) -> None:
        """Move to an absolute screen position (physical pixels)."""
        ...
    def click(self, button: str = "left", count: int = 1) -> None: ...
    def button_down(self, button: str = "left") -> None: ...
    def button_up(self, button: str = "left") -> None: ...
    def scroll(self, vertical: int = 0, horizontal: int = 0) -> None:
        """Positive vertical = up, positive horizontal = right (in wheel notches)."""
        ...


class DryRunMouse:
    """Records calls and tracks a virtual cursor position. No side effects."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.x = 0
        self.y = 0

    @property
    def position(self) -> tuple[int, int]:
        return self.x, self.y

    def move_rel(self, dx: int, dy: int) -> None:
        self.x += dx
        self.y += dy
        self.calls.append(("move_rel", dx, dy))
        log.debug("move_rel(%d, %d) -> %s", dx, dy, self.position)

    def move_to(self, x: int, y: int) -> None:
        self.x, self.y = x, y
        self.calls.append(("move_to", x, y))
        log.debug("move_to(%d, %d)", x, y)

    def click(self, button: str = "left", count: int = 1) -> None:
        self.calls.append(("click", button, count))
        log.debug("click(%s x%d)", button, count)

    def button_down(self, button: str = "left") -> None:
        self.calls.append(("button_down", button))
        log.debug("button_down(%s)", button)

    def button_up(self, button: str = "left") -> None:
        self.calls.append(("button_up", button))
        log.debug("button_up(%s)", button)

    def scroll(self, vertical: int = 0, horizontal: int = 0) -> None:
        self.calls.append(("scroll", vertical, horizontal))
        log.debug("scroll(v=%d, h=%d)", vertical, horizontal)
