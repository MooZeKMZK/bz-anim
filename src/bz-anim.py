#!/usr/bin/env python3
"""Unified entrypoint for the 2D Belousov-Zhabotinsky reaction-diffusion simulator.

Supports:
- CLI mode (default): `python src/bz-anim.py -o bz_reaction.gif` or `python src/cli.py`
- TUI mode (Textual): `python src/bz-anim.py --tui` or `python src/tui.py`
- GUI mode (PySide6): `python src/bz-anim.py --gui` or `python src/gui.py`
"""

from __future__ import annotations

import sys
from typing import Sequence

from base import (
    BASE_STEPS_PER_SECOND,
    BZSimulator,
    ColorLike,
    SimulationConfig,
    SizeLike,
    _downsample_field,
    _initialize_fields,
    _moore_average,
    _optimize_cell_deltas,
    _quantize_field,
    _render_frame,
    _step_bz,
    _upsample_indices,
    build_palette,
    build_palette_array,
    parse_color,
    parse_size,
    simulate_bz_reaction,
    simulate_from_config,
)
from cli import args_to_config, build_arg_parser, run_cli


def _build_arg_parser():
    """Backward-compatible helper returning the CLI argument parser."""
    return build_arg_parser(add_mode_flag=True)


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch to CLI, Textual TUI, or PySide6 GUI based on command-line arguments."""
    args_list = list(sys.argv[1:] if argv is None else argv)

    # Allow subcommand syntax (`bz-anim.py cli|tui|gui ...`) in addition to `--tui`/`--gui`/`--mode`
    subcommand_mode: str | None = None
    if args_list and args_list[0] in {"cli", "tui", "gui"}:
        subcommand_mode = args_list.pop(0)

    parser = build_arg_parser(add_mode_flag=True)
    args = parser.parse_args(args_list)
    mode = subcommand_mode or args.mode
    config = args_to_config(args)

    if mode == "tui":
        from tui import BZTuiApp

        app = BZTuiApp(
            initial_config=config,
            config_path=args.config or "config.toml",
            theme_path=args.theme or "theme.toml",
        )
        app.run()
        return 0

    if mode == "gui":
        from PySide6.QtWidgets import QApplication
        from gui import BZGuiWindow

        qapp = QApplication.instance() or QApplication(sys.argv)
        window = BZGuiWindow(
            initial_config=config,
            config_path=args.config or "config.toml",
            theme_path=args.theme or "theme.toml",
        )
        window.show()
        return qapp.exec()

    saved_path = simulate_from_config(config)
    print(f"Saved Belousov-Zhabotinsky simulation GIF to: {saved_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
