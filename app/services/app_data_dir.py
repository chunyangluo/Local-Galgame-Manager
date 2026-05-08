from __future__ import annotations

import os
import shutil
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


def _legacy_data_candidates() -> list[Path]:
    candidates: list[Path] = [Path.cwd() / "data"]
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "data")
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
