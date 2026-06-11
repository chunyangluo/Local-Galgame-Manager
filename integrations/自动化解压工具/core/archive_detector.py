from __future__ import annotations

import re
from pathlib import Path
from typing import Optional


MAGIC_SIGNATURES: list[tuple[bytes, int, str]] = [
    (b"PK\x03\x04", 0, "zip"),
    (b"PK\x05\x06", 0, "zip"),
    (b"Rar!\x1a\x07", 0, "rar"),
    (b"7z\xbc\xaf\x27\x1c", 0, "7z"),
    (b"\x1f\x8b", 0, "gzip"),
    (b"BZh", 0, "bzip2"),
    (b"\xfd7zXZ\x00", 0, "xz"),
    (b"\x04\x22\x4D\x18", 0, "lz4"),  # LZ4 magic number
]

DISGUISED_EXTENSIONS: set[str] = {
    ".mp4", ".avi", ".mkv", ".wmv", ".flv",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp",
    ".pdf", ".doc", ".docx",
}

VIDEO_EXTENSIONS: set[str] = {
    ".mp4", ".mkv", ".avi", ".wmv", ".flv",
    ".mov", ".webm", ".m4v", ".ts", ".m2ts",
}

ISO_SIGNATURE = (b"CD001", 0x8001, "iso")

EXTENSION_MAP: dict[str, str] = {
    ".zip": "zip",
    ".rar": "rar",
    ".7z": "7z",
    ".tar": "tar",
    ".gz": "gzip",
    ".tgz": "gzip",
    ".bz2": "bzip2",
    ".tbz2": "bzip2",
    ".xz": "xz",
    ".txz": "xz",
    ".iso": "iso",
    ".lz4": "lz4",
}

COMPOUND_PATTERNS: list[tuple[str, str]] = [
    (".tar.gz", "gzip"),
    (".tar.bz2", "bzip2"),
    (".tar.xz", "xz"),
    (".tgz", "gzip"),
    (".tbz2", "bzip2"),
    (".txz", "xz"),
]

SPLIT_VOLUME_RE = re.compile(r"^(.*)\.e(\d+)$", re.IGNORECASE)
SFX_EXE_RE = re.compile(r"^(.*)\.exe$", re.IGNORECASE)
SEVENZ_SPLIT_RE = re.compile(r"^(.*)\.(\d{3})$", re.IGNORECASE)
# RAR multi-part: basename.part1.rar, basename.part2.rar, … (also .part01.rar etc.)
RAR_MULTI_PART_RE = re.compile(r"^(.*)\.part(\d+)\.rar$", re.IGNORECASE)
# RAR old-style split: basename.r00, basename.r01, …
RAR_OLD_SPLIT_RE = re.compile(r"^(.*)\.r(\d+)$", re.IGNORECASE)

DOWNLOAD_TEMP_SUFFIXES: list[str] = [
    ".baiduyun.p.downloading",
    ".baiduyun.downloading",
    ".baiduyun.downloading.cfg",
    ".uploading",
    ".baiduyun.uploading",
    ".tmp",
    ".bd!",
    ".part",
    ".pcs",
]


def is_download_temp_file(file_path: str | Path) -> bool:
    p = Path(file_path)
    name = p.name.lower()
    # 对于 .7z.tmp 或 .zip.tmp，先检查是否有压缩包签名
    if name.endswith(".7z.tmp") or name.endswith(".zip.tmp") or name.endswith(".rar.tmp"):
        magic = detect_by_magic(file_path)
        if magic:
            return False
    for suffix in DOWNLOAD_TEMP_SUFFIXES:
        if name.endswith(suffix.lower()):
            return True
    return False


