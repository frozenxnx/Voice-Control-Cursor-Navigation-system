"""Command router and mode state machine."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

from .backends import MouseBackend
from .commands import Action, Command, Mode
from .config import Config
from .elements import ElementInfo
from .geometry import Rect
from .glide import Glider
from .grid import GridSelector
from .labels import LabelSelector, Labeled, assign_labels
from .parser import parse, parse_grid, parse_labels

log = logging.getLogger(__name__)


@dataclass
class HandleResult:
    text: str
    executed: list[Command] = field(default_factory=list)
    unrecognized: list[str] = field(default_factory=list)
    mode: Mode = Mode.COMMAND
    grid_bounds: Rect | None = None   # set when mode is GRID, for the overlay
    grid_cells: list[Rect] | None = None
    label_bounds: Rect | None = None  # set when mode is LABELS, for the overlay
    label_items: list[Labeled] | None = None

    def summary(self) -> str:
        """Short human-readable line for the overlay / console."""
        if self.executed:
            return " · ".join(c.describe() for c in self.executed)
        if self.unrecognized:
            return "? " + " ".join(self.unrecognized)
        return ""


def _amount(cmd: Command, default: int, maximum: int) -> int:
    value = cmd.amount if cmd.amount is not None else default
    return max(1, min(value, maximum))


class Controller:
    """Owns the current Mode and executes parsed commands on a MouseBackend."""

    def __init__(self, mouse: MouseBackend, cfg: Config, screen_bounds: Rect | None = None,
                 elements_provider: Callable[[], list[ElementInfo]] | None = None) -> None:
        self.mouse = mouse
        self.cfg = cfg
        self.mode = Mode.SLEEPING if cfg.start_asleep else Mode.COMMAND
        self.should_quit = False
        self._glider = Glider(mouse, cfg.glide_speed)
        self._button_held = False
        self._grid: GridSelector | None = None
        # Fixed bounds (used by tests); None means "ask the real screen each
        # time a grid/labels session starts", since monitor layout can change.
        self._screen_bounds = screen_bounds
        self._labels: LabelSelector | None = None
        self._label_bounds: Rect | None = None
        # Injectable for tests; None means "use the real UI Automation scan".
        self._elements_provider = elements_provider

    def handle(self, text: str) -> HandleResult:
        if self.mode is Mode.GRID:
            parsed = parse_grid(text)
        elif self.mode is Mode.LABELS:
            parsed = parse_labels(text)
        else:
            parsed = parse(text)
        result = HandleResult(text=text, unrecognized=parsed.unrecognized)
        for cmd in parsed.commands:
            if self.mode is Mode.SLEEPING and cmd.action is not Action.WAKE:
                continue  # asleep: ignore everything except the wake phrase
            log.info("command: %s", cmd.describe())
            self._execute(cmd)
            result.executed.append(cmd)
        result.mode = self.mode
        if self.mode is Mode.GRID and self._grid is not None:
            result.grid_bounds = self._grid.current
            result.grid_cells = self._grid.cells
        elif self.mode is Mode.LABELS and self._labels is not None:
            result.label_bounds = self._label_bounds
            result.label_items = self._labels.items
        return result

    def close(self) -> None:
        """Stop background work and release anything we're holding down."""
        self._glider.stop()
        if self._button_held:
            self.mouse.button_up("left")
            self._button_held = False
        self._grid = None
        self._labels = None

    def _execute(self, cmd: Command) -> None:
        cfg = self.cfg
        if cmd.action is not Action.GLIDE:
            self._glider.stop()  # any new command cancels an active glide

        match cmd.action:
            case Action.MOVE:
                assert cmd.direction is not None
                n = _amount(cmd, cfg.move_step, cfg.max_move)
                dx, dy = cmd.direction.vector
                self.mouse.move_rel(dx * n, dy * n)
            case Action.GLIDE:
                assert cmd.direction is not None
                self._glider.start(cmd.direction)
            case Action.STOP:
                pass  # the glide was already cancelled above
            case Action.CLICK:
                self.mouse.click("left", 1)
            case Action.DOUBLE_CLICK:
                self.mouse.click("left", 2)
            case Action.RIGHT_CLICK:
                self.mouse.click("right", 1)
            case Action.MIDDLE_CLICK:
                self.mouse.click("middle", 1)
            case Action.HOLD:
                if not self._button_held:
                    self.mouse.button_down("left")
                    self._button_held = True
            case Action.RELEASE:
                if self._button_held:
                    self.mouse.button_up("left")
                    self._button_held = False
            case Action.SCROLL:
                assert cmd.direction is not None
                n = _amount(cmd, cfg.scroll_notches, cfg.max_scroll)
                dx, dy = cmd.direction.vector
                # Screen y grows downward but wheel-up is positive, so flip y.
                self.mouse.scroll(vertical=-dy * n, horizontal=dx * n)
            case Action.SLEEP:
                self.mode = Mode.SLEEPING
            case Action.WAKE:
                self.mode = Mode.COMMAND
            case Action.QUIT:
                self.should_quit = True
            case Action.GRID_ENTER:
                self._grid_enter()
            case Action.GRID_SELECT:
                assert cmd.amount is not None
                self._grid_select(cmd.amount)
            case Action.GRID_BACK:
                self._grid_back()
            case Action.GRID_CANCEL:
                self._grid_exit()
            case Action.GRID_CLICK:
                self._grid_click()
            case Action.LABELS_ENTER:
                self._labels_enter()
            case Action.LABELS_SELECT:
                assert cmd.amount is not None
                self._labels_select(cmd.amount)
            case Action.LABELS_CANCEL:
                self._labels_exit()
            case Action.LABELS_REFRESH:
                self._labels_enter()  # re-scan; elements may have changed

    def _labels_enter(self) -> None:
        bounds = self._screen_bounds
        if bounds is None:
            from .screen import virtual_screen_rect
            bounds = virtual_screen_rect()
        provider = self._elements_provider
        if provider is None:
            from .elements import find_actionable_elements
            cfg = self.cfg
            provider = lambda: find_actionable_elements(  # noqa: E731
                max_elements=cfg.labels_max_elements, max_depth=cfg.labels_max_depth)
        elements = provider()
        labeled = assign_labels(elements)
        if not labeled:
            log.info("no clickable elements found; staying in command mode")
            self._labels = None
            self.mode = Mode.COMMAND
            return
        self._label_bounds = bounds
        self._labels = LabelSelector(labeled)
        self.mode = Mode.LABELS

    def _labels_select(self, n: int) -> None:
        if self._labels is None:
            return
        item = self._labels.get(n)
        if item is None:
            log.info("no label %d on screen; ignoring", n)
            return
        x, y = item.rect.center
        self.mouse.move_to(x, y)
        self.mouse.click("left", 1)
        self._labels_exit()

    def _labels_exit(self) -> None:
        self._labels = None
        self._label_bounds = None
        self.mode = Mode.COMMAND

    def _grid_enter(self) -> None:
        bounds = self._screen_bounds
        if bounds is None:
            from .screen import virtual_screen_rect
            bounds = virtual_screen_rect()
        self._grid = GridSelector(bounds, self.cfg.grid_rows, self.cfg.grid_cols)
        self.mode = Mode.GRID

    def _grid_select(self, n: int) -> None:
        if self._grid is None:
            return
        count = self._grid.rows * self._grid.cols
        if not 1 <= n <= count:
            log.info("cell %d is out of range for a %dx%d grid; ignoring",
                      n, self._grid.rows, self._grid.cols)
            return
        target = self._grid.cells[n - 1]
        if min(target.width, target.height) < self.cfg.grid_min_cell:
            log.info("that cell would go below the minimum size; ignoring further zoom")
            return
        self._grid.select(n)

    def _grid_back(self) -> None:
        if self._grid is None:
            return
        if not self._grid.back():  # already at the root: "back" exits
            self._grid_exit()

    def _grid_exit(self) -> None:
        self._grid = None
        self.mode = Mode.COMMAND

    def _grid_click(self) -> None:
        if self._grid is None:
            return
        x, y = self._grid.current.center
        self.mouse.move_to(x, y)
        self.mouse.click("left", 1)
        self._grid_exit()
