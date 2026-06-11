"""Quick workflow dialog: Auto-extract → Incremental scan → Incremental VNDB import."""

from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.ui.dialog_presenter import present_auxiliary_dialog


class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


_STATUS_DISPLAY = {
    StepStatus.PENDING: ("⏳", "#6B7280", "等待中"),
    StepStatus.RUNNING: ("⚙️", "#3B82F6", "执行中…"),
    StepStatus.SUCCESS: ("✅", "#10B981", ""),
    StepStatus.FAILED: ("❌", "#EF4444", ""),
    StepStatus.SKIPPED: ("⏭️", "#9CA3AF", "已跳过"),
}


class StepWidget(QGroupBox):
    """Visual representation of a single workflow step."""

    def __init__(self, title: str, description: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setTitle(title)
        self._status = StepStatus.PENDING
        self._result_text = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        self._desc_label = QLabel(description)
        self._desc_label.setStyleSheet("color:#93A1B6;font-size:13px;")
        layout.addWidget(self._desc_label)

        row = QHBoxLayout()
        self._status_icon = QLabel("⏳")
        self._status_icon.setStyleSheet("font-size:18px;")
        row.addWidget(self._status_icon)

        self._status_label = QLabel("等待中")
        self._status_label.setStyleSheet("color:#6B7280;font-size:13px;font-weight:bold;")
        row.addWidget(self._status_label)

        row.addStretch(1)

        self._result_label = QLabel("")
        self._result_label.setStyleSheet("color:#93A1B6;font-size:11px;")
        self._result_label.setWordWrap(True)
        row.addWidget(self._result_label, 1)

        layout.addLayout(row)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setMaximumHeight(6)
        self._progress.setVisible(False)
        self._progress.setTextVisible(False)
        layout.addWidget(self._progress)

    def set_status(self, status: StepStatus, result: str = "") -> None:
        self._status = status
        icon, color, default_text = _STATUS_DISPLAY[status]
        self._status_icon.setText(icon)
        self._status_label.setStyleSheet(f"color:{color};font-size:13px;font-weight:bold;")
        self._status_label.setText(result if result else default_text)
        self._result_label.setText(result if status != StepStatus.RUNNING else "")
        self._progress.setVisible(status == StepStatus.RUNNING)
        if status != StepStatus.RUNNING:
            self._progress.setVisible(False)

    def set_progress(self, value: int) -> None:
        self._progress.setVisible(True)
        self._progress.setValue(value)


class QuickWorkflowDialog(QDialog):
    """One-click workflow: Auto-extract → Incremental scan → Incremental VNDB import."""

    workflow_finished = Signal(bool)  # True if all steps completed (even with skips)

    def __init__(self, main_window, parent: QWidget | None = None):
        super().__init__(parent)
        self._main = main_window
        self.setWindowTitle("一键工作流")
        self.setMinimumSize(600, 720)
        self.resize(660, 820)
        self._running = False
        self._cancelled = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Header
        header = QLabel("一键工作流：下载 → 解压 → 扫描 → 导入")
        header.setStyleSheet("font-size:15px;font-weight:bold;color:#E5E7EB;")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        desc = QLabel("自动执行：解压监控目录中的压缩包 → 增量扫描新游戏 → 增量 VNDB 元数据导入")
        desc.setStyleSheet("color:#93A1B6;font-size:13px;")
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc)

        # Steps — scrollable so the log panel keeps enough height
        steps_scroll = QScrollArea()
        steps_scroll.setWidgetResizable(True)
        steps_scroll.setFrameShape(QFrame.Shape.NoFrame)
        steps_scroll.setMaximumHeight(300)
        steps_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        steps_body = QWidget()
        steps_layout = QVBoxLayout(steps_body)
        steps_layout.setContentsMargins(0, 0, 4, 0)
        steps_layout.setSpacing(8)

        self._step_extract = StepWidget("步骤 1：自动解压", "扫描监控目录中的压缩包并自动解压到目标目录")
        steps_layout.addWidget(self._step_extract)

        self._step_clean_dead = StepWidget("步骤 2：清理死链接", "检测并清理文件夹已不存在的游戏记录")
        steps_layout.addWidget(self._step_clean_dead)

        self._step_scan = StepWidget("步骤 3：增量扫描", "扫描游戏目录，仅导入新增游戏（跳过已有记录）")
        steps_layout.addWidget(self._step_scan)

        self._step_vndb = StepWidget("步骤 4：增量 VNDB 导入", "为新导入的游戏匹配 VNDB/Bangumi 元数据与封面")
        steps_layout.addWidget(self._step_vndb)

        self._step_done = StepWidget("完成", "工作流执行完毕")
        steps_layout.addWidget(self._step_done)

        steps_scroll.setWidget(steps_body)
        layout.addWidget(steps_scroll)

        # Log area — primary reading surface during workflow runs
        log_group = QGroupBox("运行日志")
        log_group.setStyleSheet("QGroupBox { font-size: 14px; font-weight: 600; }")
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(10, 14, 10, 10)
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(240)
        self._log.setFont(QFont("Consolas", 11))
        self._log.setStyleSheet(
            "QTextEdit{"
            "background-color:#1C2230;"
            "color:#E5E7EB;"
            "border:1px solid #374151;"
            "border-radius:6px;"
            "padding:10px;"
            "font-size:13px;"
            "line-height:1.45;"
            "}"
        )
        self._log.setPlaceholderText("运行日志将显示在这里…")
        log_layout.addWidget(self._log)
        layout.addWidget(log_group, 2)

        # Buttons
        btn_row = QHBoxLayout()

        self._btn_fdm = QPushButton("📥 FDM 下载")
        self._btn_fdm.setToolTip("打开 FDM 下载窗口，粘贴链接并发送到 Free Download Manager")
        self._btn_fdm.clicked.connect(self._open_fdm)
        btn_row.addWidget(self._btn_fdm)

        self._btn_pwd = QPushButton("🔑 管理密码本")
        self._btn_pwd.setToolTip("打开密码本管理窗口，维护解压密码列表")
        self._btn_pwd.clicked.connect(self._open_password_manager)
        btn_row.addWidget(self._btn_pwd)

        btn_row.addStretch(1)

        self._btn_start = QPushButton("🚀 开始执行")
        self._btn_start.setProperty("btnRole", "primary")
        self._btn_start.setMinimumWidth(120)
        self._btn_start.clicked.connect(self._start_workflow)
        btn_row.addWidget(self._btn_start)

        self._btn_cancel = QPushButton("取消")
        self._btn_cancel.setEnabled(False)
        self._btn_cancel.clicked.connect(self._cancel_workflow)
        btn_row.addWidget(self._btn_cancel)

        self._btn_close = QPushButton("关闭")
        self._btn_close.clicked.connect(self._on_close_requested)
        btn_row.addWidget(self._btn_close)

        layout.addLayout(btn_row)

    def _open_fdm(self) -> None:
        from app.ui.dialogs.fdm_dialog import FdmDialog

        try:
            if getattr(self, "_fdm_dlg", None) is not None and self._fdm_dlg.isVisible():
                present_auxiliary_dialog(self, self._fdm_dlg)
                return
            self._fdm_dlg = FdmDialog(self._main, parent=self)
            present_auxiliary_dialog(self, self._fdm_dlg)
        except Exception as e:
            QMessageBox.warning(self, "打开失败", str(e))

    def _open_password_manager(self) -> None:
        from app.ui.dialogs.password_manager_dialog import PasswordManagerDialog

        try:
            if getattr(self, "_pwd_dlg", None) is not None and self._pwd_dlg.isVisible():
                present_auxiliary_dialog(self, self._pwd_dlg)
                return
            self._pwd_dlg = PasswordManagerDialog(self)
            self._pwd_dlg.setWindowTitle("密码本管理")
            self._pwd_dlg.resize(560, 480)
            present_auxiliary_dialog(self, self._pwd_dlg)
        except Exception as e:
            QMessageBox.warning(self, "打开失败", str(e))

    def _log_message(self, msg: str) -> None:
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self._log.append(f"<span style='color:#6B7280;'>[{ts}]</span> {msg}")
        # Also write to standard logging
        logging.getLogger(__name__).info("QuickWorkflow: %s", msg)

    def _start_workflow(self) -> None:
        if self._running:
            return
        self._running = True
        self._cancelled = False
        self._btn_start.setEnabled(False)
        self._btn_cancel.setEnabled(True)
        self._btn_close.setEnabled(False)

        # Reset all steps
        self._step_extract.set_status(StepStatus.PENDING)
        self._step_clean_dead.set_status(StepStatus.PENDING)
        self._step_scan.set_status(StepStatus.PENDING)
        self._step_vndb.set_status(StepStatus.PENDING)
        self._step_done.set_status(StepStatus.PENDING)
        self._log.clear()

        self._log_message("工作流启动")
        self._run_step_extract()

    def _cancel_workflow(self) -> None:
        self._cancelled = True
        self._log_message("用户请求取消…")
        self._btn_cancel.setEnabled(False)
        # Cancel extract task
        if hasattr(self, '_extract_task') and self._extract_task is not None:
            try:
                self._extract_task.cancel()
            except Exception:
                pass
        # Cancel scan worker (owned by this dialog, not main window)
        if hasattr(self, '_scan_worker') and self._scan_worker is not None:
            self._scan_worker.request_cancel()
        # Cancel VNDB worker (owned by main window)
        if hasattr(self._main, '_vndb_worker') and self._main._vndb_worker is not None:
            self._main._vndb_worker.request_cancel()

    def _on_close_requested(self) -> None:
        if self._running:
            return
        self.accept()

    def reject(self) -> None:
        """Prevent closing via ESC/X while workflow is running."""
        if self._running:
            self._cancel_workflow()
            return
        super().reject()

    def _finish_workflow(self, success: bool) -> None:
        self._running = False
        self._btn_start.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._btn_close.setEnabled(True)
        if success:
            self._step_done.set_status(StepStatus.SUCCESS, "所有步骤已完成")
            self._log_message("工作流执行完毕")
        else:
            self._step_done.set_status(StepStatus.FAILED, "工作流被取消或出错")
            self._log_message("工作流未完成")
        self.workflow_finished.emit(success)

    # ---- Step 1: Auto-extract ----

    def _run_step_extract(self) -> None:
        if self._cancelled:
            self._finish_workflow(False)
            return

        self._step_extract.set_status(StepStatus.RUNNING)
        self._log_message("步骤 1：开始自动解压…")

        try:
            from app.services.auto_extract_service import is_auto_extract_available, read_directory_config
            if not is_auto_extract_available():
                self._step_extract.set_status(StepStatus.SKIPPED, "自动解压工具不可用")
                self._log_message("自动解压工具不可用，跳过此步骤")
                self._run_step_clean_dead()
                return

            config = read_directory_config()
            watch_dir = config.get("watch", "")
            if not watch_dir or not Path(watch_dir).is_dir():
                self._step_extract.set_status(StepStatus.SKIPPED, "监控目录未配置")
                self._log_message("监控目录未配置，跳过自动解压")
                self._run_step_clean_dead()
                return

        except Exception as e:
            self._step_extract.set_status(StepStatus.SKIPPED, f"检查失败: {e}")
            self._log_message(f"自动解压检查失败，跳过: {e}")
            self._run_step_clean_dead()
            return

        # Run extraction scan in background
        from app.workers.auto_extract_worker import AutoExtractScanTask
        from PySide6.QtCore import QThreadPool

        self._extract_task = AutoExtractScanTask()
        self._extract_task.signals.progress.connect(self._on_extract_progress)
        self._extract_task.signals.scan_finished.connect(self._on_extract_finished)
        self._extract_task.signals.failed.connect(self._on_extract_failed)
        QThreadPool.globalInstance().start(self._extract_task)

    def _on_extract_progress(self, payload: dict) -> None:
        if self._cancelled:
            return
        phase = payload.get("phase", "")
        if phase == "extracting":
            index = payload.get("index", 0)
            total = payload.get("total", 1)
            name = payload.get("name", "")
            pct = int((index / max(total, 1)) * 100)
            self._step_extract.set_progress(pct)
            self._step_extract.set_status(StepStatus.RUNNING, f"解压中 {index}/{total}: {name}")
        elif phase == "file_done":
            name = payload.get("name", "")
            success = payload.get("success", False)
            if success:
                self._log_message(f"  解压成功: {name}")
            else:
                msg = payload.get("message", "未知错误")
                self._log_message(f"  <span style='color:#EF4444;'>解压失败: {name} — {msg}</span>")
        elif phase == "collected":
            total = payload.get("total", 0)
            self._log_message(f"  发现 {total} 个压缩包")

    def _on_extract_finished(self, result) -> None:
        if self._cancelled:
            self._step_extract.set_status(StepStatus.FAILED, "已取消")
            self._finish_workflow(False)
            return

        success = result.success if result else 0
        failed = result.failed if result else 0
        total = result.total if result else 0

        if total == 0:
            self._step_extract.set_status(StepStatus.SKIPPED, "未发现满足条件的压缩包")
            self._log_message("未发现满足条件的压缩包（≥200MB），跳过")
        else:
            self._step_extract.set_status(StepStatus.SUCCESS, f"成功 {success}，失败 {failed}，共 {total}")
            self._log_message(f"自动解压完成：成功 {success}，失败 {failed}")

        self._run_step_clean_dead()

    def _on_extract_failed(self, error_msg: str) -> None:
        self._step_extract.set_status(StepStatus.FAILED, error_msg)
        self._log_message(f"<span style='color:#EF4444;'>自动解压失败: {error_msg}</span>")
        # Continue to next step anyway
        self._run_step_clean_dead()

    # ---- Step 2: Clean dead links ----

    def _run_step_clean_dead(self) -> None:
        if self._cancelled:
            self._finish_workflow(False)
            return

        self._step_clean_dead.set_status(StepStatus.RUNNING)
        self._log_message("步骤 2：检测死链接…")

        try:
            dead_games = self._main.db.list_dead_games()
            if not dead_games:
                self._step_clean_dead.set_status(StepStatus.SKIPPED, "无死链接")
                self._log_message("无死链接，跳过此步骤")
                self._run_step_scan()
                return

            count = len(dead_games)
            # Auto-clean dead links without custom data
            ids = [g.id for g in dead_games]
            removed = self._main.db.remove_games_by_ids(ids, keep_custom=True)
            kept = count - removed

            if removed > 0:
                self._step_clean_dead.set_status(StepStatus.SUCCESS, f"清理 {removed} 个死链接")
                self._log_message(f"已清理 {removed} 个死链接" + (f"，保留 {kept} 个含自定义数据" if kept else ""))
                self._main.refresh_games()
            else:
                self._step_clean_dead.set_status(StepStatus.SKIPPED, f"{count} 个含自定义数据，已保留")
                self._log_message(f"检测到 {count} 个死链接但均含自定义数据，已保留")
        except Exception as e:
            self._step_clean_dead.set_status(StepStatus.FAILED, str(e))
            self._log_message(f"<span style='color:#EF4444;'>死链接清理失败: {e}</span>")

        self._run_step_scan()

    # ---- Step 3: Incremental scan ----

    def _run_step_scan(self) -> None:
        if self._cancelled:
            self._finish_workflow(False)
            return

        self._step_scan.set_status(StepStatus.RUNNING)
        self._log_message("步骤 2：开始增量扫描…")

        roots = self._main.db.list_scan_roots()
        if not roots:
            self._step_scan.set_status(StepStatus.SKIPPED, "未配置扫描目录")
            self._log_message("未配置扫描目录，跳过扫描")
            self._run_step_vndb([])
            return

        # Use the main window's scan infrastructure
        from PySide6.QtCore import QThread
        from app.workers import ScanWorker

        self._scan_thread = QThread(self)
        self._scan_worker = ScanWorker(roots, self._main.scanner, self._main.plugin_manager)
        self._scan_worker.moveToThread(self._scan_thread)
        self._scan_thread.started.connect(self._scan_worker.run)
        self._scan_worker.progress.connect(self._on_scan_progress)
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.finished.connect(self._scan_thread.quit)
        self._scan_thread.finished.connect(self._scan_thread.deleteLater)
        self._scan_thread.start()

    def _on_scan_progress(self, current_root, total_roots, imported, root) -> None:
        if self._cancelled:
            return
        pct = int((current_root / max(total_roots, 1)) * 100)
        self._step_scan.set_progress(pct)
        self._step_scan.set_status(StepStatus.RUNNING, f"扫描 {current_root}/{total_roots}，已识别 {imported} 个")

    def _on_scan_finished(self, roots, rows, imported, error) -> None:
        if self._cancelled or error == "__CANCELLED__":
            self._step_scan.set_status(StepStatus.FAILED, "已取消")
            self._finish_workflow(False)
            return

        if error:
            self._step_scan.set_status(StepStatus.FAILED, error)
            self._log_message(f"<span style='color:#EF4444;'>扫描失败: {error}</span>")
            self._finish_workflow(False)
            return

        # Filter for incremental (only new games)
        from app.services.path_utils import normalize_game_dir
        existing_dirs = self._main.db.list_all_game_dirs()
        new_rows = [row for row in rows if normalize_game_dir(row[1]) not in existing_dirs]
        skipped = len(rows) - len(new_rows)
        video_rows = [row for row in new_rows if self._scan_row_content_type(row) == "video"]
        game_rows = [row for row in new_rows if self._scan_row_content_type(row) == "game"]
        for name, root_dir, launch_path, *_ in video_rows:
            self._main.db.upsert_game(name, root_dir, launch_path, content_type="video")

        if not new_rows:
            self._step_scan.set_status(StepStatus.SKIPPED, f"未发现新游戏（已跳过 {skipped} 个已有）")
            self._log_message(f"增量扫描完成，未发现新游戏（跳过 {skipped} 个已有）")
            self._run_step_vndb([])
            return

        if not game_rows:
            self._step_scan.set_status(StepStatus.SUCCESS, f"导入 {len(video_rows)} 个视频（跳过 {skipped} 个已有）")
            self._log_message(f"增量扫描完成：导入 {len(video_rows)} 个视频，无新游戏")
            self._main.refresh_games()
            self._run_step_vndb([])
            return

        suffix = f"，视频 {len(video_rows)} 个" if video_rows else ""
        self._step_scan.set_status(StepStatus.SUCCESS, f"发现 {len(game_rows)} 个新游戏{suffix}（跳过 {skipped} 个已有）")
        self._log_message(f"增量扫描完成：发现 {len(game_rows)} 个新游戏{suffix}")
        self._scan_rows = game_rows
        self._run_step_vndb([(row[0], row[1], row[2]) for row in game_rows])

    # ---- Step 3: Incremental VNDB import ----

    def _run_step_vndb(self, targets: list) -> None:
        if self._cancelled:
            self._finish_workflow(False)
            return

        if not targets:
            self._step_vndb.set_status(StepStatus.SKIPPED, "无新游戏需要导入")
            self._log_message("无新游戏需要 VNDB 导入，跳过")
            self._finish_workflow(True)
            return

        self._step_vndb.set_status(StepStatus.RUNNING)
        self._log_message(f"步骤 3：开始增量 VNDB 导入（{len(targets)} 项）…")

        # Use main window's VNDB import infrastructure
        valid_dirs = {row[1] for row in targets}
        self._main._start_vndb_batch_import(
            targets=targets,
            roots=None,
            valid_dirs=valid_dirs,
            show_result_dialog=False,
            on_import_finished=self._on_vndb_import_done,
        )

    def _on_vndb_import_done(self) -> None:
        if self._cancelled:
            self._step_vndb.set_status(StepStatus.FAILED, "已取消")
            self._finish_workflow(False)
            return

        self._step_vndb.set_status(StepStatus.SUCCESS, "VNDB 元数据导入完成")
        self._log_message("VNDB 增量导入完成")
        self._main.refresh_games()
        self._finish_workflow(True)

    @staticmethod
    def _scan_row_content_type(row: tuple) -> str:
        if len(row) >= 4 and str(row[3]).strip().lower() == "video":
            return "video"
        return "game"
