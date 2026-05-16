from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from app.core.cover_manager import CoverManager
from app.data.database import VndbImportRow
from app.services.vndb_service import VndbOutcome, VndbService


class VndbTaskSignals(QObject):
    finished = Signal(int, object, object)


class VndbTask(QRunnable):
    def __init__(
        self,
        index: int,
        name: str,
        root_dir: str,
        launch_exe: str,
        vndb_service: VndbService,
        cover_manager: CoverManager,
        cancel_check,
    ) -> None:
        super().__init__()
        self.signals = VndbTaskSignals()
        self.index = index
        self.name = name
        self.root_dir = root_dir
        self.launch_exe = launch_exe
        self._vndb_service = vndb_service
        self._cover_manager = cover_manager
        self._cancel_check = cancel_check

    def run(self) -> None:  # type: ignore[override]
        if self._cancel_check():
            self.signals.finished.emit(self.index, None, None)
            return
        outcome = self._vndb_service.search_title(self.name, limit=1)
        cached_cover: str | None = None
        if outcome.success and outcome.record:
            try:
                cached_cover = self._cover_manager.cache_cover_with_fallback(
                    image_url=outcome.record.image_url,
                    cache_key=outcome.record.vndb_id,
                    game_name=self.name,
                )
            except Exception:
                cached_cover = None
        row: VndbImportRow | None = None
        if outcome.success and outcome.record is not None:
            rec = outcome.record
            row = VndbImportRow(
                name=self.name,
                root_dir=self.root_dir,
                launch_exe=self.launch_exe,
                vndb_id=rec.vndb_id,
                title_original=rec.title_original,
                title_localized=rec.title_localized,
                description=rec.description,
                rating=rec.rating,
                platforms=rec.platforms_to_str(),
                languages=rec.languages_to_str(),
                image_url=rec.image_url,
                screenshots_json=rec.screenshots_to_json(),
                cover_path=cached_cover,
            )
        self.signals.finished.emit(self.index, row, outcome)


class VndbImportWorker(QObject):
    progress = Signal(int, int, int, int, str)
    finished = Signal(object, object, bool)

    def __init__(
        self,
        targets: list[tuple[str, str, str]],
        vndb_service: VndbService,
        cover_manager: CoverManager,
        max_threads: int = 6,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._targets = targets
        self._vndb_service = vndb_service
        self._cover_manager = cover_manager
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(max(1, int(max_threads)))
        self._cancel = False
        self._processed = 0
        self._success = 0
        self._fail = 0
        self._rows: list[VndbImportRow] = []
        self._outcomes: list[VndbOutcome] = []

    def start(self) -> None:
        if not self._targets:
            self.finished.emit([], [], False)
            return
        for index, (name, root_dir, launch_exe) in enumerate(self._targets):
            task = VndbTask(
                index=index,
                name=name,
                root_dir=root_dir,
                launch_exe=launch_exe,
                vndb_service=self._vndb_service,
                cover_manager=self._cover_manager,
                cancel_check=self._is_cancelled,
            )
            task.signals.finished.connect(self._on_task_finished)
            self._pool.start(task)

    def request_cancel(self) -> None:
        self._cancel = True
        self._pool.clear()

    def _is_cancelled(self) -> bool:
        return self._cancel

    def _on_task_finished(
        self, index: int, row: VndbImportRow | None, outcome: VndbOutcome | None
    ) -> None:
        self._processed += 1
        total = len(self._targets)
        if outcome is None:
            self._fail += 1
            current_query = ""
        else:
            self._outcomes.append(outcome)
            if row is not None:
                self._rows.append(row)
                self._success += 1
            else:
                self._fail += 1
            current_query = outcome.query or ""
        self.progress.emit(self._processed, total, self._success, self._fail, current_query)
        if self._processed >= total:
            self.finished.emit(self._rows, self._outcomes, self._cancel)
