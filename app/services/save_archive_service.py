"""Zip / unzip save directories with basic zip-slip protection."""

from __future__ import annotations

import shutil
import zipfile
import hashlib
from pathlib import Path
from collections.abc import Callable


def directory_has_files(root: Path) -> bool:
    root = root.resolve()
    if not root.is_dir():
        return False
    for p in root.rglob("*"):
        if p.is_file():
            return True
    return False


def zip_directory(src_dir: Path, dest_zip: Path) -> int:
    """Write all files under ``src_dir`` into ``dest_zip``. Returns file size in bytes."""
    src = src_dir.resolve()
    if not src.is_dir():
        raise FileNotFoundError(str(src))
    dest_zip.parent.mkdir(parents=True, exist_ok=True)
    if dest_zip.exists():
        dest_zip.unlink()
    with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in src.rglob("*"):
            if not path.is_file():
                continue
            arc = path.relative_to(src).as_posix()
            zf.write(path, arc)
    return int(dest_zip.stat().st_size)


def zip_directory_with_progress(
    src_dir: Path,
    dest_zip: Path,
    *,
    progress_cb: Callable[[int, int, str], None] | None = None,
) -> int:
    """Zip dir with file-level progress callback: (done, total, filename)."""
    src = src_dir.resolve()
    if not src.is_dir():
        raise FileNotFoundError(str(src))
    files = [p for p in src.rglob("*") if p.is_file()]
    total = max(1, len(files))
    dest_zip.parent.mkdir(parents=True, exist_ok=True)
    if dest_zip.exists():
        dest_zip.unlink()
    with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        done = 0
        for path in files:
            arc = path.relative_to(src).as_posix()
            zf.write(path, arc)
            done += 1
            if progress_cb is not None:
                progress_cb(done, total, arc)
    return int(dest_zip.stat().st_size)


def unzip_safely(zip_path: Path, dest_dir: Path) -> None:
    """Extract zip members into ``dest_dir``; reject paths that escape the destination."""
    dest = dest_dir.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        for m in zf.infolist():
            if m.is_dir():
                continue
            target = (dest / m.filename).resolve()
            if not target.is_relative_to(dest):
                raise ValueError(f"压缩包内包含非法路径: {m.filename!r}")
        for m in zf.infolist():
            if m.is_dir():
                continue
            zf.extract(m, dest)


def unzip_safely_with_progress(
    zip_path: Path,
    dest_dir: Path,
    *,
    progress_cb: Callable[[int, int, str], None] | None = None,
) -> None:
    """Safe unzip with file-level progress callback: (done, total, filename)."""
    dest = dest_dir.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        files = [m for m in zf.infolist() if not m.is_dir()]
        total = max(1, len(files))
        for m in files:
            target = (dest / m.filename).resolve()
            if not target.is_relative_to(dest):
                raise ValueError(f"压缩包内包含非法路径: {m.filename!r}")
        done = 0
        for m in files:
            zf.extract(m, dest)
            done += 1
            if progress_cb is not None:
                progress_cb(done, total, m.filename)


def clear_directory_contents(d: Path) -> None:
    """Remove all children of ``d``; keep ``d`` itself."""
    root = d.resolve()
    if not root.is_dir():
        return
    for child in list(root.iterdir()):
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def sha256_file(path: Path) -> str:
    """Return lowercase SHA256 hex for file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest().lower()
