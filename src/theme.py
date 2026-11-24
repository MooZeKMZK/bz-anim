"""Shared Neo-Brutalist design system and TOML theme loader for both Textual TUI and PySide6 GUI."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from pathlib import Path
import tomllib


DEFAULT_THEME_FILENAME = "theme.toml"


@dataclass
class ThemeConfig:
    """Color palette and label tokens for the Neo-Brutalist TUI and GUI."""

    # Core Warm-Dark Surfaces & Crisp Borders
    ink: str = "#161821"
    surface: str = "#1e212d"
    panel: str = "#262a38"
    paper: str = "#e8e4dc"
    muted: str = "#9499ad"

    # Pleasant Muted Pastels for Section Headers & Action Buttons
    acid_cyan: str = "#5bc0be"
    acid_yellow: str = "#e9c46a"
    hot_magenta: str = "#e07a5f"
    acid_lime: str = "#81b29a"
    electric_blue: str = "#729fcf"

    # Typography & Titles
    app_title: str = "BZ-ANIM // BELOUSOV-ZHABOTINSKY LAB"
    app_subtitle: str = "2D REACTION-DIFFUSION ENGINE"
    section_canvas: str = "01 // OUTPUT & CANVAS"
    section_colors: str = "02 // PALETTE & RASTER"
    section_kinetics: str = "03 // REACTION KINETICS"
    section_optimize: str = "04 // LZW & DELTA COMPRESSION"

    @property
    def section_titles(self) -> dict[str, str]:
        return {
            "canvas": self.section_canvas,
            "colors": self.section_colors,
            "kinetics": self.section_kinetics,
            "optimize": self.section_optimize,
        }

    @classmethod
    def from_toml(cls, path: str | Path) -> ThemeConfig:
        """Load a `ThemeConfig` from a TOML file, supporting `[colors]`, `[titles]`, or flat keys."""
        p = Path(path)
        with p.open("rb") as f:
            raw = tomllib.load(f)

        merged: dict[str, object] = {}
        # Support either flat keys or nested [palette]/[colors]/[surfaces]/[accents]/[titles]/[sections]
        for key, val in raw.items():
            if isinstance(val, dict):
                for sub_k, sub_v in val.items():
                    merged[sub_k.lower().replace("-", "_")] = sub_v
            else:
                merged[key.lower().replace("-", "_")] = val

        # Map friendly section keys if present under [sections]
        alias_map = {
            "canvas": "section_canvas",
            "colors": "section_colors",
            "kinetics": "section_kinetics",
            "optimize": "section_optimize",
        }
        for short_k, field_k in alias_map.items():
            if short_k in merged and field_k not in merged and isinstance(merged[short_k], str):
                merged[field_k] = merged.pop(short_k)

        valid_fields = {f.name for f in fields(cls)}
        filtered = {k: str(v) for k, v in merged.items() if k in valid_fields and v is not None}
        return cls(**filtered)

    def to_toml_string(self) -> str:
        """Serialize this `ThemeConfig` into a clean, commented TOML string."""
        return (
            "# Neo-Brutalist UI Theme Configuration for bz-anim (TUI & GUI)\n\n"
            "[surfaces]\n"
            f'ink = "{self.ink}"          # Deep base & hard drop-shadow ink\n'
            f'surface = "{self.surface}"      # Sidebar background\n'
            f'panel = "{self.panel}"        # Elevated card surface\n'
            f'paper = "{self.paper}"        # Crisp borders & primary text\n'
            f'muted = "{self.muted}"        # Secondary labels\n\n'
            "[accents]\n"
            f'acid_cyan = "{self.acid_cyan}"     # Canvas header & Play button\n'
            f'acid_yellow = "{self.acid_yellow}"   # Top banner, Palette header & Reset button\n'
            f'hot_magenta = "{self.hot_magenta}"   # Kinetics header & Progress bar fill\n'
            f'acid_lime = "{self.acid_lime}"     # Compression header & Export button\n'
            f'electric_blue = "{self.electric_blue}" # Secondary accent blue\n\n'
            "[titles]\n"
            f'app_title = "{self.app_title}"\n'
            f'app_subtitle = "{self.app_subtitle}"\n'
            f'section_canvas = "{self.section_canvas}"\n'
            f'section_colors = "{self.section_colors}"\n'
            f'section_kinetics = "{self.section_kinetics}"\n'
            f'section_optimize = "{self.section_optimize}"\n'
        )

    def save_toml(self, path: str | Path) -> Path:
        """Write this `ThemeConfig` to a TOML file at `path`."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_toml_string(), encoding="utf-8")
        return p


# Global active theme instance
ACTIVE_THEME = ThemeConfig()

# Module-level constants kept in sync with ACTIVE_THEME
INK = ACTIVE_THEME.ink
SURFACE = ACTIVE_THEME.surface
PANEL = ACTIVE_THEME.panel
PAPER = ACTIVE_THEME.paper
MUTED = ACTIVE_THEME.muted

ACID_CYAN = ACTIVE_THEME.acid_cyan
ACID_YELLOW = ACTIVE_THEME.acid_yellow
HOT_MAGENTA = ACTIVE_THEME.hot_magenta
ACID_LIME = ACTIVE_THEME.acid_lime
ELECTRIC_BLUE = ACTIVE_THEME.electric_blue

APP_TITLE = ACTIVE_THEME.app_title
APP_SUBTITLE = ACTIVE_THEME.app_subtitle
SECTION_TITLES = ACTIVE_THEME.section_titles


def apply_theme(theme: ThemeConfig) -> ThemeConfig:
    """Update the active global theme tokens in-place."""
    global ACTIVE_THEME, INK, SURFACE, PANEL, PAPER, MUTED
    global ACID_CYAN, ACID_YELLOW, HOT_MAGENTA, ACID_LIME, ELECTRIC_BLUE
    global APP_TITLE, APP_SUBTITLE, SECTION_TITLES

    ACTIVE_THEME = theme
    INK = theme.ink
    SURFACE = theme.surface
    PANEL = theme.panel
    PAPER = theme.paper
    MUTED = theme.muted

    ACID_CYAN = theme.acid_cyan
    ACID_YELLOW = theme.acid_yellow
    HOT_MAGENTA = theme.hot_magenta
    ACID_LIME = theme.acid_lime
    ELECTRIC_BLUE = theme.electric_blue

    APP_TITLE = theme.app_title
    APP_SUBTITLE = theme.app_subtitle
    SECTION_TITLES.clear()
    SECTION_TITLES.update(theme.section_titles)
    return ACTIVE_THEME


def load_theme_file(path: str | Path | None = None) -> ThemeConfig:
    """Load and apply a TOML theme file.

    If `path` is None, automatically checks `./theme.toml` and `<project_root>/theme.toml`.
    """
    if path is not None:
        theme = ThemeConfig.from_toml(path)
        return apply_theme(theme)

    candidates = [
        Path.cwd() / DEFAULT_THEME_FILENAME,
        Path(__file__).resolve().parent.parent / DEFAULT_THEME_FILENAME,
    ]
    for candidate in candidates:
        if candidate.is_file():
            try:
                return apply_theme(ThemeConfig.from_toml(candidate))
            except Exception:
                pass
    return ACTIVE_THEME


# Auto-load default theme.toml if present on import
load_theme_file(None)
