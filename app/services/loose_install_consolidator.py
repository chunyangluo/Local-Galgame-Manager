"""Detect PC game files installed directly into library root and move into a subfolder."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

# Typical support folders when a legacy installer dumps into the chosen path root.
LOOSE_INSTALL_DIR_NAMES: frozenset[str] = frozenset(
    name.lower()
    for name in (
        "exe",
        "cg",
        "pcm",
        "dll",
        "gamedata",
        "data",
        "save",
        "savedata",
        "bgm",
        "voice",
        "movie",
        "sys",
        "system",
        "font",
        "fonts",
        "wave",
        "img",
        "image",
        "gra",
        "graphic",
        "mes",
        "scr",
        "manual",
        "readme",
        "update",
    )
)

LAUNCHER_EXE_SKIP: frozenset[str] = frozenset(
    name.lower()
    for name in (
        "setup.exe",
        "install.exe",
        "uninstall.exe",
        "uninst.exe",
        "autorun.exe",
        "start.exe",
        "launcher.exe",
        "7z.exe",
        "7za.exe",
        "unrar.exe",
    )
)

LIBRARY_RESERVED_DIR_NAMES: frozenset[str] = frozenset(
    name.lower()
    for name in (
        "_disc_images",
        ".git",
        "node_modules",
        "local-galgame-manager",
    )
)

_INVALID_FOLDER_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass
class LooseInstallCluster:
    library_root: Path
    launcher_exe: Path
    suggested_folder_name: str
    items: list[Path] = field(default_factory=list)


@dataclass
class ConsolidateResult:
    success: bool
    destination: str = ""
    moved: list[str] = field(default_factory=list)
    error: str = ""


def _sanitize_folder_name(name: str) -> str:
    cleaned = _INVALID_FOLDER_CHARS.sub("_", name.strip())
    cleaned = cleaned.strip(" .")
    return cleaned or "InstalledGame"


def is_game_launcher_exe(file_name: str) -> bool:
    lower = file_name.lower()
    if not lower.endswith(".exe"):
        return False
    if lower in LAUNCHER_EXE_SKIP:
        return False
    if lower.startswith(("uninst", "uinst", "uninstall")):
        return False
    return True


def suggest_install_folder_name(
    *,
    installer_exe: str | Path | None = None,
    iso_names: tuple[str, ...] | list[str] = (),
    archive_file_name: str = "",
) -> str:
    for raw in iso_names:
        stem = Path(str(raw)).stem
        if stem and stem.lower() not in ("setup", "disc"):
            return _sanitize_folder_name(stem)
    if installer_exe:
        stem = Path(installer_exe).stem
        if stem.lower() not in ("setup", "install", "autorun", "inst"):
            return _sanitize_folder_name(stem)
    if archive_file_name:
        stem = Path(archive_file_name).stem
        stem = re.sub(r"\s*\(iso\+mds\)\s*$", "", stem, flags=re.I)
        stem = re.sub(r"\[.*?\]", "", stem).strip()
        if stem:
            return _sanitize_folder_name(stem[:80])
    return "InstalledGame"


def suggested_install_directory(
    library_root: str | Path,
    *,
    folder_name: str,
) -> Path:
    return Path(library_root).resolve() / _sanitize_folder_name(folder_name)


def _quick_entry_count(dir_path: Path, limit: int = 400) -> int:
    count = 0
    try:
        for _ in dir_path.rglob("*"):
            count += 1
            if count >= limit:
                break
    except OSError:
        return 0
    return count


def _dir_size_bytes(dir_path: Path, limit_files: int = 500) -> int:
    total = 0
    n = 0
    try:
        for f in dir_path.rglob("*"):
            if f.is_file():
                try:
                    total += f.stat().st_size
                except OSError:
                    pass
                n += 1
                if n >= limit_files:
                    break
    except OSError:
        return 0
    return total


def is_existing_game_folder(dir_path: Path) -> bool:
    """Heuristic: established game install subfolder — do not move when consolidating."""
    if not dir_path.is_dir():
        return False
    name = dir_path.name.lower()
    if name in LIBRARY_RESERVED_DIR_NAMES:
        return False
    if name in LOOSE_INSTALL_DIR_NAMES:
        return False
    try:
        entries = list(dir_path.iterdir())
    except OSError:
        return False
    if not entries:
        return False
    has_exe = any(
        p.is_file() and p.suffix.lower() == ".exe" and is_game_launcher_exe(p.name)
        for p in entries
    )
    size = _dir_size_bytes(dir_path)
    count = _quick_entry_count(dir_path)
    if has_exe and (size > 30 * 1024 * 1024 or count > 25):
        return True
    if size > 200 * 1024 * 1024:
        return True
    if count > 120:
        return True
    return False


def detect_loose_install_at_root(library_root: str | Path) -> LooseInstallCluster | None:
    root = Path(library_root).resolve()
    if not root.is_dir():
        return None

    launchers: list[Path] = []
    try:
        for item in root.iterdir():
            if item.is_file() and is_game_launcher_exe(item.name):
                launchers.append(item)
    except OSError:
        return None

    if not launchers:
        return None

    primary = max(launchers, key=lambda p: p.stat().st_size if p.exists() else 0)
    folder_name = _sanitize_folder_name(primary.stem)

    items: list[Path] = []
    try:
        for item in root.iterdir():
            if item == primary:
                items.append(item)
                continue
            if item.is_file():
                if item.name.lower() in ("desktop.ini", "thumbs.db"):
                    continue
                items.append(item)
                continue
            if not item.is_dir():
                continue
            name = item.name.lower()
            if name in LIBRARY_RESERVED_DIR_NAMES:
                if name == "_disc_images":
                    items.append(item)
                continue
            if is_existing_game_folder(item):
                continue
            if name in LOOSE_INSTALL_DIR_NAMES:
                items.append(item)
                continue
            # Small ambiguous folder: few entries, no nested game launcher
            count = _quick_entry_count(item, limit=50)
            size = _dir_size_bytes(item, limit_files=80)
            nested_launcher = any(
                p.is_file() and is_game_launcher_exe(p.name)
                for p in item.iterdir()
                if p.parent == item
            ) if count <= 50 else False
            if not nested_launcher and count <= 40 and size < 80 * 1024 * 1024:
                items.append(item)
    except OSError:
        return None

    if len(items) <= 1:
        return None

    return LooseInstallCluster(
        library_root=root,
        launcher_exe=primary,
        suggested_folder_name=folder_name,
        items=items,
    )


def consolidate_loose_install(
    library_root: str | Path,
    *,
    folder_name: str | None = None,
    dry_run: bool = False,
) -> ConsolidateResult:
    cluster = detect_loose_install_at_root(library_root)
    if cluster is None:
        return ConsolidateResult(success=False, error="未检测到游戏库根目录下的散落安装文件")

    dest_name = _sanitize_folder_name(folder_name or cluster.suggested_folder_name)
    dest = cluster.library_root / dest_name
    if dest.exists() and dest.resolve() == cluster.library_root.resolve():
        return ConsolidateResult(success=False, error="目标文件夹无效")

    moved: list[str] = []
    try:
        if not dry_run:
            dest.mkdir(parents=True, exist_ok=True)
        for src in cluster.items:
            target = dest / src.name
            if not dry_run:
                if target.exists():
                    if target.is_dir():
                        shutil.rmtree(target)
                    else:
                        target.unlink()
                shutil.move(str(src), str(target))
            moved.append(src.name)
    except OSError as exc:
        return ConsolidateResult(
            success=False,
            destination=str(dest),
            moved=moved,
            error=str(exc),
        )

    return ConsolidateResult(
        success=True,
        destination=str(dest),
        moved=moved,
    )
