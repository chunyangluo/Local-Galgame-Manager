from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal

from app.core.launcher import GameLauncher


class LaunchGameSignals(QObject):
    finished = Signal(int, int, str, bool)  # game_id, duration, game_name, used_le
    failed = Signal(str)
    window_title_captured = Signal(int, str)  # game_id, window_title


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

    def run(self) -> None:  # type: ignore[override]
        import sys
        import threading

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
            if self._locale_emulator:
                duration = self._launcher.launch_via_locale_emulator(
                    self._le_proc_path, self._launch_exe
                )
            else:
                duration = self._launcher.launch(self._launch_exe, as_admin=self._as_admin)

            capture_thread.join(timeout=20.0)
            if captured_title:
                self.signals.window_title_captured.emit(self._game_id, captured_title)

            self.signals.finished.emit(self._game_id, duration, self._game_name, self._locale_emulator)
        except Exception as exc:  # pragma: no cover
            self.signals.failed.emit(str(exc))
