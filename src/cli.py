"""Command-line interface (CLI) for the 2D Belousov-Zhabotinsky reaction-diffusion simulator."""

from __future__ import annotations

import argparse
from typing import Sequence

from base import SimulationConfig, load_config_file, simulate_from_config
from theme import ThemeConfig, load_theme_file


def build_arg_parser(add_mode_flag: bool = False) -> argparse.ArgumentParser:
    """Build the CLI argument parser for BZ simulation parameters and TOML config/theme files."""
    parser = argparse.ArgumentParser(
        description="Generate an animated GIF of a 2D Belousov-Zhabotinsky reaction simulation (or launch TUI/GUI)."
    )
    if add_mode_flag:
        parser.add_argument(
            "--mode",
            choices=["cli", "tui", "gui"],
            default="cli",
            help="Interface mode to launch: 'cli' (default), 'tui' (Textual terminal UI), or 'gui' (PySide6 desktop GUI).",
        )
        parser.add_argument(
            "--tui",
            action="store_const",
            const="tui",
            dest="mode",
            help="Launch the Textual TUI.",
        )
        parser.add_argument(
            "--gui",
            action="store_const",
            const="gui",
            dest="mode",
            help="Launch the PySide6 desktop GUI.",
        )

    parser.add_argument(
        "--config",
        default=None,
        help="Path to TOML simulation options file (defaults to ./config.toml if present).",
    )
    parser.add_argument(
        "--save-config",
        default=None,
        metavar="PATH",
        help="Write the resolved simulation options to a TOML file at PATH.",
    )
    parser.add_argument(
        "--theme",
        default=None,
        help="Path to TOML UI theme file for TUI/GUI (defaults to ./theme.toml if present).",
    )
    parser.add_argument(
        "--save-theme",
        default=None,
        metavar="PATH",
        help="Write the active UI theme tokens to a TOML file at PATH.",
    )

    parser.add_argument("-o", "--output", default=None, help="Output GIF path.")
    parser.add_argument(
        "-s", "--size", default=None, help="Canvas size as WxH or N (e.g. 320x320 or 256)."
    )
    parser.add_argument(
        "-l", "--length", type=float, default=None, help="Animation duration in seconds."
    )
    parser.add_argument(
        "-f", "--framerate", type=int, default=None, help="Frames per second."
    )
    parser.add_argument(
        "--palette-mode",
        choices=["gradient", "ferroin"],
        default=None,
        help="Color lookup mode: 'gradient' (2-stop bg->rings) or 'ferroin' (multi-stop rust-red -> lavender -> cobalt/cyan LUT).",
    )
    parser.add_argument(
        "--bg-color", default=None, help="Background color (hex, name, or R,G,B)."
    )
    parser.add_argument(
        "--rings-color", default=None, help="Wavefront rings color (hex, name, or R,G,B)."
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=None,
        help="Reaction playback speed multiplier (e.g. 0.5 for half speed, 2.0 for double speed).",
    )
    parser.add_argument(
        "--warmup", type=int, default=None, help="Warmup simulation steps before recording."
    )
    parser.add_argument(
        "--steps-per-frame",
        type=float,
        default=None,
        help="Optional override for base simulation steps per frame (scaled by --speed).",
    )
    parser.add_argument(
        "--seed", type=int, default=None, help="Random seed for reproducible initial conditions."
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=None,
        help="Reaction rate parameter alpha (A + B -> 2A, default: 1.2).",
    )
    parser.add_argument(
        "--beta",
        type=float,
        default=None,
        help="Reaction rate parameter beta (B + C -> 2B, default: 1.0).",
    )
    parser.add_argument(
        "--gamma",
        type=float,
        default=None,
        help="Reaction rate parameter gamma (C + A -> 2C, default: 1.0).",
    )
    parser.add_argument(
        "-c",
        "--colors",
        type=int,
        default=None,
        help="Number of gradient palette colors (2..256, default: 10).",
    )
    parser.add_argument(
        "-p",
        "--pixel-size",
        "--raster-size",
        dest="pixel_size",
        type=int,
        default=None,
        help="Raster pixel block size in pixels (1 for full resolution, default: 1).",
    )
    parser.add_argument(
        "--palette-gamma",
        type=float,
        default=None,
        help="Palette color ramp gamma curve exponent (default: 1.15).",
    )
    parser.add_argument(
        "--contrast-gamma",
        type=float,
        default=None,
        help="Field quantization contrast exponent (>1 suppresses wake noise, default: 1.15).",
    )
    parser.add_argument(
        "--seamless-loop",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable seamless temporal loop via chemical oxidation pulse wipe (default: enabled).",
    )
    parser.add_argument(
        "--loop-wipe-ratio",
        type=float,
        default=None,
        help="Fraction of loop duration used for the chemical oxidation pulse wipe in 0.05..0.95 (default: 0.28).",
    )
    parser.add_argument(
        "--pulse-count",
        type=int,
        default=None,
        help="Number of staggered anti-grid radial oxidation pulses on the 2D torus (default: 3).",
    )
    parser.add_argument(
        "--pulse-speed",
        type=float,
        default=None,
        help="Relative wave speed of the oxidation trigger pulse (default: 1.45).",
    )
    parser.add_argument(
        "--pulse-sharpness",
        type=float,
        default=None,
        help="Leading-edge oxidation sharpness of the pulse wavefront (default: 18.0).",
    )
    parser.add_argument(
        "--pulse-decay",
        type=float,
        default=None,
        help="Trailing refractory recovery decay rate behind the pulse crest (default: 4.0).",
    )
    parser.add_argument(
        "--pulse-noise-amp",
        type=float,
        default=None,
        help="Amplitude of 4D toroidal Perlin/Fourier wavefront distortion noise (0 to disable, default: 0.08).",
    )
    parser.add_argument(
        "--pulse-noise-freq",
        type=int,
        default=None,
        help="Base spatial frequency of 4D toroidal wavefront distortion noise (default: 3).",
    )
    parser.add_argument(
        "--tileable",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enforce strict 2D torus spatial wrap-around across all simulation, pulse, and post-processing passes (default: enabled).",
    )
    parser.add_argument(
        "--scanline-smooth",
        type=float,
        default=None,
        help="Horizontal scanline smoothing neighbor weight in 0.0..0.5 for LZW compression (0 to disable, default: 0.15).",
    )
    parser.add_argument(
        "--no-scanline-smooth",
        action="store_const",
        const=0.0,
        dest="scanline_smooth",
        help="Disable horizontal scanline smoothing.",
    )
    parser.add_argument(
        "--diff-threshold",
        type=int,
        default=None,
        help="Inter-frame palette index diff tolerance for delta compression (0 for exact, default: 1).",
    )
    parser.add_argument(
        "--bg-snap-threshold",
        type=float,
        default=None,
        help="Threshold factor to snap decaying cells back to background index 0 (0 to disable, default: 0.25).",
    )
    parser.add_argument(
        "--despeckle",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Suppress isolated 1-cell delta speckles and bridge 1-cell horizontal gaps (default: enabled).",
    )
    parser.add_argument(
        "--snap-steps",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Snap to discrete simulation steps when step_advance <= 1.0 instead of sub-step linear interpolation (default: enabled).",
    )
    parser.add_argument(
        "--optimize",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable GIF delta-frame transparency and LZW optimizations (default: enabled).",
    )
    return parser


