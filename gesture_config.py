"""Per-user gesture configuration. Atomic writes; invalid files fail closed."""

import json
import os
from pathlib import Path
import tempfile

from gestures import DEFAULTS, validate


def data_dir() -> Path:
    return Path(os.environ["APPDATA"]) / "TrackpadFree"


def atomic_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as file:
            name = file.name
            json.dump(data, file, indent=2, allow_nan=False)
            file.flush()
            os.fsync(file.fileno())
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def load() -> dict:
    try:
        return validate(json.loads((data_dir() / "gestures.json").read_text(encoding="utf-8")))
    except FileNotFoundError:
        return DEFAULTS.copy()


def save(settings: dict) -> None:
    atomic_json(data_dir() / "gestures.json", validate(settings))
