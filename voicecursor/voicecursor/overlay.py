"""Always-on-top status overlay, plus the numbered grid and UI-label overlays.

Uses tkinter (stdlib). All windows are click-through and non-activating on
Windows, so they can never steal a click or focus from the app you're
controlling. Thread-safe: call post()/show_grid()/show_labels()/etc from any
thread; run() must be called on the main thread.
"""

from __future__ import annotations

import logging
import queue
import sys
import threading

from .commands import Mode
from .geometry import Rect
from .labels import Labeled

log = logging.getLogger(__name__)

_COLORS = {Mode.COMMAND: "#7ee787", Mode.SLEEPING: "#8b949e", Mode.GRID: "#58a6ff",
           Mode.LABELS: "#d29922"}

# Colour-keyed out of the grid window so only the grid lines/labels are
# visible; picked to be unlikely to appear in real UI chrome.
_GRID_TRANSPARENT = "#fe00fe"


class NullOverlay:
    """Used with --no-overlay, and as the fallback when tkinter isn't
    available: log to the console instead of drawing anything."""

    def post(self, text: str, mode: Mode) -> None:
        if text:
            log.info("[%s] %s", mode.value, text)

    def show_grid(self, bounds: Rect, cells: list[Rect]) -> None:
        log.info("grid: %dx%d at (%d, %d)", bounds.width, bounds.height, bounds.left, bounds.top)

    def hide_grid(self) -> None:
        pass

    def show_labels(self, bounds: Rect, items: list[Labeled]) -> None:
        log.info("labels: %d element(s) found", len(items))
        for item in items:
            log.debug("  [%d] %s at %s", item.label, item.name or item.rect, item.rect)

    def hide_labels(self) -> None:
        pass

    def run(self, stop: threading.Event) -> None:
        while not stop.wait(0.2):  # timeout keeps Ctrl+C responsive on Windows
            pass


