"""Detect optional paths when running from the Local-Galgame-Manager source tree."""

from __future__ import annotations

from pathlib import Path

_APP_DIR = Path(__file__).resolve().parent.parent  # app/services/ -> app/


def dev_repo_root() -> Path | None:
    """Return repository root if dev tree markers are present (source checkout)."""
    root = _APP_DIR.parent
    markers = (
        root / "tools" / "2dfan-save-crawler" / "README.md",
        root / "integrations" / "README.md",
    )
    if any(p.is_file() for p in markers):
        return root
    return None


def integrations_dir() -> Path | None:
    """Directory for bundled Python subprojects pending or in progress integration."""
    root = dev_repo_root()
    if root is None:
        return None
    d = root / "integrations"
    return d if d.is_dir() else None


def hbe_decryptor_dir() -> Path | None:
    """Bundled Hexo Blog Encrypt decryptor under integrations/."""
    root = dev_repo_root()
    if root is None:
        return None
    d = root / "integrations" / "hbe-decryptor"
    return d if d.is_dir() and (d / "decry-chunyang.py").is_file() else None


def hbe_decryptor_readme() -> Path | None:
    d = hbe_decryptor_dir()
    if d is None:
        return None
    p = d / "README.md"
    return p if p.is_file() else None


def auto_extract_tool_dir() -> Path | None:
    """Bundled galgame archive auto-extractor under integrations/."""
    root = dev_repo_root()
    if root is None:
        return None
    d = root / "integrations" / "自动化解压工具"
    return d if d.is_dir() and (d / "main.py").is_file() else None


def auto_extract_config_path() -> Path | None:
    d = auto_extract_tool_dir()
    if d is None:
        return None
    p = d / "config" / "config.yaml"
    return p if p.is_file() else None


def auto_extract_readme() -> Path | None:
    d = auto_extract_tool_dir()
    if d is None:
        return None
    p = d / "README.md"
    return p if p.is_file() else None


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
