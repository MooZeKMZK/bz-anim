#!/usr/bin/env bash
# Build modular Debian (.deb) packages for bz-anim:
#   - python3-bz-anim-core
#   - bz-anim-cli
#   - bz-anim-tui
#   - bz-anim-gui
#   - bz-anim (umbrella metapackage + unified dispatcher)
set -euo pipefail

VERSION="${1:-0.1.0}"
VERSION="${VERSION#v}"
ARCH="all"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_DIR="${2:-${ROOT_DIR}/dist/deb}"
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "${WORK_DIR}"' EXIT

mkdir -p "${OUT_DIR}"

# 1. Build wheels for all subpackages and root umbrella package
cd "${ROOT_DIR}"
for subpkg in core cli tui gui; do
  python3 -m build --wheel --outdir "${WORK_DIR}/wheels/${subpkg}" "packages/${subpkg}"
done
python3 -m build --wheel --outdir "${WORK_DIR}/wheels/umbrella" "${ROOT_DIR}"

install_wheel_into_deb_root() {
  local wheel_path="$1"
  local deb_root="$2"
  local tmp_install="${WORK_DIR}/tmp_install"
  rm -rf "${tmp_install}"
  mkdir -p "${tmp_install}"
  python3 -m pip install --no-deps --no-compile --root "${tmp_install}" --prefix /usr "${wheel_path}"

  mkdir -p "${deb_root}/usr/lib/python3/dist-packages"
  for site_dir in "${tmp_install}"/usr/lib/python*/site-packages "${tmp_install}"/usr/lib/python*/dist-packages "${tmp_install}"/usr/local/lib/python*/dist-packages "${tmp_install}"/usr/local/lib/python*/site-packages; do
    if [ -d "${site_dir}" ]; then
      cp -a "${site_dir}/." "${deb_root}/usr/lib/python3/dist-packages/"
    fi
  done

  for bin_dir in "${tmp_install}/usr/bin" "${tmp_install}/usr/local/bin"; do
    if [ -d "${bin_dir}" ]; then
      mkdir -p "${deb_root}/usr/bin"
      cp -a "${bin_dir}/." "${deb_root}/usr/bin/"
      sed -i '1s|^#!.*python.*|#!/usr/bin/python3|' "${deb_root}/usr/bin/"* || true
    fi
  done
}

build_deb_pkg() {
  local pkg_name="$1"
  local deps="$2"
  local recommends="$3"
  local desc_short="$4"
  local desc_long="$5"
  local wheel_dir="$6"
  local extra_hook="${7:-}"

  local pkg_root="${WORK_DIR}/${pkg_name}_${VERSION}_${ARCH}"
  mkdir -p "${pkg_root}/DEBIAN"

  install_wheel_into_deb_root "${wheel_dir}"/*.whl "${pkg_root}"

  if [ -n "${extra_hook}" ]; then
    ${extra_hook} "${pkg_root}"
  fi

  cat > "${pkg_root}/DEBIAN/control" <<EOF
Package: ${pkg_name}
Version: ${VERSION}
Section: science
Priority: optional
Architecture: ${ARCH}
Maintainer: MooZeKMZK <mooz.05@hotmail.com>
Homepage: https://github.com/MooZeKMZK/bz-anim
Depends: ${deps}
EOF

  if [ -n "${recommends}" ]; then
    echo "Recommends: ${recommends}" >> "${pkg_root}/DEBIAN/control"
  fi

  cat >> "${pkg_root}/DEBIAN/control" <<EOF
Description: ${desc_short}
 ${desc_long}
EOF

  find "${pkg_root}" -type d -exec chmod 0755 {} +
  dpkg-deb --root-owner-group --build "${pkg_root}" "${OUT_DIR}/${pkg_name}_${VERSION}_${ARCH}.deb"
}

hook_core() {
  local pkg_root="$1"
  install -Dm644 "${ROOT_DIR}/config.toml" "${pkg_root}/etc/bz-anim/config.toml"
  install -Dm644 "${ROOT_DIR}/theme.toml" "${pkg_root}/etc/bz-anim/theme.toml"
  cat > "${pkg_root}/DEBIAN/conffiles" <<EOF
/etc/bz-anim/config.toml
/etc/bz-anim/theme.toml
EOF
}

hook_gui() {
  local pkg_root="$1"
  install -Dm644 "${ROOT_DIR}/packaging/desktop/bz-anim.desktop" "${pkg_root}/usr/share/applications/bz-anim.desktop"
  install -Dm644 "${ROOT_DIR}/packaging/desktop/bz-anim.svg" "${pkg_root}/usr/share/icons/hicolor/scalable/apps/bz-anim.svg"
}

build_deb_pkg \
  "python3-bz-anim-core" \
  "python3 (>= 3.10), python3-numpy, python3-pil" \
  "" \
  "Core 2D Belousov-Zhabotinsky reaction-diffusion engine" \
  "Core 2D Belousov-Zhabotinsky reaction-diffusion simulation engine, TOML config loader, and Neo-Brutalist theme system." \
  "${WORK_DIR}/wheels/core" \
  "hook_core"

build_deb_pkg \
  "bz-anim-cli" \
  "python3 (>= 3.10), python3-bz-anim-core (>= ${VERSION})" \
  "" \
  "Command-line interface (bz-cli) for the BZ reaction simulator" \
  "Command-line interface for generating seamlessly looping, 2D torus-tileable Belousov-Zhabotinsky reaction GIF animations." \
  "${WORK_DIR}/wheels/cli"

build_deb_pkg \
  "bz-anim-tui" \
  "python3 (>= 3.10), python3-bz-anim-core (>= ${VERSION}), bz-anim-cli (>= ${VERSION})" \
  "python3-textual" \
  "Neo-Brutalist Textual terminal UI (bz-tui) for the BZ simulator" \
  "Interactive Textual terminal UI with 2x4 Braille sub-pixel rendering and live simulation controls for bz-anim." \
  "${WORK_DIR}/wheels/tui"

build_deb_pkg \
  "bz-anim-gui" \
  "python3 (>= 3.10), python3-bz-anim-core (>= ${VERSION}), bz-anim-cli (>= ${VERSION})" \
  "python3-pyside6.qtwidgets | python3-pyside6" \
  "Neo-Brutalist PySide6 desktop GUI (bz-gui) for the BZ simulator" \
  "Interactive cross-platform PySide6 desktop GUI with live viewport preview, Ferroin LUT, and GIF export for bz-anim." \
  "${WORK_DIR}/wheels/gui" \
  "hook_gui"

build_deb_pkg \
  "bz-anim" \
  "python3 (>= 3.10), python3-bz-anim-core (>= ${VERSION}), bz-anim-cli (>= ${VERSION})" \
  "bz-anim-tui (>= ${VERSION}), bz-anim-gui (>= ${VERSION})" \
  "Unified Belousov-Zhabotinsky reaction-diffusion simulator (CLI, TUI, GUI)" \
  "Umbrella dispatcher package providing the unified bz-anim command for CLI, Textual TUI, and PySide6 GUI modes." \
  "${WORK_DIR}/wheels/umbrella"

echo "Built Debian packages in ${OUT_DIR}:"
ls -lh "${OUT_DIR}"/*.deb