class TkOverlay:
    def __init__(self) -> None:
        self._q: queue.SimpleQueue[tuple] = queue.SimpleQueue()

    def post(self, text: str, mode: Mode) -> None:
        self._q.put(("status", text, mode))

    def show_grid(self, bounds: Rect, cells: list[Rect]) -> None:
        self._q.put(("grid_show", bounds, cells))

    def hide_grid(self) -> None:
        self._q.put(("grid_hide", None, None))

    def show_labels(self, bounds: Rect, items: list[Labeled]) -> None:
        self._q.put(("labels_show", bounds, items))

    def hide_labels(self) -> None:
        self._q.put(("labels_hide", None, None))

    def run(self, stop: threading.Event) -> None:
        import tkinter as tk

        bg = "#111418"
        root = tk.Tk()
        root.title("voicecursor")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", 0.88)
        _make_click_through(root)  # before further attribute changes - see the
                                    # matching comment in ensure_grid_window()
        root.configure(bg=bg)

        dot = tk.Label(root, text="●", font=("Segoe UI", 16), bg=bg, fg=_COLORS[Mode.COMMAND])
        dot.pack(side="left", padx=(16, 8), pady=10)
        msg = tk.Label(root, text="", font=("Segoe UI", 16), bg=bg, fg="#f2f4f8")
        msg.pack(side="left", padx=(0, 16), pady=10)

        screen_w, screen_h = root.winfo_screenwidth(), root.winfo_screenheight()

        def reposition_status() -> None:
            # Size from content and place relative to the screen so it
            # behaves on any DPI scale.
            root.update_idletasks()
            w = max(root.winfo_reqwidth(), int(screen_w * 0.22))
            h = root.winfo_reqheight()
            x = (screen_w - w) // 2
            y = screen_h - h - int(screen_h * 0.08)
            root.geometry(f"{w}x{h}+{x}+{y}")

        # --- grid window: created lazily, since we don't know its size or
        # position (a monitor's virtual-screen bounds) until the first
        # show_grid() call. ---
        grid = {"win": None, "canvas": None, "shown": False}

        def ensure_grid_window() -> None:
            if grid["win"] is not None:
                return
            win = tk.Toplevel(root)
            win.withdraw()  # configure while hidden; some of this silently
                             # fails on Windows if applied to an already-mapped window
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            win.configure(bg=_GRID_TRANSPARENT)
            try:
                win.attributes("-transparentcolor", _GRID_TRANSPARENT)
            except tk.TclError:
                log.warning("-transparentcolor unsupported here; grid window will be opaque")
            canvas = tk.Canvas(win, bg=_GRID_TRANSPARENT, highlightthickness=0)
            canvas.pack(fill="both", expand=True)
            grid["win"], grid["canvas"] = win, canvas
            #_make_click_through() # is deliberately NOT called here. On some
            # Windows/Tk builds the colour-key transparency only actually
            # takes hold once the window has been mapped and painted at
            # least once; touching GWL_EXSTYLE before that first paint (even
            # in the "right" order) has been observed to leave the window
            # fully invisible instead of transparent-with-drawing. So it's
            # applied after the first real deiconify, on a later event-loop
            # tick - see draw_grid().

        def draw_grid(bounds: Rect, cells: list[Rect]) -> None:
            ensure_grid_window()
            win, canvas = grid["win"], grid["canvas"]
            first_show = not grid["shown"]
            win.geometry(f"{bounds.width}x{bounds.height}+{bounds.left}+{bounds.top}")
            canvas.delete("all")
            font_size = max(12, min(bounds.width, bounds.height) // 12)
            for i, cell in enumerate(cells, start=1):
                x0, y0 = cell.left - bounds.left, cell.top - bounds.top
                x1, y1 = x0 + cell.width, y0 + cell.height
                canvas.create_rectangle(x0, y0, x1, y1, outline="#7ee787", width=2)
                cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
                canvas.create_text(cx, cy, text=str(i), fill="#f2f4f8",
                                    font=("Segoe UI", font_size, "bold"))
            win.deiconify()
            win.lift()
            win.attributes("-topmost", True)  # re-assert: some window managers
                                               # drop topmost across deiconify
            try:  # re-assert too: withdraw()/deiconify() can drop this as well
                win.attributes("-transparentcolor", _GRID_TRANSPARENT)
            except tk.TclError:
                pass
            win.update_idletasks()
            log.info("grid window: requested %dx%d+%d+%d, actual %dx%d+%d+%d",
                      bounds.width, bounds.height, bounds.left, bounds.top,
                      win.winfo_width(), win.winfo_height(), win.winfo_x(), win.winfo_y())
            if first_show:
                grid["shown"] = True
                # Apply click-through one tick later, after this first paint,
                # instead of synchronously - see the comment in
                # ensure_grid_window().
                win.after(30, lambda: _make_click_through(win))

        def hide_grid_window() -> None:
            if grid["win"] is not None:
                grid["win"].withdraw()

        def draw_labels(bounds: Rect, items: list[Labeled]) -> None:
            # Reuses the exact same transparent, click-through window as the
            # grid (ensure_grid_window/hide_grid_window) - the two modes are
            # mutually exclusive, so there's never a need for both windows
            # at once, and this avoids duplicating the delicate first-paint/
            # click-through sequencing that took real effort to get working.
            ensure_grid_window()
            win, canvas = grid["win"], grid["canvas"]
            first_show = not grid["shown"]
            win.geometry(f"{bounds.width}x{bounds.height}+{bounds.left}+{bounds.top}")
            canvas.delete("all")
            for item in items:
                x = item.rect.left - bounds.left
                y = item.rect.top - bounds.top
                r = 11  # badge radius; small enough to sit in a corner without
                        # covering whatever it's labelling
                canvas.create_oval(x - 2, y - 2, x + 2 * r, y + 2 * r,
                                    fill="#1f6feb", outline="#f2f4f8", width=1)
                canvas.create_text(x + r, y + r, text=str(item.label), fill="#ffffff",
                                    font=("Segoe UI", 10, "bold"))
            win.deiconify()
            win.lift()
            win.attributes("-topmost", True)
            try:
                win.attributes("-transparentcolor", _GRID_TRANSPARENT)
            except tk.TclError:
                pass
            if first_show:
                grid["shown"] = True
                win.after(30, lambda: _make_click_through(win))

        def poll() -> None:
            status_changed = False
            try:
                while True:
                    try:
                        tag, a, b = self._q.get_nowait()
                    except queue.Empty:
                        break
                    if tag == "status":
                        dot.config(fg=_COLORS[b])
                        msg.config(text=a)
                        status_changed = True
                    elif tag == "grid_show":
                        draw_grid(a, b)
                    elif tag == "grid_hide":
                        hide_grid_window()
                    elif tag == "labels_show":
                        draw_labels(a, b)
                    elif tag == "labels_hide":
                        hide_grid_window()
                if status_changed:
                    reposition_status()
            except Exception:  # noqa: BLE001 - never let this kill the poll loop
                log.exception("overlay update failed")
            if stop.is_set():
                root.destroy()
                return
            root.after(40, poll)

        reposition_status()
        root.after(40, poll)
        root.mainloop()


def _make_click_through(win) -> None:
    """Layered + transparent + no-activate + tool window (Windows only)."""
    if sys.platform != "win32":
        return
    import ctypes

    user32 = ctypes.windll.user32
    hwnd = user32.GetParent(win.winfo_id()) or win.winfo_id()
    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW, WS_EX_TRANSPARENT = 0x00000080, 0x00000020
    WS_EX_LAYERED, WS_EX_NOACTIVATE = 0x00080000, 0x08000000
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(
        hwnd, GWL_EXSTYLE,
        style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
