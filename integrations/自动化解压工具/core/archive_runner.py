"""Run 7-Zip / UnRAR with path-safe arguments and RAR5 fallbacks."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

_WILDCARD_CHARS = "[]*?"


def path_needs_literal_switch(archive_path: str) -> bool:
    return any(ch in archive_path for ch in _WILDCARD_CHARS)


def _dedupe_paths(paths: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in paths:
        try:
            key = str(Path(raw).resolve()).lower()
        except OSError:
            key = raw.lower()
        if key in seen:
            continue
        seen.add(key)
        if Path(raw).is_file():
            out.append(raw)
    return out


def discover_extract_engines(primary_seven_zip: str, archive_path: str) -> list[tuple[str, str]]:
    """Return [(executable, label), ...] in try order."""
    candidates: list[tuple[str, str]] = []
    primary = Path(primary_seven_zip)
    if primary.is_file():
        candidates.append((str(primary), primary.name))

    for name, label in (("7z.exe", "7z"), ("7z", "7z")):
        if name == primary.name:
            continue
        side = primary.parent / name
        if side.is_file():
            candidates.append((str(side), label))

    which_7z = shutil.which("7z")
    if which_7z:
        candidates.append((which_7z, "7z(PATH)"))

    if Path(archive_path).suffix.lower() == ".rar":
        for unrar in (
            Path(r"C:\Program Files\WinRAR\UnRAR.exe"),
            Path(r"C:\Program Files (x86)\WinRAR\UnRAR.exe"),
        ):
            if unrar.is_file():
                candidates.append((str(unrar), "UnRAR"))

    deduped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for exe, label in candidates:
        try:
            key = str(Path(exe).resolve()).lower()
        except OSError:
            key = exe.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append((exe, label))
    return deduped


def build_7z_extract_cmd(
    seven_zip: str,
    archive_path: str,
    output_dir: str,
    password: Optional[str] = None,
) -> list[str]:
    cmd = [seven_zip, "x", archive_path, f"-o{output_dir}", "-aoa", "-y"]
    if path_needs_literal_switch(archive_path):
        cmd.append("-spf2")
    if password is not None:
        cmd.append(f"-p{password}")
    else:
        cmd.append("-p")
    return cmd


def build_unrar_extract_cmd(
    unrar: str,
    archive_path: str,
    output_dir: str,
    password: Optional[str] = None,
) -> list[str]:
    out = output_dir.rstrip("\\/") + ("" if output_dir.endswith(("\\", "/")) else "")
    if os.name == "nt":
        dest = out + "\\"
    else:
        dest = out + "/"
    cmd = [unrar, "x", "-y"]
    if password:
        cmd.append(f"-p{password}")
    else:
        cmd.append("-p-")
    cmd.extend([archive_path, dest])
    return cmd


def build_extract_cmd(
    engine_exe: str,
    archive_path: str,
    output_dir: str,
    password: Optional[str] = None,
) -> list[str]:
    if Path(engine_exe).name.lower() == "unrar.exe":
        return build_unrar_extract_cmd(engine_exe, archive_path, output_dir, password)
    return build_7z_extract_cmd(engine_exe, archive_path, output_dir, password)


def run_extract_cmd(cmd: list[str], *, timeout: int = 7200) -> tuple[bool, str]:
    startupinfo = None
    creationflags = 0
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        creationflags = subprocess.CREATE_NO_WINDOW

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            startupinfo=startupinfo,
            creationflags=creationflags,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode == 0:
            return True, ""
        stderr = result.stderr or result.stdout or ""
        return False, stderr.strip()
    except subprocess.TimeoutExpired:
        return False, "解压超时"
    except FileNotFoundError:
        return False, f"解压程序未找到: {cmd[0]}"
    except Exception as exc:
        return False, str(exc)


def run_extract_with_fallback(
    primary_seven_zip: str,
    archive_path: str,
    output_dir: str,
    password: Optional[str] = None,
) -> tuple[bool, str, str]:
    """Try engines in order. Returns (ok, error, engine_label)."""
    last_error = ""
    for exe, label in discover_extract_engines(primary_seven_zip, archive_path):
        cmd = build_extract_cmd(exe, archive_path, output_dir, password)
        ok, err = run_extract_cmd(cmd)
        if ok:
            return True, "", label
        last_error = err
        lower = err.lower()
        if "cannot open the file as archive" in lower or "can not open the file" in lower:
            continue
        if "wrong password" in lower or "encrypted" in lower:
            return False, err, label
    return False, last_error, ""
