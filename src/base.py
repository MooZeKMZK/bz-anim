"""Core 2D Belousov-Zhabotinsky (BZ) reaction-diffusion simulation engine and GIF exporter."""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path
import tomllib
from typing import Callable, Sequence

import numpy as np
from PIL import Image, ImageColor


ColorLike = str | Sequence[int]
SizeLike = int | Sequence[int] | str

BASE_STEPS_PER_SECOND = 40.0
DEFAULT_CONFIG_FILENAME = "config.toml"


@dataclass
class SimulationConfig:
    """Configuration parameters for a 2D Belousov-Zhabotinsky reaction simulation."""

    output_path: str = "bz_reaction.gif"
    size: SizeLike = (320, 320)
    length: float = 5.0
    framerate: int = 20
    bg_color: ColorLike = "#0b132b"
    rings_color: ColorLike = "#00f5d4"
    palette_mode: str = "gradient"  # "gradient" or "ferroin"
    speed: float = 1.0
    alpha: float = 1.2
    beta: float = 1.0
    gamma: float = 1.0
    warmup_steps: int = 65
    steps_per_frame: float | None = None
    seed: int | None = 42
    colors: int = 10
    pixel_size: int = 1
    palette_gamma: float = 1.15
    contrast_gamma: float = 1.15
    scanline_smooth: float = 0.15
    bg_snap_threshold: float = 0.25
    despeckle: bool = True
    snap_steps: bool = True
    optimize: bool = True
    diff_threshold: int = 1
    seamless_loop: bool = True
    loop_wipe_ratio: float = 0.28
    pulse_count: int = 3
    pulse_speed: float = 1.45
    pulse_sharpness: float = 18.0
    pulse_decay: float = 4.0
    pulse_noise_amp: float = 0.08
    pulse_noise_freq: int = 3
    tileable: bool = True

    def validate(self) -> None:
        """Validate all simulation parameters and raise ValueError if invalid."""
        if self.length <= 0:
            raise ValueError(f"length must be positive, got {self.length}")
        if self.framerate <= 0:
            raise ValueError(f"framerate must be positive, got {self.framerate}")
        if self.speed <= 0:
            raise ValueError(f"speed must be positive, got {self.speed}")
        if self.warmup_steps < 0:
            raise ValueError(f"warmup_steps must be non-negative, got {self.warmup_steps}")
        if self.steps_per_frame is not None and self.steps_per_frame <= 0:
            raise ValueError(f"steps_per_frame must be positive, got {self.steps_per_frame}")
        if not (2 <= self.colors <= 256):
            raise ValueError(f"colors must be between 2 and 256, got {self.colors}")
        if self.pixel_size < 1:
            raise ValueError(f"pixel_size must be at least 1, got {self.pixel_size}")
        if self.palette_gamma <= 0:
            raise ValueError(f"palette_gamma must be positive, got {self.palette_gamma}")
        if self.contrast_gamma <= 0:
            raise ValueError(f"contrast_gamma must be positive, got {self.contrast_gamma}")
        if self.palette_mode not in {"gradient", "ferroin"}:
            raise ValueError(
                f"palette_mode must be 'gradient' or 'ferroin', got {self.palette_mode!r}"
            )
        if not (0.0 <= self.scanline_smooth <= 0.5):
            raise ValueError(
                f"scanline_smooth must be between 0.0 and 0.5, got {self.scanline_smooth}"
            )
        if self.bg_snap_threshold < 0:
            raise ValueError(
                f"bg_snap_threshold must be non-negative, got {self.bg_snap_threshold}"
            )
        if self.diff_threshold < 0:
            raise ValueError(f"diff_threshold must be non-negative, got {self.diff_threshold}")
        if not (0.05 <= self.loop_wipe_ratio <= 0.95):
            raise ValueError(
                f"loop_wipe_ratio must be between 0.05 and 0.95, got {self.loop_wipe_ratio}"
            )
        if self.pulse_count < 1:
            raise ValueError(f"pulse_count must be at least 1, got {self.pulse_count}")
        if self.pulse_speed <= 0:
            raise ValueError(f"pulse_speed must be positive, got {self.pulse_speed}")
        if self.pulse_sharpness <= 0:
            raise ValueError(f"pulse_sharpness must be positive, got {self.pulse_sharpness}")
        if self.pulse_decay <= 0:
            raise ValueError(f"pulse_decay must be positive, got {self.pulse_decay}")
        if self.pulse_noise_amp < 0:
            raise ValueError(
                f"pulse_noise_amp must be non-negative, got {self.pulse_noise_amp}"
            )
        if self.pulse_noise_freq < 1:
            raise ValueError(
                f"pulse_noise_freq must be at least 1, got {self.pulse_noise_freq}"
            )
        parse_size(self.size)
        parse_color(self.bg_color)
        parse_color(self.rings_color)

    @classmethod
    def from_toml(cls, path: str | Path) -> SimulationConfig:
        """Load a `SimulationConfig` from a TOML file (flat or sectioned into `[canvas]`, `[palette]`, `[kinetics]`, `[loop]`, `[compression]`)."""
        p = Path(path)
        with p.open("rb") as f:
            raw = tomllib.load(f)

        merged: dict[str, object] = {}
        for key, val in raw.items():
            if isinstance(val, dict):
                for sub_k, sub_v in val.items():
                    merged[sub_k.lower().replace("-", "_")] = sub_v
            else:
                merged[key.lower().replace("-", "_")] = val

        alias_map = {
            "output": "output_path",
            "warmup": "warmup_steps",
            "raster_size": "pixel_size",
            "wipe_ratio": "loop_wipe_ratio",
        }
        for alias_k, target_k in alias_map.items():
            if alias_k in merged and target_k not in merged:
                merged[target_k] = merged.pop(alias_k)

        # Treat negative seed or "none" string as None (random seed)
        if "seed" in merged:
            s_val = merged["seed"]
            if s_val == "" or (isinstance(s_val, str) and s_val.lower() in {"none", "random", "null"}) or (isinstance(s_val, int) and s_val < 0):
                merged["seed"] = None

        if "steps_per_frame" in merged:
            spf = merged["steps_per_frame"]
            if spf == "" or (isinstance(spf, str) and spf.lower() in {"none", "auto", "null"}) or (isinstance(spf, (int, float)) and spf <= 0):
                merged["steps_per_frame"] = None

        valid_fields = {f.name for f in fields(cls)}
        kwargs = {k: v for k, v in merged.items() if k in valid_fields}
        cfg = cls(**kwargs)  # type: ignore[arg-type]
        cfg.validate()
        return cfg

    def to_toml_string(self) -> str:
        """Serialize this `SimulationConfig` into a structured, commented TOML string."""
        w, h = parse_size(self.size)
        bg_hex = "#{:02x}{:02x}{:02x}".format(*parse_color(self.bg_color)) if not isinstance(self.bg_color, str) else self.bg_color
        rings_hex = "#{:02x}{:02x}{:02x}".format(*parse_color(self.rings_color)) if not isinstance(self.rings_color, str) else self.rings_color
        seed_val = -1 if self.seed is None else int(self.seed)
        spf_line = (
            f"steps_per_frame = {float(self.steps_per_frame)}\n"
            if self.steps_per_frame is not None
            else "# steps_per_frame = 2.0  # Optional override (uncomment to set explicit steps/frame)\n"
        )
        return (
            "# Belousov-Zhabotinsky Reaction-Diffusion Simulation Options (config.toml)\n\n"
            "[canvas]\n"
            f'output_path = "{self.output_path}"\n'
            f'size = "{w}x{h}"\n'
            f"length = {float(self.length)}\n"
            f"framerate = {int(self.framerate)}\n"
            f"tileable = {'true' if self.tileable else 'false'}\n\n"
            "[palette]\n"
            f'palette_mode = "{self.palette_mode}"  # "gradient" or "ferroin"\n'
            f'bg_color = "{bg_hex}"\n'
            f'rings_color = "{rings_hex}"\n'
            f"colors = {int(self.colors)}\n"
            f"pixel_size = {int(self.pixel_size)}\n"
            f"palette_gamma = {float(self.palette_gamma)}\n"
            f"contrast_gamma = {float(self.contrast_gamma)}\n\n"
            "[kinetics]\n"
            f"speed = {float(self.speed)}\n"
            f"alpha = {float(self.alpha)}\n"
            f"beta = {float(self.beta)}\n"
            f"gamma = {float(self.gamma)}\n"
            f"warmup_steps = {int(self.warmup_steps)}\n"
            f"seed = {seed_val}  # Use -1 for random seed\n"
            f"{spf_line}\n"
            "[loop]\n"
            f"seamless_loop = {'true' if self.seamless_loop else 'false'}\n"
            f"loop_wipe_ratio = {float(self.loop_wipe_ratio)}\n"
            f"pulse_count = {int(self.pulse_count)}\n"
            f"pulse_speed = {float(self.pulse_speed)}\n"
            f"pulse_sharpness = {float(self.pulse_sharpness)}\n"
            f"pulse_decay = {float(self.pulse_decay)}\n"
            f"pulse_noise_amp = {float(self.pulse_noise_amp)}\n"
            f"pulse_noise_freq = {int(self.pulse_noise_freq)}\n\n"
            "[compression]\n"
            f"optimize = {'true' if self.optimize else 'false'}\n"
            f"despeckle = {'true' if self.despeckle else 'false'}\n"
            f"snap_steps = {'true' if self.snap_steps else 'false'}\n"
            f"scanline_smooth = {float(self.scanline_smooth)}\n"
            f"diff_threshold = {int(self.diff_threshold)}\n"
            f"bg_snap_threshold = {float(self.bg_snap_threshold)}\n"
        )

    def save_toml(self, path: str | Path) -> Path:
        """Write this `SimulationConfig` to a TOML file at `path`."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_toml_string(), encoding="utf-8")
        return p


def get_default_config_candidates(filename: str) -> list[Path]:
    """Return ordered candidate paths for `config.toml` or `theme.toml` (CWD -> XDG -> /etc/bz-anim -> repo/package)."""
    import os

    candidates: list[Path] = [Path.cwd() / filename]
    xdg_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_home:
        candidates.append(Path(xdg_home) / "bz-anim" / filename)
    candidates.append(Path.home() / ".config" / "bz-anim" / filename)
    candidates.append(Path("/etc/bz-anim") / filename)
    candidates.append(Path(__file__).resolve().parent / "defaults" / filename)
    candidates.append(Path(__file__).resolve().parent.parent / filename)
    return candidates


def load_config_file(path: str | Path | None = None) -> SimulationConfig:
    """Load a `SimulationConfig` from `path`, or search CWD -> XDG -> `/etc/bz-anim` -> package defaults."""
    if path is not None:
        return SimulationConfig.from_toml(path)

    for candidate in get_default_config_candidates(DEFAULT_CONFIG_FILENAME):
        if candidate.is_file():
            try:
                return SimulationConfig.from_toml(candidate)
            except Exception:
                pass
    return SimulationConfig()


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


def build_palette_array(
    bg_rgb: tuple[int, int, int],
    rings_rgb: tuple[int, int, int],
    gamma: float = 1.15,
    num_colors: int = 256,
    palette_mode: str = "gradient",
) -> np.ndarray:
    """Build an (N, 3) uint8 RGB palette array.

    Supports two chemical color lookup modes:
    - `'gradient'`: 2-stop gamma-curved ramp from `bg_rgb` to `rings_rgb`.
    - `'ferroin'`: Multi-stop 1D LUT inspired by ferroin-catalyzed BZ reactions
      (deep rust-red resting medium -> pale lavender/white transitional fringes ->
      bright cobalt-blue/cyan oxidized wavefronts). If custom `bg_rgb` / `rings_rgb`
      are provided, they anchor the resting medium and peak oxidized wavefront while
      preserving the pale lavender transitional fringe.
    """
    if gamma <= 0:
        raise ValueError(f"gamma must be positive, got {gamma}")
    if not (2 <= num_colors <= 256):
        raise ValueError(f"num_colors must be in 2..256, got {num_colors}")
    t = np.linspace(0.0, 1.0, num_colors, dtype=np.float32) ** gamma

    if palette_mode == "ferroin":
        default_bg = (11, 19, 43)
        default_fg = (0, 245, 212)
        rest_rgb = (78, 18, 16) if bg_rgb == default_bg else bg_rgb
        peak_rgb = (18, 228, 255) if rings_rgb == default_fg else rings_rgb
        stops_t = np.array([0.0, 0.35, 0.62, 0.84, 1.0], dtype=np.float32)
        stops_rgb = np.array(
            [
                rest_rgb,            # Deep rust-red resting medium
                (148, 48, 42),       # Warm ferric/ferroin terracotta transition
                (234, 218, 248),     # Pale lavender / white transitional fringe
                (28, 118, 232),      # Rich cobalt-blue oxidized wave body
                peak_rgb,            # Bright cyan oxidized wavefront crest
            ],
            dtype=np.float32,
        )
        r = np.interp(t, stops_t, stops_rgb[:, 0])
        g = np.interp(t, stops_t, stops_rgb[:, 1])
        b = np.interp(t, stops_t, stops_rgb[:, 2])
        ramp = np.clip(np.round(np.stack([r, g, b], axis=1)), 0, 255).astype(np.uint8)
    else:
        bg = np.array(bg_rgb, dtype=np.float32)
        fg = np.array(rings_rgb, dtype=np.float32)
        ramp = np.clip(
            np.round(bg[None, :] + (fg - bg)[None, :] * t[:, None]), 0, 255
        ).astype(np.uint8)

    _, first_idx = np.unique(ramp, axis=0, return_index=True)
    return ramp[np.sort(first_idx)]


def build_palette(
    bg_rgb: tuple[int, int, int],
    rings_rgb: tuple[int, int, int],
    gamma: float = 1.15,
    num_colors: int = 256,
    palette_mode: str = "gradient",
) -> list[int]:
    """Build a flat RGB palette list (up to 256 entries) interpolating from bg_rgb to rings_rgb."""
    return (
        build_palette_array(
            bg_rgb,
            rings_rgb,
            gamma=gamma,
            num_colors=num_colors,
            palette_mode=palette_mode,
        )
        .flatten()
        .tolist()
    )


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


def _toroidal_4d_noise(
    height: int,
    width: int,
    rng: np.random.Generator,
    base_freq: int = 3,
    octaves: int = 3,
) -> np.ndarray:
    """Generate smooth, strictly periodic 2D noise by sampling 4D Fourier/Perlin modes on a 2D torus.

    Maps normalized `[0, 1)` coordinates `(u, v)` onto the 4D torus:
    `(cos(2*pi*u), sin(2*pi*u), cos(2*pi*v), sin(2*pi*v))`
    so the resulting distortion field wraps seamlessly across both X and Y boundaries.
    """
    u = np.arange(width, dtype=np.float32) / float(max(1, width))
    v = np.arange(height, dtype=np.float32) / float(max(1, height))
    uu, vv = np.meshgrid(u, v)

    two_pi = np.float32(2.0 * np.pi)
    noise = np.zeros((height, width), dtype=np.float32)
    total_weight = 0.0

    for octave in range(octaves):
        freq = max(1, base_freq * (2**octave))
        weight = 1.0 / (2.0**octave)
        total_weight += weight

        # Project 4D torus coordinates (cos(2pi*k*u), sin(2pi*k*u), cos(2pi*m*v), sin(2pi*m*v))
        # with coupled random 4D gradient vectors for isotropic periodic warping
        for _ in range(4):
            kx = int(rng.integers(1, freq + 1)) * int(rng.choice([-1, 1]))
            ky = int(rng.integers(1, freq + 1)) * int(rng.choice([-1, 1]))
            g4 = rng.normal(0.0, 1.0, size=4).astype(np.float32)
            g4 /= max(1e-6, float(np.linalg.norm(g4)))
            phase = np.float32(rng.uniform(0.0, 2.0 * np.pi))

            torus_proj = (
                g4[0] * np.cos(two_pi * kx * uu)
                + g4[1] * np.sin(two_pi * kx * uu)
                + g4[2] * np.cos(two_pi * ky * vv)
                + g4[3] * np.sin(two_pi * ky * vv)
            )
            noise += np.float32(weight) * np.sin(two_pi * torus_proj + phase)

    if total_weight > 0:
        noise /= np.float32(total_weight)
    max_abs = float(np.max(np.abs(noise)))
    if max_abs > 1e-6:
        noise /= np.float32(max_abs)
    return noise


def _generate_pulse_origins(
    pulse_count: int,
    rng: np.random.Generator,
) -> list[tuple[float, float, float]]:
    """Generate anti-grid staggered pulse origins `(u0, v0, delay)` in normalized `[0, 1)` torus space.

    Instead of a single centered radial pulse (which creates an obvious polka-dot grid when tiled),
    places 2-3+ staggered radial pulses at golden-ratio offset coordinates within the tile so their
    expanding rings collide and merge organically across tile boundaries.
    """
    count = max(1, pulse_count)
    u_base = float(rng.uniform(0.0, 1.0))
    v_base = float(rng.uniform(0.0, 1.0))
    # Golden-ratio quasi-random offsets in 2D prevent collinear or grid-aligned origins
    phi1 = 0.618033988749895
    phi2 = 0.7548776662466927
    origins: list[tuple[float, float, float]] = []
    for i in range(count):
        jitter_u = float(rng.uniform(-0.06, 0.06)) if count > 1 else 0.0
        jitter_v = float(rng.uniform(-0.06, 0.06)) if count > 1 else 0.0
        u0 = (u_base + i * phi1 + jitter_u) % 1.0
        v0 = (v_base + i * phi2 + jitter_v) % 1.0
        # Slight temporal stagger in [0, 0.14] so rings collide asymmetrically
        delay = (i / float(max(1, count))) * 0.14 if count > 1 else 0.0
        origins.append((u0, v0, delay))
    return origins


def _build_toroidal_arrival_map(
    height: int,
    width: int,
    pulse_count: int,
    noise_amp: float,
    noise_freq: int,
    rng: np.random.Generator,
) -> tuple[np.ndarray, float]:
    """Compute a tileable normalized arrival-time field for the chemical oxidation pulse wipe.

    Uses wrapped toroidal distance from staggered origins plus 4D torus noise distortion:
      `dx = min(|x - x0|, W - |x - x0|)`
      `dy = min(|y - y0|, H - |y - y0|)`
      `dist = sqrt(dx^2 + dy^2)`
    """
    yy, xx = np.ogrid[:height, :width]
    xx_f = xx.astype(np.float32)
    yy_f = yy.astype(np.float32)
    diag = float(np.hypot(width * 0.5, height * 0.5))
    inv_diag = 1.0 / max(1.0, diag)

    origins = _generate_pulse_origins(pulse_count, rng)
    arrival = np.full((height, width), np.inf, dtype=np.float32)

    for u0, v0, delay in origins:
        x0 = np.float32(u0 * width)
        y0 = np.float32(v0 * height)
        abs_dx = np.abs(xx_f - x0)
        abs_dy = np.abs(yy_f - y0)
        dx = np.minimum(abs_dx, np.float32(width) - abs_dx)
        dy = np.minimum(abs_dy, np.float32(height) - abs_dy)
        norm_dist = np.sqrt(dx * dx + dy * dy) * np.float32(inv_diag)
        arrival = np.minimum(arrival, norm_dist + np.float32(delay))

    if noise_amp > 0.0:
        torus_noise = _toroidal_4d_noise(
            height, width, rng, base_freq=max(1, noise_freq)
        )
        # Attenuate distortion right at the origin core so nucleation points stay clean
        core_atten = np.clip(arrival / 0.15, 0.0, 1.0)
        arrival = np.maximum(
            0.0, arrival + np.float32(noise_amp) * torus_noise * core_atten
        )

    max_arrival = float(np.max(arrival))
    return arrival, max(1e-4, max_arrival)


def _blend_pulse_wipe_field(
    a_tail: np.ndarray,
    a_head: np.ndarray,
    arrival_map: np.ndarray,
    max_arrival: float,
    wipe_progress: float,
    pulse_speed: float = 1.45,
    pulse_sharpness: float = 18.0,
    pulse_decay: float = 4.0,
) -> np.ndarray:
    """Blend tail and head scalar concentration fields across an asymmetric oxidation trigger wave.

    - Ahead of the wave (`s < 0`): samples `a_tail` (frames `N` to `N + K - 1`).
    - Behind the wave (`s > 0`): reveals `a_head` (frames `0` to `K - 1`).
    - On the wave crest (`s == 0`): drives scalar chemical concentration to peak oxidation (`1.0`)
      with a razor-sharp leading edge and a gradual trailing recovery tail.
    """
    # Scale wave radius so that at wipe_progress=0 the entire canvas is ahead of the wave (a_tail)
    # and at wipe_progress=1 the trailing recovery tail has completely settled to a_head.
    lead_margin = 3.5 / max(1.0, pulse_sharpness)
    tail_margin = 4.2 / max(0.5, pulse_decay)
    total_span = max_arrival + lead_margin + tail_margin
    wave_radius = -lead_margin + float(np.clip(wipe_progress, 0.0, 1.0)) * total_span

    # Signed phase distance behind the wave crest ( scaled by pulse_speed )
    s = (np.float32(wave_radius) - arrival_map) * np.float32(max(0.5, pulse_speed))

    # Smooth sigmoid state handoff centered right under the peak oxidation crest
    handoff = (1.0 / (1.0 + np.exp(np.clip(-pulse_sharpness * s, -40.0, 40.0)))).astype(
        np.float32
    )
    base_field = (1.0 - handoff) * a_tail + handoff * a_head

    # Asymmetric oxidation flash profile:
    # - Razor-sharp Gaussian leading edge ahead of crest (s < 0)
    # - Slower exponential refractory recovery tail behind crest (s >= 0)
    lead_profile = np.exp(-np.square(np.minimum(s, 0.0) * np.float32(pulse_sharpness)))
    trail_profile = np.exp(-np.maximum(s, 0.0) * np.float32(pulse_decay))
    crest_flash = np.where(s < 0.0, lead_profile, trail_profile).astype(np.float32)

    # Push scalar concentration to peak oxidation (1.0) on the wave crest before LUT mapping
    blended = base_field + crest_flash * (1.0 - base_field)
    return np.clip(blended, 0.0, 1.0).astype(np.float32)


def _downsample_field(a: np.ndarray, pixel_size: int) -> np.ndarray:
    """Average concentration field `a` over `pixel_size x pixel_size` blocks with periodic wrap padding."""
    if pixel_size < 1:
        raise ValueError(f"pixel_size must be at least 1, got {pixel_size}")
    if pixel_size == 1:
        return a

    height, width = a.shape
    pad_h = (-height) % pixel_size
    pad_w = (-width) % pixel_size
    if pad_h or pad_w:
        a = np.pad(a, ((0, pad_h), (0, pad_w)), mode="wrap")
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
    tileable: bool = True,
) -> np.ndarray:
    """Stabilize inter-frame cell deltas to maximize GIF LZW horizontal run lengths.

    When `tileable=True`, uses toroidal (`np.roll`) neighborhood checks so delta despeckling
    never introduces seam discrepancies along the top/bottom or left/right canvas borders.
    """
    diff = np.abs(raw_indices.astype(np.int16) - canvas_indices.astype(np.int16))
    unchanged = diff <= diff_threshold
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
    if tileable:
        h_neighbors = (
            np.roll(changed, 1, axis=1).astype(np.int8)
            + np.roll(changed, -1, axis=1).astype(np.int8)
        )
        v_neighbors = (
            np.roll(changed, 1, axis=0).astype(np.int8)
            + np.roll(changed, -1, axis=0).astype(np.int8)
        )
    else:
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
    if tileable:
        left_chg = np.roll(changed_now, 1, axis=1)
        right_chg = np.roll(changed_now, -1, axis=1)
        left_idx = np.roll(cell_indices, 1, axis=1)
        right_idx = np.roll(cell_indices, -1, axis=1)
        same_lr = (
            left_chg
            & right_chg
            & (~changed_now)
            & (left_idx == right_idx)
            & (raw_indices == left_idx)
        )
    else:
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


class BZSimulator:
    """Stateful Belousov-Zhabotinsky reaction-diffusion simulator for live previews and rendering."""

    def __init__(self, config: SimulationConfig | None = None) -> None:
        self.config = config or SimulationConfig()
        self.config.validate()
        self.width: int = 320
        self.height: int = 320
        self.bg_rgb: tuple[int, int, int] = (11, 19, 43)
        self.rings_rgb: tuple[int, int, int] = (0, 245, 212)
        self.palette_array: np.ndarray = np.zeros((10, 3), dtype=np.uint8)
        self.palette_flat: list[int] = []
        self.num_shades: int = 10
        self.a: np.ndarray = np.zeros((1, 1), dtype=np.float32)
        self.b: np.ndarray = np.zeros((1, 1), dtype=np.float32)
        self.c: np.ndarray = np.zeros((1, 1), dtype=np.float32)
        self.a_prev: np.ndarray = np.zeros((1, 1), dtype=np.float32)
        self.curr_step: int = 0
        self.sim_time: float = 0.0
        self.frame_idx: int = 0
        self._head_fields: list[np.ndarray] = []
        self._arrival_map: np.ndarray = np.zeros((1, 1), dtype=np.float32)
        self._max_arrival: float = 1.0
        self.reset()

    def update_visual_params(self) -> None:
        """Rebuild color palette and visual parameters without resetting the chemical grids."""
        self.bg_rgb = parse_color(self.config.bg_color)
        self.rings_rgb = parse_color(self.config.rings_color)
        max_shades = (
            self.config.colors - 1
            if self.config.optimize and self.config.colors > 2
            else self.config.colors
        )
        self.palette_array = build_palette_array(
            self.bg_rgb,
            self.rings_rgb,
            gamma=self.config.palette_gamma,
            num_colors=max_shades,
            palette_mode=self.config.palette_mode,
        )
        self.palette_flat = self.palette_array.flatten().tolist()
        self.num_shades = len(self.palette_array)
        self._smooth_palette_64 = build_palette_array(
            self.bg_rgb,
            self.rings_rgb,
            gamma=self.config.palette_gamma,
            num_colors=max(self.num_shades, 64),
            palette_mode=self.config.palette_mode,
        )
        self._tui_palette_16 = build_palette_array(
            self.bg_rgb,
            self.rings_rgb,
            gamma=self.config.palette_gamma,
            num_colors=min(max(self.num_shades, 4), 6),
            palette_mode=self.config.palette_mode,
        )
        if len(self.palette_array) > 0:
            self.bg_rgb = tuple(int(c) for c in self.palette_array[0])  # type: ignore[assignment]

    def reset(self, config: SimulationConfig | None = None) -> None:
        """Re-initialize the chemical grids and run warmup steps."""
        if config is not None:
            config.validate()
            self.config = config
        self.width, self.height = parse_size(self.config.size)
        self.update_visual_params()

        rng = np.random.default_rng(self.config.seed)
        self.a, self.b, self.c = _initialize_fields(self.height, self.width, rng)
        for _ in range(self.config.warmup_steps):
            self.a, self.b, self.c = _step_bz(
                self.a,
                self.b,
                self.c,
                self.config.alpha,
                self.config.beta,
                self.config.gamma,
            )
        self.a_prev = self.a
        self.curr_step = 0
        self.sim_time = 0.0
        self.frame_idx = 0
        self._head_fields = [self.a.copy()]
        self._arrival_map, self._max_arrival = _build_toroidal_arrival_map(
            self.height,
            self.width,
            pulse_count=self.config.pulse_count,
            noise_amp=self.config.pulse_noise_amp,
            noise_freq=self.config.pulse_noise_freq,
            rng=rng,
        )

    @property
    def step_advance(self) -> float:
        """Compute simulation steps advanced per rendered frame."""
        if self.config.steps_per_frame is not None:
            return self.config.steps_per_frame * self.config.speed
        return (BASE_STEPS_PER_SECOND * self.config.speed) / self.config.framerate

    def _raw_current_field(self) -> np.ndarray:
        """Return the raw unblended interpolated `a` concentration field."""
        if (
            self.config.optimize
            and self.config.snap_steps
            and self.step_advance <= 1.0
        ) or self.curr_step == 0:
            return self.a
        frac = self.sim_time - (self.curr_step - 1)
        return (1.0 - frac) * self.a_prev + frac * self.a

    def step_frame(self) -> np.ndarray:
        """Advance simulation by one frame interval and return the active `a` concentration field."""
        self.sim_time += self.step_advance
        self.frame_idx += 1
        target_step = int(np.ceil(self.sim_time))
        while self.curr_step < target_step:
            self.a_prev = self.a
            self.a, self.b, self.c = _step_bz(
                self.a,
                self.b,
                self.c,
                self.config.alpha,
                self.config.beta,
                self.config.gamma,
            )
            self.curr_step += 1

        raw_a = self._raw_current_field()
        if not self.config.seamless_loop:
            return raw_a

        n_frames = max(4, int(round(self.config.length * self.config.framerate)))
        k_frames = max(2, min(n_frames - 1, int(round(n_frames * self.config.loop_wipe_ratio))))
        cycle_idx = self.frame_idx % n_frames
        if len(self._head_fields) < k_frames:
            self._head_fields.append(raw_a.copy())

        wipe_start = n_frames - k_frames
        if cycle_idx >= wipe_start and len(self._head_fields) >= k_frames:
            k_idx = cycle_idx - wipe_start
            wipe_progress = (k_idx + 0.5) / float(k_frames)
            return _blend_pulse_wipe_field(
                a_tail=raw_a,
                a_head=self._head_fields[k_idx],
                arrival_map=self._arrival_map,
                max_arrival=self._max_arrival,
                wipe_progress=wipe_progress,
                pulse_speed=self.config.pulse_speed,
                pulse_sharpness=self.config.pulse_sharpness,
                pulse_decay=self.config.pulse_decay,
            )
        return raw_a

    def current_field(self) -> np.ndarray:
        """Return the current interpolated `a` concentration field without advancing."""
        return self._raw_current_field()

    def render_rgb_array(
        self,
        a_field: np.ndarray | None = None,
        target_size: tuple[int, int] | None = None,
        smooth_preview: bool = False,
        tui_fast: bool = False,
    ) -> np.ndarray:
        """Render a concentration field to an `(H, W, 3)` uint8 RGB array.

        - `smooth_preview=True` (GUI): uses cached 64-shade gradient.
        - `tui_fast=True` (TUI): resizes concentration field in 2D grayscale first
          (3x faster than resizing 3-channel RGB) and quantizes to 16 shades so
          horizontal ANSI run-lengths coalesce cleanly.
        """
        if a_field is None:
            a_field = self.current_field()
        coarse_a = _downsample_field(a_field, self.config.pixel_size)

        if tui_fast:
            pal = self._tui_palette_16
            if target_size is not None:
                tw, th = target_size
                if tw > 0 and th > 0:
                    pil_l = Image.fromarray(
                        np.clip(coarse_a * 255.0, 0.0, 255.0).astype(np.uint8), mode="L"
                    ).resize((tw, th), resample=Image.Resampling.BILINEAR)
                    resized_a = np.asarray(pil_l, dtype=np.float32) * (1.0 / 255.0)
                    idx = _quantize_field(
                        resized_a, len(pal), contrast_gamma=self.config.contrast_gamma
                    )
                    return pal[idx]
            idx = _quantize_field(
                coarse_a, len(pal), contrast_gamma=self.config.contrast_gamma
            )
            return pal[idx]

        if smooth_preview:
            smooth_palette = self._smooth_palette_64
            cell_indices = _quantize_field(
                coarse_a, len(smooth_palette), contrast_gamma=self.config.contrast_gamma
            )
            indices = _upsample_indices(
                cell_indices, self.config.pixel_size, self.height, self.width
            )
            rgb = smooth_palette[indices]
            if target_size is not None:
                tw, th = target_size
                if tw > 0 and th > 0 and (tw != self.width or th != self.height):
                    pil_img = Image.fromarray(rgb, mode="RGB").resize(
                        (tw, th), resample=Image.Resampling.BILINEAR
                    )
                    return np.asarray(pil_img, dtype=np.uint8)
            return rgb

        cell_indices = _quantize_field(
            coarse_a, self.num_shades, contrast_gamma=self.config.contrast_gamma
        )
        indices = _upsample_indices(
            cell_indices, self.config.pixel_size, self.height, self.width
        )
        if target_size is not None:
            tw, th = target_size
            if tw > 0 and th > 0 and (tw != self.width or th != self.height):
                y_idx = np.linspace(0, self.height - 1, th).astype(np.int32)
                x_idx = np.linspace(0, self.width - 1, tw).astype(np.int32)
                indices = indices[np.ix_(y_idx, x_idx)]
        return self.palette_array[indices]

    def render_braille_data(
        self,
        char_w: int,
        char_h: int,
        a_field: np.ndarray | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Compute vectorized 2x4 sub-pixel Braille codepoints and quantized fg shade indices.

        Because Braille sub-pixel density (8 dots per cell) already encodes fine spatial
        shading, using a uniform canvas background + 12 foreground shade levels reduces
        terminal ANSI escape sequences by >75% while keeping wavefronts crisp.

        Returns `(codepoints, fg_rgb)` where:
        - `codepoints` is `(char_h, char_w)` uint16 Unicode codepoints in `0x2800..0x28FF`
        - `fg_rgb` is `(char_h, char_w, 3)` uint8 foreground dot color
        """
        if a_field is None:
            a_field = self.current_field()
        coarse_a = _downsample_field(a_field, self.config.pixel_size)

        sub_w = max(2, char_w * 2)
        sub_h = max(4, char_h * 4)

        pil_a = Image.fromarray(
            np.clip(coarse_a * 255.0, 0.0, 255.0).astype(np.uint8), mode="L"
        ).resize((sub_w, sub_h), resample=Image.Resampling.BILINEAR)
        sub = (np.asarray(pil_a, dtype=np.float32) * (1.0 / 255.0)) ** self.config.contrast_gamma

        blocks = sub.reshape(char_h, 4, char_w, 2)
        b_min = blocks.min(axis=(1, 3), keepdims=True)
        b_max = blocks.max(axis=(1, 3), keepdims=True)
        b_mean = blocks.mean(axis=(1, 3), keepdims=True)
        span = b_max - b_min

        thresh = np.where(span > 0.07, b_mean * 0.92, 0.18)
        dots = blocks >= thresh

        weights = np.array(
            [[0x01, 0x08], [0x02, 0x10], [0x04, 0x20], [0x40, 0x80]],
            dtype=np.uint16,
        )
        codepoints = 0x2800 + (dots * weights[None, :, None, :]).sum(
            axis=(1, 3), dtype=np.uint16
        )

        pal = self._tui_palette_16
        n_pal = len(pal)
        fg_val = 0.75 * b_max[:, 0, :, 0] + 0.25 * b_mean[:, 0, :, 0]
        fg_idx = np.clip(np.round(fg_val * (n_pal - 1)), 0, n_pal - 1).astype(np.uint8)
        # Empty Braille cells (0x2800) all share shade index 0 so entire empty runs merge into 1 span
        fg_idx = np.where(codepoints == 0x2800, 0, fg_idx)

        return codepoints, pal[fg_idx]


