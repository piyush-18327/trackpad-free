"""Fetch the unmodified, signed upstream driver and its corresponding source."""

from __future__ import annotations

import argparse
import hashlib
import io
import os
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent
PACKAGE_DIR = ROOT / "drivers" / "v2.2"
RELEASE = "https://github.com/vitoplantamura/MagicTrackpad2ForWindows/releases/tag/v2.2"
ARCHIVE_NAME = "MT2FW11-20261012-MSSigned.zip"
DOWNLOAD = RELEASE.replace("/tag/", "/download/") + "/" + ARCHIVE_NAME
SHA256 = "211afdbe1e9265cd1f5e3f7d1a711e947e96b48e9e8e63fec6b857f354e4489f"
SOURCE_URL = "https://codeload.github.com/vitoplantamura/MagicTrackpad2ForWindows/zip/refs/tags/v2.2"
MAX_DOWNLOAD = 16 * 1024 * 1024


def architecture() -> str:
    native = os.environ.get("PROCESSOR_ARCHITEW6432") or os.environ.get("PROCESSOR_ARCHITECTURE", "")
    if native.upper() not in ("AMD64", "ARM64"):
        raise RuntimeError("The signed package requires Windows 11 AMD64 or ARM64.")
    return native.upper()


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "TrackpadFree/0.2"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(MAX_DOWNLOAD + 1)
    if len(data) > MAX_DOWNLOAD:
        raise RuntimeError("Download exceeded the expected package size.")
    return data


def checked_zip(data: bytes) -> zipfile.ZipFile:
    archive = zipfile.ZipFile(io.BytesIO(data))
    total = 0
    for entry in archive.infolist():
        path = Path(entry.filename)
        if path.is_absolute() or path.drive or ".." in path.parts or ":" in entry.filename:
            archive.close()
            raise RuntimeError("Unsafe path in upstream archive.")
        total += entry.file_size
    if total > MAX_DOWNLOAD * 8:
        archive.close()
        raise RuntimeError("Unexpected expanded archive size.")
    return archive


def verify_package() -> Path:
    data = (PACKAGE_DIR / ARCHIVE_NAME).read_bytes()
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise RuntimeError("Driver archive SHA-256 does not match the pinned upstream release.")
    with checked_zip(data) as archive:
        for entry in archive.infolist():
            if entry.is_dir():
                continue
            target = PACKAGE_DIR / entry.filename
            if not target.is_file() or target.read_bytes() != archive.read(entry):
                raise RuntimeError(f"Missing or changed driver file: {entry.filename}")
    matches = list((PACKAGE_DIR / architecture()).glob("*.inf"))
    if len(matches) != 1:
        raise RuntimeError("Expected one INF in the architecture-specific driver folder.")
    return matches[0]


def prepare_package() -> Path:
    architecture()
    cache = PACKAGE_DIR / ARCHIVE_NAME
    data = cache.read_bytes() if cache.exists() else download(DOWNLOAD)
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise RuntimeError("Driver checksum mismatch; the package has not been installed.")
    # Keep the exact release source with the binary for GPL redistribution.
    source_cache = PACKAGE_DIR / "MagicTrackpad2ForWindows-v2.2-source.zip"
    source = source_cache.read_bytes() if source_cache.exists() else download(SOURCE_URL)
    with checked_zip(source) as archive:
        license_text = archive.read("MagicTrackpad2ForWindows-2.2/LICENSE")
    PACKAGE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(data)
    source_cache.write_bytes(source)
    (PACKAGE_DIR / "UPSTREAM-LICENSE.txt").write_bytes(license_text)
    with checked_zip(data) as archive:
        archive.extractall(PACKAGE_DIR)
    return verify_package()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="Check cached files without downloading")
    args = parser.parse_args()
    try:
        print(verify_package() if args.verify else prepare_package())
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, KeyError) as error:
        parser.exit(1, f"{error}\n")
