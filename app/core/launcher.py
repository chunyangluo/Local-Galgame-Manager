from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from pathlib import Path
from ctypes import wintypes


SEE_MASK_NOCLOSEPROCESS = 0x00000040
INFINITE = 0xFFFFFFFF


class SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("fMask", wintypes.ULONG),
        ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", wintypes.LPCWSTR),
        ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD),
        ("hIconOrMonitor", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
    ]


class GameLauncher:
    def launch(self, exe_path: str, as_admin: bool = False) -> int:
        exe = Path(exe_path)
        if not exe.exists():
            raise FileNotFoundError(f"Launch target not found: {exe_path}")
        if as_admin:
            return self._launch_as_admin(exe)
        process = subprocess.Popen([str(exe)], cwd=str(exe.parent))
        started = int(time.time())
        process.wait()
        ended = int(time.time())
        return max(0, ended - started)

    def launch_via_locale_emulator(self, leproc_exe: str, target_exe: str) -> int:
        """Run game.exe through Locale Emulator's LEProc (waits until game exits).

        Uses the default invocation ``LEProc.exe <absolute_target>`` so LE picks
        per-exe ``.le.config`` / global profile / built-in ja-JP (see upstream LE).
        """
        if sys.platform != "win32":
            raise RuntimeError("Locale Emulator is only supported on Windows.")
        leproc = Path(leproc_exe)
        exe = Path(target_exe)
        if not leproc.is_file():
            raise FileNotFoundError(f"LEProc not found: {leproc_exe}")
        if not exe.is_file():
            raise FileNotFoundError(f"Launch target not found: {target_exe}")
        if leproc.name.lower() != "leproc.exe":
            raise ValueError("Locale Emulator setting must point to LEProc.exe")
        abs_target = str(exe.resolve())
        # Use the game's directory as cwd (same as normal ``launch()``). Many packed
        # titles (e.g. MoleBox "boxfile") resolve archives relative to cwd; using LE's
        # install dir here breaks those with "COULD NOT OPEN BOXFILE". LEProc still
        # loads its DLLs from its own executable directory via the Windows loader.
        process = subprocess.Popen(
            [str(leproc.resolve()), abs_target],
            cwd=str(exe.parent),
        )
        started = int(time.time())
        process.wait()
        ended = int(time.time())
        rc = process.returncode
        if rc is not None and rc != 0:
            raise RuntimeError(
                f"LEProc.exe 退出码 {rc}，游戏可能未成功启动。请确认 LE 已正确安装、"
                "且指向安装目录内的 LEProc.exe。"
            )
        return max(0, ended - started)

    def _launch_as_admin(self, exe: Path) -> int:
        # ShellExecuteExW with SEE_MASK_NOCLOSEPROCESS triggers UAC prompt and
        # returns an OS process handle, so we can wait and measure real duration.
        shell32 = ctypes.windll.shell32  # type: ignore[attr-defined]
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

        execute_info = SHELLEXECUTEINFOW()
        execute_info.cbSize = ctypes.sizeof(SHELLEXECUTEINFOW)
        execute_info.fMask = SEE_MASK_NOCLOSEPROCESS
        execute_info.hwnd = None
        execute_info.lpVerb = "runas"
        execute_info.lpFile = str(exe)
        execute_info.lpParameters = None
        execute_info.lpDirectory = str(exe.parent)
        execute_info.nShow = 1

        started = int(time.time())
        ok = shell32.ShellExecuteExW(ctypes.byref(execute_info))
        if not ok:
            error_code = ctypes.GetLastError()
            raise PermissionError(f"UAC elevate launch failed, win32 code={error_code}")

        if not execute_info.hProcess:
            raise RuntimeError("Admin launch returned no process handle.")

        kernel32.WaitForSingleObject(execute_info.hProcess, INFINITE)
        kernel32.CloseHandle(execute_info.hProcess)
        ended = int(time.time())
        return max(0, ended - started)
