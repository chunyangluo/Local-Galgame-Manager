from __future__ import annotations

import ctypes
import os
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
    # Common galgame exe names (lowercase) that are likely the main game executable
    _GAME_EXE_PATTERNS = (
        "game", "start", "main", "launch", "play", "run",
        "siglus", "siglusengine", "kirikiri", "krkr", "renpy",
        "arcgame", "system", "cmvs", "rpg", "wolf",
    )

    # Exe names to skip when searching for alternatives
    _SKIP_EXE_NAMES = {
        "uninstall.exe", "uninst.exe", "setup.exe", "install.exe",
        "update.exe", "updater.exe", "patch.exe", "config.exe",
        "settings.exe", "crashreporter.exe", "unitycrashhandler.exe",
        "vcredist.exe", "dxsetup.exe", "oalinst.exe",
    }

    def find_alternative_exe(self, original_exe: str) -> str | None:
        """Try to find an alternative exe if the original doesn't exist.

        Searches the game's root_dir for other exe files, scoring them
        similarly to the scanner's _pick_main_exe logic.

        Returns:
            Path to alternative exe, or None if nothing suitable found.
        """
        exe = Path(original_exe)
        game_dir = exe.parent

        # If the directory itself doesn't exist, try parent directories
        if not game_dir.is_dir():
            # Walk up to find an existing directory
            for parent in exe.parents:
                if parent.is_dir():
                    game_dir = parent
                    break
            else:
                return None

        try:
            exes = sorted(game_dir.rglob("*.exe"))
        except (PermissionError, OSError):
            return None

        if not exes:
            return None

        dir_key = game_dir.name.lower().replace(" ", "").replace("-", "").replace("_", "")

        scored: list[tuple[int, Path]] = []
        for candidate in exes:
            lower = candidate.name.lower()
            if lower in self._SKIP_EXE_NAMES:
                continue
            if candidate.resolve() == exe.resolve():
                continue

            score = 0
            stem_key = candidate.stem.lower().replace(" ", "").replace("-", "").replace("_", "")

            # Name matches directory
            if dir_key and stem_key == dir_key:
                score += 8
            elif dir_key and dir_key in stem_key:
                score += 5

            # Game-like names
            if any(p in lower for p in self._GAME_EXE_PATTERNS):
                score += 3

            # Prefer larger files (more likely to be the game)
            try:
                size_mb = candidate.stat().st_size / (1024 * 1024)
                if size_mb >= 5:
                    score += 2
                elif size_mb >= 1:
                    score += 1
                elif size_mb < 0.5:
                    score -= 2
            except OSError:
                pass

            # Penalize config/setup-like names
            if any(k in lower for k in ("config", "setup", "setting", "tool")):
                score -= 5

            # Prefer 64-bit
            if "x64" in lower or "64" in lower:
                score += 1

            if score > 0:
                scored.append((score, candidate))

        if not scored:
            return None

        scored.sort(key=lambda x: (x[0], x[1].stat().st_size if x[1].exists() else 0), reverse=True)
        return str(scored[0][1])

    def launch(self, exe_path: str, as_admin: bool = False) -> int:
        exe = Path(exe_path)
        if not exe.exists():
            raise FileNotFoundError(f"Launch target not found: {exe_path}")
        if as_admin:
            return self._launch_as_admin(exe)
        env = os.environ.copy()
        env["PATH"] = str(exe.parent) + os.pathsep + env["PATH"]
        process = subprocess.Popen([str(exe)], cwd=str(exe.parent), env=env)
        started = int(time.time())
        process.wait()
        ended = int(time.time())
        duration = max(0, ended - started)
        rc = process.returncode
        # Detect quick crash: game exited within 5 seconds with a non-zero code
        if duration <= 5 and rc is not None and rc != 0:
            raise RuntimeError(
                f"游戏快速退出 (退出码 0x{rc & 0xFFFFFFFF:08X}，运行 {duration}s)，"
                "可能缺少运行时组件或需要转区启动。"
            )
        return duration

    def quick_check_launch(self, exe_path: str, *, use_le: bool = False,
                           leproc_exe: str = "", le_profile_guid: str = "",
                           timeout: float = 8.0) -> dict:
        """Quickly test if a game can start (wait only a few seconds).

        Returns a dict with: started, exit_code, duration_seconds, error_message.
        Unlike debug_launch, this doesn't capture stdout/stderr and uses a shorter timeout.
        """
        exe = Path(exe_path)
        result: dict = {
            "started": False,
            "exit_code": None,
            "duration_seconds": 0,
            "error_message": "",
        }

        if not exe.is_file():
            result["error_message"] = f"启动目标不存在: {exe_path}"
            return result

        env = os.environ.copy()
        env["PATH"] = str(exe.parent) + os.pathsep + env["PATH"]

        try:
            if use_le and leproc_exe:
                leproc = Path(leproc_exe)
                if not leproc.is_file():
                    result["error_message"] = f"LEProc.exe 不存在: {leproc_exe}"
                    return result
                cmd = self._build_le_cmd(leproc_exe, exe_path, le_profile_guid)
            else:
                cmd = [str(exe)]

            started_at = time.monotonic()
            process = subprocess.Popen(cmd, cwd=str(exe.parent), env=env)
            result["started"] = True

            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                # Still running after timeout — likely OK
                process.kill()
                process.wait(timeout=5)
                result["duration_seconds"] = timeout
                result["exit_code"] = None
                return result

            elapsed = time.monotonic() - started_at
            result["duration_seconds"] = round(elapsed, 2)
            result["exit_code"] = process.returncode

            rc = process.returncode
            if rc is not None and rc != 0:
                if elapsed < 2:
                    result["error_message"] = f"进程立即退出（退出码 {rc}，耗时 {elapsed:.1f}s）"
                elif elapsed < timeout:
                    result["error_message"] = f"进程短暂运行后退出（退出码 {rc}，耗时 {elapsed:.1f}s）"

        except FileNotFoundError as e:
            result["error_message"] = f"文件未找到: {e}"
        except PermissionError as e:
            result["error_message"] = f"权限不足: {e}"
        except Exception as e:
            result["error_message"] = f"启动异常: {e}"

        return result

    def debug_launch(self, exe_path: str, *, use_le: bool = False,
                     leproc_exe: str = "", le_profile_guid: str = "") -> dict:
        """Launch game in debug mode and return detailed diagnostic info.

        Returns a dict with keys:
            exe_path, use_le, started, exit_code, duration_seconds,
            stdout, stderr, error_message, suggestions
        """
        exe = Path(exe_path)
        result: dict = {
            "exe_path": str(exe),
            "use_le": use_le,
            "started": False,
            "exit_code": None,
            "duration_seconds": 0,
            "stdout": "",
            "stderr": "",
            "error_message": "",
            "suggestions": [],
        }

        if not exe.is_file():
            result["error_message"] = f"启动目标不存在: {exe_path}"
            result["suggestions"].append("确认游戏安装目录是否完整，是否已被移动或删除")
            result["suggestions"].append("右键「编辑名称/路径」修正启动 exe 路径")
            return result

        env = os.environ.copy()
        env["PATH"] = str(exe.parent) + os.pathsep + env["PATH"]

        try:
            if use_le and leproc_exe:
                # Validate LEProc exists
                local_leproc = exe.parent / "LEProc.exe"
                if not local_leproc.is_file():
                    leproc = Path(leproc_exe)
                    if not leproc.is_file():
                        result["error_message"] = f"LEProc.exe 不存在: {leproc_exe}"
                        result["suggestions"].append("在「更多 → 工具箱 → Locale Emulator」中重新配置 LEProc.exe 路径")
                        return result
                cmd = self._build_le_cmd(leproc_exe, exe_path, le_profile_guid)
            else:
                cmd = [str(exe)]

            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE  # hide console for debug
            creationflags = subprocess.CREATE_NO_WINDOW

            started_at = time.monotonic()
            process = subprocess.Popen(
                cmd,
                cwd=str(exe.parent),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                startupinfo=startupinfo,
                creationflags=creationflags,
            )
            result["started"] = True

            # Wait up to 30 seconds — if game runs longer, it's likely OK
            try:
                stdout, stderr = process.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                # Game is still running after 30s — likely launched successfully
                process.kill()
                stdout, stderr = process.communicate()
                result["duration_seconds"] = 30
                result["exit_code"] = None
                result["stdout"] = stdout.decode("utf-8", errors="replace")[:4096] if stdout else ""
                result["stderr"] = stderr.decode("utf-8", errors="replace")[:4096] if stderr else ""
                result["error_message"] = ""
                result["suggestions"].append("游戏进程运行超过 30 秒未退出，可能已正常启动")
                return result

            elapsed = time.monotonic() - started_at
            result["duration_seconds"] = round(elapsed, 2)
            result["exit_code"] = process.returncode
            result["stdout"] = stdout.decode("utf-8", errors="replace")[:4096] if stdout else ""
            result["stderr"] = stderr.decode("utf-8", errors="replace")[:4096] if stderr else ""

            rc = process.returncode
            if rc == 0:
                pass  # Clean exit
            elif rc is not None and rc != 0:
                duration = elapsed
                if duration < 2:
                    result["error_message"] = f"进程立即退出（退出码 {rc}，耗时 {duration:.1f}s）"
                    result["suggestions"].append("游戏可能缺少运行库（VC++、DirectX 等），检查游戏目录下的 _Redist 文件夹")
                    result["suggestions"].append("可能需要 LE 转区启动（日文游戏在中文系统上可能闪退）")
                    result["suggestions"].append("尝试右键「管理员启动」")
                elif duration < 10:
                    result["error_message"] = f"进程短暂运行后退出（退出码 {rc}，耗时 {duration:.1f}s）"
                    result["suggestions"].append("游戏可能遇到初始化错误，检查 stderr 输出")
                    result["suggestions"].append("可能需要 LE 转区启动")
                else:
                    result["error_message"] = f"进程运行后退出（退出码 {rc}，耗时 {duration:.1f}s）"

                # Specific exit code hints
                if rc == -1073741515:
                    result["suggestions"].append("退出码 0xC0000135 = DLL 未找到，缺少 Visual C++ 运行库或游戏核心 DLL")
                elif rc == -1073741819:
                    result["suggestions"].append("退出码 0xC0000005 = 访问违规，可能需要管理员权限或 LE 转区")
                elif rc == -1073740791:
                    result["suggestions"].append("退出码 0xC0000409 = 堆栈缓冲区溢出，可能需要 LE 转区或兼容模式")

            if use_le and rc is not None and rc != 0:
                result["suggestions"].append("LE 转区启动失败，确认 LE 已正确安装且 LEProc.exe 路径正确")

        except FileNotFoundError as e:
            result["error_message"] = f"文件未找到: {e}"
            result["suggestions"].append("确认游戏 exe 和 LEProc.exe 路径是否正确")
        except PermissionError as e:
            result["error_message"] = f"权限不足: {e}"
            result["suggestions"].append("尝试右键「管理员启动」")
        except Exception as e:
            result["error_message"] = f"启动异常: {e}"

        if not result["suggestions"] and not result["error_message"]:
            result["suggestions"].append("游戏进程正常退出，启动未发现明显问题")

        return result

    def _build_le_cmd(
        self, leproc_exe: str, target_exe: str, le_profile_guid: str = ""
    ) -> list[str]:
        """Build the LEProc command line for launching a game.

        Priority order for LEProc selection:
        1. Local LEProc.exe in the game directory (reads local LEConfig.xml)
        2. Global LEProc.exe from user settings

        Priority order for profile selection:
        1. If .le.config exists next to target → no -runas (auto-detect)
        2. If le_profile_guid provided → use -runas <guid>
        3. Otherwise → no -runas (LE uses default profile)

        Returns:
            Command list, e.g. ["C:\\...\\LEProc.exe", "C:\\...\\game.exe"]
        """
        exe = Path(target_exe)
        # Prefer local LEProc.exe in the game directory
        local_leproc = exe.parent / "LEProc.exe"
        if local_leproc.is_file():
            leproc = local_leproc
        else:
            leproc = Path(leproc_exe)

        abs_target = str(exe.resolve())
        local_le_config = exe.parent / f"{exe.name}.le.config"
        if local_le_config.exists() or not le_profile_guid:
            return [str(leproc.resolve()), abs_target]
        else:
            return [str(leproc.resolve()), "-runas", le_profile_guid, abs_target]

    def launch_via_locale_emulator(self, leproc_exe: str, target_exe: str, *, le_profile_guid: str = "") -> int:
        """Run game.exe through Locale Emulator's LEProc (waits until game exits).

        See ``_build_le_cmd`` for LEProc and profile selection logic.
        """
        if sys.platform != "win32":
            raise RuntimeError("Locale Emulator is only supported on Windows.")
        exe = Path(target_exe)
        if not exe.is_file():
            raise FileNotFoundError(f"Launch target not found: {target_exe}")

        # Validate LEProc exists (local or global)
        local_leproc = exe.parent / "LEProc.exe"
        if not local_leproc.is_file():
            leproc = Path(leproc_exe)
            if not leproc.is_file():
                raise FileNotFoundError(f"LEProc not found: {leproc_exe}")
            if leproc.name.lower() != "leproc.exe":
                raise ValueError("Locale Emulator setting must point to LEProc.exe")

        cmd = self._build_le_cmd(leproc_exe, target_exe, le_profile_guid)
        env = os.environ.copy()
        env["PATH"] = str(exe.parent) + os.pathsep + env["PATH"]
        process = subprocess.Popen(
            cmd,
            cwd=str(exe.parent),
            env=env,
        )
        started = int(time.time())
        process.wait()
        rc = process.returncode
        if rc is not None and rc != 0:
            raise RuntimeError(
                f"LEProc.exe 退出码 {rc}，游戏可能未成功启动。请确认 LE 已正确安装、"
                "且指向安装目录内的 LEProc.exe。"
            )

        # LEProc exits quickly after injecting into the game process.
        # Wait a moment, then check if the game process is actually running.
        game_exe_name = exe.name
        time.sleep(3)
        if not self._is_process_running(game_exe_name):
            raise RuntimeError(
                f"LE 转区启动失败：LEProc 已退出但游戏进程 ({game_exe_name}) 未运行。\n"
                "可能原因：游戏缺少运行库、Graphics.dll 加载失败、或需要不同的 LE 配置。\n"
                "请尝试在游戏目录手动右键 Start.exe → Locale Emulator 启动，确认游戏本身是否正常。"
            )

        # Game is running — wait for it to exit
        ended = self._wait_for_process_exit(game_exe_name, started)
        return max(0, ended - started)

    @staticmethod
    def _is_process_running(name: str) -> bool:
        """Check if a process with the given name is running (Windows only)."""
        if sys.platform != "win32":
            return False
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=5,
            )
            return name.lower() in result.stdout.lower()
        except Exception:
            return False

    @staticmethod
    def _wait_for_process_exit(name: str, started: int, poll_interval: float = 2.0) -> int:
        """Poll until the process with given name exits. Returns end timestamp."""
        while True:
            if not GameLauncher._is_process_running(name):
                return int(time.time())
            time.sleep(poll_interval)

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