def detect_by_magic(file_path: str | Path) -> Optional[str]:
    p = Path(file_path)
    if not p.exists() or not p.is_file():
        return None
    try:
        with open(p, "rb") as f:
            header = f.read(512)
    except OSError:
        return None

    for sig, offset, atype in MAGIC_SIGNATURES:
        end = offset + len(sig)
        if len(header) >= end and header[offset:end] == sig:
            return atype

    if len(header) >= 0x8006:
        iso_offset = 0x8001
        iso_sig = ISO_SIGNATURE[0]
        if header[iso_offset:iso_offset + len(iso_sig)] == iso_sig:
            return "iso"
    else:
        try:
            with open(p, "rb") as f:
                f.seek(0x8001)
                data = f.read(5)
                if data == ISO_SIGNATURE[0]:
                    return "iso"
        except OSError:
            pass

    return None


def detect_disguised_archive(file_path: str | Path) -> Optional[str]:
    p = Path(file_path)
    if p.suffix.lower() not in DISGUISED_EXTENSIONS:
        return None
    try:
        file_size = p.stat().st_size
        if file_size < 1024:
            return None
        with open(p, "rb") as f:
            if file_size > 65536:
                f.seek(-65536, 2)
            else:
                f.seek(0)
            tail = f.read()
        if tail.rfind(b"PK\x05\x06") >= 0:
            return "zip"
        if tail.rfind(b"Rar!\x1a\x07") >= 0:
            return "rar"
        if tail.rfind(b"7z\xbc\xaf\x27\x1c") >= 0:
            return "7z"
    except OSError:
        pass
    return None


def is_real_video_file(file_path: str | Path) -> bool:
    """Return True only for video files that are not disguised archives."""
    p = Path(file_path)
    if p.suffix.lower() not in VIDEO_EXTENSIONS:
        return False
    return detect_archive_type(file_path) is None


def classify_content_file(file_path: str | Path) -> str:
    """Classify a file for extraction/import decisions."""
    if is_download_temp_file(file_path):
        return "download_temp"
    if detect_archive_type(file_path) is not None:
        return "archive"
    if is_real_video_file(file_path):
        return "video"
    return "unknown"


def detect_by_extension(file_path: str | Path) -> Optional[str]:
    name = Path(file_path).name.lower()
    for suffix, atype in COMPOUND_PATTERNS:
        if name.endswith(suffix):
            return atype

    name_lower = name
    for ext, atype in EXTENSION_MAP.items():
        if name_lower.endswith(ext):
            return atype

    for ext, atype in EXTENSION_MAP.items():
        pattern = re.compile(re.escape(ext) + r".*$", re.IGNORECASE)
        if pattern.search(name_lower):
            return atype

    return None


def detect_archive_type(file_path: str | Path) -> Optional[str]:
    p = Path(file_path)
    name = p.name.lower()
    
    if is_download_temp_file(file_path):
        return None
    
    if name.endswith(".exe") or name.endswith(".e01") or name.endswith(".e02"):
        split_info = detect_split_volume_set(file_path)
        if split_info:
            return "7z"
    
    magic_type = detect_by_magic(file_path)
    if magic_type:
        return magic_type
    
    ext_type = detect_by_extension(file_path)
    if ext_type:
        return ext_type
    
    disguised_type = detect_disguised_archive(file_path)
    if disguised_type:
        return disguised_type
    
    return None


def is_supported_archive(file_path: str | Path) -> bool:
    return detect_archive_type(file_path) is not None


