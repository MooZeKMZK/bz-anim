"""Belousov-Zhabotinsky reaction-diffusion simulation package."""

from base import (
    BASE_STEPS_PER_SECOND,
    BZSimulator,
    ColorLike,
    SimulationConfig,
    SizeLike,
    build_palette,
    build_palette_array,
    parse_color,
    parse_size,
    simulate_bz_reaction,
    simulate_from_config,
)

__all__ = [
    "BASE_STEPS_PER_SECOND",
    "BZSimulator",
    "ColorLike",
    "SimulationConfig",
    "SizeLike",
    "build_palette",
    "build_palette_array",
    "parse_color",
    "parse_size",
    "simulate_bz_reaction",
    "simulate_from_config",
]
