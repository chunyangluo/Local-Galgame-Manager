"""Extract PC game disc images (ISO + MDS/CUE sidecars) after archive unpacking."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from loguru import logger

from core.config import Settings, get_settings
from core.logger import print_error, print_step

DISC_SIDECAR_SUFFIXES: set[str] = {".mds", ".mdf", ".cue", ".ccd", ".sub", ".img", ".bin"}
INSTALLER_NAMES: set[str] = {
    "setup.exe",
    "install.exe",
    "inst.exe",
    "autorun.exe",
}


def is_disc_sidecar(path: Path) -> bool:
    return path.suffix.lower() in DISC_SIDECAR_SUFFIXES


def find_iso_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    isos = [p for p in directory.iterdir() if p.is_file() and p.suffix.lower() == ".iso"]
    return sorted(isos, key=lambda p: p.name.lower())


def _sidecar_for_iso(iso_path: Path, directory: Path) -> list[Path]:
    stem = iso_path.stem.lower()
    sidecars: list[Path] = []
    for item in directory.iterdir():
        if not item.is_file() or item == iso_path:
            continue
        if not is_disc_sidecar(item):
            continue
        if item.stem.lower() == stem:
            sidecars.append(item)
    return sidecars


def is_disc_image_staging_dir(directory: Path) -> bool:
    """Directory contains ISO(s) and no playable PC game files at top level."""
    if not directory.is_dir():
        return False
    isos = find_iso_files(directory)
    if not isos:
        return False
    game_engine_ext = {".ypf", ".xp3", ".rpy", ".rpyc", ".rpa", ".ks", ".tjs", ".pck", ".pak"}
    for item in directory.iterdir():
        if not item.is_file():
            continue
        lower = item.name.lower()
        if item.suffix.lower() == ".exe" and lower not in {"unrar.exe", "7z.exe", "7za.exe"}:
            return False
        if item.suffix.lower() in game_engine_ext:
            return False
    return True


def _run_7z_extract(
    seven_zip: str,
    archive_path: str,
    output_dir: str,
    password: Optional[str] = None,
) -> tuple[bool, str]:
    from core.archive_runner import run_extract_with_fallback

    ok, err, _engine = run_extract_with_fallback(
        seven_zip, archive_path, output_dir, password
    )
    return ok, err


def _run_mount_extract(iso_path: Path, output_dir: Path) -> tuple[bool, str]:
    """Windows: mount ISO and copy contents (fallback when 7-Zip cannot open ISO)."""
    if os.name != "nt":
        return False, "非 Windows 系统，无法挂载 ISO"
    output_dir.mkdir(parents=True, exist_ok=True)
    iso_literal = str(iso_path.resolve()).replace("'", "''")
    dest_literal = str(output_dir.resolve()).replace("'", "''")
    ps = (
        f"$img = Mount-DiskImage -ImagePath '{iso_literal}' -PassThru -ErrorAction Stop; "
        f"$vol = $img | Get-Volume | Where-Object {{ $_.DriveLetter }} | Select-Object -First 1; "
        f"if (-not $vol) {{ throw 'no drive letter' }}; "
        f"$src = $vol.DriveLetter + ':\\'; "
        f"Copy-Item -Path ($src + '*') -Destination '{dest_literal}' -Recurse -Force -ErrorAction Stop; "
        f"Dismount-DiskImage -ImagePath '{iso_literal}' -ErrorAction SilentlyContinue"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=7200,
            creationflags=subprocess.CREATE_NO_WINDOW,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode == 0:
            return True, ""
        err = (result.stderr or result.stdout or "挂载复制失败").strip()
        return False, err
    except subprocess.TimeoutExpired:
        return False, "ISO 挂载复制超时"
    except Exception as exc:
        return False, str(exc)


def _resolve_dest_conflict(dest: Path) -> Path:
    if not dest.exists():
        return dest
    parent = dest.parent
    stem = dest.stem if dest.is_file() else dest.name
    suffix = dest.suffix if dest.is_file() else ""
    counter = 1
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def _move_extracted_children(staging: Path, parent: Path) -> int:
    moved = 0
    for item in list(staging.iterdir()):
        dest = _resolve_dest_conflict(parent / item.name)
        shutil.move(str(item), str(dest))
        moved += 1
    return moved


def _relocate_disc_files(
    iso_path: Path,
    sidecars: list[Path],
    parent: Path,
    *,
    subfolder: str,
) -> None:
    disc_dir = parent / subfolder
    disc_dir.mkdir(parents=True, exist_ok=True)
    for src in [iso_path, *sidecars]:
        if not src.exists():
            continue
        dest = disc_dir / src.name
        if dest.exists():
            dest = _resolve_dest_conflict(dest)
        shutil.move(str(src), str(dest))


def expand_iso_image(
    iso_path: Path,
    parent_dir: Path,
    settings: Settings,
) -> tuple[bool, str, int]:
    """Extract one ISO into parent_dir; return (ok, error, files_moved)."""
    cfg = settings.post_process.iso_images
    if not cfg.enabled:
        return False, "ISO 后处理未启用", 0

    seven_zip = settings.seven_zip.path
    staging = parent_dir / f".iso_staging_{iso_path.stem}_{os.getpid()}"
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)

    print_step("展开光盘镜像", iso_path.name)
    success, error = _run_7z_extract(seven_zip, str(iso_path), str(staging), None)
    engine = "7-Zip"
    if not success and cfg.try_mount_fallback:
        logger.warning(f"7-Zip 无法展开 ISO，尝试挂载: {iso_path.name} | {error[:120]}")
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True, exist_ok=True)
        success, error = _run_mount_extract(iso_path, staging)
        engine = "挂载"

    if not success:
        shutil.rmtree(staging, ignore_errors=True)
        return False, error or f"{engine} 无法展开 ISO", 0

    moved = _move_extracted_children(staging, parent_dir)
    shutil.rmtree(staging, ignore_errors=True)

    if moved == 0:
        return False, "ISO 内没有可提取的文件", 0

    sidecars = _sidecar_for_iso(iso_path, parent_dir)
    if cfg.move_iso_to_subfolder:
        try:
            _relocate_disc_files(iso_path, sidecars, parent_dir, subfolder=cfg.disc_subfolder)
        except OSError as exc:
            logger.warning(f"移动光盘文件失败: {exc}")

    print_step("光盘镜像已展开", f"{iso_path.name} → {moved} 项 ({engine})")
    return True, "", moved


def expand_disc_images_in_directory(
    directory: str | Path,
    settings: Settings | None = None,
) -> dict:
    """Expand all top-level ISO files in directory. Returns summary dict for post_process."""
    settings = settings or get_settings()
    cfg = settings.post_process.iso_images
    if not cfg.enabled:
        return {"expanded": [], "errors": [], "skipped": True}

    root = Path(directory).resolve()
    if not root.is_dir():
        return {"expanded": [], "errors": [{"iso": "", "error": "目录不存在"}]}

    expanded: list[str] = []
    errors: list[dict[str, str]] = []

    if is_disc_image_staging_dir(root) or find_iso_files(root):
        for iso in find_iso_files(root):
            if not iso.is_file():
                continue
            ok, err, moved = expand_iso_image(iso, root, settings)
            if ok:
                expanded.append(iso.name)
                logger.info(f"ISO 展开成功: {iso.name} ({moved} 项)")
            else:
                errors.append({"iso": iso.name, "error": err})
                print_error(f"光盘镜像展开失败: {iso.name}", err)

    # Detect ISOs that were already expanded during nested extraction.
    # They are moved to the disc subfolder (e.g. _disc_images/) so they
    # won't appear at the top level, but we still need to report them
    # so that the disc install guide is triggered correctly.
    if not expanded:
        disc_subfolder = cfg.disc_subfolder or "_disc_images"
        disc_dir = root / disc_subfolder
        if disc_dir.is_dir():
            previously_expanded = [
                f.name for f in disc_dir.iterdir()
                if f.is_file() and f.suffix.lower() == ".iso"
            ]
            if previously_expanded:
                logger.info(f"检测到嵌套解压中已展开的光盘镜像: {previously_expanded}")
                expanded = previously_expanded

    return {"expanded": expanded, "errors": errors}


def find_installer_exe(directory: Path, *, max_depth: int = 4) -> Optional[Path]:
    if not directory.is_dir():
        return None
    best: Optional[Path] = None

    def walk(dir_path: Path, depth: int) -> None:
        nonlocal best
        if depth > max_depth:
            return
        try:
            items = list(dir_path.iterdir())
        except OSError:
            return
        for item in items:
            if item.is_file() and item.suffix.lower() == ".exe":
                if item.name.lower() in INSTALLER_NAMES:
                    best = item
                    return
            elif item.is_dir():
                walk(item, depth + 1)
                if best is not None:
                    return

    walk(directory, 0)
    return best
