"""Path normalization for stable game directory keys across scans and DB."""

from __future__ import annotations

import os
from pathlib import Path


def normalize_game_dir(path: str | Path) -> str:
    """Return a canonical string for ``root_dir`` storage and set comparison."""
    original = str(path).replace("\\", "/")
    raw = Path(path)
    if raw.exists():
        try:
            text = str(raw.resolve(strict=False))
        except (OSError, RuntimeError):
            text = os.path.normpath(str(raw))
    elif os.name == "nt" and original.startswith("/") and ":" not in original[:3]:
        text = original
    else:
        text = os.path.normpath(str(raw))
    if os.name == "nt":
        return os.path.normcase(text)
    return text


def is_path_under_root(child: str | Path, root: str | Path) -> bool:
    """True if ``child`` is the same as or nested under ``root``."""
    child_p = Path(normalize_game_dir(child))
    root_p = Path(normalize_game_dir(root))
    try:
        child_p.relative_to(root_p)
        return True
    except ValueError:
        return False