def args_to_config(args: argparse.Namespace) -> SimulationConfig:
    """Load base `SimulationConfig` from `--config` (or `./config.toml`) and overlay any explicit CLI arguments.

    Also loads `--theme` (or `./theme.toml`) and handles `--save-config` / `--save-theme`.
    """
    active_theme: ThemeConfig = load_theme_file(getattr(args, "theme", None))
    if getattr(args, "save_theme", None):
        saved_theme_path = active_theme.save_toml(args.save_theme)
        print(f"Saved TOML theme configuration to: {saved_theme_path}")

    cfg = load_config_file(getattr(args, "config", None))

    override_map = {
        "output": "output_path",
        "size": "size",
        "length": "length",
        "framerate": "framerate",
        "palette_mode": "palette_mode",
        "bg_color": "bg_color",
        "rings_color": "rings_color",
        "speed": "speed",
        "alpha": "alpha",
        "beta": "beta",
        "gamma": "gamma",
        "warmup": "warmup_steps",
        "steps_per_frame": "steps_per_frame",
        "seed": "seed",
        "colors": "colors",
        "pixel_size": "pixel_size",
        "palette_gamma": "palette_gamma",
        "contrast_gamma": "contrast_gamma",
        "seamless_loop": "seamless_loop",
        "loop_wipe_ratio": "loop_wipe_ratio",
        "pulse_count": "pulse_count",
        "pulse_speed": "pulse_speed",
        "pulse_sharpness": "pulse_sharpness",
        "pulse_decay": "pulse_decay",
        "pulse_noise_amp": "pulse_noise_amp",
        "pulse_noise_freq": "pulse_noise_freq",
        "tileable": "tileable",
        "scanline_smooth": "scanline_smooth",
        "bg_snap_threshold": "bg_snap_threshold",
        "despeckle": "despeckle",
        "snap_steps": "snap_steps",
        "optimize": "optimize",
        "diff_threshold": "diff_threshold",
    }
    for arg_name, cfg_field in override_map.items():
        val = getattr(args, arg_name, None)
        if val is not None:
            setattr(cfg, cfg_field, val)

    cfg.validate()

    if getattr(args, "save_config", None):
        saved_cfg_path = cfg.save_toml(args.save_config)
        print(f"Saved TOML simulation options to: {saved_cfg_path}")

    return cfg


def run_cli(argv: Sequence[str] | None = None) -> str:
    """Parse CLI arguments, execute the simulation, and print the output GIF path."""
    parser = build_arg_parser(add_mode_flag=False)
    args = parser.parse_args(argv)
    config = args_to_config(args)
    saved_path = simulate_from_config(config)
    print(f"Saved Belousov-Zhabotinsky simulation GIF to: {saved_path}")
    return saved_path


if __name__ == "__main__":
    run_cli()
