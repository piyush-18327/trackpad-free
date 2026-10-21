"""Build dist/TrackpadFree.exe: one windowed executable for the app, tray and helpers.

    python -m pip install pyinstaller      (once, ideally in a virtual environment)
    python tools/build_exe.py

Uses PyInstaller in one-file mode. The exe relaunches itself for each entry
point (see runtime.py and trackpadfree.py), so it needs no Python install.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
# Read-only files the code opens at run time (runtime.RESOURCES), as (source, folder in bundle).
DATA = [("assets", "assets"), ("gesture_mapping.json", "."), ("Install-Driver.ps1", "."),
        ("Install-Tray.ps1", "."), ("THIRD_PARTY.md", "."), ("LICENSE", ".")]


def main() -> None:
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", "TrackpadFree", "--icon", str(ROOT / "assets" / "icon.ico"),
        "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / "build"), "--specpath", str(ROOT / "build"),
    ]
    for source, target in DATA:
        command += ["--add-data", f"{ROOT / source};{target}"]
    command.append(str(ROOT / "trackpadfree.py"))
    subprocess.run(command, check=True, cwd=ROOT)
    print(f"Built {ROOT / 'dist' / 'TrackpadFree.exe'}")


if __name__ == "__main__":
    main()
