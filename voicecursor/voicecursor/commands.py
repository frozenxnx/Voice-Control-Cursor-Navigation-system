"""Domain types shared by the parser, controller and recognizer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Mode(Enum):
    SLEEPING = "sleeping"  # only the wake phrase is recognised
    COMMAND = "command"    # full command grammar
    GRID = "grid"          # only digits 1-9, click, back, cancel
    LABELS = "labels"      # only numbers, cancel, refresh


class Direction(Enum):
    LEFT = "left"
    RIGHT = "right"
    UP = "up"
    DOWN = "down"

    @property
    def vector(self) -> tuple[int, int]:
        """Unit vector in screen coordinates (y grows downward)."""
        return _VECTORS[self]


_VECTORS = {
    Direction.LEFT: (-1, 0),
    Direction.RIGHT: (1, 0),
    Direction.UP: (0, -1),
    Direction.DOWN: (0, 1),
}


class Action(Enum):
    MOVE = "move"
    GLIDE = "glide"
    STOP = "stop"
    CLICK = "click"
    DOUBLE_CLICK = "double click"
    RIGHT_CLICK = "right click"
    MIDDLE_CLICK = "middle click"
    HOLD = "hold"
    RELEASE = "release"
    SCROLL = "scroll"
    SLEEP = "sleep"
    WAKE = "wake"
    QUIT = "quit"
    GRID_ENTER = "grid"
    GRID_SELECT = "select"
    GRID_BACK = "back"
    GRID_CANCEL = "cancel"
    GRID_CLICK = "grid click"
    LABELS_ENTER = "labels"
    LABELS_SELECT = "select label"
    LABELS_CANCEL = "labels cancel"
    LABELS_REFRESH = "refresh"


@dataclass(frozen=True)
class Command:
    """A parsed voice command. `amount` is None when the user didn't say one;
    the controller substitutes a configured default."""

    action: Action
    direction: Direction | None = None
    amount: int | None = None

    def describe(self) -> str:
        parts = [self.action.value]
        if self.direction is not None:
            parts.append(self.direction.value)
        if self.amount is not None:
            parts.append(str(self.amount))
        return " ".join(parts)
