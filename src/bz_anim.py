#!/usr/bin/env python3
"""Importable entrypoint module for the `bz-anim` console script."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

# Ensure `src` directory is on sys.path when invoked directly or via console_scripts
_SRC_DIR = str(Path(__file__).resolve().parent)
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

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
