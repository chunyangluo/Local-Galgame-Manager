"""Detect optional paths when running from the Local-Galgame-Manager source tree."""

from __future__ import annotations

from pathlib import Path

_APP_DIR = Path(__file__).resolve().parent


def dev_repo_root() -> Path | None:
    """Return repository root if ``tools/2dfan-save-crawler`` is present (dev checkout)."""
    root = _APP_DIR.parent
    marker = root / "tools" / "2dfan-save-crawler" / "README.md"
    return root if marker.is_file() else None


def twodfan_crawler_dir() -> Path | None:
    root = dev_repo_root()
    if root is None:
        return None
    d = root / "tools" / "2dfan-save-crawler"
    return d if d.is_dir() else None


def twodfan_crawler_readme() -> Path | None:
    d = twodfan_crawler_dir()
    if d is None:
        return None
    p = d / "README.md"
    return p if p.is_file() else None


def default_twodfan_sqlite_path() -> Path | None:
    """Canonical output path from README (file may not exist yet)."""
    d = twodfan_crawler_dir()
    if d is None:
        return None
    return d / "data" / "2dfan_saves.sqlite3"


def existing_twodfan_sqlite_files() -> list[Path]:
    """SQLite files already present under the crawler tool (if any)."""
    d = twodfan_crawler_dir()
    if d is None:
        return []
    out: list[Path] = []
    data = d / "data"
    if not data.is_dir():
        return out
    for name in ("2dfan_saves.sqlite3", "test.sqlite3"):
        p = data / name
        if p.is_file():
            out.append(p)
    return out
