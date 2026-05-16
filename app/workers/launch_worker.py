from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal

from app.core.launcher import GameLauncher


class LaunchGameSignals(QObject):
    finished = Signal(int, int, str)
    failed = Signal(str)


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
        try:
            if self._locale_emulator:
                duration = self._launcher.launch_via_locale_emulator(
                    self._le_proc_path, self._launch_exe
                )
            else:
                duration = self._launcher.launch(self._launch_exe, as_admin=self._as_admin)
            self.signals.finished.emit(self._game_id, duration, self._game_name)
        except Exception as exc:  # pragma: no cover
            self.signals.failed.emit(str(exc))
