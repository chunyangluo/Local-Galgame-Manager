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
        "请从官网下载安装：https://www.freedownloadmanager.org/zh/\n"
        "或在「设置 → 工具路径」中指定 fdm.exe。"
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


def _popen(cmd: list[str], *, show_window: bool = True) -> None:
    kwargs: dict = {}
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        # subprocess only exposes SW_HIDE; use Win32 SW_SHOWNORMAL (1) to show GUI.
        startupinfo.wShowWindow = 1 if show_window else subprocess.SW_HIDE
        kwargs["startupinfo"] = startupinfo
        if not show_window:
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    subprocess.Popen(cmd, cwd=os.path.dirname(cmd[0]) or None, **kwargs)
