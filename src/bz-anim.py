"""2D Belousov-Zhabotinsky (BZ) reaction-diffusion simulation exporting to animated GIF."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

import numpy as np
from PIL import Image, ImageColor


ColorLike = str | Sequence[int]
SizeLike = int | Sequence[int] | str


def parse_color(color: ColorLike) -> tuple[int, int, int]:
    """Parse an RGB tuple, 'R,G,B' string, hex code, or color name into (R, G, B)."""
    if isinstance(color, str):
        stripped = color.strip()
        if "," in stripped:
            parts = [p.strip() for p in stripped.split(",")]
            if len(parts) != 3:
                raise ValueError(f"Expected 3 comma-separated RGB channels, got: {color!r}")
            rgb = tuple(int(p) for p in parts)
        else:
            rgb = ImageColor.getrgb(stripped)[:3]
    elif isinstance(color, Sequence) and len(color) == 3:
        rgb = tuple(int(c) for c in color)
    else:
        raise ValueError(f"Unsupported color format: {color!r}")

    if any(not (0 <= c <= 255) for c in rgb):
        raise ValueError(f"RGB channels must be in 0..255, got: {rgb}")
    return rgb  # type: ignore[return-value]


def parse_size(size: SizeLike) -> tuple[int, int]:
    """Parse a square integer, (width, height) sequence, or 'WxH'/'N' string into (width, height)."""
    if isinstance(size, int):
        w, h = size, size
    elif isinstance(size, str):
        cleaned = size.strip().lower()
        if "x" in cleaned:
            parts = cleaned.split("x", maxsplit=1)
            w, h = int(parts[0].strip()), int(parts[1].strip())
        else:
            w = h = int(cleaned)
    elif isinstance(size, Sequence) and len(size) == 2:
        w, h = int(size[0]), int(size[1])
    else:
        raise ValueError(f"Unsupported size format: {size!r}")

    if w <= 0 or h <= 0:
        raise ValueError(f"Size dimensions must be positive, got: {(w, h)}")
    return w, h


def build_palette(
    bg_rgb: tuple[int, int, int],
    rings_rgb: tuple[int, int, int],
    gamma: float = 1.15,
    num_colors: int = 256,
) -> list[int]:
    """Build an RGB palette (up to 256 entries) interpolating from bg_rgb to rings_rgb."""
    if gamma <= 0:
        raise ValueError(f"gamma must be positive, got {gamma}")
    if not (2 <= num_colors <= 256):
        raise ValueError(f"num_colors must be in 2..256, got {num_colors}")
    t = np.linspace(0.0, 1.0, num_colors, dtype=np.float32) ** gamma
    bg = np.array(bg_rgb, dtype=np.float32)
    fg = np.array(rings_rgb, dtype=np.float32)
    ramp = np.clip(np.round(bg[None, :] + (fg - bg)[None, :] * t[:, None]), 0, 255).astype(np.uint8)
    _, first_idx = np.unique(ramp, axis=0, return_index=True)
    unique_ramp = ramp[np.sort(first_idx)]
    return unique_ramp.flatten().tolist()


def _moore_average(grid: np.ndarray) -> np.ndarray:
    """Compute 3x3 Moore neighborhood average with periodic wrap-around boundaries."""
    up = np.roll(grid, -1, axis=0)
    down = np.roll(grid, 1, axis=0)
    total = (
        grid
        + np.roll(grid, -1, axis=1)
        + np.roll(grid, 1, axis=1)
        + up
        + np.roll(up, -1, axis=1)
        + np.roll(up, 1, axis=1)
        + down
        + np.roll(down, -1, axis=1)
        + np.roll(down, 1, axis=1)
    )
    return total * (1.0 / 9.0)


def _initialize_fields(
    height: int,
    width: int,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Initialize 3-species concentration grids with random noise and circular nucleation seeds."""
    a = rng.random((height, width), dtype=np.float32)
    b = rng.random((height, width), dtype=np.float32)
    c = rng.random((height, width), dtype=np.float32)

    yy, xx = np.ogrid[:height, :width]
    num_seeds = max(4, (width * height) // 16000)
    radius_base = max(4.0, min(width, height) * 0.045)

    for _ in range(num_seeds):
        cx = int(rng.integers(0, width))
        cy = int(rng.integers(0, height))
        r = radius_base * float(rng.uniform(0.7, 1.3))
        dx = np.minimum(np.abs(xx - cx), width - np.abs(xx - cx))
        dy = np.minimum(np.abs(yy - cy), height - np.abs(yy - cy))
        mask = (dx * dx + dy * dy) <= (r * r)
        a[mask] = 1.0
        b[mask] = 0.0
        c[mask] = 0.25

    return a, b, c


def _step_bz(
    a: np.ndarray,
    b: np.ndarray,
    c: np.ndarray,
    alpha: float,
    beta: float,
    gamma: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Advance the 3-species Belousov-Zhabotinsky reaction-diffusion system by one step."""
    ab = _moore_average(a)
    bb = _moore_average(b)
    cb = _moore_average(c)

    a_next = np.clip(ab + ab * (alpha * bb - gamma * cb), 0.0, 1.0)
    b_next = np.clip(bb + bb * (beta * cb - alpha * ab), 0.0, 1.0)
    c_next = np.clip(cb + cb * (gamma * ab - beta * bb), 0.0, 1.0)
    return a_next, b_next, c_next


def _downsample_field(a: np.ndarray, pixel_size: int) -> np.ndarray:
    """Average concentration field `a` over `pixel_size x pixel_size` blocks."""
    if pixel_size < 1:
        raise ValueError(f"pixel_size must be at least 1, got {pixel_size}")
    if pixel_size == 1:
        return a

    height, width = a.shape
    pad_h = (-height) % pixel_size
    pad_w = (-width) % pixel_size
    if pad_h or pad_w:
        a = np.pad(a, ((0, pad_h), (0, pad_w)), mode="edge")
    bh = a.shape[0] // pixel_size
    bw = a.shape[1] // pixel_size
    return a.reshape(bh, pixel_size, bw, pixel_size).mean(axis=(1, 3))


def _upsample_indices(
    cell_indices: np.ndarray, pixel_size: int, height: int, width: int
) -> np.ndarray:
    """Expand coarse palette indices back to `(height, width)` via nearest-neighbor blocks."""
    if pixel_size == 1:
        return cell_indices
    return np.repeat(np.repeat(cell_indices, pixel_size, axis=0), pixel_size, axis=1)[
        :height, :width
    ]


def _quantize_field(
    a: np.ndarray, num_colors: int, contrast_gamma: float = 1.15
) -> np.ndarray:
    """Map concentration field `a` in [0, 1] to palette indices in 0..num_colors-1."""
    # Mild contrast curve to suppress low-level refractory wake noise while keeping wave crests crisp.
    intensity = np.clip(a, 0.0, 1.0) ** contrast_gamma
    return np.clip(np.round(intensity * (num_colors - 1)), 0, num_colors - 1).astype(np.uint8)


def _optimize_cell_deltas(
    raw_indices: np.ndarray,
    canvas_indices: np.ndarray,
    coarse_a: np.ndarray,
    num_shades: int,
    diff_threshold: int,
    bg_snap_threshold: float = 0.25,
    despeckle: bool = True,
) -> np.ndarray:
    """Stabilize inter-frame cell deltas to maximize GIF LZW horizontal run lengths."""
    diff = np.abs(raw_indices.astype(np.int16) - canvas_indices.astype(np.int16))
    unchanged = diff <= diff_threshold
    # Allow cells that have fully decayed near zero to snap cleanly back to background index 0.
    if bg_snap_threshold > 0:
        snap_bg = (
            (raw_indices == 0)
            & (coarse_a < (bg_snap_threshold / max(1, num_shades - 1)))
            & (canvas_indices != 0)
        )
        unchanged &= ~snap_bg

    if not despeckle:
        return np.where(unchanged, canvas_indices, raw_indices)

    changed = ~unchanged
    h_neighbors = np.zeros(changed.shape, dtype=np.int8)
    h_neighbors[:, 1:] += changed[:, :-1]
    h_neighbors[:, :-1] += changed[:, 1:]
    v_neighbors = np.zeros(changed.shape, dtype=np.int8)
    v_neighbors[1:, :] += changed[:-1, :]
    v_neighbors[:-1, :] += changed[1:, :]
    isolated = (h_neighbors == 0) & ((v_neighbors == 0) | (diff <= diff_threshold + 1))
    unchanged |= isolated

    cell_indices = np.where(unchanged, canvas_indices, raw_indices)

    changed_now = cell_indices != canvas_indices
    same_lr = np.zeros(cell_indices.shape, dtype=bool)
    same_lr[:, 1:-1] = (
        changed_now[:, :-2]
        & changed_now[:, 2:]
        & (~changed_now[:, 1:-1])
        & (cell_indices[:, :-2] == cell_indices[:, 2:])
        & (raw_indices[:, 1:-1] == cell_indices[:, :-2])
    )
    return np.where(same_lr, raw_indices, cell_indices)


def _render_frame(
    a: np.ndarray,
    palette: list[int],
    pixel_size: int = 1,
    contrast_gamma: float = 1.15,
) -> Image.Image:
    """Convert concentration field `a` to a paletted PIL image."""
    num_colors = max(1, len(palette) // 3)
    height, width = a.shape
    coarse_a = _downsample_field(a, pixel_size)
    cell_indices = _quantize_field(coarse_a, num_colors, contrast_gamma=contrast_gamma)
    indices = _upsample_indices(cell_indices, pixel_size, height, width)
    frame = Image.fromarray(indices, mode="P")
    frame.putpalette(palette)
    return frame


BASE_STEPS_PER_SECOND = 40.0


def simulate_bz_reaction(
    output_path: str = "bz_reaction.gif",
    size: SizeLike = (320, 320),
    length: float = 5.0,
    framerate: int = 20,
    bg_color: ColorLike = "#0b132b",
    rings_color: ColorLike = "#00f5d4",
    speed: float = 1.0,
    alpha: float = 1.2,
    beta: float = 1.0,
    gamma: float = 1.0,
    warmup_steps: int = 65,
    steps_per_frame: float | None = None,
    seed: int | None = 42,
    colors: int = 10,
    pixel_size: int = 1,
    palette_gamma: float = 1.15,
    contrast_gamma: float = 1.15,
    scanline_smooth: float = 0.15,
    bg_snap_threshold: float = 0.25,
    despeckle: bool = True,
    snap_steps: bool = True,
    optimize: bool = True,
    diff_threshold: int = 1,
) -> str:
    """Simulate a 2D Belousov-Zhabotinsky reaction and save it as an animated GIF."""
    if length <= 0:
        raise ValueError(f"length must be positive, got {length}")
    if framerate <= 0:
        raise ValueError(f"framerate must be positive, got {framerate}")
    if speed <= 0:
        raise ValueError(f"speed must be positive, got {speed}")
    if warmup_steps < 0:
        raise ValueError(f"warmup_steps must be non-negative, got {warmup_steps}")
    if steps_per_frame is not None and steps_per_frame <= 0:
        raise ValueError(f"steps_per_frame must be positive, got {steps_per_frame}")
    if not (2 <= colors <= 256):
        raise ValueError(f"colors must be between 2 and 256, got {colors}")
    if pixel_size < 1:
        raise ValueError(f"pixel_size must be at least 1, got {pixel_size}")
    if palette_gamma <= 0:
        raise ValueError(f"palette_gamma must be positive, got {palette_gamma}")
    if contrast_gamma <= 0:
        raise ValueError(f"contrast_gamma must be positive, got {contrast_gamma}")
    if not (0.0 <= scanline_smooth <= 0.5):
        raise ValueError(
            f"scanline_smooth must be between 0.0 and 0.5, got {scanline_smooth}"
        )
    if bg_snap_threshold < 0:
        raise ValueError(
            f"bg_snap_threshold must be non-negative, got {bg_snap_threshold}"
        )
    if diff_threshold < 0:
        raise ValueError(f"diff_threshold must be non-negative, got {diff_threshold}")

    width, height = parse_size(size)
    bg_rgb = parse_color(bg_color)
    rings_rgb = parse_color(rings_color)
    max_shades = colors - 1 if optimize and colors > 2 else colors
    palette = build_palette(
        bg_rgb, rings_rgb, gamma=palette_gamma, num_colors=max_shades
    )
    num_shades = len(palette) // 3

    total_frames = max(1, int(round(length * framerate)))
    frame_duration_ms = max(10, int(round(1000.0 / framerate)))
    step_advance = (
        steps_per_frame * speed
        if steps_per_frame is not None
        else (BASE_STEPS_PER_SECOND * speed) / framerate
    )

    rng = np.random.default_rng(seed)
    a, b, c = _initialize_fields(height, width, rng)

    for _ in range(warmup_steps):
        a, b, c = _step_bz(a, b, c, alpha, beta, gamma)

    a_prev = a
    curr_step = 0
    canvas_indices: np.ndarray | None = None
    frames: list[Image.Image] = []
    for frame_idx in range(total_frames):
        sim_time = frame_idx * step_advance
        target_step = int(np.ceil(sim_time))
        while curr_step < target_step:
            a_prev = a
            a, b, c = _step_bz(a, b, c, alpha, beta, gamma)
            curr_step += 1

        if (optimize and snap_steps and step_advance <= 1.0) or curr_step == 0:
            a_frame = a
        else:
            frac = sim_time - (curr_step - 1)
            a_frame = (1.0 - frac) * a_prev + frac * a

        coarse_a = _downsample_field(a_frame, pixel_size)
        if optimize and scanline_smooth > 0:
            coarse_a = (1.0 - 2.0 * scanline_smooth) * coarse_a + scanline_smooth * (
                np.roll(coarse_a, 1, axis=1) + np.roll(coarse_a, -1, axis=1)
            )
        cell_indices = _quantize_field(
            coarse_a, num_shades, contrast_gamma=contrast_gamma
        )
        if optimize and (diff_threshold > 0 or despeckle) and canvas_indices is not None:
            cell_indices = _optimize_cell_deltas(
                cell_indices,
                canvas_indices,
                coarse_a,
                num_shades,
                diff_threshold,
                bg_snap_threshold=bg_snap_threshold,
                despeckle=despeckle,
            )
        if optimize:
            canvas_indices = cell_indices
        indices = _upsample_indices(cell_indices, pixel_size, height, width)
        frame = Image.fromarray(indices, mode="P")
        frame.putpalette(palette)
        frames.append(frame)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        out,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=frame_duration_ms,
        loop=0,
        disposal=1 if optimize else 2,
        optimize=optimize,
    )
    return str(out)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate an animated GIF of a 2D Belousov-Zhabotinsky reaction simulation."
    )
    parser.add_argument("-o", "--output", default="bz_reaction.gif", help="Output GIF path.")
    parser.add_argument(
        "-s", "--size", default="320x320", help="Canvas size as WxH or N (e.g. 320x320 or 256)."
    )
    parser.add_argument(
        "-l", "--length", type=float, default=5.0, help="Animation duration in seconds."
    )
    parser.add_argument(
        "-f", "--framerate", type=int, default=20, help="Frames per second."
    )
    parser.add_argument(
        "--bg-color", default="#0b132b", help="Background color (hex, name, or R,G,B)."
    )
    parser.add_argument(
        "--rings-color", default="#00f5d4", help="Wavefront rings color (hex, name, or R,G,B)."
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Reaction playback speed multiplier (e.g. 0.5 for half speed, 2.0 for double speed).",
    )
    parser.add_argument(
        "--warmup", type=int, default=65, help="Warmup simulation steps before recording."
    )
    parser.add_argument(
        "--steps-per-frame",
        type=float,
        default=None,
        help="Optional override for base simulation steps per frame (scaled by --speed).",
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Random seed for reproducible initial conditions."
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=1.2,
        help="Reaction rate parameter alpha (A + B -> 2A, default: 1.2).",
    )
    parser.add_argument(
        "--beta",
        type=float,
        default=1.0,
        help="Reaction rate parameter beta (B + C -> 2B, default: 1.0).",
    )
    parser.add_argument(
        "--gamma",
        type=float,
        default=1.0,
        help="Reaction rate parameter gamma (C + A -> 2C, default: 1.0).",
    )
    parser.add_argument(
        "-c",
        "--colors",
        type=int,
        default=10,
        help="Number of gradient palette colors (2..256, default: 10).",
    )
    parser.add_argument(
        "-p",
        "--pixel-size",
        "--raster-size",
        dest="pixel_size",
        type=int,
        default=1,
        help="Raster pixel block size in pixels (1 for full resolution, default: 1).",
    )
    parser.add_argument(
        "--palette-gamma",
        type=float,
        default=1.15,
        help="Palette color ramp gamma curve exponent (default: 1.15).",
    )
    parser.add_argument(
        "--contrast-gamma",
        type=float,
        default=1.15,
        help="Field quantization contrast exponent (>1 suppresses wake noise, default: 1.15).",
    )
    parser.add_argument(
        "--scanline-smooth",
        type=float,
        default=0.15,
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
        default=1,
        help="Inter-frame palette index diff tolerance for delta compression (0 for exact, default: 1).",
    )
    parser.add_argument(
        "--bg-snap-threshold",
        type=float,
        default=0.25,
        help="Threshold factor to snap decaying cells back to background index 0 (0 to disable, default: 0.25).",
    )
    parser.add_argument(
        "--despeckle",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Suppress isolated 1-cell delta speckles and bridge 1-cell horizontal gaps (default: enabled).",
    )
    parser.add_argument(
        "--snap-steps",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Snap to discrete simulation steps when step_advance <= 1.0 instead of sub-step linear interpolation (default: enabled).",
    )
    parser.add_argument(
        "--optimize",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable GIF delta-frame transparency and LZW optimizations (default: enabled).",
    )
    return parser


if __name__ == "__main__":
    args = _build_arg_parser().parse_args()
    saved_path = simulate_bz_reaction(
        output_path=args.output,
        size=args.size,
        length=args.length,
        framerate=args.framerate,
        bg_color=args.bg_color,
        rings_color=args.rings_color,
        speed=args.speed,
        alpha=args.alpha,
        beta=args.beta,
        gamma=args.gamma,
        warmup_steps=args.warmup,
        steps_per_frame=args.steps_per_frame,
        seed=args.seed,
        colors=args.colors,
        pixel_size=args.pixel_size,
        palette_gamma=args.palette_gamma,
        contrast_gamma=args.contrast_gamma,
        scanline_smooth=args.scanline_smooth,
        bg_snap_threshold=args.bg_snap_threshold,
        despeckle=args.despeckle,
        snap_steps=args.snap_steps,
        optimize=args.optimize,
        diff_threshold=args.diff_threshold,
    )
    print(f"Saved Belousov-Zhabotinsky simulation GIF to: {saved_path}")
