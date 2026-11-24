"""Textual TUI for interactive 2D Belousov-Zhabotinsky reaction-diffusion simulation and GIF export.

Styled with the unified Neo-Brutalist design system shared with the PySide6 GUI.
"""

from __future__ import annotations

from pathlib import Path

from rich.color import Color
from rich.style import Style
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import (
    Button,
    Checkbox,
    Input,
    Label,
    ProgressBar,
    Static,
)

from bz_anim_core.base import BZSimulator, SimulationConfig, simulate_from_config
from bz_anim_core.theme import (
    ACID_CYAN,
    ACID_LIME,
    ACID_YELLOW,
    APP_SUBTITLE,
    APP_TITLE,
    HOT_MAGENTA,
    INK,
    MUTED,
    PANEL,
    PAPER,
    SECTION_TITLES,
    SURFACE,
    ThemeConfig,
)


from rich.segment import Segment
from textual.strip import Strip


class BZCanvas(Widget):
    """High-speed, aspect-corrected terminal canvas using Textual's direct `Strip` line renderer.

    Render modes:
    - 'braille' (default): High-density 2x4 sub-pixel Unicode Braille (`⠀`..`⣿`, 8 sub-pixels
      per terminal cell) with coalesced ANSI shade runs.
    - 'soft': Pure background-color cells (`  ` per pixel, 2x1 aspect-corrected) with zero
      foreground glyphs.
    - 'hd': Bilinearly smoothed half-block (`▀`) sub-pixel rendering.
    - 'dots': Soft glowing orb matrix (`●`) on a uniform deep canvas background.
    """

    MODES = ("braille", "soft", "hd", "dots")
    MODE_LABELS = {
        "braille": "2×4 BRAILLE SUB-PIXEL",
        "soft": "SOFT PIXELS (NO GLYPHS)",
        "hd": "SMOOTH HALF-BLOCK",
        "dots": "SOFT ORB MATRIX",
    }

    step_count: reactive[int] = reactive(0)
    render_mode: reactive[str] = reactive("braille")

    def __init__(self, simulator: BZSimulator, **kwargs) -> None:
        super().__init__(**kwargs)
        self.simulator = simulator
        self._active_field = None
        self._style_cache: dict[tuple, Style] = {}
        self._cached_strips: list[Strip] = []
        self._cached_key: tuple | None = None

    def cycle_mode(self) -> str:
        idx = (self.MODES.index(self.render_mode) + 1) % len(self.MODES)
        self.render_mode = self.MODES[idx]
        self._cached_key = None
        self.refresh()
        return self.MODE_LABELS[self.render_mode]

    def _build_strips(self, avail_w: int, avail_h: int) -> list[Strip]:
        sim_aspect = self.simulator.width / max(1, self.simulator.height)
        mode = self.render_mode
        style_cache = self._style_cache
        base_r, base_g, base_b = self.simulator.bg_rgb
        bg_key = ("bg", base_r, base_g, base_b)
        canvas_bg = style_cache.get(bg_key)
        if canvas_bg is None:
            canvas_bg = Style(bgcolor=Color.from_rgb(base_r, base_g, base_b))
            style_cache[bg_key] = canvas_bg

        blank_strip = Strip([Segment(" " * avail_w, canvas_bg)], avail_w)
        strips: list[Strip] = []

        if mode == "braille":
            if (avail_w / max(1, avail_h * 2)) > sim_aspect:
                char_h = avail_h
                char_w = max(4, min(avail_w, int(round(char_h * 2 * sim_aspect))))
            else:
                char_w = avail_w
                char_h = max(4, min(avail_h, int(round(char_w / (2 * sim_aspect)))))

            pad_left = max(0, (avail_w - char_w) // 2)
            pad_top = max(0, (avail_h - char_h) // 2)
            pad_right = max(0, avail_w - pad_left - char_w)
            left_seg = Segment(" " * pad_left, canvas_bg) if pad_left else None
            right_seg = Segment(" " * pad_right, canvas_bg) if pad_right else None

            codepoints, fg_rgb = self.simulator.render_braille_data(
                char_w, char_h, a_field=self._active_field
            )
            cp_list = codepoints.tolist()
            fg_list = fg_rgb.tolist()

            for _ in range(pad_top):
                strips.append(blank_strip)

            for row in range(char_h):
                segs: list[Segment] = []
                if left_seg is not None:
                    segs.append(left_seg)
                cp_row = cp_list[row]
                fg_row = fg_list[row]

                run_chars: list[str] = []
                last_key: tuple | None = None

                for col in range(char_w):
                    ch = chr(cp_row[col])
                    fr, fg_c, fb = fg_row[col]
                    key = ("br", fr, fg_c, fb, base_r, base_g, base_b)
                    if key == last_key:
                        run_chars.append(ch)
                    else:
                        if last_key is not None and run_chars:
                            st = style_cache.get(last_key)
                            if st is None:
                                st = Style(
                                    color=Color.from_rgb(last_key[1], last_key[2], last_key[3]),
                                    bgcolor=Color.from_rgb(base_r, base_g, base_b),
                                )
                                style_cache[last_key] = st
                            segs.append(Segment("".join(run_chars), st))
                        last_key = key
                        run_chars = [ch]

                if last_key is not None and run_chars:
                    st = style_cache.get(last_key)
                    if st is None:
                        st = Style(
                            color=Color.from_rgb(last_key[1], last_key[2], last_key[3]),
                            bgcolor=Color.from_rgb(base_r, base_g, base_b),
                        )
                        style_cache[last_key] = st
                    segs.append(Segment("".join(run_chars), st))

                if right_seg is not None:
                    segs.append(right_seg)
                strips.append(Strip(segs, avail_w))

            while len(strips) < avail_h:
                strips.append(blank_strip)
            return strips

        if mode in ("soft", "dots"):
            max_pix_w = avail_w // 2
            max_pix_h = avail_h
            if max_pix_w / max(1, max_pix_h) > sim_aspect:
                pix_h = max_pix_h
                pix_w = max(4, min(max_pix_w, int(round(pix_h * sim_aspect))))
            else:
                pix_w = max_pix_w
                pix_h = max(4, min(max_pix_h, int(round(pix_w / sim_aspect))))

            pad_left = max(0, (avail_w - pix_w * 2) // 2)
            pad_top = max(0, (avail_h - pix_h) // 2)
            pad_right = max(0, avail_w - pad_left - pix_w * 2)
            left_seg = Segment(" " * pad_left, canvas_bg) if pad_left else None
            right_seg = Segment(" " * pad_right, canvas_bg) if pad_right else None

            rgb = self.simulator.render_rgb_array(
                a_field=self._active_field, target_size=(pix_w, pix_h), tui_fast=True
            )
            rgb_list = rgb.tolist()
            unit = "  " if mode == "soft" else "● "

            for _ in range(pad_top):
                strips.append(blank_strip)

            for row in range(pix_h):
                segs = []
                if left_seg is not None:
                    segs.append(left_seg)
                row_rgb = rgb_list[row]
                run_len = 0
                last_key = None
                for col in range(pix_w):
                    r_c, g_c, b_c = row_rgb[col]
                    key = (mode, r_c, g_c, b_c, base_r, base_g, base_b)
                    if key == last_key:
                        run_len += 1
                    else:
                        if last_key is not None and run_len > 0:
                            st = style_cache.get(last_key)
                            if st is None:
                                if mode == "soft":
                                    st = Style(bgcolor=Color.from_rgb(last_key[1], last_key[2], last_key[3]))
                                else:
                                    st = Style(
                                        color=Color.from_rgb(last_key[1], last_key[2], last_key[3]),
                                        bgcolor=Color.from_rgb(base_r, base_g, base_b),
                                    )
                                style_cache[last_key] = st
                            segs.append(Segment(unit * run_len, st))
                        last_key = key
                        run_len = 1
                if last_key is not None and run_len > 0:
                    st = style_cache.get(last_key)
                    if st is None:
                        if mode == "soft":
                            st = Style(bgcolor=Color.from_rgb(last_key[1], last_key[2], last_key[3]))
                        else:
                            st = Style(
                                color=Color.from_rgb(last_key[1], last_key[2], last_key[3]),
                                bgcolor=Color.from_rgb(base_r, base_g, base_b),
                            )
                        style_cache[last_key] = st
                    segs.append(Segment(unit * run_len, st))
                if right_seg is not None:
                    segs.append(right_seg)
                strips.append(Strip(segs, avail_w))

            while len(strips) < avail_h:
                strips.append(blank_strip)
            return strips

        # 'hd' half-block mode
        max_pix_w = avail_w
        max_pix_h = avail_h * 2
        if max_pix_w / max(1, max_pix_h) > sim_aspect:
            pix_h = (max_pix_h // 2) * 2
            pix_w = max(8, min(max_pix_w, int(round(pix_h * sim_aspect))))
        else:
            pix_w = max_pix_w
            pix_h = max(8, min(max_pix_h, (int(round(pix_w / sim_aspect)) // 2) * 2))

        char_h = pix_h // 2
        pad_left = max(0, (avail_w - pix_w) // 2)
        pad_top = max(0, (avail_h - char_h) // 2)
        pad_right = max(0, avail_w - pad_left - pix_w)
        left_seg = Segment(" " * pad_left, canvas_bg) if pad_left else None
        right_seg = Segment(" " * pad_right, canvas_bg) if pad_right else None

        rgb = self.simulator.render_rgb_array(
            a_field=self._active_field, target_size=(pix_w, pix_h), tui_fast=True
        )
        rgb_list = rgb.tolist()

        for _ in range(pad_top):
            strips.append(blank_strip)

        for row in range(char_h):
            segs = []
            if left_seg is not None:
                segs.append(left_seg)
            top_row = rgb_list[row * 2]
            bot_row = rgb_list[row * 2 + 1]
            run_chars = 0
            last_key = None

            for col in range(pix_w):
                tr, tg, tb = top_row[col]
                br, bg_c, bb = bot_row[col]
                key = ("hd", tr, tg, tb, br, bg_c, bb)
                if key == last_key:
                    run_chars += 1
                else:
                    if last_key is not None and run_chars > 0:
                        st = style_cache.get(last_key)
                        if st is None:
                            st = Style(
                                color=Color.from_rgb(last_key[1], last_key[2], last_key[3]),
                                bgcolor=Color.from_rgb(last_key[4], last_key[5], last_key[6]),
                            )
                            style_cache[last_key] = st
                        segs.append(Segment("▀" * run_chars, st))
                    last_key = key
                    run_chars = 1

            if last_key is not None and run_chars > 0:
                st = style_cache.get(last_key)
                if st is None:
                    st = Style(
                        color=Color.from_rgb(last_key[1], last_key[2], last_key[3]),
                        bgcolor=Color.from_rgb(last_key[4], last_key[5], last_key[6]),
                    )
                    style_cache[last_key] = st
                segs.append(Segment("▀" * run_chars, st))

            if right_seg is not None:
                segs.append(right_seg)
            strips.append(Strip(segs, avail_w))

        while len(strips) < avail_h:
            strips.append(blank_strip)
        return strips

    def render_line(self, y: int) -> Strip:
        avail_w = max(8, self.content_size.width)
        avail_h = max(4, self.content_size.height)
        key = (
            self.step_count,
            self.render_mode,
            avail_w,
            avail_h,
            self.simulator.bg_rgb,
            self.simulator.rings_rgb,
            self.simulator.config.pixel_size,
        )
        if self._cached_key != key:
            self._cached_strips = self._build_strips(avail_w, avail_h)
            self._cached_key = key
        if 0 <= y < len(self._cached_strips):
            return self._cached_strips[y]
        return Strip.blank(avail_w)


def build_tui_css(theme: ThemeConfig | None = None) -> str:
    """Build Textual Neo-Brutalist CSS dynamically from a `ThemeConfig`."""
    import bz_anim_core.theme as theme_mod

    t = theme or theme_mod.ACTIVE_THEME
    return f"""
    Screen {{
        background: {t.ink};
        color: {t.paper};
        layout: vertical;
    }}

    #top-banner {{
        height: 3;
        background: {t.acid_yellow};
        color: {t.ink};
        border-bottom: heavy {t.ink};
        padding: 0 2;
        content-align: left middle;
        text-style: bold;
    }}

    #workspace {{
        width: 1fr;
        height: 1fr;
        layout: horizontal;
    }}

    #sidebar {{
        width: 50;
        height: 100%;
        background: {t.surface};
        border-right: heavy {t.acid_cyan};
        padding: 1 2;
    }}

    .brutal-card {{
        height: auto;
        background: {t.panel};
        border: heavy {t.paper};
        padding: 0 1 1 1;
        margin-bottom: 1;
    }}

    .section-tag {{
        width: 100%;
        background: {t.acid_cyan};
        color: {t.ink};
        text-style: bold;
        padding: 0 1;
        margin-bottom: 1;
    }}

    .section-tag-yellow {{
        width: 100%;
        background: {t.acid_yellow};
        color: {t.ink};
        text-style: bold;
        padding: 0 1;
        margin-bottom: 1;
    }}

    .section-tag-magenta {{
        width: 100%;
        background: {t.hot_magenta};
        color: {t.ink};
        text-style: bold;
        padding: 0 1;
        margin-bottom: 1;
    }}

    .section-tag-lime {{
        width: 100%;
        background: {t.acid_lime};
        color: {t.ink};
        text-style: bold;
        padding: 0 1;
        margin-bottom: 1;
    }}

    .section-tag-blue {{
        width: 100%;
        background: {t.electric_blue};
        color: {t.ink};
        text-style: bold;
        padding: 0 1;
        margin-bottom: 1;
    }}

    .field-row {{
        height: 3;
        margin-bottom: 0;
        align: left middle;
    }}

    .toml-btn-row {{
        height: 3;
        margin-top: 1;
        align: left middle;
    }}

    .toml-btn-row Button {{
        width: 1fr;
        margin-right: 1;
        height: 3;
        text-style: bold;
        border: heavy {t.paper};
        background: {t.surface};
        color: {t.paper};
    }}

    .field-label {{
        width: 16;
        height: 3;
        content-align: left middle;
        color: {t.paper};
        text-style: bold;
    }}

    .field-input {{
        width: 1fr;
        background: {t.ink};
        color: {t.acid_cyan};
        border: tall {t.paper};
        text-style: bold;
    }}

    .field-input:focus {{
        border: heavy {t.acid_yellow};
        color: {t.acid_yellow};
    }}

    Checkbox {{
        background: {t.panel};
        color: {t.paper};
        text-style: bold;
        border: none;
        padding: 0 0;
    }}

    Checkbox:focus {{
        text-style: bold underline;
        color: {t.acid_yellow};
    }}

    #main-panel {{
        width: 1fr;
        height: 100%;
        background: {t.ink};
        padding: 1 2;
    }}

    #viewport-header {{
        height: 1;
        background: {t.acid_cyan};
        color: {t.ink};
        text-style: bold;
        padding: 0 1;
    }}

    #bz-canvas {{
        width: 1fr;
        height: 1fr;
        min-width: 24;
        min-height: 12;
        border: heavy {t.acid_cyan};
        background: {t.ink};
    }}

    #controls-row {{
        height: auto;
        margin-top: 1;
        margin-bottom: 1;
    }}

    #controls-row Button {{
        margin-right: 1;
        min-width: 11;
        height: 3;
        text-style: bold;
        border: heavy {t.paper};
    }}

    #btn-play {{
        background: {t.acid_cyan};
        color: {t.ink};
        border: heavy {t.paper};
    }}

    #btn-step, #btn-view {{
        background: {t.panel};
        color: {t.paper};
        border: heavy {t.paper};
    }}

    #btn-reset {{
        background: {t.acid_yellow};
        color: {t.ink};
        border: heavy {t.paper};
    }}

    #btn-export {{
        background: {t.acid_lime};
        color: {t.ink};
        border: heavy {t.paper};
    }}

    #telemetry-box {{
        height: 3;
        background: {t.surface};
        border: heavy {t.paper};
        padding: 0 1;
        align: left middle;
    }}

    #status-bar {{
        width: 1fr;
        color: {t.acid_yellow};
        text-style: bold;
    }}

    #export-progress {{
        width: 28;
        margin-left: 2;
    }}

    #bottom-keys {{
        height: 1;
        background: {t.surface};
        color: {t.muted};
        padding: 0 2;
        text-style: bold;
    }}

    Tooltip {{
        background: {t.ink};
        color: {t.acid_yellow};
        border: heavy {t.acid_cyan};
        padding: 0 1;
        text-style: bold;
        max-width: 56;
    }}
    """


class BZTuiApp(App):
    """Neo-Brutalist Textual application for live previewing and exporting BZ animations."""

    TITLE = APP_TITLE
    SUB_TITLE = APP_SUBTITLE
    CSS = build_tui_css()
    TOOLTIP_DELAY = 0.25

    BINDINGS = [
        Binding("space", "toggle_play", "PLAY/PAUSE"),
        Binding("v", "cycle_view", "VIEW MODE"),
        Binding("r", "reset_sim", "RESET GRID"),
        Binding("s", "save_config_toml", "SAVE CONFIG"),
        Binding("e", "export_gif", "EXPORT GIF"),
        Binding("q", "quit", "QUIT"),
    ]

    is_playing: reactive[bool] = reactive(True)

    def __init__(
        self,
        initial_config: SimulationConfig | None = None,
        config_path: str = "config.toml",
        theme_path: str = "theme.toml",
    ) -> None:
        import bz_anim_core.theme as theme_mod

        self.CSS = build_tui_css(theme_mod.ACTIVE_THEME)
        super().__init__()
        self.config = initial_config or SimulationConfig()
        self.config_path = config_path
        self.theme_path = theme_path
        self.simulator = BZSimulator(self._make_preview_config(self.config))
        self._timer = None
        self._exporting = False
        self._active_tip: str | None = None

    @staticmethod
    def _make_preview_config(cfg: SimulationConfig) -> SimulationConfig:
        """Create a fast preview copy of `cfg` capped at 160px on the longest side for TUI responsiveness."""
        from bz_anim_core.base import parse_size

        w, h = parse_size(cfg.size)
        max_dim = 160
        if max(w, h) > max_dim:
            scale = max_dim / float(max(w, h))
            w = max(16, int(round(w * scale)))
            h = max(16, int(round(h * scale)))

        return SimulationConfig(
            output_path=cfg.output_path,
            size=(w, h),
            length=cfg.length,
            framerate=cfg.framerate,
            bg_color=cfg.bg_color,
            rings_color=cfg.rings_color,
            palette_mode=cfg.palette_mode,
            speed=cfg.speed,
            alpha=cfg.alpha,
            beta=cfg.beta,
            gamma=cfg.gamma,
            warmup_steps=cfg.warmup_steps,
            steps_per_frame=cfg.steps_per_frame,
            seed=cfg.seed,
            colors=cfg.colors,
            pixel_size=cfg.pixel_size,
            palette_gamma=cfg.palette_gamma,
            contrast_gamma=cfg.contrast_gamma,
            scanline_smooth=cfg.scanline_smooth,
            bg_snap_threshold=cfg.bg_snap_threshold,
            despeckle=cfg.despeckle,
            snap_steps=cfg.snap_steps,
            optimize=cfg.optimize,
            diff_threshold=cfg.diff_threshold,
            seamless_loop=cfg.seamless_loop,
            loop_wipe_ratio=cfg.loop_wipe_ratio,
            pulse_count=cfg.pulse_count,
            pulse_speed=cfg.pulse_speed,
            pulse_sharpness=cfg.pulse_sharpness,
            pulse_decay=cfg.pulse_decay,
            pulse_noise_amp=cfg.pulse_noise_amp,
            pulse_noise_freq=cfg.pulse_noise_freq,
            tileable=cfg.tileable,
        )

    @staticmethod
    def _field_row(label_text: str, value_str: str, input_id: str, tip_key: str) -> Horizontal:
        """Build a labeled input row with a hover tooltip on both the label and input field."""
        import bz_anim_core.theme as theme_mod

        tip = theme_mod.OPTION_TOOLTIPS.get(tip_key, "")
        lbl = Label(label_text, classes="field-label")
        inp = Input(value_str, id=input_id, classes="field-input")
        row = Horizontal(lbl, inp, classes="field-row")
        if tip:
            lbl.tooltip = tip
            inp.tooltip = tip
            row.tooltip = tip
        return row

    @staticmethod
    def _checkbox(label_text: str, checked: bool, cb_id: str, tip_key: str) -> Checkbox:
        """Build a Neo-Brutalist Checkbox with a hover tooltip description."""
        import bz_anim_core.theme as theme_mod

        cb = Checkbox(label_text, value=checked, id=cb_id)
        tip = theme_mod.OPTION_TOOLTIPS.get(tip_key, "")
        if tip:
            cb.tooltip = tip
        return cb

    def compose(self) -> ComposeResult:
        import bz_anim_core.theme as theme_mod

        t = theme_mod.ACTIVE_THEME
        tips = theme_mod.OPTION_TOOLTIPS
        yield Static(
            f"■ {t.app_title}   //   {t.app_subtitle}   [NEO-BRUTALIST TUI]",
            id="top-banner",
        )
        with Horizontal(id="workspace"):
            with VerticalScroll(id="sidebar"):
                with Container(classes="brutal-card"):
                    yield Label(t.section_canvas, classes="section-tag")
                    yield self._field_row("OUTPUT GIF", str(self.config.output_path), "in-output", "output_path")
                    size_str = (
                        f"{self.config.size[0]}x{self.config.size[1]}"
                        if isinstance(self.config.size, tuple)
                        else str(self.config.size)
                    )
                    yield self._field_row("SIZE (WxH)", size_str, "in-size", "size")
                    yield self._field_row("LENGTH (S)", str(self.config.length), "in-length", "length")
                    yield self._field_row("FRAMERATE", str(self.config.framerate), "in-framerate", "framerate")

                with Container(classes="brutal-card"):
                    yield Label(t.section_colors, classes="section-tag-yellow")
                    yield self._checkbox(
                        "FERROIN 1D LUT MODE",
                        self.config.palette_mode == "ferroin",
                        "cb-ferroin",
                        "palette_mode",
                    )
                    yield self._field_row("BG COLOR", str(self.config.bg_color), "in-bg-color", "bg_color")
                    yield self._field_row("RINGS COLOR", str(self.config.rings_color), "in-rings-color", "rings_color")
                    yield self._field_row("SHADES", str(self.config.colors), "in-colors", "colors")
                    yield self._field_row("PIXEL SIZE", str(self.config.pixel_size), "in-pixel-size", "pixel_size")
                    yield self._field_row("PAL GAMMA", str(self.config.palette_gamma), "in-palette-gamma", "palette_gamma")
                    yield self._field_row("CNT GAMMA", str(self.config.contrast_gamma), "in-contrast-gamma", "contrast_gamma")

                with Container(classes="brutal-card"):
                    yield Label(t.section_kinetics, classes="section-tag-magenta")
                    yield self._field_row("SPEED (X)", str(self.config.speed), "in-speed", "speed")
                    yield self._field_row("ALPHA A+B", str(self.config.alpha), "in-alpha", "alpha")
                    yield self._field_row("BETA B+C", str(self.config.beta), "in-beta", "beta")
                    yield self._field_row("GAMMA C+A", str(self.config.gamma), "in-gamma", "gamma")
                    yield self._field_row("WARMUP", str(self.config.warmup_steps), "in-warmup", "warmup_steps")
                    yield self._field_row(
                        "RNG SEED",
                        "" if self.config.seed is None else str(self.config.seed),
                        "in-seed",
                        "seed",
                    )

                with Container(classes="brutal-card"):
                    yield Label("04 // SEAMLESS LOOP & TORUS", classes="section-tag")
                    yield self._checkbox("SEAMLESS PULSE WIPE LOOP", self.config.seamless_loop, "cb-seamless-loop", "seamless_loop")
                    yield self._checkbox("2D TORUS SPATIAL TILING", self.config.tileable, "cb-tileable", "tileable")
                    yield self._field_row("WIPE RATIO", str(self.config.loop_wipe_ratio), "in-wipe-ratio", "loop_wipe_ratio")
                    yield self._field_row("PULSES (N)", str(self.config.pulse_count), "in-pulse-count", "pulse_count")
                    yield self._field_row("PULSE SPD", str(self.config.pulse_speed), "in-pulse-speed", "pulse_speed")
                    yield self._field_row("4D NOISE", str(self.config.pulse_noise_amp), "in-pulse-noise", "pulse_noise_amp")

                with Container(classes="brutal-card"):
                    yield Label(t.section_optimize, classes="section-tag-lime")
                    yield self._checkbox("DELTA / LZW OPTIMIZE", self.config.optimize, "cb-optimize", "optimize")
                    yield self._checkbox("DESPECKLE CELL DELTAS", self.config.despeckle, "cb-despeckle", "despeckle")
                    yield self._checkbox("SNAP DISCRETE STEPS", self.config.snap_steps, "cb-snap-steps", "snap_steps")

                with Container(classes="brutal-card"):
                    yield Label("06 // TOML CONFIG & THEME", classes="section-tag-blue")
                    yield self._field_row("CONFIG TOML", self.config_path, "in-config-toml", "config_toml")
                    with Horizontal(classes="toml-btn-row"):
                        btn_load_cfg = Button("LOAD CFG", id="btn-load-cfg")
                        btn_load_cfg.tooltip = tips["config_toml"]
                        btn_save_cfg = Button("SAVE CFG", id="btn-save-cfg")
                        btn_save_cfg.tooltip = tips["config_toml"]
                        yield btn_load_cfg
                        yield btn_save_cfg
                    yield self._field_row("THEME TOML", self.theme_path, "in-theme-toml", "theme_toml")
                    with Horizontal(classes="toml-btn-row"):
                        btn_save_theme = Button("SAVE THEME", id="btn-save-theme")
                        btn_save_theme.tooltip = tips["theme_toml"]
                        yield btn_save_theme

            with Vertical(id="main-panel"):
                yield Static(
                    "LIVE REACTION VIEWPORT // 2×4 BRAILLE SUB-PIXEL",
                    id="viewport-header",
                )
                yield BZCanvas(self.simulator, id="bz-canvas")
                with Horizontal(id="controls-row"):
                    btn_play = Button("❚❚ PAUSE", id="btn-play")
                    btn_play.tooltip = tips["btn_play"]
                    btn_step = Button("⏭ STEP", id="btn-step")
                    btn_step.tooltip = tips["btn_step"]
                    btn_view = Button("◈ VIEW MODE", id="btn-view")
                    btn_view.tooltip = tips["btn_view"]
                    btn_reset = Button("↺ APPLY & RESET", id="btn-reset")
                    btn_reset.tooltip = tips["btn_reset"]
                    btn_export = Button("⬇ EXPORT GIF", id="btn-export")
                    btn_export.tooltip = tips["btn_export"]
                    yield btn_play
                    yield btn_step
                    yield btn_view
                    yield btn_reset
                    yield btn_export
                with Horizontal(id="telemetry-box"):
                    yield Static("STATUS // READY", id="status-bar")
                    yield ProgressBar(total=100, show_eta=False, id="export-progress")
        yield Static(
            "[SPACE] PLAY/PAUSE // [V] VIEW MODE // [R] RESET // [S] SAVE TOML // [E] EXPORT GIF // [Q] QUIT",
            id="bottom-keys",
        )

    def on_mount(self) -> None:
        interval = 1.0 / max(1, min(30, self.config.framerate))
        self._timer = self.set_interval(interval, self._tick_simulation)

    def _resolve_widget_tip(self, widget: Widget | None) -> str | None:
        node = widget
        while isinstance(node, Widget):
            if node.tooltip:
                return str(node.tooltip)
            node = node.parent  # type: ignore[assignment]
        return None

    def _update_status_bar(self) -> None:
        if self._exporting:
            return
        status = self.query_one("#status-bar", Static)
        if self._active_tip:
            status.update(f"INFO // {self._active_tip}")
        else:
            state = "LIVE" if self.is_playing else "PAUSED"
            status.update(
                f"{state} // GRID {self.simulator.width}x{self.simulator.height} // "
                f"STEP #{self.simulator.curr_step:04d} // SPEED {self.simulator.config.speed:.2f}X"
            )

    def on_mouse_move(self, event) -> None:
        try:
            widget, _ = self.screen.get_widget_at(event.screen_x, event.screen_y)
        except Exception:
            widget = None
        tip = self._resolve_widget_tip(widget)
        if tip != self._active_tip:
            self._active_tip = tip
            self._update_status_bar()

    def on_descendant_focus(self, event) -> None:
        tip = self._resolve_widget_tip(getattr(event, "widget", None))
        if tip:
            self._active_tip = tip
            self._update_status_bar()

    def _tick_simulation(self) -> None:
        if not self.is_playing:
            return
        field = self.simulator.step_frame()
        canvas = self.query_one("#bz-canvas", BZCanvas)
        canvas._active_field = field
        canvas.step_count = self.simulator.frame_idx
        canvas.refresh()
        self._update_status_bar()

    def _populate_inputs_from_config(self, cfg: SimulationConfig) -> None:
        """Update all sidebar input widgets from `cfg`."""
        self.query_one("#in-output", Input).value = str(cfg.output_path)
        size_str = (
            f"{cfg.size[0]}x{cfg.size[1]}"
            if isinstance(cfg.size, (tuple, list))
            else str(cfg.size)
        )
        self.query_one("#in-size", Input).value = size_str
        self.query_one("#in-length", Input).value = str(cfg.length)
        self.query_one("#in-framerate", Input).value = str(cfg.framerate)
        self.query_one("#cb-ferroin", Checkbox).value = cfg.palette_mode == "ferroin"
        self.query_one("#in-bg-color", Input).value = str(cfg.bg_color)
        self.query_one("#in-rings-color", Input).value = str(cfg.rings_color)
        self.query_one("#in-colors", Input).value = str(cfg.colors)
        self.query_one("#in-pixel-size", Input).value = str(cfg.pixel_size)
        self.query_one("#in-palette-gamma", Input).value = str(cfg.palette_gamma)
        self.query_one("#in-contrast-gamma", Input).value = str(cfg.contrast_gamma)
        self.query_one("#in-speed", Input).value = str(cfg.speed)
        self.query_one("#in-alpha", Input).value = str(cfg.alpha)
        self.query_one("#in-beta", Input).value = str(cfg.beta)
        self.query_one("#in-gamma", Input).value = str(cfg.gamma)
        self.query_one("#in-warmup", Input).value = str(cfg.warmup_steps)
        self.query_one("#in-seed", Input).value = "" if cfg.seed is None else str(cfg.seed)
        self.query_one("#cb-seamless-loop", Checkbox).value = bool(cfg.seamless_loop)
        self.query_one("#cb-tileable", Checkbox).value = bool(cfg.tileable)
        self.query_one("#in-wipe-ratio", Input).value = str(cfg.loop_wipe_ratio)
        self.query_one("#in-pulse-count", Input).value = str(cfg.pulse_count)
        self.query_one("#in-pulse-speed", Input).value = str(cfg.pulse_speed)
        self.query_one("#in-pulse-noise", Input).value = str(cfg.pulse_noise_amp)
        self.query_one("#cb-optimize", Checkbox).value = bool(cfg.optimize)
        self.query_one("#cb-despeckle", Checkbox).value = bool(cfg.despeckle)
        self.query_one("#cb-snap-steps", Checkbox).value = bool(cfg.snap_steps)

    def _read_config_from_inputs(self) -> SimulationConfig:
        """Parse all form widgets into a validated `SimulationConfig`."""
        seed_raw = self.query_one("#in-seed", Input).value.strip()
        seed_val = int(seed_raw) if seed_raw else None
        if seed_val is not None and seed_val < 0:
            seed_val = None

        cfg = SimulationConfig(
            output_path=self.query_one("#in-output", Input).value.strip() or "bz_reaction.gif",
            size=self.query_one("#in-size", Input).value.strip() or "320x320",
            length=float(self.query_one("#in-length", Input).value),
            framerate=int(self.query_one("#in-framerate", Input).value),
            palette_mode="ferroin" if self.query_one("#cb-ferroin", Checkbox).value else "gradient",
            bg_color=self.query_one("#in-bg-color", Input).value.strip(),
            rings_color=self.query_one("#in-rings-color", Input).value.strip(),
            colors=int(self.query_one("#in-colors", Input).value),
            pixel_size=int(self.query_one("#in-pixel-size", Input).value),
            palette_gamma=float(self.query_one("#in-palette-gamma", Input).value),
            contrast_gamma=float(self.query_one("#in-contrast-gamma", Input).value),
            speed=float(self.query_one("#in-speed", Input).value),
            alpha=float(self.query_one("#in-alpha", Input).value),
            beta=float(self.query_one("#in-beta", Input).value),
            gamma=float(self.query_one("#in-gamma", Input).value),
            warmup_steps=int(self.query_one("#in-warmup", Input).value),
            seed=seed_val,
            seamless_loop=self.query_one("#cb-seamless-loop", Checkbox).value,
            tileable=self.query_one("#cb-tileable", Checkbox).value,
            loop_wipe_ratio=float(self.query_one("#in-wipe-ratio", Input).value),
            pulse_count=int(self.query_one("#in-pulse-count", Input).value),
            pulse_speed=float(self.query_one("#in-pulse-speed", Input).value),
            pulse_noise_amp=float(self.query_one("#in-pulse-noise", Input).value),
            optimize=self.query_one("#cb-optimize", Checkbox).value,
            despeckle=self.query_one("#cb-despeckle", Checkbox).value,
            snap_steps=self.query_one("#cb-snap-steps", Checkbox).value,
        )
        cfg.validate()
        return cfg

    def action_toggle_play(self) -> None:
        self.is_playing = not self.is_playing
        btn = self.query_one("#btn-play", Button)
        btn.label = "❚❚ PAUSE" if self.is_playing else "▶ PLAY"

    def action_cycle_view(self) -> None:
        canvas = self.query_one("#bz-canvas", BZCanvas)
        label = canvas.cycle_mode()
        header = self.query_one("#viewport-header", Static)
        header.update(f"LIVE REACTION VIEWPORT // {label}")

    def action_reset_sim(self) -> None:
        status = self.query_one("#status-bar", Static)
        try:
            cfg = self._read_config_from_inputs()
        except Exception as exc:
            status.update(f"ERR // {exc}")
            self.notify(f"Parameter error: {exc}", severity="error")
            return

        self.config = cfg
        self.simulator.reset(self._make_preview_config(cfg))
        if self._timer is not None:
            self._timer.stop()
        interval = 1.0 / max(1, min(30, self.config.framerate))
        self._timer = self.set_interval(interval, self._tick_simulation)
        canvas = self.query_one("#bz-canvas", BZCanvas)
        canvas._active_field = self.simulator.current_field()
        canvas.step_count = self.simulator.frame_idx
        canvas.refresh()
        status.update(f"RESET // {self.simulator.width}x{self.simulator.height} GRID INITIALIZED")

    def action_load_config_toml(self) -> None:
        status = self.query_one("#status-bar", Static)
        path_str = self.query_one("#in-config-toml", Input).value.strip() or "config.toml"
        try:
            cfg = SimulationConfig.from_toml(path_str)
            self._populate_inputs_from_config(cfg)
            self.action_reset_sim()
            status.update(f"LOADED CONFIG // {path_str}")
            self.notify(f"Loaded simulation config from {path_str}", severity="information")
        except Exception as exc:
            status.update(f"LOAD ERR // {exc}")
            self.notify(f"Failed to load {path_str}: {exc}", severity="error")

    def action_save_config_toml(self) -> None:
        status = self.query_one("#status-bar", Static)
        path_str = self.query_one("#in-config-toml", Input).value.strip() or "config.toml"
        try:
            cfg = self._read_config_from_inputs()
            saved = cfg.save_toml(path_str)
            status.update(f"SAVED CONFIG // {saved}")
            self.notify(f"Saved simulation config to {saved}", severity="information")
        except Exception as exc:
            status.update(f"SAVE ERR // {exc}")
            self.notify(f"Failed to save {path_str}: {exc}", severity="error")

    def action_save_theme_toml(self) -> None:
        import bz_anim_core.theme as theme_mod

        status = self.query_one("#status-bar", Static)
        path_str = self.query_one("#in-theme-toml", Input).value.strip() or "theme.toml"
        try:
            saved = theme_mod.ACTIVE_THEME.save_toml(path_str)
            status.update(f"SAVED THEME // {saved}")
            self.notify(f"Saved UI theme to {saved}", severity="information")
        except Exception as exc:
            status.update(f"THEME ERR // {exc}")
            self.notify(f"Failed to save theme {path_str}: {exc}", severity="error")

    def action_export_gif(self) -> None:
        if self._exporting:
            self.notify("Export already in progress.", severity="warning")
            return
        status = self.query_one("#status-bar", Static)
        try:
            cfg = self._read_config_from_inputs()
        except Exception as exc:
            status.update(f"ERR // {exc}")
            self.notify(f"Parameter error: {exc}", severity="error")
            return

        self.config = cfg
        self._run_export_worker(cfg)

    @work(thread=True)
    def _run_export_worker(self, cfg: SimulationConfig) -> None:
        self._exporting = True
        progress = self.query_one("#export-progress", ProgressBar)
        status = self.query_one("#status-bar", Static)
        total_frames = max(1, int(round(cfg.length * cfg.framerate)))
        self.call_from_thread(progress.update, total=total_frames, progress=0)
        self.call_from_thread(status.update, f"RENDERING // {cfg.output_path} (0/{total_frames})")

        def on_progress(done: int, total: int) -> None:
            self.call_from_thread(progress.update, total=total, progress=done)
            self.call_from_thread(
                status.update, f"RENDERING // {cfg.output_path} ({done}/{total} FRAMES)"
            )

        try:
            saved = simulate_from_config(cfg, progress_callback=on_progress)
            size_kb = Path(saved).stat().st_size / 1024.0
            self.call_from_thread(
                status.update, f"EXPORTED // {saved} ({size_kb:.1f} KB)"
            )
            self.call_from_thread(
                self.notify, f"Saved GIF to {saved} ({size_kb:.1f} KB)", severity="information"
            )
        except Exception as exc:
            self.call_from_thread(status.update, f"EXPORT ERR // {exc}")
            self.call_from_thread(self.notify, f"Export failed: {exc}", severity="error")
        finally:
            self._exporting = False

    @on(Button.Pressed, "#btn-play")
    def _on_play_pressed(self) -> None:
        self.action_toggle_play()

    @on(Button.Pressed, "#btn-step")
    def _on_step_pressed(self) -> None:
        if self.is_playing:
            self.action_toggle_play()
        field = self.simulator.step_frame()
        canvas = self.query_one("#bz-canvas", BZCanvas)
        canvas._active_field = field
        canvas.step_count = self.simulator.frame_idx
        canvas.refresh()

    @on(Button.Pressed, "#btn-view")
    def _on_view_pressed(self) -> None:
        self.action_cycle_view()

    @on(Button.Pressed, "#btn-reset")
    def _on_reset_pressed(self) -> None:
        self.action_reset_sim()

    @on(Button.Pressed, "#btn-export")
    def _on_export_pressed(self) -> None:
        self.action_export_gif()

    @on(Button.Pressed, "#btn-load-cfg")
    def _on_load_cfg_pressed(self) -> None:
        self.action_load_config_toml()

    @on(Button.Pressed, "#btn-save-cfg")
    def _on_save_cfg_pressed(self) -> None:
        self.action_save_config_toml()

    @on(Button.Pressed, "#btn-save-theme")
    def _on_save_theme_pressed(self) -> None:
        self.action_save_theme_toml()


def run_tui(config: SimulationConfig | None = None) -> None:
    """Launch the interactive Neo-Brutalist Textual TUI application."""
    config_path = "config.toml"
    theme_path = "theme.toml"
    if config is None:
        from bz_anim_cli.cli import args_to_config, build_arg_parser

        parser = build_arg_parser(add_mode_flag=False)
        args, _ = parser.parse_known_args()
        config = args_to_config(args)
        if args.config:
            config_path = args.config
        if args.theme:
            theme_path = args.theme
    app = BZTuiApp(initial_config=config, config_path=config_path, theme_path=theme_path)
    app.run()


if __name__ == "__main__":
    run_tui()
