from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from app.services.cover_manager import CoverManager
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
        *,
        window_title: str | None = None,
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
        self._window_title = window_title

    def run(self) -> None:  # type: ignore[override]
        try:
            if self._cancel_check():
                self.signals.finished.emit(self.index, None, None)
                return
            # 多关键词检索：目录名 + 窗口标题
            extra_queries: list[str] | None = None
            if self._window_title:
                extra_queries = [self._window_title]
            outcome = self._vndb_service.search_title(self.name, limit=1, extra_queries=extra_queries)
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
        except Exception:
            # Ensure finished is always emitted so the counter reaches total
            self.signals.finished.emit(self.index, None, None)


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
        *,
        window_titles: dict[str, str] | None = None,
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
        # root_dir → window_title 映射
        self._window_titles = window_titles or {}

    def start(self) -> None:
        if not self._targets:
            self.finished.emit([], [], False)
            return
        for index, (name, root_dir, launch_exe) in enumerate(self._targets):
            wt = self._window_titles.get(root_dir)
            task = VndbTask(
                index=index,
                name=name,
                root_dir=root_dir,
                launch_exe=launch_exe,
                vndb_service=self._vndb_service,
                cover_manager=self._cover_manager,
                cancel_check=self._is_cancelled,
                window_title=wt,
            )
            task.signals.finished.connect(self._on_task_finished)
            self._pool.start(task)

    def request_cancel(self) -> None:
        self._cancel = True
        # 不调用 clear()，让正在运行的任务自然完成
        # 任务会通过 _is_cancelled() 检查取消状态

    def _is_cancelled(self) -> bool:
        return self._cancel

    def _on_task_finished(
        self, index: int, row: VndbImportRow | None, outcome: VndbOutcome | None
    ) -> None:
        # 如果已取消，跳过统计，直接检查是否可以结束
        if self._cancel:
            self._processed += 1
            if self._processed >= len(self._targets):
                self.finished.emit(self._rows, self._outcomes, True)
            return
        
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
