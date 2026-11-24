# BZ-ANIM // 2D Belousov-Zhabotinsky Reaction-Diffusion Studio

A 2D **Belousov-Zhabotinsky (BZ)** excitable-media chemical reaction simulator and optimized animated GIF generator that **loops seamlessly in time** and **tiles seamlessly in space (2D Torus Topology)**.

Includes three unified interfaces sharing a Neo-Brutalist theme and TOML configuration system:
- **Headless CLI** (`bz-anim --mode cli` / `bz-anim-cli`)
- **Terminal User Interface (TUI)** (`bz-anim --mode tui` / `bz-anim-tui`) powered by Textual with 2×4 Braille sub-pixel, Soft Pixel, Half-Block, and Orb Matrix live viewports
- **Desktop Graphical User Interface (GUI)** (`bz-anim --mode gui` / `bz-anim-gui`) powered by PySide6

---

## Core Features

### 1. 3-Species Cyclic Reaction-Diffusion Simulation
- **`float32` Ping-Pong Buffers:** High-precision 2D floating-point concentration arrays (`a, b, c` in `[0, 1]`) eliminate quantization and color banding during simulation.
- **Warm-Up & Multi-Substepping:** Runs configurable warm-up steps before recording frame 0 so random noise nucleates into stable spiral waves, and supports fractional/multi-substep integration per output frame.
- **Chemical Color Mapping (1D LUT):**
  - **Custom 2-Stop Gradient (`--palette-mode gradient`):** Gamma-corrected ramp between `--bg-color` and `--rings-color`.
  - **Ferroin 1D Chemical LUT (`--palette-mode ferroin`):** Realistic 5-stop ferroin-catalyzed BZ gradient (deep rust-red resting medium → dark crimson → pale lavender/white transitional fringe → bright cobalt-blue → peak cyan oxidized wavefronts).

### 2. Seamless Temporal Loop via Chemical Color-Pulse Wipe
Digital BZ spiral waves are chaotic and dissipative, rarely returning to their starting state. `bz-anim` hides the loop seam using an expanding high-intensity oxidation trigger wave:
- **Wave-Masked Pre-LUT Scalar Field Blend:** Simulates $N + K$ post-warmup frames ($N$ = loop length, $K = \text{round}(N \times \text{loop\_wipe\_ratio})$). During the wipe window, samples ahead of the expanding front from tail frames ($N \dots N+K-1$), reveals start frames ($0 \dots K-1$) behind the front, and drives the wave crest to peak oxidation (`1.0`).
- **Pre-LUT Blending:** Blends raw `float32` scalar chemical concentration fields *before* palette quantization and LUT mapping—preventing muddy RGB crossfading.
- **Asymmetric Wave Profile & Organic 4D Noise:** Features a razor-sharp leading oxidation flash (`--pulse-sharpness`), gradual trailing recovery tail (`--pulse-decay`), faster propagation than underlying spirals (`--pulse-speed`), and periodic 4D torus noise warping (`--pulse-noise-amp`, `--pulse-noise-freq`).

### 3. Seamless Spatial Tileability (2D Torus Topology)
Every stage of the simulation, pulse wipe, and post-processing preserves periodic wrap-around continuity (`--tileable` / `--no-tileable`):
- **Toroidal Neighborhood Convolutions:** 3×3 spatial averages wrap across opposite canvas edges.
- **Toroidal Radial Distance & Anti-Grid Origins:** Computes shortest wrapped distance on the 2D torus from `--pulse-count` staggered golden-ratio pulse origins so expanding rings collide organically across tile boundaries instead of forming a centered polka-dot grid.
- **4D Torus Wavefront Distortion Noise:** Maps normalized $(u, v) \in [0, 1]^2$ onto a 4D hypertorus $(\cos 2\pi u, \sin 2\pi u, \cos 2\pi v, \sin 2\pi v)$ so wavefront distortion has zero seam discontinuity at $u, v \in \{0, 1\}$.
- **Tileable Post-Processing:** Block downsampling (`--pixel-size`), horizontal scanline smoothing (`--scanline-smooth`), and inter-frame delta despeckling (`--despeckle`) all use periodic wrap-around indexing.

### 4. Interactive Hover Descriptions (TUI & GUI)
Every parameter row, label, input field, checkbox, and button in both the Textual TUI and PySide6 GUI provides:
- **Instant (`0 ms`) Status-Bar Description:** Hovering or focusing (`Tab`) any control immediately shows `INFO // <description>` in the bottom telemetry bar.
- **Floating Neo-Brutalist Tooltip Popup:** Resting the cursor over any option opens a themed floating tooltip box.

---

## Quick Start

### Virtual Environment Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Launching the Interfaces
```bash
# Launch the PySide6 Desktop GUI
python src/bz-anim.py --mode gui

# Launch the Textual Terminal UI (TUI)
python src/bz-anim.py --mode tui

# Run Headless CLI Export using config.toml
python src/bz-anim.py --mode cli --config config.toml -o bz_reaction.gif
```

### Headless CLI Examples
```bash
# Seamlessly looping & tileable Ferroin-catalyzed BZ reaction (320x320, 5s @ 20fps)
python src/bz-anim.py --mode cli \
  --size 320x320 \
  --length 5 \
  --framerate 20 \
  --palette-mode ferroin \
  --seamless-loop \
  --tileable \
  --pulse-count 3 \
  --loop-wipe-ratio 0.28 \
  -o bz_ferroin_loop.gif

# Custom 2-stop gradient with chunky retro pixel blocks
python src/bz-anim.py --mode cli \
  --size 256x256 \
  --bg-color "#0b132b" \
  --rings-color "#00f5d4" \
  --pixel-size 2 \
  --colors 12 \
  -o bz_retro.gif
```

---