def detect_split_volume_set(file_path: str | Path) -> Optional[dict]:
    p = Path(file_path).resolve()
    name = p.name
    parent = p.parent

    exe_match = SFX_EXE_RE.match(name)
    e01_match = SPLIT_VOLUME_RE.match(name)
    
    base_stem = ""
    has_e01 = False
    
    if exe_match:
        base_stem = exe_match.group(1)
        e01_file = parent / f"{base_stem}.e01"
        has_e01 = e01_file.exists()
        if not has_e01:
            try:
                from core.config import get_settings
                settings = get_settings()
                archive_dir = Path(settings.directories.archive)
                archive_e01 = archive_dir / f"{base_stem}.e01"
                if archive_e01.exists():
                    has_e01 = True
            except Exception:
                pass
    elif e01_match:
        base_stem = e01_match.group(1)
        has_e01 = True
    else:
        return None
    
    if not has_e01:
        return None
    
    all_files = []
    all_paths = [parent]
    
    try:
        from core.config import get_settings
        settings = get_settings()
        archive_dir = Path(settings.directories.archive)
        if archive_dir.exists():
            all_paths.append(archive_dir)
    except:
        pass
    
    exe_file = None
    e01_file = None
    
    for search_path in all_paths:
        candidate_exe = search_path / f"{base_stem}.exe"
        candidate_e01 = search_path / f"{base_stem}.e01"
        if exe_file is None and candidate_exe.exists():
            exe_file = candidate_exe.resolve()
        if e01_file is None and candidate_e01.exists():
            e01_file = candidate_e01.resolve()
    
    if exe_file:
        all_files.append(exe_file)
    if e01_file:
        all_files.append(e01_file)
    
    vol_index = 2
    while True:
        vol_file = None
        for search_path in all_paths:
            candidate_vol = search_path / f"{base_stem}.e{vol_index:02d}"
            if candidate_vol.exists():
                vol_file = candidate_vol.resolve()
                break
        if not vol_file:
            break
        all_files.append(vol_file)
        vol_index += 1

    extract_entry = str(exe_file) if exe_file else str(e01_file)
    
    return {
        "type": "split_sfx",
        "base_name": base_stem,
        "extract_entry": extract_entry,
        "all_files": [str(f) for f in all_files],
        "volume_count": len(all_files),
    }


def check_volume_integrity(volume_info: dict) -> tuple[bool, str]:
    base_name = volume_info["base_name"]
    parent = Path(volume_info["extract_entry"]).parent
    expected_count = volume_info["volume_count"]
    
    all_paths = [parent]
    
    try:
        from core.config import get_settings
        settings = get_settings()
        archive_dir = Path(settings.directories.archive)
        if archive_dir.exists() and archive_dir != parent:
            all_paths.append(archive_dir)
    except:
        pass

    for i in range(2, expected_count):
        found = False
        vol_name = f"{base_name}.e{i:02d}"
        for search_path in all_paths:
            if (search_path / vol_name).exists():
                found = True
                break
        if not found:
            return False, f"缺失分卷：{base_name}.e{i:02d}"
    return True, "分卷完整"


def is_split_volume_file(file_path: str | Path) -> bool:
    p = Path(file_path).resolve()
    name = p.name
    if SPLIT_VOLUME_RE.match(name):
        return True
    if SFX_EXE_RE.match(name):
        vol_match = SPLIT_VOLUME_RE.match(name)
        base_stem = SFX_EXE_RE.match(name).group(1)
        parent = p.parent
        for f in parent.iterdir():
            if f.is_file() and SPLIT_VOLUME_RE.match(f.name):
                if SPLIT_VOLUME_RE.match(f.name).group(1) == base_stem:
                    return True
    return False


def detect_7z_split_volume_set(file_path: str | Path) -> Optional[dict]:
    p = Path(file_path).resolve()
    name = p.name
    parent = p.parent

    match = SEVENZ_SPLIT_RE.match(name)
    if not match:
        return None

    base_stem = match.group(1)
    first_num = int(match.group(2))

    if first_num != 1:
        return None

    all_parts = []
    part_num = 1
    while True:
        next_part = parent / f"{base_stem}.{part_num:03d}"
        if next_part.exists():
            all_parts.append(str(next_part.resolve()))
            part_num += 1
        else:
            break

    if len(all_parts) < 2:
        return None

    return {
        "type": "7z_split",
        "base_name": base_stem,
        "extract_entry": all_parts[0],
        "all_files": all_parts,
        "volume_count": len(all_parts),
    }


