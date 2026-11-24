"""Cross-platform PySide6 GUI for interactive 2D Belousov-Zhabotinsky simulation and GIF export.

Styled with the unified Neo-Brutalist design system shared with the Textual TUI, with live
TOML theme and options config file loading/saving.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from base import BZSimulator, SimulationConfig, parse_color, parse_size, simulate_from_config
import theme as theme_mod
from theme import ThemeConfig, apply_theme, load_theme_file


def build_gui_qss(theme: ThemeConfig | None = None) -> str:
    """Build the Neo-Brutalist Qt StyleSheet dynamically from `ThemeConfig`."""
    t = theme or theme_mod.ACTIVE_THEME
    return f"""
QMainWindow, QWidget#root {{
    background-color: {t.ink};
    color: {t.paper};
    font-family: "JetBrains Mono", "Fira Code", "Consolas", "Monospace";
    font-size: 12px;
}}

QScrollArea {{
    background-color: {t.surface};
    border: none;
    border-right: 4px solid {t.acid_cyan};
}}

QWidget#sidebar-content {{
    background-color: {t.surface};
}}

QScrollBar:vertical {{
    background: {t.ink};
    width: 12px;
    border-left: 2px solid {t.paper};
}}

QScrollBar::handle:vertical {{
    background: {t.acid_yellow};
    min-height: 24px;
    border: 2px solid {t.ink};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QFrame.brutal-card {{
    background-color: {t.panel};
    border: 3px solid {t.paper};
    border-radius: 0px;
}}

QLabel.field-label {{
    color: {t.paper};
    font-weight: 800;
    letter-spacing: 0.5px;
}}

QLineEdit, QSpinBox, QDoubleSpinBox {{
    background-color: {t.ink};
    color: {t.acid_cyan};
    border: 2px solid {t.paper};
    border-radius: 0px;
    padding: 5px 8px;
    font-weight: 800;
    selection-background-color: {t.acid_yellow};
    selection-color: {t.ink};
}}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 3px solid {t.acid_yellow};
    color: {t.acid_yellow};
}}

QCheckBox {{
    color: {t.paper};
    font-weight: 800;
    spacing: 8px;
    padding: 3px 0px;
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    background-color: {t.ink};
    border: 2px solid {t.paper};
}}

QCheckBox::indicator:checked {{
    background-color: {t.acid_lime};
    border: 2px solid {t.paper};
}}

QPushButton {{
    background-color: {t.panel};
    color: {t.paper};
    border: 3px solid {t.paper};
    border-radius: 0px;
    padding: 7px 14px;
    font-weight: 900;
    letter-spacing: 0.8px;
}}

QPushButton:hover {{
    background-color: {t.paper};
    color: {t.ink};
}}

QPushButton:pressed {{
    background-color: {t.acid_yellow};
    color: {t.ink};
}}

QPushButton#btn-play {{
    background-color: {t.acid_cyan};
    color: {t.ink};
    border: 3px solid {t.paper};
}}

QPushButton#btn-play:hover {{
    background-color: {t.paper};
    color: {t.ink};
}}

QPushButton#btn-reset {{
    background-color: {t.acid_yellow};
    color: {t.ink};
    border: 3px solid {t.paper};
}}

QPushButton#btn-reset:hover {{
    background-color: {t.paper};
    color: {t.ink};
}}

QPushButton#btn-export {{
    background-color: {t.acid_lime};
    color: {t.ink};
    border: 3px solid {t.paper};
    padding: 8px 18px;
}}

QPushButton#btn-export:hover {{
    background-color: {t.paper};
    color: {t.ink};
}}

QPushButton#btn-export:disabled {{
    background-color: {t.surface};
    color: {t.muted};
    border: 3px solid {t.muted};
}}

QProgressBar {{
    background-color: {t.ink};
    color: {t.paper};
    border: 3px solid {t.paper};
    border-radius: 0px;
    text-align: center;
    font-weight: 900;
    height: 24px;
}}