## CLI Options Reference

| Flag | Default | Description |
| :--- | :--- | :--- |
| `-o`, `--output` | `bz_reaction.gif` | Destination path for the exported animated GIF |
| `--config` | `config.toml` | Load simulation parameters from a TOML file |
| `--save-config` | — | Save resolved simulation parameters to a TOML file |
| `--theme` | `theme.toml` | Load Neo-Brutalist UI theme colors from a TOML file |
| `-s`, `--size` | `240x240` | Grid and output GIF resolution (`WIDTHxHEIGHT` or single integer) |
| `-l`, `--length` | `4.0` | Animation duration in seconds |
| `-f`, `--framerate` | `20` | Output frame rate in frames per second (FPS) |
| `--palette-mode` | `gradient` | Chemical color LUT mode: `gradient` or `ferroin` |
| `--bg-color` | `#0b132b` | Resting background color (hex, name, or `R,G,B`) |
| `--rings-color` | `#00f5d4` | Oxidized wavefront ring color (hex, name, or `R,G,B`) |
| `--colors` | `10` | Discrete color shades in the quantized GIF palette (`2..256`) |
| `--pixel-size` | `1` | Pixel block downsampling factor (`1` = full resolution) |
| `--palette-gamma` | `1.15` | Gamma exponent for palette ramp generation |
| `--contrast-gamma` | `1.15` | Field quantization contrast exponent |
| `--speed` | `1.0` | Reaction evolution speed multiplier |
| `--alpha` | `1.2` | Reaction rate $\alpha$ ($A + B \to 2A$) |
| `--beta` | `1.0` | Reaction rate $\beta$ ($B + C \to 2B$) |
| `--gamma` | `1.0` | Reaction rate $\gamma$ ($C + A \to 2C$) |
| `--warmup` | `65` | Initial warm-up steps before recording frame 0 |
| `--seed` | `None` | Optional deterministic RNG seed (`-1` for random) |
| `--seamless-loop` / `--no-seamless-loop` | `True` | Enable/disable seamless temporal loop via chemical oxidation pulse wipe |
| `--tileable` / `--no-tileable` | `True` | Enable/disable 2D torus periodic spatial wrap-around |
| `--loop-wipe-ratio` | `0.28` | Fraction of loop duration (`0.05..0.95`) for the oxidation pulse wipe |
| `--pulse-count` | `3` | Number of staggered anti-grid radial oxidation pulses |
| `--pulse-speed` | `1.45` | Propagation speed of the oxidation trigger pulse |
| `--pulse-sharpness` | `18.0` | Leading-edge steepness of the oxidation trigger wave |
| `--pulse-decay` | `4.0` | Trailing recovery decay rate behind the trigger wave |
| `--pulse-noise-amp` | `0.08` | Amplitude of 4D toroidal wavefront distortion noise |
| `--pulse-noise-freq` | `3` | Spatial harmonic frequency of 4D toroidal distortion noise |
| `--optimize` / `--no-optimize` | `True` | Enable GIF delta-frame transparency and LZW optimization |
| `--despeckle` / `--no-despeckle` | `True` | Suppress isolated 1-cell inter-frame delta speckles |
| `--snap-steps` / `--no-snap-steps` | `True` | Snap frames to discrete simulation steps when step advance $\le 1.0$ |
| `--scanline-smooth` | `0.15` | Horizontal scanline smoothing weight (`0.0..0.5`) for LZW runs |
| `--diff-threshold` | `1` | Inter-frame palette index difference tolerance (`0..32`) |
| `--bg-snap-threshold` | `0.25` | Threshold factor snapping decaying background wake cells to index 0 |

---

## Modular Package Layout

The repository is structured both as direct top-level modules in `src/` and as independent PEP 621 packages under `packages/`:

- `packages/core` (`bz-anim-core`): Core 2D reaction-diffusion engine (`BZSimulator`, `SimulationConfig`), Ferroin LUT, 4D torus noise, GIF optimizer, and Neo-Brutalist theme/tooltip catalog.
- `packages/cli` (`bz-anim-cli`): Headless command-line parser and runner (`bz-anim-cli`).
- `packages/tui` (`bz-anim-tui`): Textual terminal UI (`bz-anim-tui`).
- `packages/gui` (`bz-anim-gui`): PySide6 desktop GUI (`bz-anim-gui`).

---

## Packaging & CI/CD Releases

Automated multi-platform release builds are configured in `.github/workflows/release.yml` (triggered on `v*` tags or manual workflow dispatch) with local build scripts under `packaging/`:

- **Debian / Ubuntu (`.deb`):**
  ```bash
  bash packaging/deb/build-deb.sh 0.1.0 dist
  ```
  Produces modular `python3-bz-anim-core`, `bz-anim-cli`, `bz-anim-tui`, `bz-anim-gui`, and metapackage `bz-anim` `.deb` archives.
- **Fedora / RHEL / openSUSE (`.rpm` & `.rpk`):**
  ```bash
  bash packaging/rpm/build-rpm.sh 0.1.0 dist
  ```
  Builds `.rpm` and `.rpk` packages from `packaging/rpm/bz-anim.spec`.
- **Arch Linux (AUR):**
  Split-package `PKGBUILD` and `.SRCINFO` in `packaging/aur/` (`bz-anim-core`, `bz-anim-cli`, `bz-anim-tui`, `bz-anim-gui`, `bz-anim`).
- **Windows (`.exe`, `.zip`, `.whl`):**
  ```bash
  python packaging/windows/build_windows.py --version 0.1.0 --out-dir dist
  ```
  Builds standalone PyInstaller executables (`bz-anim-gui.exe`, `bz-anim-tui.exe`, `bz-anim-cli.exe`), a portable `.zip` bundle, and Python wheels.
