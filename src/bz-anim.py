#!/usr/bin/env python3
"""Unified entrypoint for the 2D Belousov-Zhabotinsky reaction-diffusion simulator."""

from __future__ import annotations

from bz_anim import (
    BASE_STEPS_PER_SECOND,
    BZSimulator,
    ColorLike,
    SimulationConfig,
    SizeLike,
    _build_arg_parser,
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
    main,
    parse_color,
    parse_size,
    simulate_bz_reaction,
    simulate_from_config,
)

if __name__ == "__main__":
    raise SystemExit(main())