QProgressBar::chunk {{
    background-color: {t.hot_magenta};
}}
"""


def _apply_brutal_shadow(widget: QWidget, color_hex: str | None = None, offset: int = 5) -> None:
    """Attach a hard-edge, 0-blur Neo-Brutalist offset block shadow to `widget`."""
    c_hex = color_hex or theme_mod.ACTIVE_THEME.ink
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(0)
    shadow.setColor(QColor(c_hex))
    shadow.setOffset(offset, offset)
    widget.setGraphicsEffect(shadow)


class GifExportWorker(QThread):
    """Background Qt thread to render and save a BZ reaction GIF with progress signals."""

    progress = Signal(int, int)
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, config: SimulationConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = config

    def run(self) -> None:
        try:
            saved = simulate_from_config(
                self.config,
                progress_callback=lambda done, total: self.progress.emit(done, total),
            )
            self.finished_ok.emit(saved)
        except Exception as exc:
            self.failed.emit(str(exc))


class PreviewCanvas(QLabel):
    """Neo-Brutalist framed canvas displaying the live BZ reaction RGB buffer."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(360, 360)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.apply_theme_style()
        self._last_rgb: np.ndarray | None = None

    def apply_theme_style(self, theme: ThemeConfig | None = None) -> None:
        t = theme or theme_mod.ACTIVE_THEME
        self.setStyleSheet(
            f"background-color: {t.ink}; border: 4px solid {t.acid_cyan}; border-radius: 0px;"
        )
        _apply_brutal_shadow(self, t.acid_yellow, offset=6)

    def update_frame(self, rgb_array: np.ndarray) -> None:
        """Convert an `(H, W, 3)` uint8 numpy array to a scaled `QPixmap`."""
        self._last_rgb = np.ascontiguousarray(rgb_array, dtype=np.uint8)
        h, w, _ = self._last_rgb.shape
        bytes_per_line = 3 * w
        qimg = QImage(
            self._last_rgb.data,
            w,
            h,
            bytes_per_line,
            QImage.Format.Format_RGB888,
        )
        pix = QPixmap.fromImage(qimg)
        scaled = pix.scaled(
            self.contentsRect().size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._last_rgb is not None:
            self.update_frame(self._last_rgb)


class BZGuiWindow(QMainWindow):
    """Neo-Brutalist desktop GUI window for live previewing and exporting BZ animations."""

    def __init__(
        self,
        initial_config: SimulationConfig | None = None,
        config_path: str = "config.toml",
        theme_path: str = "theme.toml",
    ) -> None:
        super().__init__()
        self.config = initial_config or SimulationConfig()
        self.config_path = config_path
        self.theme_path = theme_path
        self.simulator = BZSimulator(self.config)
        self.is_playing = True
        self._worker: GifExportWorker | None = None
        self._section_tags: list[tuple[QLabel, str]] = []

        t = theme_mod.ACTIVE_THEME
        self.setWindowTitle(f"{t.app_title} — {t.app_subtitle}")
        self.resize(1140, 800)
        self.setStyleSheet(build_gui_qss(t))

        self._build_ui()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._update_timer_interval()
        self._timer.start()
        self._render_current()

    def _make_brutal_card(
        self, title: str, tag_role: str, tag_bg: str, tag_fg: str | None = None
    ) -> tuple[QFrame, QFormLayout]:
        """Create a Neo-Brutalist thick-bordered card with a high-contrast header banner."""
        t = theme_mod.ACTIVE_THEME
        fg = tag_fg or t.ink
        card = QFrame()
        card.setProperty("class", "brutal-card")
        _apply_brutal_shadow(card, t.ink, offset=5)

        outer = QVBoxLayout(card)
        outer.setContentsMargins(0, 0, 0, 10)
        outer.setSpacing(8)

        tag = QLabel(title)
        tag.setStyleSheet(
            f"background-color: {tag_bg}; color: {fg}; font-weight: 900; "
            f"padding: 6px 10px; border-bottom: 3px solid {t.paper}; letter-spacing: 1px;"
        )
        self._section_tags.append((tag, tag_role))
        outer.addWidget(tag)

        form_holder = QWidget()
        form = QFormLayout(form_holder)
        form.setContentsMargins(10, 4, 10, 4)
        form.setSpacing(8)
        outer.addWidget(form_holder)
        return card, form

    @staticmethod
    def _lbl(text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("class", "field-label")
        return label

    def _build_ui(self) -> None:
        t = theme_mod.ACTIVE_THEME
        central = QWidget(self)
        central.setObjectName("root")
        self.setCentralWidget(central)

        outer_col = QVBoxLayout(central)
        outer_col.setContentsMargins(0, 0, 0, 0)
        outer_col.setSpacing(0)

        # Top Neo-Brutalist Banner matching TUI
        self.top_banner = QLabel(
            f"■ {t.app_title}   //   {t.app_subtitle}   [NEO-BRUTALIST GUI]"
        )
        self.top_banner.setStyleSheet(
            f"background-color: {t.acid_yellow}; color: {t.ink}; font-weight: 900; "
            f"font-size: 13px; padding: 8px 16px; border-bottom: 4px solid {t.paper}; "
            f"letter-spacing: 1.2px;"
        )
        outer_col.addWidget(self.top_banner)

        # Workspace Split
        workspace = QHBoxLayout()
        workspace.setContentsMargins(0, 0, 0, 0)
        workspace.setSpacing(0)

        # Left scrollable parameter sidebar
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedWidth(440)
        sidebar = QWidget()
        sidebar.setObjectName("sidebar-content")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(14, 14, 18, 14)
        sidebar_layout.setSpacing(16)

        # 1. Output & Canvas Card
        card_canvas, form_canvas = self._make_brutal_card(
            t.section_canvas, "canvas", t.acid_cyan, t.ink
        )
        out_row = QHBoxLayout()
        self.ed_output = QLineEdit(str(self.config.output_path))
        btn_browse = QPushButton("FILE...")
        btn_browse.clicked.connect(self._browse_output)
        out_row.addWidget(self.ed_output)
        out_row.addWidget(btn_browse)
        form_canvas.addRow(self._lbl("OUTPUT GIF"), out_row)

        w, h = parse_size(self.config.size)
        size_row = QHBoxLayout()
        self.sp_width = QSpinBox()
        self.sp_width.setRange(16, 4096)
        self.sp_width.setValue(w)
        self.sp_height = QSpinBox()
        self.sp_height.setRange(16, 4096)
        self.sp_height.setValue(h)
        size_row.addWidget(self.sp_width)
        size_row.addWidget(self._lbl("×"))
        size_row.addWidget(self.sp_height)
        form_canvas.addRow(self._lbl("SIZE (W×H)"), size_row)

        self.sp_length = QDoubleSpinBox()
        self.sp_length.setRange(0.1, 300.0)
        self.sp_length.setSingleStep(0.5)
        self.sp_length.setDecimals(2)
        self.sp_length.setValue(float(self.config.length))
        form_canvas.addRow(self._lbl("LENGTH (S)"), self.sp_length)

        self.sp_framerate = QSpinBox()
        self.sp_framerate.setRange(1, 120)
        self.sp_framerate.setValue(int(self.config.framerate))
        self.sp_framerate.valueChanged.connect(self._on_live_param_changed)
        form_canvas.addRow(self._lbl("FRAMERATE"), self.sp_framerate)
        sidebar_layout.addWidget(card_canvas)

        # 2. Colors & Palette Card
        card_colors, form_colors = self._make_brutal_card(
            t.section_colors, "colors", t.acid_yellow, t.ink
        )
        bg_row = QHBoxLayout()
        self.ed_bg_color = QLineEdit(str(self.config.bg_color))
        self.ed_bg_color.editingFinished.connect(self._on_live_visual_changed)
        self.btn_bg_pick = QPushButton("PICK")
        self.btn_bg_pick.clicked.connect(lambda: self._pick_color(self.ed_bg_color))
        bg_row.addWidget(self.ed_bg_color)
        bg_row.addWidget(self.btn_bg_pick)
        form_colors.addRow(self._lbl("BG COLOR"), bg_row)

        rings_row = QHBoxLayout()
        self.ed_rings_color = QLineEdit(str(self.config.rings_color))
        self.ed_rings_color.editingFinished.connect(self._on_live_visual_changed)
        self.btn_rings_pick = QPushButton("PICK")
        self.btn_rings_pick.clicked.connect(lambda: self._pick_color(self.ed_rings_color))
        rings_row.addWidget(self.ed_rings_color)
        rings_row.addWidget(self.btn_rings_pick)
        form_colors.addRow(self._lbl("RINGS COLOR"), rings_row)

        self.sp_colors = QSpinBox()
        self.sp_colors.setRange(2, 256)
        self.sp_colors.setValue(int(self.config.colors))
        self.sp_colors.valueChanged.connect(self._on_live_visual_changed)
        form_colors.addRow(self._lbl("SHADES"), self.sp_colors)

        self.sp_pixel_size = QSpinBox()
        self.sp_pixel_size.setRange(1, 64)
        self.sp_pixel_size.setValue(int(self.config.pixel_size))
        self.sp_pixel_size.valueChanged.connect(self._on_live_visual_changed)
        form_colors.addRow(self._lbl("PIXEL SIZE"), self.sp_pixel_size)

        self.sp_palette_gamma = QDoubleSpinBox()
        self.sp_palette_gamma.setRange(0.1, 5.0)
        self.sp_palette_gamma.setSingleStep(0.05)
        self.sp_palette_gamma.setDecimals(2)
        self.sp_palette_gamma.setValue(float(self.config.palette_gamma))
        self.sp_palette_gamma.valueChanged.connect(self._on_live_visual_changed)
        form_colors.addRow(self._lbl("PAL GAMMA"), self.sp_palette_gamma)

        self.sp_contrast_gamma = QDoubleSpinBox()
        self.sp_contrast_gamma.setRange(0.1, 5.0)
        self.sp_contrast_gamma.setSingleStep(0.05)
        self.sp_contrast_gamma.setDecimals(2)
        self.sp_contrast_gamma.setValue(float(self.config.contrast_gamma))
        self.sp_contrast_gamma.valueChanged.connect(self._on_live_visual_changed)
        form_colors.addRow(self._lbl("CNT GAMMA"), self.sp_contrast_gamma)
        sidebar_layout.addWidget(card_colors)

        # 3. Reaction Kinetics Card
        card_kinetics, form_kinetics = self._make_brutal_card(
            t.section_kinetics, "kinetics", t.hot_magenta, t.ink
        )
        self.sp_speed = QDoubleSpinBox()
        self.sp_speed.setRange(0.05, 20.0)
        self.sp_speed.setSingleStep(0.1)
        self.sp_speed.setDecimals(2)
        self.sp_speed.setValue(float(self.config.speed))
        self.sp_speed.valueChanged.connect(self._on_live_param_changed)
        form_kinetics.addRow(self._lbl("SPEED (X)"), self.sp_speed)

        self.sp_alpha = QDoubleSpinBox()
        self.sp_alpha.setRange(0.0, 5.0)
        self.sp_alpha.setSingleStep(0.05)
        self.sp_alpha.setDecimals(2)
        self.sp_alpha.setValue(float(self.config.alpha))
        self.sp_alpha.valueChanged.connect(self._on_live_param_changed)
        form_kinetics.addRow(self._lbl("ALPHA A+B"), self.sp_alpha)

        self.sp_beta = QDoubleSpinBox()
        self.sp_beta.setRange(0.0, 5.0)
        self.sp_beta.setSingleStep(0.05)
        self.sp_beta.setDecimals(2)
        self.sp_beta.setValue(float(self.config.beta))
        self.sp_beta.valueChanged.connect(self._on_live_param_changed)
        form_kinetics.addRow(self._lbl("BETA B+C"), self.sp_beta)

        self.sp_gamma = QDoubleSpinBox()
        self.sp_gamma.setRange(0.0, 5.0)
        self.sp_gamma.setSingleStep(0.05)
        self.sp_gamma.setDecimals(2)
        self.sp_gamma.setValue(float(self.config.gamma))
        self.sp_gamma.valueChanged.connect(self._on_live_param_changed)
        form_kinetics.addRow(self._lbl("GAMMA C+A"), self.sp_gamma)

        self.sp_warmup = QSpinBox()
        self.sp_warmup.setRange(0, 2000)
        self.sp_warmup.setValue(int(self.config.warmup_steps))
        form_kinetics.addRow(self._lbl("WARMUP"), self.sp_warmup)

        self.sp_seed = QSpinBox()
        self.sp_seed.setRange(-1, 999999999)
        self.sp_seed.setSpecialValueText("RANDOM (-1)")
        self.sp_seed.setValue(-1 if self.config.seed is None else int(self.config.seed))
        form_kinetics.addRow(self._lbl("RNG SEED"), self.sp_seed)
        sidebar_layout.addWidget(card_kinetics)

        # 4. GIF Compression Card
        card_opt, form_opt = self._make_brutal_card(
            t.section_optimize, "optimize", t.acid_lime, t.ink
        )
        self.cb_optimize = QCheckBox("DELTA / LZW OPTIMIZE")
        self.cb_optimize.setChecked(bool(self.config.optimize))
        form_opt.addRow(self.cb_optimize)

        self.cb_despeckle = QCheckBox("DESPECKLE CELL DELTAS")
        self.cb_despeckle.setChecked(bool(self.config.despeckle))
        form_opt.addRow(self.cb_despeckle)

        self.cb_snap_steps = QCheckBox("SNAP DISCRETE STEPS")
        self.cb_snap_steps.setChecked(bool(self.config.snap_steps))
        form_opt.addRow(self.cb_snap_steps)

        self.sp_scanline = QDoubleSpinBox()
        self.sp_scanline.setRange(0.0, 0.5)
        self.sp_scanline.setSingleStep(0.05)
        self.sp_scanline.setDecimals(2)
        self.sp_scanline.setValue(float(self.config.scanline_smooth))
        form_opt.addRow(self._lbl("SCANLINE"), self.sp_scanline)

        self.sp_diff_thresh = QSpinBox()
        self.sp_diff_thresh.setRange(0, 32)
        self.sp_diff_thresh.setValue(int(self.config.diff_threshold))
        form_opt.addRow(self._lbl("DIFF THRESH"), self.sp_diff_thresh)

        self.sp_bg_snap = QDoubleSpinBox()
        self.sp_bg_snap.setRange(0.0, 2.0)
        self.sp_bg_snap.setSingleStep(0.05)
        self.sp_bg_snap.setDecimals(2)
        self.sp_bg_snap.setValue(float(self.config.bg_snap_threshold))
        form_opt.addRow(self._lbl("BG SNAP"), self.sp_bg_snap)
        sidebar_layout.addWidget(card_opt)

        # 5. TOML Config & Theme Card
        card_toml, form_toml = self._make_brutal_card(
            "05 // TOML CONFIG & THEME", "toml", t.electric_blue, t.ink
        )
        cfg_btn_row = QHBoxLayout()
        btn_load_cfg = QPushButton("LOAD CONFIG...")
        btn_load_cfg.clicked.connect(self._load_config_dialog)
        btn_save_cfg = QPushButton("SAVE CONFIG...")
        btn_save_cfg.clicked.connect(self._save_config_dialog)
        cfg_btn_row.addWidget(btn_load_cfg)
        cfg_btn_row.addWidget(btn_save_cfg)
        form_toml.addRow(self._lbl("OPTIONS"), cfg_btn_row)

        theme_btn_row = QHBoxLayout()
        btn_load_theme = QPushButton("LOAD THEME...")
        btn_load_theme.clicked.connect(self._load_theme_dialog)
        btn_save_theme = QPushButton("SAVE THEME...")
        btn_save_theme.clicked.connect(self._save_theme_dialog)
        theme_btn_row.addWidget(btn_load_theme)
        theme_btn_row.addWidget(btn_save_theme)
        form_toml.addRow(self._lbl("UI THEME"), theme_btn_row)
        sidebar_layout.addWidget(card_toml)

        sidebar_layout.addStretch()

        scroll.setWidget(sidebar)
        workspace.addWidget(scroll)

        # Right panel: live viewport + Neo-Brutalist action buttons + telemetry box
        right_container = QWidget()
        right_panel = QVBoxLayout(right_container)
        right_panel.setContentsMargins(18, 14, 22, 16)
        right_panel.setSpacing(12)

        self.viewport_header = QLabel("LIVE REACTION VIEWPORT // HIGH-SPEED RASTER BUFFER")
        self.viewport_header.setStyleSheet(
            f"background-color: {t.acid_cyan}; color: {t.ink}; font-weight: 900; "
            f"padding: 6px 12px; border: 3px solid {t.paper}; letter-spacing: 1px;"
        )
        right_panel.addWidget(self.viewport_header)

        self.canvas = PreviewCanvas()
        right_panel.addWidget(self.canvas, stretch=1)

        controls_row = QHBoxLayout()
        controls_row.setSpacing(12)

        self.btn_play = QPushButton("❚❚ PAUSE")
        self.btn_play.setObjectName("btn-play")
        _apply_brutal_shadow(self.btn_play, t.paper, offset=4)
        self.btn_play.clicked.connect(self._toggle_play)

        self.btn_step = QPushButton("⏭ STEP FRAME")
        _apply_brutal_shadow(self.btn_step, t.paper, offset=4)
        self.btn_step.clicked.connect(self._step_once)

        self.btn_reset = QPushButton("↺ APPLY & RESET")
        self.btn_reset.setObjectName("btn-reset")
        _apply_brutal_shadow(self.btn_reset, t.paper, offset=4)
        self.btn_reset.clicked.connect(self._reset_simulation)

        self.btn_export = QPushButton("⬇ EXPORT ANIMATED GIF")
        self.btn_export.setObjectName("btn-export")
        _apply_brutal_shadow(self.btn_export, t.acid_cyan, offset=4)
        self.btn_export.clicked.connect(self._start_export)

        controls_row.addWidget(self.btn_play)
        controls_row.addWidget(self.btn_step)
        controls_row.addWidget(self.btn_reset)
        controls_row.addStretch()
        controls_row.addWidget(self.btn_export)
        right_panel.addLayout(controls_row)

        self.telemetry_frame = QFrame()
        self.telemetry_frame.setStyleSheet(
            f"background-color: {t.surface}; border: 3px solid {t.paper}; padding: 6px;"
        )
        status_row = QHBoxLayout(self.telemetry_frame)
        status_row.setContentsMargins(8, 4, 8, 4)

        self.lbl_status = QLabel("STATUS // READY")
        self.lbl_status.setStyleSheet(
            f"color: {t.acid_yellow}; font-weight: 900; border: none; letter-spacing: 0.8px;"
        )
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedWidth(250)
        status_row.addWidget(self.lbl_status, stretch=1)
        status_row.addWidget(self.progress_bar)
        right_panel.addWidget(self.telemetry_frame)

        workspace.addWidget(right_container, stretch=1)
        outer_col.addLayout(workspace, stretch=1)

    def apply_loaded_theme(self, theme: ThemeConfig) -> None:
        """Dynamically restyle the entire PySide6 GUI window when a new TOML theme is loaded."""
        t = apply_theme(theme)
        self.setWindowTitle(f"{t.app_title} — {t.app_subtitle}")
        self.setStyleSheet(build_gui_qss(t))
        self.top_banner.setText(
            f"■ {t.app_title}   //   {t.app_subtitle}   [NEO-BRUTALIST GUI]"
        )
        self.top_banner.setStyleSheet(
            f"background-color: {t.acid_yellow}; color: {t.ink}; font-weight: 900; "
            f"font-size: 13px; padding: 8px 16px; border-bottom: 4px solid {t.paper}; "
            f"letter-spacing: 1.2px;"
        )
        self.viewport_header.setStyleSheet(
            f"background-color: {t.acid_cyan}; color: {t.ink}; font-weight: 900; "
            f"padding: 6px 12px; border: 3px solid {t.paper}; letter-spacing: 1px;"
        )
        self.telemetry_frame.setStyleSheet(
            f"background-color: {t.surface}; border: 3px solid {t.paper}; padding: 6px;"
        )
        self.lbl_status.setStyleSheet(
            f"color: {t.acid_yellow}; font-weight: 900; border: none; letter-spacing: 0.8px;"
        )
        self.canvas.apply_theme_style(t)

        role_map = {
            "canvas": (t.section_canvas, t.acid_cyan),
            "colors": (t.section_colors, t.acid_yellow),
            "kinetics": (t.section_kinetics, t.hot_magenta),
            "optimize": (t.section_optimize, t.acid_lime),
            "toml": ("05 // TOML CONFIG & THEME", t.electric_blue),
        }
        for lbl_widget, role in self._section_tags:
            if role in role_map:
                title_txt, bg_hex = role_map[role]
                lbl_widget.setText(title_txt)
                lbl_widget.setStyleSheet(
                    f"background-color: {bg_hex}; color: {t.ink}; font-weight: 900; "
                    f"padding: 6px 10px; border-bottom: 3px solid {t.paper}; letter-spacing: 1px;"
                )

    def _populate_ui_from_config(self, cfg: SimulationConfig) -> None:
        """Populate all GUI controls from a `SimulationConfig` instance."""
        self.ed_output.setText(str(cfg.output_path))
        w, h = parse_size(cfg.size)
        self.sp_width.setValue(w)
        self.sp_height.setValue(h)
        self.sp_length.setValue(float(cfg.length))
        self.sp_framerate.setValue(int(cfg.framerate))
        self.ed_bg_color.setText(str(cfg.bg_color))
        self.ed_rings_color.setText(str(cfg.rings_color))
        self.sp_colors.setValue(int(cfg.colors))
        self.sp_pixel_size.setValue(int(cfg.pixel_size))
        self.sp_palette_gamma.setValue(float(cfg.palette_gamma))
        self.sp_contrast_gamma.setValue(float(cfg.contrast_gamma))
        self.sp_speed.setValue(float(cfg.speed))
        self.sp_alpha.setValue(float(cfg.alpha))
        self.sp_beta.setValue(float(cfg.beta))
        self.sp_gamma.setValue(float(cfg.gamma))
        self.sp_warmup.setValue(int(cfg.warmup_steps))
        self.sp_seed.setValue(-1 if cfg.seed is None else int(cfg.seed))
        self.cb_optimize.setChecked(bool(cfg.optimize))
        self.cb_despeckle.setChecked(bool(cfg.despeckle))
        self.cb_snap_steps.setChecked(bool(cfg.snap_steps))
        self.sp_scanline.setValue(float(cfg.scanline_smooth))
        self.sp_diff_thresh.setValue(int(cfg.diff_threshold))
        self.sp_bg_snap.setValue(float(cfg.bg_snap_threshold))

    def _load_config_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Simulation Options (TOML)",
            self.config_path,
            "TOML Files (*.toml);;All Files (*)",
        )
        if not path:
            return
        try:
            cfg = SimulationConfig.from_toml(path)
            self.config_path = path
            self._populate_ui_from_config(cfg)
            self._reset_simulation()
            self.lbl_status.setText(f"LOADED CONFIG // {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Failed to Load Config TOML", str(exc))

    def _save_config_dialog(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Simulation Options (TOML)",
            self.config_path,
            "TOML Files (*.toml);;All Files (*)",
        )
        if not path:
            return
        try:
            cfg = self._build_config_from_ui()
            saved = cfg.save_toml(path)
            self.config_path = str(saved)
            self.lbl_status.setText(f"SAVED CONFIG // {saved}")
        except Exception as exc:
            QMessageBox.critical(self, "Failed to Save Config TOML", str(exc))

    def _load_theme_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load UI Theme (TOML)",
            self.theme_path,
            "TOML Files (*.toml);;All Files (*)",
        )
        if not path:
            return
        try:
            theme = ThemeConfig.from_toml(path)
            self.theme_path = path
            self.apply_loaded_theme(theme)
            self.lbl_status.setText(f"LOADED THEME // {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Failed to Load Theme TOML", str(exc))

    def _save_theme_dialog(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save UI Theme (TOML)",
            self.theme_path,
            "TOML Files (*.toml);;All Files (*)",
        )
        if not path:
            return
        try:
            saved = theme_mod.ACTIVE_THEME.save_toml(path)
            self.theme_path = str(saved)
            self.lbl_status.setText(f"SAVED THEME // {saved}")
        except Exception as exc:
            QMessageBox.critical(self, "Failed to Save Theme TOML", str(exc))

    def _browse_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Animated GIF",
            self.ed_output.text() or "bz_reaction.gif",
            "GIF Images (*.gif);;All Files (*)",
        )
        if path:
            self.ed_output.setText(path)

    def _pick_color(self, line_edit: QLineEdit) -> None:
        try:
            r, g, b = parse_color(line_edit.text())
            initial = QColor(r, g, b)
        except Exception:
            initial = QColor(theme_mod.ACTIVE_THEME.acid_cyan)
        chosen = QColorDialog.getColor(initial, self, "Select Color")
        if chosen.isValid():
            line_edit.setText(chosen.name())
            self._on_live_visual_changed()

    def _build_config_from_ui(self) -> SimulationConfig:
        seed_val = self.sp_seed.value()
        cfg = SimulationConfig(
            output_path=self.ed_output.text().strip() or "bz_reaction.gif",
            size=(self.sp_width.value(), self.sp_height.value()),
            length=self.sp_length.value(),
            framerate=self.sp_framerate.value(),
            bg_color=self.ed_bg_color.text().strip(),
            rings_color=self.ed_rings_color.text().strip(),
            speed=self.sp_speed.value(),
            alpha=self.sp_alpha.value(),
            beta=self.sp_beta.value(),
            gamma=self.sp_gamma.value(),
            warmup_steps=self.sp_warmup.value(),
            seed=None if seed_val < 0 else seed_val,
            colors=self.sp_colors.value(),
            pixel_size=self.sp_pixel_size.value(),
            palette_gamma=self.sp_palette_gamma.value(),
            contrast_gamma=self.sp_contrast_gamma.value(),
            scanline_smooth=self.sp_scanline.value(),
            bg_snap_threshold=self.sp_bg_snap.value(),
            despeckle=self.cb_despeckle.isChecked(),
            snap_steps=self.cb_snap_steps.isChecked(),
            optimize=self.cb_optimize.isChecked(),
            diff_threshold=self.sp_diff_thresh.value(),
        )
        cfg.validate()
        return cfg

    def _update_timer_interval(self) -> None:
        fps = max(1, min(60, self.sp_framerate.value()))
        self._timer.setInterval(max(15, int(round(1000.0 / fps))))

    def _on_live_param_changed(self) -> None:
        try:
            self.simulator.config.speed = self.sp_speed.value()
            self.simulator.config.alpha = self.sp_alpha.value()
            self.simulator.config.beta = self.sp_beta.value()
            self.simulator.config.gamma = self.sp_gamma.value()
            self.simulator.config.framerate = self.sp_framerate.value()
            self._update_timer_interval()
        except Exception:
            pass

    def _on_live_visual_changed(self) -> None:
        try:
            parse_color(self.ed_bg_color.text().strip())
            parse_color(self.ed_rings_color.text().strip())
            self.simulator.config.bg_color = self.ed_bg_color.text().strip()
            self.simulator.config.rings_color = self.ed_rings_color.text().strip()
            self.simulator.config.colors = self.sp_colors.value()
            self.simulator.config.pixel_size = self.sp_pixel_size.value()
            self.simulator.config.palette_gamma = self.sp_palette_gamma.value()
            self.simulator.config.contrast_gamma = self.sp_contrast_gamma.value()
            self.simulator.update_visual_params()
            self._render_current()
        except Exception:
            pass

    def _on_tick(self) -> None:
        if not self.is_playing:
            return
        field = self.simulator.step_frame()
        rgb = self.simulator.render_rgb_array(field, smooth_preview=True)
        self.canvas.update_frame(rgb)
        if self._worker is None or not self._worker.isRunning():
            self.lbl_status.setText(
                f"LIVE // GRID {self.simulator.width}×{self.simulator.height} // "
                f"STEP #{self.simulator.curr_step:04d} // SPEED {self.simulator.config.speed:.2f}X"
            )

    def _render_current(self) -> None:
        rgb = self.simulator.render_rgb_array(smooth_preview=True)
        self.canvas.update_frame(rgb)

    def _toggle_play(self) -> None:
        self.is_playing = not self.is_playing
        self.btn_play.setText("❚❚ PAUSE" if self.is_playing else "▶ PLAY")

    def _step_once(self) -> None:
        if self.is_playing:
            self._toggle_play()
        field = self.simulator.step_frame()
        rgb = self.simulator.render_rgb_array(field, smooth_preview=True)
        self.canvas.update_frame(rgb)
        self.lbl_status.setText(
            f"PAUSED // GRID {self.simulator.width}×{self.simulator.height} // "
            f"STEP #{self.simulator.curr_step:04d}"
        )

    def _reset_simulation(self) -> None:
        try:
            cfg = self._build_config_from_ui()
        except Exception as exc:
            QMessageBox.warning(self, "Invalid Parameter", str(exc))
            return
        self.config = cfg
        self.simulator.reset(cfg)
        self._update_timer_interval()
        self._render_current()
        self.lbl_status.setText(
            f"RESET // {self.simulator.width}×{self.simulator.height} GRID INITIALIZED"
        )

    def _start_export(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        try:
            cfg = self._build_config_from_ui()
        except Exception as exc:
            QMessageBox.warning(self, "Invalid Parameter", str(exc))
            return

        self.config = cfg
        self.btn_export.setEnabled(False)
        total_frames = max(1, int(round(cfg.length * cfg.framerate)))
        self.progress_bar.setRange(0, total_frames)
        self.progress_bar.setValue(0)
        self.lbl_status.setText(f"RENDERING // {cfg.output_path} (0/{total_frames})")

        self._worker = GifExportWorker(cfg, self)
        self._worker.progress.connect(self._on_export_progress)
        self._worker.finished_ok.connect(self._on_export_finished)
        self._worker.failed.connect(self._on_export_failed)
        self._worker.start()

    def _on_export_progress(self, done: int, total: int) -> None:
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(done)
        self.lbl_status.setText(f"RENDERING // {self.config.output_path} ({done}/{total} FRAMES)")

    def _on_export_finished(self, saved_path: str) -> None:
        self.btn_export.setEnabled(True)
        size_kb = Path(saved_path).stat().st_size / 1024.0
        self.lbl_status.setText(f"EXPORTED // {saved_path} ({size_kb:.1f} KB)")
        QMessageBox.information(
            self,
            "Export Complete",
            f"Saved Belousov-Zhabotinsky animation to:\n{saved_path}\n({size_kb:.1f} KB)",
        )

    def _on_export_failed(self, err_msg: str) -> None:
        self.btn_export.setEnabled(True)
        self.lbl_status.setText(f"EXPORT ERR // {err_msg}")
        QMessageBox.critical(self, "Export Failed", err_msg)


def run_gui(config: SimulationConfig | None = None) -> int:
    """Launch the Neo-Brutalist PySide6 GUI application."""
    config_path = "config.toml"
    theme_path = "theme.toml"
    if config is None:
        from cli import args_to_config, build_arg_parser

        parser = build_arg_parser(add_mode_flag=False)
        args, _ = parser.parse_known_args()
        config = args_to_config(args)
        if args.config:
            config_path = args.config
        if args.theme:
            theme_path = args.theme
    app = QApplication.instance() or QApplication(sys.argv)
    window = BZGuiWindow(initial_config=config, config_path=config_path, theme_path=theme_path)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(run_gui())