def simulate_bz_reaction(
    output_path: str = "bz_reaction.gif",
    size: SizeLike = (320, 320),
    length: float = 5.0,
    framerate: int = 20,
    bg_color: ColorLike = "#0b132b",
    rings_color: ColorLike = "#00f5d4",
    palette_mode: str = "gradient",
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
    seamless_loop: bool = True,
    loop_wipe_ratio: float = 0.28,
    pulse_count: int = 3,
    pulse_speed: float = 1.45,
    pulse_sharpness: float = 18.0,
    pulse_decay: float = 4.0,
    pulse_noise_amp: float = 0.08,
    pulse_noise_freq: int = 3,
    tileable: bool = True,
    progress_callback: Callable[[int, int], None] | None = None,
) -> str:
    """Simulate a 2D Belousov-Zhabotinsky reaction and save it as a seamlessly looping, tileable animated GIF."""
    config = SimulationConfig(
        output_path=output_path,
        size=size,
        length=length,
        framerate=framerate,
        bg_color=bg_color,
        rings_color=rings_color,
        palette_mode=palette_mode,
        speed=speed,
        alpha=alpha,
        beta=beta,
        gamma=gamma,
        warmup_steps=warmup_steps,
        steps_per_frame=steps_per_frame,
        seed=seed,
        colors=colors,
        pixel_size=pixel_size,
        palette_gamma=palette_gamma,
        contrast_gamma=contrast_gamma,
        scanline_smooth=scanline_smooth,
        bg_snap_threshold=bg_snap_threshold,
        despeckle=despeckle,
        snap_steps=snap_steps,
        optimize=optimize,
        diff_threshold=diff_threshold,
        seamless_loop=seamless_loop,
        loop_wipe_ratio=loop_wipe_ratio,
        pulse_count=pulse_count,
        pulse_speed=pulse_speed,
        pulse_sharpness=pulse_sharpness,
        pulse_decay=pulse_decay,
        pulse_noise_amp=pulse_noise_amp,
        pulse_noise_freq=pulse_noise_freq,
        tileable=tileable,
    )
    config.validate()

    width, height = parse_size(size)
    bg_rgb = parse_color(bg_color)
    rings_rgb = parse_color(rings_color)
    max_shades = colors - 1 if optimize and colors > 2 else colors
    palette = build_palette(
        bg_rgb,
        rings_rgb,
        gamma=palette_gamma,
        num_colors=max_shades,
        palette_mode=palette_mode,
    )
    num_shades = len(palette) // 3

    total_frames = max(1, int(round(length * framerate)))
    wipe_frames = (
        max(1, min(total_frames, int(round(total_frames * loop_wipe_ratio))))
        if seamless_loop and total_frames > 1
        else 0
    )
    sim_frames = total_frames + wipe_frames

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

    # Simulate N + K frames so frames [0..K-1] can be revealed behind the oxidation trigger pulse
    # over the tail frames [N..N+K-1]
    a_prev = a
    curr_step = 0
    raw_fields: list[np.ndarray] = []
    for sim_idx in range(sim_frames):
        sim_time = sim_idx * step_advance
        target_step = int(np.ceil(sim_time))
        while curr_step < target_step:
            a_prev = a
            a, b, c = _step_bz(a, b, c, alpha, beta, gamma)
            curr_step += 1

        if (optimize and snap_steps and step_advance <= 1.0) or curr_step == 0:
            a_frame = a.copy()
        else:
            frac = sim_time - (curr_step - 1)
            a_frame = ((1.0 - frac) * a_prev + frac * a).astype(np.float32)
        raw_fields.append(a_frame)

    if wipe_frames > 0:
        arrival_map, max_arrival = _build_toroidal_arrival_map(
            height,
            width,
            pulse_count=pulse_count,
            noise_amp=pulse_noise_amp,
            noise_freq=pulse_noise_freq,
            rng=rng,
        )
        output_fields: list[np.ndarray] = []
        for idx in range(total_frames):
            if idx < wipe_frames:
                wipe_progress = (idx + 0.5) / float(wipe_frames)
                blended = _blend_pulse_wipe_field(
                    a_tail=raw_fields[total_frames + idx],
                    a_head=raw_fields[idx],
                    arrival_map=arrival_map,
                    max_arrival=max_arrival,
                    wipe_progress=wipe_progress,
                    pulse_speed=pulse_speed,
                    pulse_sharpness=pulse_sharpness,
                    pulse_decay=pulse_decay,
                )
                output_fields.append(blended)
            else:
                output_fields.append(raw_fields[idx])
    else:
        output_fields = raw_fields[:total_frames]

    canvas_indices: np.ndarray | None = None
    frames: list[Image.Image] = []
    for frame_idx, a_frame in enumerate(output_fields):
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
                tileable=tileable,
            )
        if optimize:
            canvas_indices = cell_indices
        indices = _upsample_indices(cell_indices, pixel_size, height, width)
        frame = Image.fromarray(indices, mode="P")
        frame.putpalette(palette)
        frames.append(frame)

        if progress_callback is not None:
            progress_callback(frame_idx + 1, total_frames)

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


