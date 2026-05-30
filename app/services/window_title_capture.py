"""窗口标题捕获服务。

在游戏启动后，通过 Win32 API 枚举窗口，找到与启动进程匹配的窗口标题。
仅读取一次并缓存到数据库，后续不再重复抓取。
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import logging
import sys
import time
from typing import Callable

log = logging.getLogger(__name__)

# Win32 API 声明
user32 = ctypes.windll.user32  # type: ignore[attr-defined]
kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

# 无效窗口标题黑名单（通用词、错误提示词，无法用于识别游戏）
_INVALID_TITLES = frozenset({
    "game", "launcher", "start", "menu", "window", "application",
    "program", "default", "untitled", "无标题", "启动程序",
    "游戏", "主程序", "开始",
    # 错误对话框相关
    "error", "错误", "exception", "exception handler",
    "runtime", "visual c++", "visual studio",
    "install", "setup", "component", "required",
    "crash", "fatal", "warning", "alert",
    "dialog", "message", "prompt", "confirm",
})


def is_valid_window_title(title: str) -> bool:
    """校验窗口标题是否有效（非通用词、非空、长度合理、非错误提示）。"""
    if not title or not title.strip():
        return False
    stripped = title.strip()
    if len(stripped) < 2:
        return False
    if stripped.lower() in _INVALID_TITLES:
        return False
    # 检查标题中是否包含黑名单词汇（不仅仅是完全匹配）
    lower_title = stripped.lower()
    for invalid_word in _INVALID_TITLES:
        if invalid_word in lower_title:
            return False
    return True


def capture_window_title(
    exe_path: str,
    *,
    timeout_seconds: float = 15.0,
    poll_interval: float = 0.5,
) -> str | None:
    """启动游戏后捕获窗口标题。

    通过枚举所有顶层窗口，匹配与 exe_path 同进程的窗口。
    最多等待 timeout_seconds 秒。

    Args:
        exe_path: 游戏可执行文件路径
        timeout_seconds: 最大等待时间
        poll_interval: 轮询间隔

    Returns:
        有效窗口标题，或 None（未找到/无效）
    """
    if sys.platform != "win32":
        return None

    from pathlib import Path
    exe_name = Path(exe_path).name.lower()

    deadline = time.monotonic() + timeout_seconds
    best_title: str | None = None

    while time.monotonic() < deadline:
        titles = _enumerate_process_window_titles(exe_name)
        for title in titles:
            if is_valid_window_title(title):
                # 优先选择更长的标题（通常是正式游戏名）
                if best_title is None or len(title) > len(best_title):
                    best_title = title
        if best_title:
            break
        time.sleep(poll_interval)

    if best_title:
        log.info("Captured window title for %s: %s", exe_name, best_title)
    else:
        log.debug("No valid window title found for %s within %.1fs", exe_name, timeout_seconds)

    return best_title


def _enumerate_process_window_titles(exe_name_lower: str) -> list[str]:
    """枚举所有顶层窗口，返回与目标 exe 同进程的窗口标题列表。"""
    titles: list[str] = []

    # 获取所有进程ID → exe名 的映射
    pid_to_name = _get_process_map()
    target_pids = {pid for pid, name in pid_to_name.items() if name == exe_name_lower}

    if not target_pids:
        return titles

    def _enum_callback(hwnd, _lparam):
        # 跳过不可见窗口
        if not user32.IsWindowVisible(hwnd):
            return True

        # 获取窗口所属进程ID
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value not in target_pids:
            return True

        # 获取窗口标题
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()
        if title:
            titles.append(title)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(_enum_callback), 0)

    return titles


def _get_process_map() -> dict[int, str]:
    """获取进程ID → exe文件名（小写）的映射。"""
    TH32CS_SNAPPROCESS = 0x00000002

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(wintypes.ULONG)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_char * 260),
        ]

    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == wintypes.HANDLE(-1).value:
        return {}

    entry = PROCESSENTRY32()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32)

    result: dict[int, str] = {}
    if kernel32.Process32First(snapshot, ctypes.byref(entry)):
        while True:
            try:
                exe_name = entry.szExeFile.decode("mbcs", errors="replace").lower()
                result[entry.th32ProcessID] = exe_name
            except Exception:
                pass
            if not kernel32.Process32Next(snapshot, ctypes.byref(entry)):
                break

    kernel32.CloseHandle(snapshot)
    return result
