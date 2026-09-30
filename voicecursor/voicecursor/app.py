"""Wires audio -> recogniser -> controller -> overlay together."""

from __future__ import annotations

import logging
import sys
import threading

from .backends import DryRunMouse, MouseBackend
from .commands import Mode
from .config import Config
from .controller import Controller

log = logging.getLogger(__name__)


def create_mouse(cfg: Config) -> MouseBackend:
    if cfg.dry_run:
        return DryRunMouse()
    if sys.platform != "win32":
        log.warning("Not running on Windows; falling back to dry-run mouse")
        return DryRunMouse()
    from .mouse_windows import WindowsMouse  # imported lazily: needs Windows
    return WindowsMouse()


def _idle_message(mode: Mode) -> str:
    if mode is Mode.SLEEPING:
        return "sleeping - say 'start listening'"
    if mode is Mode.GRID:
        return "grid - say a number 1-9 to zoom, 'click' to click, 'back' or 'cancel' to exit"
    if mode is Mode.LABELS:
        return "labels - say a number to click it, or 'cancel'/'refresh'"
    return "listening - try 'move left two hundred', 'grid', or 'show numbers'"


def run_test_grid(cfg: Config) -> int:
    """Show the grid overlay immediately, with no mic/Vosk involved at all.
    Isolates whether a problem is in the overlay/rendering or in the
    audio/recognition path. Ctrl+C to exit."""
    from .geometry import Rect
    from .grid import GridSelector
    from .overlay import TkOverlay
    from .screen import virtual_screen_rect

    if sys.platform == "win32":
        from .mouse_windows import enable_dpi_awareness
        enable_dpi_awareness()  # do this before reading screen size, as usual

    bounds = virtual_screen_rect()
    print(f"Detected virtual screen: {bounds.width}x{bounds.height} at "
          f"({bounds.left}, {bounds.top})")
    grid = GridSelector(bounds, cfg.grid_rows, cfg.grid_cols)

    overlay = TkOverlay()
    stop = threading.Event()

    def worker() -> None:
        overlay.post("test grid - should be visible now. Ctrl+C to quit.", Mode.GRID)
        overlay.show_grid(grid.current, grid.cells)
        print("Grid should now be visible on screen. Press Ctrl+C here to stop.")

    threading.Thread(target=worker, daemon=True).start()
    try:
        overlay.run(stop)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
    return 0


def run(cfg: Config) -> int:
    mouse = create_mouse(cfg)  # first: enables DPI awareness before any window exists
    controller = Controller(mouse, cfg)
    try:
        if cfg.text_mode:
            return _run_text(controller)
        return _run_voice(controller, cfg)
    finally:
        controller.close()


def _run_text(controller: Controller) -> int:
    """Type commands instead of speaking them: handy for testing the parser
    and mouse backend without a microphone or a Vosk model."""
    if sys.stdin.isatty():
        print("Type commands (e.g. 'move left two hundred', 'click'). Ctrl+D / Ctrl+Z to quit.")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        result = controller.handle(line)
        print(f"[{result.mode.value}] {result.summary() or '-'}")
        if isinstance(controller.mouse, DryRunMouse):
            print(f"        cursor at {controller.mouse.position}")
        if result.grid_bounds is not None:
            b = result.grid_bounds
            print(f"        grid cell: {b.width}x{b.height} at ({b.left}, {b.top}), "
                  f"centre {b.center}")
        if result.label_items is not None:
            print(f"        {len(result.label_items)} element(s) labelled:")
            for item in result.label_items:
                print(f"          [{item.label}] {item.name or '(unnamed)'} at {item.rect}")
        if controller.should_quit:
            break
    return 0


def _run_voice(controller: Controller, cfg: Config) -> int:
    from .audio import MicStream
    from .overlay import NullOverlay, TkOverlay
    from .recognizer import VoskRecognizer

    recognizer = VoskRecognizer(cfg.model_path, cfg.sample_rate)  # fail fast if model missing
    overlay = TkOverlay() if cfg.overlay else NullOverlay()
    stop = threading.Event()

    def worker() -> None:
        last_partial = ""
        try:
            overlay.post(_idle_message(controller.mode), controller.mode)
            with MicStream(cfg.sample_rate, cfg.block_ms, cfg.device) as mic:
                for chunk in mic.chunks(stop):
                    hyp = recognizer.feed(controller.mode, chunk)
                    if hyp is None:
                        continue
                    if not hyp.final:
                        if hyp.text != last_partial:
                            last_partial = hyp.text
                            overlay.post(f"… {hyp.text}", controller.mode)
                        continue
                    last_partial = ""
                    if not hyp.text:
                        continue
                    result = controller.handle(hyp.text)
                    if result.mode is Mode.GRID and result.grid_bounds is not None:
                        overlay.show_grid(result.grid_bounds, result.grid_cells)
                    elif result.mode is Mode.LABELS and result.label_bounds is not None:
                        overlay.show_labels(result.label_bounds, result.label_items)
                    else:
                        overlay.hide_grid()
                        overlay.hide_labels()
                    overlay.post(result.summary() or _idle_message(result.mode), result.mode)
                    if controller.should_quit:
                        break
        except Exception:  # noqa: BLE001 - surface any failure, then shut down
            log.exception("audio/recognition thread crashed")
        finally:
            stop.set()

    thread = threading.Thread(target=worker, name="recognizer", daemon=True)
    thread.start()
    try:
        overlay.run(stop)  # blocks on the main thread until stop is set
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        thread.join(timeout=2)
    return 0
