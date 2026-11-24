"""Build standalone Windows executables (`bz-anim.exe`, `bz-cli.exe`, `bz-tui.exe`, `bz-gui.exe`) and a portable release ZIP."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent.parent
SRC_DIR = ROOT_DIR / "src"
DIST_DIR = ROOT_DIR / "dist"
STAGE_DIR = DIST_DIR / "bz-anim-windows-x86_64"


def run_pyinstaller(args: list[str]) -> None:
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", *args]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, cwd=str(ROOT_DIR), check=True)


def main() -> int:
    version = sys.argv[1].lstrip("v") if len(sys.argv) > 1 else "0.1.0"

    if STAGE_DIR.exists():
        shutil.rmtree(STAGE_DIR)
    STAGE_DIR.mkdir(parents=True, exist_ok=True)

    common_args = [
        "--paths",
        str(SRC_DIR),
        "--distpath",
        str(STAGE_DIR),
        "--workpath",
        str(ROOT_DIR / "build" / "pyinstaller"),
        "--specpath",
        str(ROOT_DIR / "build" / "pyinstaller"),
    ]

    # 1. Unified dispatcher (bz-anim.exe) - console entrypoint supporting CLI, TUI, and GUI
    run_pyinstaller(
        [
            *common_args,
            "--onefile",
            "--console",
            "--name",
            "bz-anim",
            "--hidden-import",
            "textual",
            "--hidden-import",
            "PySide6",
            str(SRC_DIR / "bz_anim.py"),
        ]
    )

    # 2. Dedicated CLI executable (bz-cli.exe)
    run_pyinstaller(
        [
            *common_args,
            "--onefile",
            "--console",
            "--name",
            "bz-cli",
            str(SRC_DIR / "cli.py"),
        ]
    )

    # 3. Dedicated Textual TUI executable (bz-tui.exe)
    run_pyinstaller(
        [
            *common_args,
            "--onefile",
            "--console",
            "--name",
            "bz-tui",
            "--hidden-import",
            "textual",
            str(SRC_DIR / "tui.py"),
        ]
    )

    # 4. Dedicated Windowed PySide6 GUI executable (bz-gui.exe)
    run_pyinstaller(
        [
            *common_args,
            "--onefile",
            "--windowed",
            "--name",
            "bz-gui",
            "--hidden-import",
            "PySide6",
            str(SRC_DIR / "gui.py"),
        ]
    )

    # Bundle default config.toml and theme.toml beside the executables
    shutil.copy2(ROOT_DIR / "config.toml", STAGE_DIR / "config.toml")
    shutil.copy2(ROOT_DIR / "theme.toml", STAGE_DIR / "theme.toml")

    zip_base = DIST_DIR / f"bz-anim-{version}-windows-x86_64"
    archive_path = shutil.make_archive(str(zip_base), "zip", root_dir=str(DIST_DIR), base_dir=STAGE_DIR.name)
    print(f"Created Windows portable release archive: {archive_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
