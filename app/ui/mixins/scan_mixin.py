from __future__ import annotations

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QMessageBox

from app.workers import ScanWorker


class ScanMixin:
    _scan_running: bool
    _scan_thread: QThread | None
    _scan_worker: ScanWorker | None
    _is_incremental_scan: bool = False
    _skip_scan_message: bool = False
    db: object
    scanner: object
    plugin_manager: object
    status: object
    scan_progress: object
    btn_scan: object
    btn_vndb_import: object
    btn_add_root: object
    act_manage_roots: object
    btn_refresh: object
    btn_more: object
    btn_cancel_scan: object

    def _add_scan_root(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        directory = QFileDialog.getExistingDirectory(self, "选择游戏根目录")
        if not directory:
            return
        self.db.add_scan_root(directory)
        self.status.setText(f"已添加扫描目录: {directory}")
        self._update_empty_state()

    def _manage_scan_roots(self) -> None:
        from app.ui.dialogs import ScanRootsDialog

        dialog = ScanRootsDialog(self.db, self)
        dialog.exec()
        roots_count = len(self.db.list_scan_roots())
        if roots_count == 0:
            removed = self.db.clear_all_games()
            self.refresh_games()
            if removed > 0:
                self.status.setText(f"扫描目录已清空，同时清理了 {removed} 条无自定义数据的游戏记录")
            else:
                self.status.setText("扫描目录已清空，保留了含自定义数据的游戏记录")
            return
        self.status.setText(f"当前扫描目录数量: {roots_count}")

    def _scan_and_vndb_import(self) -> None:
        """扫描目录并自动执行VNDB导入（跳过扫描完成消息框）"""
        self._skip_scan_message = True
        self._scan_all()

    def _scan_incremental_and_vndb_import(self) -> None:
        """增量扫描并自动执行增量VNDB导入"""
        self._skip_scan_message = True
        self._scan_incremental()

    def _scan_all(self) -> None:
        if self._scan_running:
            self.status.setText("正在扫描中，请稍候...")
            return
        roots = self.db.list_scan_roots()
        if not roots:
            self.status.setText("请先添加扫描目录")
            return
        self._is_incremental_scan = False
        self._scan_running = True
        self._start_scan_ui()
        self.status.setText("扫描中，请稍候（扫描结束后将自动执行 VNDB 导入）...")
        self._scan_thread = QThread(self)
        self._scan_worker = ScanWorker(roots, self.scanner, self.plugin_manager)
        self._scan_worker.moveToThread(self._scan_thread)
        self._scan_thread.started.connect(self._scan_worker.run)
        self._scan_worker.progress.connect(self._on_scan_progress)
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.finished.connect(self._scan_thread.quit)
        self._scan_thread.finished.connect(self._clear_scan_worker)
        self._scan_thread.start()

    def _scan_incremental(self) -> None:
        if self._scan_running:
            self.status.setText("正在扫描中，请稍候...")
            return
        roots = self.db.list_scan_roots()
        if not roots:
            self.status.setText("请先添加扫描目录")
            return
        existing_dirs = self.db.list_all_game_dirs()
        if existing_dirs:
            self.status.setText(f"增量扫描：已跳过 {len(existing_dirs)} 个已有游戏，只导入新游戏...")
        else:
            self.status.setText("增量扫描：无已有游戏记录，将导入所有扫描到的游戏...")
        self._is_incremental_scan = True
        self._scan_running = True
        self._start_scan_ui()
        self.status.setText("增量扫描中，请稍候（扫描结束后将自动执行 VNDB 导入）...")
        self._scan_thread = QThread(self)
        self._scan_worker = ScanWorker(roots, self.scanner, self.plugin_manager)
        self._scan_worker.moveToThread(self._scan_thread)
        self._scan_thread.started.connect(self._scan_worker.run)
        self._scan_worker.progress.connect(self._on_scan_progress)
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.finished.connect(self._scan_thread.quit)
        self._scan_thread.finished.connect(self._clear_scan_worker)
        self._scan_thread.start()

    def _on_scan_progress(self, current_root: int, total_roots: int, imported: int, root: str) -> None:
        if total_roots <= 0:
            return
        percent = int((current_root / total_roots) * 100)
        self.scan_progress.setValue(percent)
        status_text = f"扫描进度 {current_root}/{total_roots}，已识别 {imported} 个游戏 | 当前目录: {root}"
        self.status.setText(status_text)
        from app.services.log_service import LogService
        LogService.get_instance().progress("扫描", current_root, total_roots)

    def _on_scan_finished(
        self,
        roots: list[str],
        rows: list[tuple[str, str, str]],
        imported: int,
        error: str,
    ) -> None:
        if error == "__CANCELLED__":
            self._scan_running = False
            self._is_incremental_scan = False
            self._skip_scan_message = False
            self._end_scan_ui()
            self.status.setText(f"扫描已取消，已识别 {imported} 个游戏")
            return
        if error:
            self._scan_running = False
            self._is_incremental_scan = False
            self._skip_scan_message = False
            self._end_scan_ui()
            QMessageBox.critical(self, "扫描失败", error)
            self.status.setText("扫描失败，请检查目录权限或文件状态")
            return
        
        # 显示扫描结果弹窗（除非跳过）
        if rows and not self._skip_scan_message:
            msg = f"扫描完成！\n\n"
            msg += f"扫描目录数: {len(roots)}\n"
            msg += f"识别到游戏: {len(rows)} 个"
            QMessageBox.information(self, "扫描完成", msg)
        
        if not rows:
            self._scan_running = False
            self._is_incremental_scan = False
            self._skip_scan_message = False
            self._end_scan_ui()
            self.refresh_games()
            self.status.setText("扫描完成，但未识别到可导入游戏（已保留原有库数据）")
            return
        if self._is_incremental_scan:
            from app.services.path_utils import normalize_game_dir

            existing_dirs = self.db.list_all_game_dirs()
            new_rows = [
                row for row in rows if normalize_game_dir(row[1]) not in existing_dirs
            ]
            skipped_count = len(rows) - len(new_rows)

            # Detect dead links (games whose folders no longer exist)
            dead_games = self.db.list_dead_games()
            if dead_games:
                self._prompt_clean_dead_links(dead_games)

            if skipped_count > 0:
                self.status.setText(f"增量扫描：已跳过 {skipped_count} 个已有游戏")
            rows = new_rows
            self._is_incremental_scan = False
        if not rows:
            self._scan_running = False
            self._skip_scan_message = False
            self._end_scan_ui()
            self.refresh_games()
            self.status.setText("增量扫描完成，没有发现新游戏（已保留原有库数据）")
            return
        valid_dirs = {row[1] for row in rows}
        self._skip_scan_message = False
        self.status.setText(f"扫描完成，开始 VNDB 导入（共 {len(rows)} 项）...")
        self._start_vndb_batch_import(
            targets=rows,
            roots=roots,
            valid_dirs=valid_dirs,
        )

    def _clear_scan_worker(self) -> None:
        self._scan_worker = None
        self._scan_thread = None

    def _prompt_clean_dead_links(self, dead_games: list) -> None:
        """Prompt user to clean up dead links (games whose folders were deleted)."""
        from PySide6.QtWidgets import QMessageBox

        import logging
        log = logging.getLogger(__name__)

        count = len(dead_games)
        names = [g.name or g.root_dir for g in dead_games[:10]]
        name_list = "\n".join(f"  • {n}" for n in names)
        if count > 10:
            name_list += f"\n  … 还有 {count - 10} 个"

        msg = (
            f"检测到 {count} 个游戏的文件夹已不存在（死链接）：\n\n"
            f"{name_list}\n\n"
            f"是否清理这些无效记录？\n"
            f"• 「清理」— 删除无自定义数据的死链接\n"
            f"• 「全部清理」— 删除所有死链接（含自定义数据）\n"
            f"• 「跳过」— 保留，稍后在数据管理中手动清理"
        )

        box = QMessageBox(self)
        box.setWindowTitle("检测到死链接")
        box.setText(msg)
        btn_clean = box.addButton("清理（保留自定义数据）", QMessageBox.AcceptRole)
        btn_clean_all = box.addButton("全部清理", QMessageBox.DestructiveRole)
        btn_skip = box.addButton("跳过", QMessageBox.RejectRole)
        box.exec()

        clicked = box.clickedButton()
        if clicked == btn_skip:
            log.info("User skipped dead link cleanup (%d items)", count)
            return

        keep_custom = clicked == btn_clean
        ids = [g.id for g in dead_games]
        removed = self.db.remove_games_by_ids(ids, keep_custom=keep_custom)
        kept = count - removed
        log.info("Cleaned %d dead links (%d kept due to custom data)", removed, kept)

        self.refresh_games()
        status = f"已清理 {removed} 个死链接"
        if kept:
            status += f"，保留 {kept} 个含自定义数据的记录"
        self.status.setText(status)

    def _cancel_scan(self) -> None:
        if self._vndb_worker is not None:
            self._vndb_worker.request_cancel()
        if self._scan_worker is not None:
            self._scan_worker.request_cancel()
        self.btn_cancel_scan.setEnabled(False)
        self.status.setText("正在取消任务，请稍候...")

    def _start_scan_ui(self) -> None:
        self.btn_scan.setEnabled(False)
        self.btn_vndb_import.setEnabled(False)
        self.btn_add_root.setEnabled(False)
        self.act_manage_roots.setEnabled(False)
        self.btn_refresh.setEnabled(False)
        self.btn_more.setEnabled(False)
        self.btn_cancel_scan.setEnabled(True)
        self.btn_cancel_scan.setVisible(True)
        self.scan_progress.setVisible(True)
        self.scan_progress.setValue(0)

    def _end_scan_ui(self) -> None:
        self.btn_scan.setEnabled(True)
        self.btn_vndb_import.setEnabled(True)
        self.btn_add_root.setEnabled(True)
        self.act_manage_roots.setEnabled(True)
        self.btn_refresh.setEnabled(True)
        self.btn_more.setEnabled(True)
        self.btn_cancel_scan.setVisible(False)
        self.scan_progress.setVisible(False)
