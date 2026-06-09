from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QRunnable, Signal

from app.core.launcher import GameLauncher


class LaunchGameSignals(QObject):
    finished = Signal(int, int, str, bool)  # game_id, duration, game_name, used_le
    failed = Signal(str)
    window_title_captured = Signal(int, str)  # game_id, window_title
    retry_started = Signal(int, str)  # game_id, retry_method ("le" / "normal")


class LaunchGameTask(QRunnable):
    def __init__(
        self,
        launcher: GameLauncher,
        *,
        launch_exe: str,
        locale_emulator: bool,
        le_proc_path: str,
        as_admin: bool,
        game_id: int,
        game_name: str,
        signal_parent: QObject | None = None,
        le_profile: str = "",
        auto_retry: bool = True,
    ) -> None:
        super().__init__()
        self.signals = LaunchGameSignals(signal_parent)
        self._launcher = launcher
        self._launch_exe = launch_exe
        self._locale_emulator = locale_emulator
        self._le_proc_path = le_proc_path
        self._as_admin = as_admin
        self._game_id = game_id
        self._game_name = game_name
        self._le_profile = le_profile
        self._auto_retry = auto_retry

    def _is_crash_exit_code(self, rc: int | None) -> bool:
        """Check if the exit code indicates a crash (game exited immediately)."""
        if rc is None:
            return False
        # Common crash exit codes
        crash_codes = {
            -1073741515,  # 0xC0000135 DLL not found
            -1073741819,  # 0xC0000005 Access violation
            -1073740791,  # 0xC0000409 Stack buffer overflow
            -1073740940,  # 0xC0000374 Heap corruption
            -1073741676,  # 0xC0000094 Integer division by zero
            -1073741571,  # 0xC00000FD Stack overflow
        }
        return rc in crash_codes or rc < 0

    def _try_launch(self, use_le: bool) -> tuple[int, bool]:
        """Try launching the game. Returns (duration, used_le)."""
        log = logging.getLogger(__name__)
        if use_le:
            log.info(
                "Launching via LE: game_id=%s exe=%s le_profile=%s",
                self._game_id, self._launch_exe, self._le_profile,
            )
            duration = self._launcher.launch_via_locale_emulator(
                self._le_proc_path, self._launch_exe,
                le_profile_guid=self._le_profile,
            )
            log.info(
                "LE launch completed: game_id=%s duration=%ds",
                self._game_id, duration,
            )
            return duration, True
        else:
            log.info(
                "Launching normally: game_id=%s exe=%s admin=%s",
                self._game_id, self._launch_exe, self._as_admin,
            )
            duration = self._launcher.launch(self._launch_exe, as_admin=self._as_admin)
            log.info(
                "Normal launch completed: game_id=%s duration=%ds",
                self._game_id, duration,
            )
            return duration, False

    def run(self) -> None:  # type: ignore[override]
        import sys
        import threading

        log = logging.getLogger(__name__)

        # 在子线程中异步捕获窗口标题
        captured_title: str | None = None

        def _capture():
            nonlocal captured_title
            if sys.platform != "win32":
                return
            try:
                from app.services.window_title_capture import capture_window_title
                captured_title = capture_window_title(self._launch_exe, timeout_seconds=15.0)
            except Exception:
                pass

        capture_thread = threading.Thread(target=_capture, daemon=True)
        capture_thread.start()

        try:
            duration, used_le = self._try_launch(self._locale_emulator)

            capture_thread.join(timeout=20.0)
            if captured_title:
                self.signals.window_title_captured.emit(self._game_id, captured_title)

            self.signals.finished.emit(self._game_id, duration, self._game_name, used_le)

        except Exception as first_exc:
            # Auto-retry: if normal launch failed, try LE; if LE failed, try normal
            if self._auto_retry:
                retry_use_le = not self._locale_emulator
                retry_available = (
                    (retry_use_le and self._le_proc_path)
                    or (not retry_use_le)
                )

                if retry_available:
                    retry_method = "LE 转区" if retry_use_le else "普通"
                    log.info(
                        "Launch failed (le=%s), auto-retrying with %s: game_id=%s exe=%s",
                        self._locale_emulator, retry_method, self._game_id, self._launch_exe,
                    )
                    self.signals.retry_started.emit(self._game_id, "le" if retry_use_le else "normal")

                    try:
                        duration, used_le = self._try_launch(retry_use_le)

                        capture_thread.join(timeout=20.0)
                        if captured_title:
                            self.signals.window_title_captured.emit(self._game_id, captured_title)

                        self.signals.finished.emit(self._game_id, duration, self._game_name, used_le)
                        return
                    except Exception:
                        pass  # Both attempts failed, report original error

            self.signals.failed.emit(str(first_exc))