def is_7z_split_part(file_path: str | Path) -> Optional[dict]:
    p = Path(file_path).resolve()
    name = p.name

    match = SEVENZ_SPLIT_RE.match(name)
    if not match:
        return None

    base_stem = match.group(1)
    part_num = int(match.group(2))

    if part_num == 1:
        return None

    search_paths = [p.parent]
    try:
        from core.config import get_settings
        settings = get_settings()
        archive_dir = Path(settings.directories.archive)
        if archive_dir.exists():
            search_paths.append(archive_dir)
    except:
        pass

    first_part = None
    for search_path in search_paths:
        candidate = search_path / f"{base_stem}.001"
        if candidate.exists():
            first_part = str(candidate.resolve())
            break

    if first_part:
        return {"base_stem": base_stem, "part_num": part_num, "first_part": first_part}

    return None


def detect_rar_multipart_volume_set(file_path: str | Path) -> Optional[dict]:
    """Detect RAR multi-part archives (basename.part1.rar, basename.part2.rar, …).

    Also handles basename.part01.rar style with zero-padded numbers.

    Returns dict with keys: type, base_name, extract_entry, all_files, volume_count.
    Only the first part (part1) should be used for extraction; 7za handles the rest.
    """
    p = Path(file_path).resolve()
    name = p.name
    parent = p.parent

    match = RAR_MULTI_PART_RE.match(name)
    if not match:
        return None

    base_stem = match.group(1)
    part_num = int(match.group(2))

    # Only trigger detection from part1
    if part_num != 1:
        return None

    # Find all parts in the same directory (and optionally in the archive dir)
    search_paths = [parent]
    try:
        from core.config import get_settings
        settings = get_settings()
        archive_dir = Path(settings.directories.archive)
        if archive_dir.exists() and archive_dir != parent:
            search_paths.append(archive_dir)
    except Exception:
        pass

    # Determine zero-padding width from the first part
    raw_num = match.group(2)
    pad_width = len(raw_num) if len(raw_num) > 1 else 0  # 0 means no padding

    all_parts: list[str] = []
    part_index = 1
    while True:
        if pad_width > 0:
            part_name = f"{base_stem}.part{part_index:0{pad_width}d}.rar"
        else:
            part_name = f"{base_stem}.part{part_index}.rar"

        found = False
        for search_path in search_paths:
            candidate = search_path / part_name
            if candidate.exists():
                all_parts.append(str(candidate.resolve()))
                found = True
                break
        if not found:
            break
        part_index += 1

    if len(all_parts) < 1:
        return None

    return {
        "type": "rar_multipart",
        "base_name": base_stem,
        "extract_entry": all_parts[0],  # part1.rar
        "all_files": all_parts,
        "volume_count": len(all_parts),
    }


def is_rar_multipart_part(file_path: str | Path) -> Optional[dict]:
    """Check if a file is a non-first part of a RAR multi-part archive.

    Returns dict with base_stem, part_num, first_part if so.
    """
    p = Path(file_path).resolve()
    name = p.name

    match = RAR_MULTI_PART_RE.match(name)
    if not match:
        return None

    base_stem = match.group(1)
    part_num = int(match.group(2))

    if part_num == 1:
        return None

    # Find part1
    raw_num = match.group(2)
    pad_width = len(raw_num) if len(raw_num) > 1 else 0

    search_paths = [p.parent]
    try:
        from core.config import get_settings
        settings = get_settings()
        archive_dir = Path(settings.directories.archive)
        if archive_dir.exists():
            search_paths.append(archive_dir)
    except Exception:
        pass

    if pad_width > 0:
        first_name = f"{base_stem}.part{1:0{pad_width}d}.rar"
    else:
        first_name = f"{base_stem}.part1.rar"

    first_part = None
    for search_path in search_paths:
        candidate = search_path / first_name
        if candidate.exists():
            first_part = str(candidate.resolve())
            break

    if first_part:
        return {"base_stem": base_stem, "part_num": part_num, "first_part": first_part}

    return None
