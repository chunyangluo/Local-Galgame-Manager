from __future__ import annotations

from collections.abc import Callable
from functools import partial

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from app.data.database import VndbImportRow
from app.services.vndb_service import VndbOutcome
from app.workers import VndbImportWorker


class VndbImportMixin:
    _scan_running: bool
    _vndb_worker: VndbImportWorker | None
    db: object
    vndb_service: object
    cover_manager: object
    games_cache: list
    status: object
    scan_progress: object

    def _vndb_import_from_existing(self) -> None:
        if self._scan_running:
            self.status.setText("任务进行中，请稍候...")
            return
        if not self.games_cache:
            self.refresh_games()
        if not self.games_cache:
            self.status.setText("当前无游戏记录，请先执行扫描")
            return
        targets = [(g.name, g.root_dir, g.launch_exe) for g in self.games_cache]
        self._scan_running = True
        self._start_scan_ui()
        self.status.setText(f"开始 VNDB 批量导入（共 {len(targets)} 项）...")
        self._start_vndb_batch_import(targets=targets, roots=None, valid_dirs=None)

    def _start_vndb_batch_import(
        self,
        targets: list[tuple[str, str, str]],
        roots: list[str] | None,
        valid_dirs: set[str] | None,
        *,
        show_result_dialog: bool = True,
        on_import_finished: Callable[[], None] | None = None,
    ) -> None:
        window_titles: dict[str, str] = {}
        root_dirs = [root_dir for _, root_dir, _ in targets]
        if root_dirs:
            window_titles = self.db.get_window_titles_by_root_dirs(root_dirs)

        self._vndb_worker = VndbImportWorker(
            targets=targets,
            vndb_service=self.vndb_service,
            cover_manager=self.cover_manager,
            max_threads=6,
            parent=self,
            window_titles=window_titles,
        )
        self._vndb_worker.progress.connect(self._on_vndb_progress)
        self._vndb_worker.finished.connect(
            partial(
                self._on_vndb_finished,
                roots=roots,
                valid_dirs=valid_dirs,
                targets=targets,
                total=len(targets),
                show_result_dialog=show_result_dialog,
                on_import_finished=on_import_finished,
            ),
            Qt.QueuedConnection,
        )
        self._vndb_worker.start()

    def _on_vndb_progress(
        self, processed: int, total: int, success: int, fail: int, query: str
    ) -> None:
        percent = int((processed / max(total, 1)) * 100)
        self.scan_progress.setValue(percent)
        q = f" | 当前: {query}" if query else ""
        status_text = f"VNDB 导入进度 {processed}/{total}，成功 {success}，失败 {fail}{q}"
        self.status.setText(status_text)
        from app.services.log_service import LogService
        LogService.get_instance().progress("VNDB导入", processed, total)

    def _on_vndb_finished(
        self,
        rows: list[VndbImportRow],
        outcomes: list[VndbOutcome],
        cancelled: bool,
        *,
        roots: list[str] | None,
        valid_dirs: set[str] | None,
        targets: list[tuple[str, str, str]],
        total: int,
        show_result_dialog: bool = True,
        on_import_finished: Callable[[], None] | None = None,
    ) -> None:
        from app.ui.dialogs import VndbImportResultDialog

        self._scan_running = False
        self._vndb_worker = None
        self._end_scan_ui()
        successful_keys = {(row.root_dir, row.launch_exe) for row in rows}
        for name, root_dir, launch_exe in targets:
            if (root_dir, launch_exe) in successful_keys:
                continue
            cover = self.cover_manager.find_cover(root_dir, name) or ""
            self.db.upsert_game(name, root_dir, launch_exe, cover)
        if rows:
            self.db.upsert_games_batch(rows)

        # Auto-detect LE profile for newly imported games
        try:
            from app.services.le_config_service import detect_recommended_le_profile
            for name, root_dir, launch_exe in targets:
                if not root_dir or not launch_exe:
                    continue
                game = self.db.find_game_by_root(root_dir)
                if game is None:
                    continue
                existing_profile = self.db.get_game_le_profile(game.id) if hasattr(self.db, 'get_game_le_profile') else ""
                if existing_profile:
                    continue  # Don't overwrite user-set profile
                recommended = detect_recommended_le_profile(root_dir, launch_exe)
                if recommended and hasattr(self.db, 'set_game_le_profile'):
                    self.db.set_game_le_profile(game.id, recommended)
        except Exception:
            pass  # Auto-detect is best-effort, don't block import

        self.refresh_games()
        success = len(rows)
        self.status.setText(f"VNDB 导入完成：成功 {success} / {total}")
        if on_import_finished is not None:
            on_import_finished()
        if show_result_dialog:
            dialog = VndbImportResultDialog(
                total=total,
                success=success,
                cancelled=cancelled,
                outcomes=outcomes,
                targets=targets,
                parent=self,
            )
            dialog.exec()
            
            selected_records = dialog.get_selected_records()
            for idx, record in selected_records:
                name, root_dir, launch_exe = targets[idx]
                cover = self.cover_manager.cache_cover_with_fallback(
                    image_url=record.image_url,
                    cache_key=record.vndb_id,
                    game_name=name,
                )
                row = VndbImportRow(
                    name=name,
                    root_dir=root_dir,
                    launch_exe=launch_exe,
                    vndb_id=record.vndb_id,
                    title_original=record.title_original,
                    title_localized=record.title_localized,
                    description=record.description,
                    rating=record.rating,
                    platforms=record.platforms_to_str(),
                    languages=record.languages_to_str(),
                    image_url=record.image_url,
                    screenshots_json=record.screenshots_to_json(),
                    cover_path=cover,
                )
                self.db.upsert_games_batch([row])
                self.status.setText(f"已更新游戏「{name}」的元数据")
            
            if selected_records:
                self.refresh_games()
        elif total <= 1:
            if cancelled:
                self.status.setText("VNDB 元数据获取已取消")
            elif success:
                self.status.setText("VNDB 元数据已更新")
            else:
                self.status.setText("VNDB 元数据获取失败或未匹配")

    def run_vndb_import_for_game_id(
        self, game_id: int, *, on_finished: Callable[[], None] | None = None
    ) -> None:
        if self._scan_running:
            QMessageBox.information(self, "请稍候", "已有扫描或 VNDB 任务在进行中。")
            return
        game = self.db.get_game_by_id(self.current_user_id, game_id)
        if game is None:
            QMessageBox.warning(self, "未找到游戏", "该游戏记录不存在。")
            return
        targets = [(game.name, game.root_dir, game.launch_exe)]
        self._scan_running = True
        self._start_scan_ui()
        self.status.setText("VNDB 元数据获取中（当前游戏）…")
        self._start_vndb_batch_import(
            targets=targets,
            roots=None,
            valid_dirs=None,
            show_result_dialog=False,
            on_import_finished=on_finished,
        )
