"""Background auto-extract tasks (single file + directory scan)."""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QRunnable, Signal

from app.services.auto_extract_service import (
    AutoExtractResult,
    AutoExtractScanResult,
    extract_archive,
    scan_watch_directory,
)


class AutoExtractSignals(QObject):
    log_line = Signal(str)
    log_level = Signal(str, str)  # message, level
    progress = Signal(dict)
    extract_finished = Signal(object)
    scan_finished = Signal(object)
    failed = Signal(str)


class AutoExtractFileTask(QRunnable):
    def __init__(
        self,
        file_path: str,
        *,
        password: str = "",
        target_dir: str = "",
        signal_parent: QObject | None = None,
    ) -> None:
        super().__init__()
        self.signals = AutoExtractSignals(signal_parent)
        self._file_path = file_path
        self._password = password
        self._target_dir = target_dir

    def run(self) -> None:  # type: ignore[override]
        try:
            self.signals.log_line.emit(f"开始解压：{self._file_path}")
            result = extract_archive(
                self._file_path,
                password=self._password,
                target_dir=self._target_dir,
            )
            self.signals.extract_finished.emit(result)
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class AutoExtractScanTask(QRunnable):
    def __init__(self, signal_parent: QObject | None = None) -> None:
        super().__init__()
        self.signals = AutoExtractSignals(signal_parent)
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        self._cancel_event.set()

    def run(self) -> None:  # type: ignore[override]
        try:
            result = scan_watch_directory(
                progress=lambda payload: self.signals.progress.emit(payload),
                should_cancel=self._cancel_event.is_set,
            )
            self.signals.scan_finished.emit(result)
        except Exception as exc:
            self.signals.failed.emit(str(exc))
