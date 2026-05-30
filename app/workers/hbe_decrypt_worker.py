"""Background HBE decrypt tasks (single + batch)."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal

from app.services.hbe_decrypt_service import (
    HbeBatchResult,
    HbeSingleResult,
    batch_decrypt_known,
    decrypt_single_auto,
    decrypt_single_known,
)


class HbeDecryptSignals(QObject):
    log_line = Signal(str)
    single_finished = Signal(object)
    batch_finished = Signal(object)
    failed = Signal(str)


class HbeSingleDecryptTask(QRunnable):
    def __init__(
        self,
        cipher_path: str,
        password: str,
        *,
        use_auto: bool,
        signal_parent: QObject | None = None,
    ) -> None:
        super().__init__()
        self.signals = HbeDecryptSignals(signal_parent)
        self._cipher_path = cipher_path
        self._password = password
        self._use_auto = use_auto

    def run(self) -> None:  # type: ignore[override]
        try:

            def _log(msg: str) -> None:
                self.signals.log_line.emit(msg)

            if self._use_auto:
                result = decrypt_single_auto(self._cipher_path, log=_log)
            else:
                result = decrypt_single_known(
                    self._cipher_path, self._password, log=_log
                )
            self.signals.single_finished.emit(result)
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class HbeBatchDecryptTask(QRunnable):
    def __init__(
        self,
        password: str,
        ciphertext_dir: str,
        output_dir: str,
        signal_parent: QObject | None = None,
    ) -> None:
        super().__init__()
        self.signals = HbeDecryptSignals(signal_parent)
        self._password = password
        self._ciphertext_dir = ciphertext_dir
        self._output_dir = output_dir

    def run(self) -> None:  # type: ignore[override]
        try:

            def _log(msg: str) -> None:
                self.signals.log_line.emit(msg)

            result = batch_decrypt_known(
                self._password,
                self._ciphertext_dir,
                self._output_dir,
                log=_log,
            )
            self.signals.batch_finished.emit(result)
        except Exception as exc:
            self.signals.failed.emit(str(exc))
