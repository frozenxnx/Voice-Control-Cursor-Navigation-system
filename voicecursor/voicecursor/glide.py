"""Continuous cursor movement ("glide left ... stop")."""

from __future__ import annotations

import threading
import time

from .backends import MouseBackend
from .commands import Direction


class Glider:
    """Moves the cursor at a constant speed on a background thread.

    Distance is computed from elapsed time (not tick count), so speed stays
    correct despite Windows' ~15 ms timer granularity. Sub-pixel remainders
    are carried between ticks.
    """

    def __init__(self, mouse: MouseBackend, speed_px_per_s: float, hz: int = 60) -> None:
        self._mouse = mouse
        self._speed = speed_px_per_s
        self._interval = 1.0 / hz
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    @property
    def active(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, direction: Direction) -> None:
        self.stop()
        self._stop = threading.Event()  # fresh event per run
        self._thread = threading.Thread(
            target=self._run, args=(direction, self._stop), daemon=True, name="glider")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=0.5)

    def _run(self, direction: Direction, stop: threading.Event) -> None:
        ux, uy = direction.vector
        carry_x = carry_y = 0.0
        last = time.monotonic()
        while not stop.wait(self._interval):
            now = time.monotonic()
            dt, last = now - last, now
            carry_x += ux * self._speed * dt
            carry_y += uy * self._speed * dt
            ix, iy = int(carry_x), int(carry_y)  # truncate toward zero
            if ix or iy:
                self._mouse.move_rel(ix, iy)
                carry_x -= ix
                carry_y -= iy