def simulate_from_config(
    config: SimulationConfig,
    progress_callback: Callable[[int, int], None] | None = None,
) -> str:
    """Run `simulate_bz_reaction` using a `SimulationConfig` instance."""
    return simulate_bz_reaction(
        output_path=config.output_path,
        size=config.size,
        length=config.length,
        framerate=config.framerate,
        bg_color=config.bg_color,
        rings_color=config.rings_color,
        palette_mode=config.palette_mode,
        speed=config.speed,
        alpha=config.alpha,
        beta=config.beta,
        gamma=config.gamma,
        warmup_steps=config.warmup_steps,
        steps_per_frame=config.steps_per_frame,
        seed=config.seed,
        colors=config.colors,
        pixel_size=config.pixel_size,
        palette_gamma=config.palette_gamma,
        contrast_gamma=config.contrast_gamma,
        scanline_smooth=config.scanline_smooth,
        bg_snap_threshold=config.bg_snap_threshold,
        despeckle=config.despeckle,
        snap_steps=config.snap_steps,
        optimize=config.optimize,
        diff_threshold=config.diff_threshold,
        seamless_loop=config.seamless_loop,
        loop_wipe_ratio=config.loop_wipe_ratio,
        pulse_count=config.pulse_count,
        pulse_speed=config.pulse_speed,
        pulse_sharpness=config.pulse_sharpness,
        pulse_decay=config.pulse_decay,
        pulse_noise_amp=config.pulse_noise_amp,
        pulse_noise_freq=config.pulse_noise_freq,
        tileable=config.tileable,
        progress_callback=progress_callback,
    )
