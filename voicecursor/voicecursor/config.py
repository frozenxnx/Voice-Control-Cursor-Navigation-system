"""Runtime configuration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Config:
    # Speech recognition
    model_path: str = "models/vosk-model-small-en-us-0.15"
    sample_rate: int = 16_000
    block_ms: int = 100  # audio chunk size; smaller = lower latency, more overhead
    device: int | str | None = None  # sounddevice input device (None = default)

    # Cursor behaviour
    move_step: int = 100        # pixels for "move left" with no number
    max_move: int = 5000        # safety clamp for a single move
    scroll_notches: int = 3     # notches for "scroll down" with no number
    max_scroll: int = 30
    glide_speed: float = 400.0  # pixels per second for "glide <direction>"

    # Grid navigation
    grid_rows: int = 3
    grid_cols: int = 3
    grid_min_cell: int = 24     # px; stop zooming once a cell gets this small

    # UI element labels
    labels_max_elements: int = 60  # cap on how many controls to scan/label
    labels_max_depth: int = 8      # cap on how deep into the UI tree to walk

    # Behaviour flags
    start_asleep: bool = False
    overlay: bool = True
    dry_run: bool = False       # log actions instead of moving the real cursor
    text_mode: bool = False     # read commands from stdin instead of the mic
    verbose: bool = False
