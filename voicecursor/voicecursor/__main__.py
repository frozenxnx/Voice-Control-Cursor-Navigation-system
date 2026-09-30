"""Command-line entry point: python -m voicecursor"""

from __future__ import annotations

import argparse
import logging

from .config import Config


def build_arg_parser() -> argparse.ArgumentParser:
    defaults = Config()
    p = argparse.ArgumentParser(prog="voicecursor", description="Voice-controlled cursor for Windows")
    p.add_argument("--model", default=defaults.model_path, help="path to an unpacked Vosk small model")
    p.add_argument("--device", help="input device index or name (see --list-devices)")
    p.add_argument("--list-devices", action="store_true", help="list audio devices and exit")
    p.add_argument("--test-grid", action="store_true",
                    help="show the grid overlay immediately, no mic/Vosk needed (for debugging)")
    p.add_argument("--dry-run", action="store_true", help="log actions instead of moving the real cursor")
    p.add_argument("--text", action="store_true", help="read commands from stdin instead of the microphone")
    p.add_argument("--no-overlay", action="store_true", help="disable the on-screen status overlay")
    p.add_argument("--start-asleep", action="store_true", help="ignore commands until you say 'start listening'")
    p.add_argument("--move-step", type=int, default=defaults.move_step, help="default pixels for 'move <dir>'")
    p.add_argument("--glide-speed", type=float, default=defaults.glide_speed, help="pixels/second for 'glide'")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%H:%M:%S")

    if args.list_devices:
        from .audio import list_devices
        list_devices()
        return 0

    if args.test_grid:
        from .app import run_test_grid
        return run_test_grid(Config(grid_rows=3, grid_cols=3))

    device: int | str | None = args.device
    if device is not None and device.isdigit():
        device = int(device)

    cfg = Config(
        model_path=args.model, device=device, dry_run=args.dry_run, text_mode=args.text,
        overlay=not args.no_overlay, start_asleep=args.start_asleep,
        move_step=args.move_step, glide_speed=args.glide_speed, verbose=args.verbose)

    from .app import run
    return run(cfg)


if __name__ == "__main__":
    raise SystemExit(main())
