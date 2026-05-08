from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QRunnable, QThread, QThreadPool, QTimer, QSize, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QColor,
    QFontMetrics,
    QIcon,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
    QPolygon,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSystemTrayIcon,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.cover_manager import CoverManager
from app.core.launcher import GameLauncher
from app.core.scanner import GameScanner
from app.data.database import Database, GameRecord, VndbImportRow
from app.plugins.manager import PluginManager
from app.services.backup_service import BackupService
from app.services.search_service import SearchService
from app.services.system_service import SystemService
from app.services.vndb_service import VndbOutcome, VndbService


class EditGameDialog(QDialog):
    def __init__(self, game: GameRecord, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("编辑游戏信息")
        self.resize(650, 150)
        self._default_browse_dir = game.root_dir
        launch_parent = Path(game.launch_exe).parent
        if launch_parent.exists():
            self._default_browse_dir = str(launch_parent)

        layout = QFormLayout(self)

        self.name_input = QLineEdit(game.name)
        layout.addRow("游戏名", self.name_input)

        launch_row = QHBoxLayout()
        self.launch_input = QLineEdit(game.launch_exe)
        launch_row.addWidget(self.launch_input, 1)
        browse_btn = QPushButton("浏览")
        browse_btn.clicked.connect(self._browse_exe)
        launch_row.addWidget(browse_btn)

        launch_wrapper = QWidget()
        launch_wrapper.setLayout(launch_row)
        layout.addRow("启动路径", launch_wrapper)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse_exe(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择启动程序",
            self._default_browse_dir,
            "Executable (*.exe)",
        )
        if path:
            self.launch_input.setText(path)
            parent = str(Path(path).parent)
            self._default_browse_dir = parent

    def values(self) -> tuple[str, str]:
        return self.name_input.text().strip(), self.launch_input.text().strip()


class ScanRootsDialog(QDialog):
    def __init__(self, db: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("扫描路径管理")
        self.resize(760, 420)

        root = QVBoxLayout(self)
        self.list_widget = QListWidget()
        root.addWidget(self.list_widget, 1)

        buttons = QHBoxLayout()
        self.btn_add = QPushButton("添加路径")
        self.btn_add.clicked.connect(self._add_root)
        buttons.addWidget(self.btn_add)

        self.btn_remove = QPushButton("删除选中")
        self.btn_remove.clicked.connect(self._remove_selected)
        buttons.addWidget(self.btn_remove)

        self.btn_clear = QPushButton("清空全部")
        self.btn_clear.clicked.connect(self._clear_all)
        buttons.addWidget(self.btn_clear)
        buttons.addStretch(1)
        root.addLayout(buttons)

        close_buttons = QDialogButtonBox(QDialogButtonBox.Close)
        close_buttons.rejected.connect(self.reject)
        close_buttons.accepted.connect(self.accept)
        root.addWidget(close_buttons)

        self._refresh()

    def _refresh(self) -> None:
        self.list_widget.clear()
        for path in self.db.list_scan_roots():
            self.list_widget.addItem(path)

    def _add_root(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择游戏根目录")
        if not directory:
            return
        self.db.add_scan_root(directory)
        self._refresh()

    def _remove_selected(self) -> None:
        item = self.list_widget.currentItem()
        if item is None:
            return
        self.db.remove_scan_root(item.text())
        self._refresh()

    def _clear_all(self) -> None:
        if QMessageBox.question(self, "确认", "确定清空所有扫描路径吗？") != QMessageBox.Yes:
            return
        for path in self.db.list_scan_roots():
            self.db.remove_scan_root(path)
        self._refresh()


class PluginSettingsDialog(QDialog):
    def __init__(
        self, plugin_names: list[str], disabled_names: set[str], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("插件管理")
        self.resize(560, 380)
        self.list_widget = QListWidget()
        root = QVBoxLayout(self)
        hint = QLabel("勾选表示启用；取消勾选表示禁用。")
        root.addWidget(hint)
        root.addWidget(self.list_widget, 1)
        for name in sorted(plugin_names):
            self.list_widget.addItem(name)
            list_item = self.list_widget.item(self.list_widget.count() - 1)
            list_item.setFlags(list_item.flags() | Qt.ItemIsUserCheckable)
            list_item.setCheckState(Qt.Unchecked if name in disabled_names else Qt.Checked)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def disabled_names(self) -> list[str]:
        disabled: list[str] = []
        for idx in range(self.list_widget.count()):
            item = self.list_widget.item(idx)
            if item.checkState() != Qt.Checked:
                disabled.append(item.text())
        return disabled


class TwoLineElideLabel(QLabel):
    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._raw_text = text
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._line_height = self.fontMetrics().lineSpacing()
        self.setMinimumHeight(self._line_height * 2)
        self.setMaximumHeight(self._line_height * 2 + 4)
        self.setText(text)

    def setText(self, text: str) -> None:
        self._raw_text = text
        super().setText(self._build_two_line_elided_text())
        self.setToolTip(text)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        super().setText(self._build_two_line_elided_text())

    def _build_two_line_elided_text(self) -> str:
        text = self._raw_text.strip()
        if not text:
            return ""
        width = max(80, self.contentsRect().width() - 2)
        metrics = QFontMetrics(self.font())
        first_line = ""
        second_line = ""
        idx = 0
        for idx, ch in enumerate(text):
            trial = first_line + ch
            if metrics.horizontalAdvance(trial) > width:
                break
            first_line = trial
        else:
            return text
        remaining = text[idx:]
        for ch in remaining:
            trial = second_line + ch
            if metrics.horizontalAdvance(trial) > width:
                second_line = metrics.elidedText(second_line + ch, Qt.ElideRight, width)
                break
            second_line = trial
        if not second_line:
            second_line = metrics.elidedText(remaining, Qt.ElideRight, width)
        return f"{first_line}\n{second_line}"


class GameCardWidget(QWidget):
    def __init__(self, game: GameRecord, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        self.cover = QLabel()
        self.cover.setObjectName("gameCover")
        # Use near 2:3 portrait slot to better fit VNDB/Bangumi covers.
        self.cover.setFixedSize(168, 252)
        self.cover.setAlignment(Qt.AlignCenter)
        self._apply_cover(game.cover_path, game.image_url)
        root.addWidget(self.cover, 0, Qt.AlignHCenter)

        text_widget = QWidget()
        text_widget.setObjectName("gameTextBlock")
        text_col = QVBoxLayout()
        text_widget.setLayout(text_col)
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setContentsMargins(10, 6, 10, 10)
        text_col.setSpacing(3)
        self.title = TwoLineElideLabel(game.name)
        self.title.setObjectName("gameTitle")
        text_col.addWidget(self.title, 1)

        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.setSpacing(6)
        meta_row.addStretch(1)
        self.play_count = QLabel(f"🎮 × {game.play_count}")
        self.play_count.setObjectName("gameMeta")
        self.play_count.setAlignment(Qt.AlignRight | Qt.AlignBottom)
        source = self._cover_source_label(game.cover_path, game.image_url)
        self.cover_source = QLabel(source)
        self.cover_source.setObjectName("gameMetaSource")
        self.cover_source.setAlignment(Qt.AlignLeft | Qt.AlignBottom)
        meta_row.addWidget(self.cover_source)
        meta_row.addStretch(1)
        meta_row.addWidget(self.play_count)
        text_col.addLayout(meta_row)
        root.addWidget(text_widget, 1)

    def _apply_cover(self, cover_path: str | None, image_url: str | None = None) -> None:
        # Show a deterministic state before trying actual image loading.
        self.cover.setPixmap(self._build_placeholder_cover("加载中"))
        if cover_path:
            path = Path(cover_path)
            if path.exists():
                pix = QPixmap(str(path))
                if not pix.isNull():
                    scaled = self._scale_and_center_crop(pix, self.cover.size())
                    self.cover.setPixmap(self._with_bottom_gradient(scaled))
                    return
        # IMPORTANT: never request network images on UI thread.
        # VNDB images should be pre-cached by worker threads during import.
        # If cache is missing, keep placeholder to avoid UI freeze.
        if image_url and image_url.startswith(("http://", "https://")):
            self.cover.setPixmap(self._build_placeholder_cover("等待缓存"))
            return
        self.cover.setPixmap(self._build_placeholder_cover("NO COVER"))

    def _scale_and_center_crop(self, source: QPixmap, target_size: QSize) -> QPixmap:
        """Scale to cover target rect, then crop center region."""
        target_w = max(1, target_size.width())
        target_h = max(1, target_size.height())
        expanded = source.scaled(
            QSize(target_w, target_h),
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation,
        )
        crop_x = max(0, (expanded.width() - target_w) // 2)
        crop_y = max(0, (expanded.height() - target_h) // 2)
        return expanded.copy(crop_x, crop_y, target_w, target_h)

    def _build_placeholder_cover(self, label: str = "NO COVER") -> QPixmap:
        size = self.cover.size()
        pix = QPixmap(size)
        pix.fill(QColor("#252C36"))
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#465061"), 1))
        painter.drawRect(0, 0, size.width() - 1, size.height() - 1)
        painter.setPen(QPen(QColor("#90A0B8"), 1))
        painter.drawText(pix.rect(), Qt.AlignCenter, label)
        painter.end()
        return self._with_bottom_gradient(pix)

    def _with_bottom_gradient(self, pixmap: QPixmap) -> QPixmap:
        output = QPixmap(pixmap)
        painter = QPainter(output)
        gradient = QLinearGradient(0, 0, 0, output.height())
        gradient.setColorAt(0.0, QColor(0, 0, 0, 0))
        gradient.setColorAt(0.75, QColor(0, 0, 0, 45))
        gradient.setColorAt(1.0, QColor(0, 0, 0, 85))
        painter.fillRect(output.rect(), gradient)
        painter.end()
        return output

    def _cover_source_label(self, cover_path: str | None, image_url: str | None = None) -> str:
        if not cover_path and image_url:
            return "VNDB"
        if not cover_path:
            return "默认"
        normalized = cover_path.replace("\\", "/").lower()
        if normalized.startswith("http://") or normalized.startswith("https://"):
            return "VNDB"
        if "/covers/vndb/" in normalized:
            return "VNDB"
        if "/covers/online/" in normalized:
            return "在线"
        return "本地"


class ScanWorker(QObject):
    progress = Signal(int, int, int, str)
    finished = Signal(object, object, int, str)

    def __init__(
        self,
        roots: list[str],
        scanner: GameScanner,
        plugin_manager: PluginManager,
    ) -> None:
        super().__init__()
        self.roots = roots
        self.scanner = scanner
        self.plugin_manager = plugin_manager
        self._cancel_requested = False

    def run(self) -> None:
        try:
            imported = 0
            rows: list[tuple[str, str, str]] = []
            total_roots = len(self.roots)
            for idx, root in enumerate(self.roots, start=1):
                if self._cancel_requested:
                    self.finished.emit(self.roots, rows, imported, "__CANCELLED__")
                    return
                results = self.scanner.scan_root(root)
                results = self.plugin_manager.transform_scan_results(root=root, results=results)
                for result in results:
                    if self._cancel_requested:
                        self.finished.emit(self.roots, rows, imported, "__CANCELLED__")
                        return
                    rows.append((result.game_name, result.game_dir, result.launch_exe))
                    imported += 1
                self.progress.emit(idx, total_roots, imported, root)
            self.finished.emit(self.roots, rows, imported, "")
        except Exception as exc:  # pragma: no cover
            self.finished.emit(self.roots, [], 0, str(exc))

    def request_cancel(self) -> None:
        self._cancel_requested = True


class _VndbTaskSignals(QObject):
    finished = Signal(int, object, object)


class _VndbTask(QRunnable):
    """Single VNDB lookup unit run inside a thread pool worker."""

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
        self.signals = _VndbTaskSignals()
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
        if outcome.success and outcome.record and outcome.record.image_url:
            try:
                cached_cover = self._cover_manager.cache_vndb_image(
                    outcome.record.image_url, outcome.record.vndb_id
                )
            except Exception:
                cached_cover = None
        row: VndbImportRow | None = None
        if outcome.success and outcome.record is not None:
            rec = outcome.record
            row = VndbImportRow(
                name=rec.title or self.name,
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
    """Coordinates a 6-thread VNDB batch import.

    Runs on the Qt main thread and dispatches tasks via :class:`QThreadPool`.
    Emits Qt signals on every completed task so the UI can stream progress.
    """

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
            task = _VndbTask(
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
            # Cancelled before run.
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


_FAILURE_REASON_LABELS = {
    "timeout": "请求超时",
    "no_match": "未匹配到 VNDB 条目",
    "http_error": "HTTP 错误",
    "parse_error": "响应解析失败",
    "rate_limit": "触发 VNDB 限流",
    "network_error": "网络错误",
    "missing_requests": "缺少 requests 依赖",
}


def _humanize_failure(reason: str | None) -> str:
    if not reason:
        return "未知错误"
    return _FAILURE_REASON_LABELS.get(reason, reason)


class VndbImportResultDialog(QDialog):
    """Summary dialog shown after a VNDB batch import completes."""

    def __init__(
        self,
        total: int,
        success: int,
        cancelled: bool,
        outcomes: list[VndbOutcome],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("VNDB 批量导入结果")
        self.resize(680, 460)
        layout = QVBoxLayout(self)

        failed = total - success
        status = "已取消" if cancelled else "已完成"
        summary = QLabel(
            f"{status}：共 {total} 个，成功 {success}，失败 {failed}"
        )
        summary.setObjectName("vndbResultHeadline")
        layout.addWidget(summary)

        if failed > 0:
            tip = QLabel("失败明细：")
            layout.addWidget(tip)
            tree = QTreeWidget()
            tree.setRootIsDecorated(False)
            tree.setHeaderLabels(["游戏名", "失败原因", "详情"])
            tree.setColumnWidth(0, 240)
            tree.setColumnWidth(1, 140)
            for outcome in outcomes:
                if outcome.success:
                    continue
                item = QTreeWidgetItem(
                    [
                        outcome.query or "(空)",
                        _humanize_failure(outcome.error_kind),
                        (outcome.error_detail or "").strip()[:200],
                    ]
                )
                tree.addTopLevelItem(item)
            tree.header().setSectionResizeMode(2, QHeaderView.Stretch)
            layout.addWidget(tree, 1)
        else:
            ok_label = QLabel("全部条目均已通过 VNDB 导入。")
            ok_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(ok_label, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


class MainWindow(QMainWindow):
    COVER_FETCH_MODE_ORDER = ("local_only", "local_prefer", "online_prefer")
    COVER_FETCH_MODE_LABELS = {
        "local_only": "封面策略: 仅本地",
        "local_prefer": "封面策略: 本地优先",
        "online_prefer": "封面策略: 网图优先",
    }

    def __init__(self, data_dir: Path, plugin_manager: PluginManager | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Local Galgame Manager")
        self.resize(1100, 700)
        self.setMinimumSize(980, 620)

        self.db = Database(data_dir)
        self.current_user_id = self.db.ensure_default_user()
        self.scanner = GameScanner()
        self.launcher = GameLauncher()
        self.cover_manager = CoverManager(data_dir / "covers")
        self.vndb_service = VndbService()
        self.system_service = SystemService(data_dir)
        self.backup_service = BackupService(data_dir)
        self.search_service = SearchService()
        self.plugin_manager = plugin_manager or PluginManager(data_dir)
        self._disabled_plugins = set(self.db.get_disabled_plugins())
        self.plugin_manager.load_all(disabled_plugins=self._disabled_plugins)
        self.cover_fetch_mode = self.db.get_cover_fetch_mode()
        self.cover_manager.cover_fetch_mode = self.cover_fetch_mode

        self.games_cache: list[GameRecord] = []
        self.filtered_games: list[GameRecord] = []
        self.tray_icon: QSystemTrayIcon | None = None
        self._allow_close = False
        self._highlight_timer = QTimer(self)
        self._highlight_phase = False
        self._is_grid_view = True
        self._scan_thread: QThread | None = None
        self._scan_worker: ScanWorker | None = None
        self._scan_running = False
        self._vndb_worker: VndbImportWorker | None = None
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._render_next_batch)
        self._render_batch_size = 10
        self._render_index = 0
        self._render_total = 0

        self._build_ui()
        self._setup_tray()
        self.refresh_games()
        if self.db.list_scan_roots():
            # Avoid blocking UI during startup; user can trigger scan explicitly.
            self.status.setText("已加载扫描目录，点击“全量扫描”开始更新游戏库")

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(14)

        group_search = QWidget()
        group_search.setProperty("toolbarGroup", True)
        search_layout = QHBoxLayout(group_search)
        search_layout.setContentsMargins(10, 8, 10, 8)
        search_layout.setSpacing(8)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索游戏（中/英/日）")
        self.search_input.textChanged.connect(self._apply_filters)
        search_layout.addWidget(self.search_input, 3)

        self.favorite_only = QCheckBox("仅收藏")
        self.favorite_only.stateChanged.connect(self._apply_filters)
        search_layout.addWidget(self.favorite_only)
        toolbar.addWidget(group_search, 3)

        group_scan = QWidget()
        group_scan.setProperty("toolbarGroup", True)
        scan_layout = QHBoxLayout(group_scan)
        scan_layout.setContentsMargins(10, 8, 10, 8)
        scan_layout.setSpacing(8)
        self.btn_add_root = QPushButton("添加目录")
        self.btn_add_root.clicked.connect(self._add_scan_root)
        scan_layout.addWidget(self.btn_add_root)
        self.btn_add_root.setToolTip("选择一个游戏根目录加入扫描范围")

        self.btn_manage_roots = QPushButton("管理目录")
        self.btn_manage_roots.clicked.connect(self._manage_scan_roots)
        scan_layout.addWidget(self.btn_manage_roots)
        self.btn_manage_roots.setToolTip("查看、删除或清空已添加的扫描目录")

        self.btn_scan = QPushButton("全量扫描")
        self.btn_scan.clicked.connect(self._scan_all)
        scan_layout.addWidget(self.btn_scan)
        self.btn_scan.setToolTip("重新扫描所有已配置目录并同步游戏列表")

        self.btn_vndb_import = QPushButton("VNDB 批量导入")
        self.btn_vndb_import.clicked.connect(self._vndb_import_from_existing)
        scan_layout.addWidget(self.btn_vndb_import)
        self.btn_vndb_import.setToolTip("使用 VNDB 对当前游戏进行批量匹配与元数据导入")

        self.btn_backup = QPushButton("导出备份")
        self.btn_backup.clicked.connect(self._backup)
        scan_layout.addWidget(self.btn_backup)
        self.btn_backup.setToolTip("备份游戏列表和设置到本地文件")

        self.btn_restore = QPushButton("恢复备份")
        self.btn_restore.clicked.connect(self._restore)
        scan_layout.addWidget(self.btn_restore)
        self.btn_restore.setToolTip("从备份文件恢复游戏列表和设置")
        toolbar.addWidget(group_scan, 4)

        group_setting = QWidget()
        group_setting.setProperty("toolbarGroup", True)
        setting_layout = QHBoxLayout(group_setting)
        setting_layout.setContentsMargins(10, 8, 10, 8)
        setting_layout.setSpacing(8)
        self.btn_startup = QPushButton("OFF")
        self.btn_startup.setCheckable(True)
        self.btn_startup.clicked.connect(self._toggle_startup)
        setting_layout.addWidget(self.btn_startup)
        self.btn_startup.setToolTip("开机时自动启动本程序")

        self.user_picker = QComboBox()
        self.user_picker.currentIndexChanged.connect(self._switch_user_from_picker)
        setting_layout.addWidget(self.user_picker)
        self.user_picker.setToolTip("切换当前本地用户")

        self.btn_add_user = QPushButton("新建用户")
        self.btn_add_user.clicked.connect(self._add_user)
        setting_layout.addWidget(self.btn_add_user)
        self.btn_add_user.setToolTip("创建并切换到新的本地用户")

        self.btn_plugins = QPushButton("插件管理")
        self.btn_plugins.clicked.connect(self._open_plugin_settings)
        setting_layout.addWidget(self.btn_plugins)
        self.btn_plugins.setToolTip("启用或禁用扫描插件")

        self.btn_online_cover = QPushButton("")
        self.btn_online_cover.clicked.connect(self._toggle_online_cover)
        setting_layout.addWidget(self.btn_online_cover)
        self.btn_online_cover.setToolTip("切换封面策略：仅本地 / 本地优先 / 网图优先")
        self._apply_cover_fetch_mode_ui()

        self.btn_toggle_view = QPushButton("视图: 网格模式")
        self.btn_toggle_view.clicked.connect(self._toggle_view_mode)
        self.btn_toggle_view.setCheckable(True)
        self.btn_toggle_view.setChecked(True)
        self.btn_toggle_view.setProperty("active", True)
        setting_layout.addWidget(self.btn_toggle_view)
        self.btn_toggle_view.setToolTip("切换网格视图/列表视图")
        toolbar.addWidget(group_setting, 3)

        root.addLayout(toolbar)

        self.empty_hint = QLabel(
            "还没有游戏？点击顶部【添加扫描目录】导入你的游戏文件夹\n"
            ">> 点击上方【添加目录】开始导入 <<"
        )
        self.empty_hint.setAlignment(Qt.AlignCenter)
        root.addWidget(self.empty_hint)

        self.games_list = QListWidget()
        self.games_list.itemSelectionChanged.connect(self._show_selected)
        self.games_list.itemDoubleClicked.connect(lambda _item: self._launch_selected())
        self.games_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.games_list.customContextMenuRequested.connect(self._show_game_context_menu)
        root.addWidget(self.games_list, 1)
        self.games_list.setToolTip("右键游戏可执行启动、修正、收藏等操作")
        self.games_list.setViewMode(QListView.IconMode)
        self.games_list.setGridSize(QSize(380, 364))
        self.games_list.setWordWrap(True)
        self.games_list.setSpacing(24)
        self.games_list.setUniformItemSizes(False)

        actions = QHBoxLayout()
        self.btn_refresh = QPushButton("刷新列表")
        self.btn_refresh.clicked.connect(self.refresh_games)
        self.btn_refresh.setToolTip("重新读取数据库并刷新当前列表")
        actions.addWidget(self.btn_refresh)
        actions.addStretch(1)
        self.scan_progress = QProgressBar()
        self.scan_progress.setMinimum(0)
        self.scan_progress.setMaximum(100)
        self.scan_progress.setValue(0)
        self.scan_progress.setVisible(False)
        self.scan_progress.setFixedWidth(260)
        actions.addWidget(self.scan_progress)
        self.btn_cancel_scan = QPushButton("取消扫描")
        self.btn_cancel_scan.clicked.connect(self._cancel_scan)
        self.btn_cancel_scan.setVisible(False)
        actions.addWidget(self.btn_cancel_scan)

        root.addLayout(actions)
        self.status = QLabel("就绪")
        self.status.setAlignment(Qt.AlignLeft)
        root.addWidget(self.status)

        self._highlight_timer.setInterval(700)
        self._highlight_timer.timeout.connect(self._pulse_add_root_button)
        self._highlight_timer.start()
        self._setup_shortcuts()
        self._apply_styles()

    def _setup_tray(self) -> None:
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon())
        menu = self.tray_icon.contextMenu() or self._create_tray_menu()
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _create_tray_menu(self):
        menu = QMenu()
        open_action = QAction("打开主界面", self)
        open_action.triggered.connect(self.showNormal)
        menu.addAction(open_action)
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self._quit_from_tray)
        menu.addAction(quit_action)
        return menu

    def _quit_from_tray(self) -> None:
        self._allow_close = True
        self.close()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self.showNormal()
            self.raise_()
            self.activateWindow()

    def _add_scan_root(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择游戏根目录")
        if not directory:
            return
        self.db.add_scan_root(directory)
        self.status.setText(f"已添加扫描目录: {directory}")
        self._update_empty_state()

    def _manage_scan_roots(self) -> None:
        dialog = ScanRootsDialog(self.db, self)
        dialog.exec()
        roots_count = len(self.db.list_scan_roots())
        if roots_count == 0:
            removed = self.db.clear_all_games()
            self.refresh_games()
            self.status.setText(f"扫描目录已清空，同时清理了 {removed} 条游戏数据")
            return
        self.status.setText(f"当前扫描目录数量: {roots_count}")

    def _scan_all(self) -> None:
        if self._scan_running:
            self.status.setText("正在扫描中，请稍候...")
            return
        roots = self.db.list_scan_roots()
        if not roots:
            self.status.setText("请先添加扫描目录")
            return
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

    def _on_scan_progress(self, current_root: int, total_roots: int, imported: int, root: str) -> None:
        if total_roots <= 0:
            return
        percent = int((current_root / total_roots) * 100)
        self.scan_progress.setValue(percent)
        self.status.setText(
            f"扫描进度 {current_root}/{total_roots}，已识别 {imported} 个游戏 | 当前目录: {root}"
        )

    def _on_scan_finished(
        self,
        roots: list[str],
        rows: list[tuple[str, str, str]],
        imported: int,
        error: str,
    ) -> None:
        if error == "__CANCELLED__":
            self._scan_running = False
            self._end_scan_ui()
            self.status.setText(f"扫描已取消，已识别 {imported} 个游戏")
            return
        if error:
            self._scan_running = False
            self._end_scan_ui()
            QMessageBox.critical(self, "扫描失败", error)
            self.status.setText("扫描失败，请检查目录权限或文件状态")
            return
        if not rows:
            self._scan_running = False
            self._end_scan_ui()
            self.db.delete_games_not_in_scan(roots, set())
            self.refresh_games()
            self.status.setText("扫描完成，但未识别到可导入游戏")
            return
        valid_dirs = {row[1] for row in rows}
        self.status.setText(f"扫描完成，开始 VNDB 导入（共 {len(rows)} 项）...")
        self._start_vndb_batch_import(
            targets=rows,
            roots=roots,
            valid_dirs=valid_dirs,
        )

    def _clear_scan_worker(self) -> None:
        self._scan_worker = None
        self._scan_thread = None

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
        self.btn_cancel_scan.setEnabled(True)
        self.btn_cancel_scan.setVisible(True)
        self.scan_progress.setVisible(True)
        self.scan_progress.setValue(0)

    def _end_scan_ui(self) -> None:
        self.btn_scan.setEnabled(True)
        self.btn_vndb_import.setEnabled(True)
        self.btn_cancel_scan.setVisible(False)
        self.scan_progress.setVisible(False)

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
    ) -> None:
        self._vndb_worker = VndbImportWorker(
            targets=targets,
            vndb_service=self.vndb_service,
            cover_manager=self.cover_manager,
            max_threads=6,
            parent=self,
        )
        self._vndb_worker.progress.connect(self._on_vndb_progress)
        self._vndb_worker.finished.connect(
            lambda rows, outcomes, cancelled: self._on_vndb_finished(
                rows=rows,
                outcomes=outcomes,
                cancelled=cancelled,
                roots=roots,
                valid_dirs=valid_dirs,
                total=len(targets),
            )
        )
        self._vndb_worker.start()

    def _on_vndb_progress(
        self, processed: int, total: int, success: int, fail: int, query: str
    ) -> None:
        percent = int((processed / max(total, 1)) * 100)
        self.scan_progress.setValue(percent)
        q = f" | 当前: {query}" if query else ""
        self.status.setText(
            f"VNDB 导入进度 {processed}/{total}，成功 {success}，失败 {fail}{q}"
        )

    def _on_vndb_finished(
        self,
        rows: list[VndbImportRow],
        outcomes: list[VndbOutcome],
        cancelled: bool,
        roots: list[str] | None,
        valid_dirs: set[str] | None,
        total: int,
    ) -> None:
        self._scan_running = False
        self._vndb_worker = None
        self._end_scan_ui()
        if rows:
            self.db.upsert_games_batch(rows)
        if roots is not None and valid_dirs is not None:
            self.db.delete_games_not_in_scan(roots, valid_dirs)
        self.refresh_games()
        success = len(rows)
        self.status.setText(f"VNDB 导入完成：成功 {success} / {total}")
        dialog = VndbImportResultDialog(
            total=total,
            success=success,
            cancelled=cancelled,
            outcomes=outcomes,
            parent=self,
        )
        dialog.exec()

    def _open_plugin_settings(self) -> None:
        # Refresh plugin registry before presenting options so new files under
        # data/plugins can appear immediately.
        self.plugin_manager.load_all(disabled_plugins=self._disabled_plugins)
        dialog = PluginSettingsDialog(
            plugin_names=self.plugin_manager.available_plugin_names,
            disabled_names=self._disabled_plugins,
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        new_disabled = set(dialog.disabled_names())
        if new_disabled == self._disabled_plugins:
            return
        self._disabled_plugins = new_disabled
        self.db.set_disabled_plugins(sorted(self._disabled_plugins))
        self.plugin_manager.load_all(disabled_plugins=self._disabled_plugins)
        enabled_count = len(self.plugin_manager.plugins)
        total_count = len(self.plugin_manager.available_plugin_names)
        self.status.setText(f"插件配置已更新：启用 {enabled_count} / {total_count}")

    def _toggle_online_cover(self) -> None:
        current_index = self.COVER_FETCH_MODE_ORDER.index(self.cover_fetch_mode)
        next_mode = self.COVER_FETCH_MODE_ORDER[(current_index + 1) % len(self.COVER_FETCH_MODE_ORDER)]
        self.cover_fetch_mode = next_mode
        self.cover_manager.cover_fetch_mode = next_mode
        self.db.set_cover_fetch_mode(next_mode)
        self._apply_cover_fetch_mode_ui()
        if next_mode == "local_only":
            self.status.setText("封面策略已切换：仅本地")
        elif next_mode == "local_prefer":
            self.status.setText("封面策略已切换：本地优先（低置信度时联网）")
        else:
            self.status.setText("封面策略已切换：网图优先")

    def _apply_cover_fetch_mode_ui(self) -> None:
        label = self.COVER_FETCH_MODE_LABELS.get(self.cover_fetch_mode, "封面策略: 本地优先")
        self.btn_online_cover.setText(label)

    def refresh_games(self) -> None:
        self._refresh_startup_state()
        self._refresh_user_picker()
        self.games_cache = self.db.list_games(self.current_user_id)
        self._apply_filters()

    def _refresh_startup_state(self) -> None:
        enabled = self.system_service.is_startup_enabled()
        self.btn_startup.setChecked(enabled)
        self.btn_startup.setText("ON" if enabled else "OFF")

    def _refresh_user_picker(self) -> None:
        users = self.db.list_users()
        self.user_picker.blockSignals(True)
        self.user_picker.clear()
        for uid, name in users:
            self.user_picker.addItem(f"当前用户: {name}", uid)
        index = self.user_picker.findData(self.current_user_id)
        if index >= 0:
            self.user_picker.setCurrentIndex(index)
        self.user_picker.blockSignals(False)

    def _apply_filters(self) -> None:
        self.filtered_games = self.search_service.filter_games(
            self.games_cache,
            query=self.search_input.text(),
            only_favorite=self.favorite_only.isChecked(),
        )
        self._start_incremental_render()
        self._update_empty_state()
        self._update_action_state()

    def _start_incremental_render(self) -> None:
        if self._render_timer.isActive():
            self._render_timer.stop()
        self.games_list.clear()
        self._render_index = 0
        self._render_total = len(self.filtered_games)
        if self._render_total == 0:
            self.status.setText(f"共 0 / {len(self.games_cache)} 个游戏")
            return
        self.status.setText(f"正在渲染 0/{self._render_total} ...")
        self._render_next_batch()

    def _render_next_batch(self) -> None:
        if self._render_index >= self._render_total:
            self.status.setText(f"共 {self._render_total} / {len(self.games_cache)} 个游戏")
            return
        end = min(self._render_index + self._render_batch_size, self._render_total)
        for idx in range(self._render_index, end):
            game = self.filtered_games[idx]
            item = QListWidgetItem()
            if self._is_grid_view:
                item.setSizeHint(QSize(340, 346))
            else:
                item.setSizeHint(QSize(300, 320))
            item.setData(Qt.UserRole, game.id)
            self.games_list.addItem(item)
            self.games_list.setItemWidget(item, GameCardWidget(game))
        self._render_index = end
        if self._render_index < self._render_total:
            self.status.setText(f"正在渲染 {self._render_index}/{self._render_total} ...")
            self._render_timer.start(0)
        else:
            self.status.setText(f"共 {self._render_total} / {len(self.games_cache)} 个游戏")

    def _selected_game(self) -> GameRecord | None:
        index = self.games_list.currentRow()
        if index < 0:
            return None
        if index >= len(self.filtered_games):
            return None
        return self.filtered_games[index]

    def _show_selected(self) -> None:
        game = self._selected_game()
        if game is None:
            self._update_action_state()
            return
        self.status.setText(
            f"{game.name} | 最近游玩: {game.last_played_at or '无'} | 分类: {game.categories or '无'}"
        )
        self._update_action_state()

    def _launch_selected(self, as_admin: bool = False) -> None:
        game = self._selected_game()
        if game is None:
            return
        try:
            duration = self.launcher.launch(game.launch_exe, as_admin=as_admin)
            self.db.record_play(self.current_user_id, game.id, duration)
            self.refresh_games()
            self.status.setText(f"已退出: {game.name}，本次时长 {duration}s")
        except Exception as exc:  # pragma: no cover
            QMessageBox.critical(self, "启动失败", str(exc))

    def _toggle_favorite(self) -> None:
        game = self._selected_game()
        if game is None:
            return
        self.db.set_favorite(self.current_user_id, game.id, not game.favorite)
        self.refresh_games()

    def _fix_launch_exe(self) -> None:
        game = self._selected_game()
        if game is None:
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择启动程序", game.root_dir, "Executable (*.exe)"
        )
        if not file_path:
            return
        # Manual fix should be treated as user override and have higher priority
        # than future auto-scan results.
        self.db.update_game_identity(game.id, game.name, file_path)
        self.refresh_games()
        self.status.setText(f"已更新启动程序: {Path(file_path).name}")

    def _edit_game_identity(self) -> None:
        game = self._selected_game()
        if game is None:
            return
        dialog = EditGameDialog(game, self)
        if dialog.exec() != QDialog.Accepted:
            return
        new_name, new_launch_exe = dialog.values()
        if not new_name:
            QMessageBox.warning(self, "输入无效", "游戏名不能为空。")
            return
        if not new_launch_exe:
            QMessageBox.warning(self, "输入无效", "启动路径不能为空。")
            return
        if not Path(new_launch_exe).exists():
            QMessageBox.warning(self, "路径无效", "启动路径不存在，请重新选择。")
            return
        self.db.update_game_identity(game.id, new_name, new_launch_exe)
        self.refresh_games()
        self.status.setText("已更新游戏名称与启动路径")

    def _create_category(self) -> None:
        text, ok = QInputDialog.getText(self, "新建分类", "分类名称")
        if not ok or not text.strip():
            return
        self.db.create_category(self.current_user_id, text.strip())
        self.status.setText(f"已创建分类: {text.strip()}")

    def _assign_categories(self) -> None:
        game = self._selected_game()
        if game is None:
            return
        current = game.categories
        text, ok = QInputDialog.getText(
            self,
            "分配分类",
            "输入多个分类名（逗号分隔）",
            text=current,
        )
        if not ok:
            return
        names = [name.strip() for name in text.split(",") if name.strip()]
        category_ids = self.db.ensure_category_ids(self.current_user_id, names)
        self.db.assign_categories(game.id, category_ids)
        self.refresh_games()
        self.status.setText(f"已更新分类: {', '.join(names) if names else '无'}")

    def _set_custom_cover(self) -> None:
        game = self._selected_game()
        if game is None:
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择封面", "", "Images (*.png *.jpg *.jpeg *.webp)"
        )
        if not file_path:
            return
        try:
            cover = self.cover_manager.import_custom_cover(game.id, file_path)
            self.db.upsert_game(game.name, game.root_dir, game.launch_exe, cover)
            self.refresh_games()
        except Exception as exc:
            QMessageBox.critical(self, "封面更新失败", str(exc))

    def _create_shortcut(self) -> None:
        game = self._selected_game()
        if game is None:
            return
        shortcut = self.system_service.create_desktop_shortcut(game.name, game.launch_exe)
        self.status.setText(f"快捷方式已创建: {shortcut}")

    def _backup(self) -> None:
        archive = self.backup_service.export_backup(self.db.db_path)
        self.status.setText(f"备份完成: {archive}")

    def _restore(self) -> None:
        archive_path, _ = QFileDialog.getOpenFileName(self, "选择备份文件", "", "Zip (*.zip)")
        if not archive_path:
            return
        try:
            self.backup_service.import_backup(Path(archive_path), self.db.db_path)
            self.refresh_games()
            self.status.setText("恢复成功")
        except Exception as exc:
            QMessageBox.critical(self, "恢复失败", str(exc))

    def _toggle_startup(self) -> None:
        enabled = self.system_service.is_startup_enabled()
        try:
            self.system_service.set_startup(not enabled)
            self._refresh_startup_state()
            self.status.setText("已更新开机自启设置")
        except Exception as exc:
            QMessageBox.critical(self, "设置失败", str(exc))

    def _setup_shortcuts(self) -> None:
        launch_action = QAction(self)
        launch_action.setShortcut("Return")
        launch_action.triggered.connect(self._launch_selected)
        self.addAction(launch_action)

        refresh_action = QAction(self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self.refresh_games)
        self.addAction(refresh_action)

        edit_action = QAction(self)
        edit_action.setShortcut("Ctrl+E")
        edit_action.triggered.connect(self._edit_game_identity)
        self.addAction(edit_action)

        rename_action = QAction(self)
        rename_action.setShortcut("F2")
        rename_action.triggered.connect(self._edit_game_identity)
        self.addAction(rename_action)

        fix_action = QAction(self)
        fix_action.setShortcut("Ctrl+R")
        fix_action.triggered.connect(self._fix_launch_exe)
        self.addAction(fix_action)

        favorite_action = QAction(self)
        favorite_action.setShortcut("Ctrl+D")
        favorite_action.triggered.connect(self._toggle_favorite)
        self.addAction(favorite_action)

    def _switch_user_from_picker(self) -> None:
        user_id = self.user_picker.currentData()
        if user_id is None:
            return
        user_id = int(user_id)
        if user_id == self.current_user_id:
            return
        self.current_user_id = user_id
        self.db.switch_user(user_id)
        self.refresh_games()

    def _add_user(self) -> None:
        name, ok = QInputDialog.getText(self, "新建本地用户", "用户名")
        if not ok or not name.strip():
            return
        try:
            user_id = self.db.create_user(name.strip())
            self.current_user_id = user_id
            self.db.switch_user(user_id)
            self.refresh_games()
            self.status.setText(f"已切换用户: {name.strip()}")
        except Exception as exc:
            QMessageBox.warning(self, "创建失败", str(exc))

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._allow_close and self.tray_icon is not None and self.isVisible():
            self.hide()
            self.tray_icon.showMessage("Local Galgame Manager", "已最小化到系统托盘")
            event.ignore()
            return
        super().closeEvent(event)

    def _show_game_context_menu(self, pos) -> None:
        game = self._selected_game()
        if game is None:
            return
        menu = QMenu(self)
        menu.setToolTipsVisible(True)

        launch_group = menu.addSection("启动")
        launch_group.setEnabled(False)

        launch_action = menu.addAction("启动游戏")
        launch_action.triggered.connect(self._launch_selected)
        launch_action.setToolTip("正常权限启动当前游戏")

        admin_action = menu.addAction("管理员启动")
        admin_action.triggered.connect(lambda: self._launch_selected(as_admin=True))
        admin_action.setToolTip("以管理员权限启动当前游戏")

        menu.addSeparator()

        edit_group = menu.addSection("编辑")
        edit_group.setEnabled(False)

        edit_action = menu.addAction("编辑名称/路径")
        edit_action.triggered.connect(self._edit_game_identity)
        edit_action.setToolTip("手动修改游戏名称或启动文件路径")

        fix_action = menu.addAction("修正启动EXE")
        fix_action.triggered.connect(self._fix_launch_exe)
        fix_action.setToolTip("重新识别或手动指定游戏启动文件")

        fav_text = "取消收藏" if game.favorite else "收藏"
        fav_action = menu.addAction(fav_text)
        fav_action.triggered.connect(self._toggle_favorite)
        fav_action.setToolTip("切换当前游戏的收藏状态")

        cover_action = menu.addAction("设置封面")
        cover_action.triggered.connect(self._set_custom_cover)
        cover_action.setToolTip("为当前游戏指定本地封面图")

        menu.addSeparator()

        manage_group = menu.addSection("管理")
        manage_group.setEnabled(False)
        shortcut_action = menu.addAction("创建桌面快捷方式")
        shortcut_action.triggered.connect(self._create_shortcut)
        shortcut_action.setToolTip("在桌面创建当前游戏的快捷方式")

        assign_action = menu.addAction("分配分类")
        assign_action.triggered.connect(self._assign_categories)
        assign_action.setToolTip("将当前游戏加入一个或多个分类")

        menu.exec(self.games_list.mapToGlobal(pos))

    def _toggle_view_mode(self) -> None:
        self._is_grid_view = not self._is_grid_view
        self.btn_toggle_view.setChecked(self._is_grid_view)
        self.btn_toggle_view.setProperty("active", self._is_grid_view)
        self.btn_toggle_view.style().unpolish(self.btn_toggle_view)
        self.btn_toggle_view.style().polish(self.btn_toggle_view)
        if self._is_grid_view:
            self.games_list.setViewMode(QListView.IconMode)
            self.games_list.setGridSize(QSize(380, 364))
            self.games_list.setWordWrap(True)
            self.games_list.setSpacing(24)
            self.btn_toggle_view.setText("视图: 网格模式")
        else:
            self.games_list.setViewMode(QListView.ListMode)
            self.games_list.setGridSize(QSize())
            self.games_list.setWordWrap(False)
            self.games_list.setSpacing(10)
            self.btn_toggle_view.setText("视图: 列表模式")
        self._apply_filters()

    def _update_empty_state(self) -> None:
        has_games = self.games_list.count() > 0
        self.empty_hint.setVisible(not has_games)
        if has_games:
            self._highlight_timer.stop()
            self.btn_add_root.setProperty("highlighted", False)
            self.btn_add_root.style().unpolish(self.btn_add_root)
            self.btn_add_root.style().polish(self.btn_add_root)
        elif not self._highlight_timer.isActive():
            self._highlight_timer.start()

    def _pulse_add_root_button(self) -> None:
        if self.games_list.count() > 0:
            return
        self._highlight_phase = not self._highlight_phase
        self.btn_add_root.setProperty("highlighted", self._highlight_phase)
        self.btn_add_root.style().unpolish(self.btn_add_root)
        self.btn_add_root.style().polish(self.btn_add_root)
        self.empty_hint.setProperty("guided", self._highlight_phase)
        self.empty_hint.style().unpolish(self.empty_hint)
        self.empty_hint.style().polish(self.empty_hint)
        if self._highlight_phase:
            self.empty_hint.setText(
                "还没有游戏？点击顶部【添加扫描目录】导入你的游戏文件夹\n"
                ">> 点击上方【添加目录】开始导入 <<"
            )
        else:
            self.empty_hint.setText(
                "还没有游戏？点击顶部【添加扫描目录】导入你的游戏文件夹\n"
                "   点击上方【添加目录】开始导入   "
            )

    def _update_action_state(self) -> None:
        has_selection = self._selected_game() is not None
        # 预留 V2.0：此处可恢复更多底部批量/全局操作按钮。
        self.btn_refresh.setEnabled(True)
        if has_selection:
            self.games_list.setFocus()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QPushButton {
                color: #F2F4F7;
                background-color: #3A3F46;
                border: 1px solid #596273;
                border-radius: 8px;
                padding: 6px 12px;
            }
            QWidget[toolbarGroup="true"] {
                background-color: #232831;
                border: 1px solid #3B4250;
                border-radius: 10px;
            }
            QPushButton:disabled {
                color: #8A93A5;
                background-color: #2E3238;
                border: 1px solid #444B57;
            }
            QPushButton[highlighted="true"] {
                border: 2px solid #FFD166;
                background-color: #5A4B2F;
            }
            QPushButton[active="true"] {
                color: #F2F4F7;
                background-color: #3A3F46;
                border: 2px solid #8FB4FF;
            }
            QListWidget {
                border: 1px solid #3E4552;
                border-radius: 10px;
                padding: 6px;
            }
            QListWidget::item {
                background: #2C3138;
                border: 1px solid #3A4250;
                border-radius: 10px;
                margin: 2px;
            }
            QListWidget::item:hover {
                background: #313844;
                border: 1px solid #4E5E79;
            }
            QListWidget::item:selected {
                background: #3B4A66;
                border: 1px solid #7597CC;
            }
            QLabel {
                color: #DCE3EE;
            }
            QLabel[guided="true"] {
                color: #FFE7A8;
            }
            QLabel#gameTitle {
                color: #F3F6FB;
                font-size: 15px;
                font-weight: 600;
            }
            QLabel#gameMeta {
                color: #93A1B6;
                font-size: 10px;
            }
            QLabel#gameMetaSource {
                color: #7FA7D9;
                font-size: 10px;
            }
            QWidget#gameTextBlock {
                background: #282F39;
                border-radius: 8px;
            }
            QLabel#gameCover {
                background: transparent;
                border: none;
                border-radius: 6px;
            }
            """
        )
