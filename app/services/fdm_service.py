"""Free Download Manager (FDM) launcher integration."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

UI_PREF_FDM_EXE_PATH = "fdm_exe_path"

DEFAULT_FDM_PATHS: tuple[str, ...] = (
    r"C:\Program Files\Softdeluxe\Free Download Manager\fdm.exe",
    r"C:\Program Files (x86)\Softdeluxe\Free Download Manager\fdm.exe",
)


class FdmNotFoundError(FileNotFoundError):
    """FDM executable could not be located."""


def resolve_fdm_exe(custom_path: str | None = None) -> Path:
    if custom_path and custom_path.strip():
        p = Path(custom_path.strip())
        if p.is_file():
            return p.resolve()
        raise FdmNotFoundError(f"未找到 FDM：{p}")

    for candidate in DEFAULT_FDM_PATHS:
        p = Path(candidate)
        if p.is_file():
            return p.resolve()

    raise FdmNotFoundError(
        "未找到 Free Download Manager。\n"
        "请安装 FDM 或在工具中指定 fdm.exe 路径。"
    )


def open_fdm(*, custom_path: str | None = None) -> Path:
    exe = resolve_fdm_exe(custom_path)
    _popen([str(exe)])
    return exe


def add_download_task(url: str, *, custom_path: str | None = None) -> Path:
    normalized = url.strip()
    if not normalized:
        raise ValueError("下载链接不能为空")
    if not normalized.startswith(("http://", "https://", "ftp://", "magnet:")):
        raise ValueError("请输入有效的 http(s) / ftp / magnet 链接")

    exe = resolve_fdm_exe(custom_path)
    _popen([str(exe), "--add", normalized])
    return exe


def _popen(cmd: list[str]) -> None:
    kwargs: dict = {}
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = startupinfo
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    subprocess.Popen(cmd, cwd=os.path.dirname(cmd[0]) or None, **kwargs)
