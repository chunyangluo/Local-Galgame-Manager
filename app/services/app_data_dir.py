from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from pathlib import Path


def get_app_data_dir() -> Path:
    base = _resolve_base_dir()
    data_dir = base / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    _migrate_legacy_data_if_needed(data_dir)
    return data_dir


def _resolve_base_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "LocalGalgameManager"
    return Path.home() / "AppData" / "Local" / "LocalGalgameManager"


def _migrate_legacy_data_if_needed(data_dir: Path) -> None:
    for old_data in _legacy_data_candidates():
        if not old_data.exists() or old_data.resolve() == data_dir.resolve():
            continue
        _copy_missing_entries(old_data, data_dir)
        _rewrite_legacy_cover_paths(old_data, data_dir)


def _legacy_data_candidates() -> list[Path]:
    candidates: list[Path] = [Path.cwd() / "data"]
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "data")
        # Handle historical project build output layout:
        # dist/LocalGalgameManager/data
        # dist/builds/<timestamp>/LocalGalgameManager/data  (current)
        try:
            dist_dir = exe_dir.parents[3]
            if dist_dir.name.lower() == "dist":
                candidates.append(dist_dir / "LocalGalgameManager" / "data")
                builds_dir = dist_dir / "builds"
                if builds_dir.exists():
                    for child in builds_dir.iterdir():
                        candidates.append(child / "LocalGalgameManager" / "data")
        except Exception:
            pass
    # Deduplicate while preserving order.
    seen: set[Path] = set()
    unique: list[Path] = []
    for item in candidates:
        resolved = item.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(item)
    return unique


def _copy_missing_entries(old_data: Path, data_dir: Path) -> None:
    try:
        for item in old_data.iterdir():
            target = data_dir / item.name
            if target.exists():
                continue
            if item.is_dir():
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)
    except Exception:
        # Migration best-effort only; startup should never fail for this.
        return


def _rewrite_legacy_cover_paths(old_data: Path, data_dir: Path) -> None:
    db_path = data_dir / "manager.sqlite3"
    if not db_path.exists():
        return

    old_prefix = str(old_data.resolve()).replace("\\", "/").lower()
    new_prefix = str(data_dir.resolve()).replace("\\", "/")

    try:
        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id, cover_path FROM games WHERE cover_path IS NOT NULL AND cover_path != ''")
            rows = cursor.fetchall()
            for game_id, cover_path in rows:
                if not isinstance(cover_path, str):
                    continue
                normalized = cover_path.replace("\\", "/")
                normalized_lower = normalized.lower()
                if not normalized_lower.startswith(old_prefix):
                    continue
                suffix = normalized[len(old_prefix) :].lstrip("/\\")
                migrated = str((data_dir / suffix).resolve())
                if not Path(migrated).exists():
                    continue
                cursor.execute("UPDATE games SET cover_path = ? WHERE id = ?", (migrated, game_id))
            conn.commit()
        finally:
            conn.close()
    except Exception:
        # Keep migration non-blocking.
        return
