from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtCore import QSize, QThread, QThreadPool, QTimer, Qt, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QAction, QCloseEvent, QIcon, QCursor, QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QStyle,
    QSystemTrayIcon,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QInputDialog,
    QListWidget,
)

from app.services.cover_manager import CoverManager
from app.core.launcher import GameLauncher
from app.core.scanner import GameScanner
from app.data.database import Database, GameRecord
from app.ui.dialogs import ScanRootsDialog
from app.ui.dialogs.game_detail_dialog import GameDetailDialog
from app.ui.paged_game_grid import PagedGameGridView
from app.ui.dialogs.play_history_window import PlayHistoryWindow
from app.ui.styles import MAIN_WINDOW_STYLESHEET
from app.plugins.manager import PluginManager
from app.services.backup_service import BackupService
from app.services.search_service import SearchService
from app.services.system_service import SystemService
from app.services.vndb_service import VndbService
from app.ui.mixins import (
    ScanMixin,
    VndbImportMixin,
    CoverMixin,
    LaunchMixin,
    GameActionMixin,
    ViewMixin,
)


class MainWindow(
    ScanMixin,
    VndbImportMixin,
    CoverMixin,
    LaunchMixin,
    GameActionMixin,
    ViewMixin,
    QMainWindow,
):
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
        self.plugin_manager.set_plugin_configs(self.db.get_plugin_configs())
        self.plugin_manager.load_all(disabled_plugins=self._disabled_plugins)
        self.cover_fetch_mode = self.db.get_cover_fetch_mode()
        self.cover_manager.cover_fetch_mode = self.cover_fetch_mode
        self.auto_backup_before_launch = self.db.get_auto_backup_before_launch()

        self.games_cache: list[GameRecord] = []
        self.filtered_games: list[GameRecord] = []
        self.tray_icon: QSystemTrayIcon | None = None
        self._allow_close = False
        self._highlight_timer = QTimer(self)
        self._highlight_phase = False
        self._is_grid_view = True
        self._scan_thread: QThread | None = None
        self._scan_worker = None
        self._scan_running = False
        self._vndb_worker = None
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._render_next_batch)
        self._render_batch_size = 10
        self._render_index = 0
        self._render_total = 0
        self._cover_retry_pool = QThreadPool(self)
        self._launch_pool = QThreadPool(self)
        self._launch_pool.setMaxThreadCount(1)
        self._cover_retry_pending: set[int] = set()
        self._launching_game_ids: set[int] = set()
        self._cover_retry_failed: set[int] = set()
        self._cover_retry_startup_running = False
        self._cover_retry_startup_total = 0
        self._cover_retry_startup_done = 0
        self._cover_retry_startup_success = 0
        self._play_history_window: PlayHistoryWindow | None = None
        self._toast_label: QLabel | None = None

        self._load_theme_preferences()
        self._build_ui()
        self._setup_tray()
        self.refresh_games()
        QTimer.singleShot(1500, self._startup_auto_fix_covers)
        if self.db.list_scan_roots():
            self.status.setText('已加载扫描目录，点击"全量扫描"开始更新游戏库')


    def _polish_toolbar_control(self, widget: QWidget) -> None:
        widget.setCursor(Qt.PointingHandCursor)

    def _toolbar_stylesheet(self) -> str:
        """Self-contained toolbar QSS (survives theme switches)."""
        return """
            QFrame#toolbarGroup {
                background: rgba(127, 167, 217, 0.07);
                border: 1px solid rgba(127, 167, 217, 0.18);
                border-radius: 10px;
            }
            QLabel#toolbarGroupLabel {
                color: #8B96AA;
                font-size: 10px;
                font-weight: 600;
                padding-left: 2px;
            }
            QWidget#mainToolbar QPushButton,
            QWidget#mainToolbar QToolButton {
                border-radius: 8px;
                padding: 6px 14px;
                font-size: 13px;
                font-weight: 600;
            }
            QWidget#mainToolbar QPushButton[btnKind="primary"],
            QWidget#mainToolbar QToolButton[btnKind="primary"] {
                color: #FFFFFF;
                background: #3D7BE0;
                border: 1px solid #4A88EE;
            }
            QWidget#mainToolbar QPushButton[btnKind="primary"]:hover,
            QWidget#mainToolbar QToolButton[btnKind="primary"]:hover {
                background: #4A88EE;
            }
            QWidget#mainToolbar QPushButton[btnKind="primary"]:pressed,
            QWidget#mainToolbar QToolButton[btnKind="primary"]:pressed {
                background: #3168C4;
            }
            QWidget#mainToolbar QPushButton[btnKind="accent"],
            QWidget#mainToolbar QToolButton[btnKind="accent"] {
                color: #DCEBFF;
                background: rgba(127, 167, 217, 0.16);
                border: 1px solid rgba(127, 167, 217, 0.45);
            }
            QWidget#mainToolbar QPushButton[btnKind="accent"]:hover,
            QWidget#mainToolbar QToolButton[btnKind="accent"]:hover {
                background: rgba(127, 167, 217, 0.30);
                border: 1px solid #7FA7D9;
            }
            QWidget#mainToolbar QPushButton[btnKind="secondary"],
            QWidget#mainToolbar QToolButton[btnKind="secondary"] {
                color: #C7D1E0;
                background: transparent;
                border: 1px solid rgba(255, 255, 255, 0.14);
            }
            QWidget#mainToolbar QPushButton[btnKind="secondary"]:hover,
            QWidget#mainToolbar QToolButton[btnKind="secondary"]:hover {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.28);
            }
            QWidget#mainToolbar QPushButton[active="true"] {
                color: #FFFFFF;
                background: #3D7BE0;
                border: 1px solid #4A88EE;
            }
            QWidget#mainToolbar QToolButton::menu-indicator {
                subcontrol-position: right center;
                right: 6px;
            }
        """

    def _style_random_button(self) -> None:
        """统一为随机按钮应用辅助色样式（无脉冲），避免色彩杂乱。"""
        if not hasattr(self, "btn_random"):
            return
        self.btn_random.setProperty("btnKind", "accent")
        self.btn_random.style().unpolish(self.btn_random)
        self.btn_random.style().polish(self.btn_random)

    def _style_history_button(self) -> None:
        """统一为历史按钮应用辅助色样式。"""
        if not hasattr(self, "btn_history"):
            return
        self.btn_history.setProperty("btnKind", "accent")
        self.btn_history.style().unpolish(self.btn_history)
        self.btn_history.style().polish(self.btn_history)

    def _setup_search_completer(self) -> None:
        history = self.db.get_search_history()
        self._search_completer = QCompleter(history, self)
        self._search_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._search_completer.setFilterMode(Qt.MatchContains)
        self._search_completer.setCompletionMode(QCompleter.PopupCompletion)
        self.search_input.setCompleter(self._search_completer)

    def _persist_search_term(self) -> None:
        term = self.search_input.text().strip()
        if not term:
            return
        history = self.db.add_search_history(term)
        model = self._search_completer.model()
        if hasattr(model, "setStringList"):
            model.setStringList(history)

    def _more_menu_icon(self, standard_pixmap: QStyle.StandardPixmap) -> QIcon:
        return self.style().standardIcon(standard_pixmap)

    def _add_more_action(
        self,
        menu: QMenu,
        text: str,
        slot,
        *,
        icon: QIcon | None = None,
        tooltip: str = "",
    ) -> QAction:
        act = QAction(text, self)
        if icon is not None:
            act.setIcon(icon)
        if tooltip:
            act.setToolTip(tooltip)
        act.triggered.connect(slot)
        menu.addAction(act)
        return act

    def _style_more_menu(self, menu: QMenu) -> None:
        menu.setStyleSheet(
            """
            QMenu {
                padding: 6px 0;
            }
            QMenu::item {
                padding: 8px 28px 8px 20px;
                border-radius: 4px;
                margin: 1px 6px;
            }
            QMenu::item:selected {
                background-color: #2D6CDF;
            }
            QMenu::separator {
                height: 1px;
                background: #3D4F63;
                margin: 6px 12px;
            }
            QMenu::icon {
                padding-left: 8px;
            }
            """
        )

    def _build_more_menu(self) -> QMenu:
        menu = QMenu(self)
        self._style_more_menu(menu)
        icon = self._more_menu_icon

        # ── 高频：目录 / 库 / 用户 / 游戏 ──
        self.act_manage_roots = self._add_more_action(
            menu,
            "管理目录…",
            self._manage_scan_roots,
            icon=icon(QStyle.StandardPixmap.SP_DirIcon),
            tooltip="查看、删除或清空已添加的扫描目录",
        )
        self._add_more_action(
            menu,
            "数据管理…",
            self._open_game_data_manager,
            icon=icon(QStyle.StandardPixmap.SP_FileDialogDetailedView),
            tooltip="查看库内游戏列表，从库中删除条目（不卸载安装目录）",
        )
        self._add_more_action(
            menu,
            "新建用户",
            self._add_user,
            icon=icon(QStyle.StandardPixmap.SP_ComputerIcon),
            tooltip="创建并切换到新的本地用户",
        )
        self._add_more_action(
            menu,
            "导出备份",
            self._backup,
            icon=icon(QStyle.StandardPixmap.SP_DialogSaveButton),
            tooltip="备份游戏库与设置到 zip",
        )
        self._add_more_action(
            menu,
            "恢复备份",
            self._restore,
            icon=icon(QStyle.StandardPixmap.SP_DialogOpenButton),
            tooltip="从备份 zip 恢复数据",
        )

        self.act_startup = QAction("开机启动: OFF", self)
        self.act_startup.setCheckable(True)
        self.act_startup.setIcon(icon(QStyle.StandardPixmap.SP_MediaPlay))
        self.act_startup.triggered.connect(self._toggle_startup)
        self.act_startup.setToolTip("点击切换：是否随 Windows 登录自动启动")
        menu.addAction(self.act_startup)

        self.act_auto_backup = QAction("启动前备份: OFF", self)
        self.act_auto_backup.setCheckable(True)
        self.act_auto_backup.setIcon(icon(QStyle.StandardPixmap.SP_DialogYesButton))
        self.act_auto_backup.triggered.connect(self._toggle_auto_backup_before_launch)
        self.act_auto_backup.setToolTip("点击切换：启动游戏前自动备份存档目录")
        menu.addAction(self.act_auto_backup)

        self._refresh_startup_state()
        self._apply_auto_backup_launch_ui()

        menu.addSeparator()

        self._add_more_action(
            menu,
            "游戏详情…",
            self._open_selected_game_detail,
            icon=icon(QStyle.StandardPixmap.SP_FileIcon),
            tooltip="完整元数据、游玩记录、文件夹与调试信息",
        )
        self._add_more_action(
            menu,
            "游玩历史…",
            self.open_play_history,
            icon=icon(QStyle.StandardPixmap.SP_FileDialogListView),
            tooltip="独立窗口：全部游玩记录、筛选、清空",
        )

        menu.addSeparator()

        # ── 工具箱（低频 / 专业工具）──
        toolbox = menu.addMenu(
            icon(QStyle.StandardPixmap.SP_FileDialogInfoView),
            "🔧 工具箱",
        )
        self._style_more_menu(toolbox)
        self._add_more_action(
            toolbox,
            "HBE 解密工具…",
            self._open_hbe_decrypt_dialog,
            tooltip="解密 Hexo Blog Encrypt 离线 HTML",
        )
        self._add_more_action(
            toolbox,
            "自动化解压工具…",
            self._open_auto_extract_dialog,
            tooltip="监控目录、解压压缩包并整理到游戏库",
        )

        extended = toolbox.addMenu("扩展工具")
        self._style_more_menu(extended)
        self._add_more_action(
            extended,
            "插件管理…",
            self._open_plugin_settings,
            icon=icon(QStyle.StandardPixmap.SP_DialogApplyButton),
            tooltip="扫描 / 启动链路上的插件钩子",
        )

        self._add_more_action(
            toolbox,
            "Locale 模拟器 (LE)…",
            self._open_locale_emulator_settings,
            tooltip="配置 LEProc.exe，用于「LE 转区启动」",
        )
        self._add_more_action(
            toolbox,
            "2DFan 线索库…",
            self._open_twodfan_library_dialog,
            tooltip="配置存档路径线索库",
        )
        self._add_more_action(
            toolbox,
            "2DFan 一键爬取…",
            self._start_twodfan_crawl,
            tooltip="从 2dfan.com 爬取存档位置线索",
        )

        # ── 设置区 ──
        self._add_more_action(
            menu,
            "⚙ 设置…",
            self._open_settings,
            icon=icon(QStyle.StandardPixmap.SP_FileDialogContentsView),
            tooltip="综合设置：启动方式、备份、封面等",
        )
        self._add_more_action(
            menu,
            "🎨 界面设置…",
            self._open_theme_settings,
            icon=icon(QStyle.StandardPixmap.SP_DesktopIcon),
            tooltip="自定义主题、字体、颜色",
        )

        return menu

    def _make_toolbar_group(self, title: str) -> tuple[QFrame, QHBoxLayout]:
        frame = QFrame()
        frame.setObjectName("toolbarGroup")
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(8, 3, 8, 4)
        outer.setSpacing(1)
        label = QLabel(title)
        label.setObjectName("toolbarGroupLabel")
        outer.addWidget(label)
        inner = QHBoxLayout()
        inner.setSpacing(6)
        inner.setContentsMargins(0, 0, 0, 0)
        outer.addLayout(inner)
        return frame, inner

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # ── 分组工具栏 ──
        toolbar_widget = QWidget()
        toolbar_widget.setObjectName("mainToolbar")
        toolbar = QHBoxLayout(toolbar_widget)
        toolbar.setSpacing(10)
        toolbar.setContentsMargins(8, 6, 8, 6)
        toolbar_widget.setStyleSheet(self._toolbar_stylesheet())

        # 搜索与筛选区
        search_frame, search_row = self._make_toolbar_group("搜索与筛选")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索游戏（中/英/日）")
        self.search_input.setFixedWidth(190)
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._apply_filters)
        self.search_input.returnPressed.connect(self._persist_search_term)
        search_row.addWidget(self.search_input)

        self.filter_combo = QComboBox()
        self.filter_combo.setToolTip("按收藏 / 游玩状态筛选")
        self.filter_combo.addItem("全部", "")
        self.filter_combo.addItem("仅收藏", "favorite")
        self.filter_combo.addItem("已游玩", "played")
        self.filter_combo.addItem("未游玩", "unplayed")
        self.filter_combo.currentIndexChanged.connect(self._apply_filters)
        search_row.addWidget(self.filter_combo)

        self.sort_combo = QComboBox()
        self.sort_combo.setToolTip("排序方式")
        self.sort_combo.addItem("默认（最近更新）", "default")
        self.sort_combo.addItem("最近添加", "added_desc")
        self.sort_combo.addItem("最早添加", "added_asc")
        self.sort_combo.addItem("最近游玩", "last_played")
        self.sort_combo.addItem("游玩次数", "play_count")
        self.sort_combo.addItem("名称", "name")
        self.sort_combo.currentIndexChanged.connect(self._apply_filters)
        search_row.addWidget(self.sort_combo)
        toolbar.addWidget(search_frame)

        self._setup_search_completer()

        # 导入管理区
        import_frame, import_row = self._make_toolbar_group("导入管理")
        self.btn_add_root = QPushButton("添加目录")
        self.btn_add_root.setProperty("btnKind", "primary")
        self.btn_add_root.clicked.connect(self._add_scan_root)
        self.btn_add_root.setToolTip("选择一个游戏根目录加入扫描范围")
        import_row.addWidget(self.btn_add_root)
        self._polish_toolbar_control(self.btn_add_root)

        self.btn_scan = QToolButton()
        self.btn_scan.setText("导入游戏")
        self.btn_scan.setProperty("btnKind", "primary")
        self.btn_scan.setPopupMode(QToolButton.InstantPopup)
        self.btn_scan.setToolTip("扫描游戏目录并导入游戏库")
        scan_menu = QMenu(self.btn_scan)
        act_full_scan = QAction("全量扫描", self)
        act_full_scan.triggered.connect(self._scan_all)
        act_full_scan.setToolTip("重新扫描所有已配置目录并同步游戏列表")
        scan_menu.addAction(act_full_scan)

        act_incremental_scan = QAction("增量扫描", self)
        act_incremental_scan.triggered.connect(self._scan_incremental)
        act_incremental_scan.setToolTip("只扫描新增游戏目录，跳过已有游戏")
        scan_menu.addAction(act_incremental_scan)

        scan_menu.addSeparator()

        act_scan_and_vndb = QAction("扫描并VNDB导入", self)
        act_scan_and_vndb.triggered.connect(self._scan_and_vndb_import)
        act_scan_and_vndb.setToolTip("先扫描目录，扫描完成后自动执行VNDB批量导入")
        scan_menu.addAction(act_scan_and_vndb)

        self.btn_scan.setMenu(scan_menu)
        import_row.addWidget(self.btn_scan)
        self._polish_toolbar_control(self.btn_scan)

        self.btn_vndb_import = QPushButton("VNDB 导入")
        self.btn_vndb_import.setProperty("btnKind", "secondary")
        self.btn_vndb_import.clicked.connect(self._vndb_import_from_existing)
        self.btn_vndb_import.setToolTip("对当前库批量匹配 VNDB / Bangumi 元数据与封面")
        import_row.addWidget(self.btn_vndb_import)
        self._polish_toolbar_control(self.btn_vndb_import)

        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.setProperty("btnKind", "secondary")
        self.btn_refresh.clicked.connect(self.refresh_games)
        self.btn_refresh.setToolTip("重新从数据库加载列表与筛选结果")
        import_row.addWidget(self.btn_refresh)
        self._polish_toolbar_control(self.btn_refresh)
        toolbar.addWidget(import_frame)

        # 视图与浏览区
        view_frame, view_row = self._make_toolbar_group("视图与浏览")
        self.btn_toggle_view = QPushButton("网格视图")
        self.btn_toggle_view.setProperty("btnKind", "secondary")
        self.btn_toggle_view.clicked.connect(self._toggle_view_mode)
        self.btn_toggle_view.setCheckable(True)
        self.btn_toggle_view.setChecked(True)
        self.btn_toggle_view.setProperty("active", True)
        self.btn_toggle_view.setToolTip("切换网格 / 列表视图")
        view_row.addWidget(self.btn_toggle_view)
        self._polish_toolbar_control(self.btn_toggle_view)

        self.btn_random = QPushButton("🎲 随机")
        self.btn_random.setProperty("btnKind", "accent")
        self.btn_random.clicked.connect(self._random_pick_game)
        self.btn_random.setToolTip("从列表中随机选择一个游戏")
        view_row.addWidget(self.btn_random)
        self._polish_toolbar_control(self.btn_random)

        self.btn_history = QPushButton("📜 历史记录")
        self.btn_history.setProperty("btnKind", "accent")
        self.btn_history.clicked.connect(self.open_play_history)
        self.btn_history.setToolTip("查看游玩历史记录")
        view_row.addWidget(self.btn_history)
        self._polish_toolbar_control(self.btn_history)

        self.btn_log = QPushButton("📋 日志")
        self.btn_log.setProperty("btnKind", "secondary")
        self.btn_log.clicked.connect(self._open_log_window)
        self.btn_log.setToolTip("查看系统日志")
        view_row.addWidget(self.btn_log)
        self._polish_toolbar_control(self.btn_log)
        toolbar.addWidget(view_frame)

        toolbar.addStretch(1)

        self.user_picker = QComboBox()
        self.user_picker.setMinimumWidth(160)
        self.user_picker.currentIndexChanged.connect(self._switch_user_from_picker)
        self.user_picker.setToolTip("切换当前本地用户")
        toolbar.addWidget(self.user_picker)

        self.btn_more = QToolButton()
        self.btn_more.setText("⚙ 更多")
        self.btn_more.setPopupMode(QToolButton.InstantPopup)
        self.btn_more.setToolTip(
            "目录与库管理、工具箱、数据备份、设置（按场景分组）"
        )
        self.btn_more.setMenu(self._build_more_menu())
        toolbar.addWidget(self.btn_more)
        self._polish_toolbar_control(self.btn_more)

        self.btn_help = QPushButton("Help")
        self.btn_help.clicked.connect(self._show_help)
        self.btn_help.setToolTip("使用帮助")
        toolbar.addWidget(self.btn_help)

        root.addWidget(toolbar_widget)

        self.empty_hint = QLabel(
            "还没有游戏？点击上方「添加目录」按钮开始导入游戏库"
        )
        self.empty_hint.setAlignment(Qt.AlignCenter)
        root.addWidget(self.empty_hint)

        self._library_stack = QStackedWidget()
        self._game_paged_grid = PagedGameGridView(self)
        self._game_paged_grid.selection_changed.connect(self._show_selected)
        self._game_paged_grid.double_clicked.connect(
            lambda gid: self.launch_game_by_id(gid, message_parent=self)
        )
        self._game_paged_grid.context_menu_requested.connect(self._open_game_context_menu_by_id)

        self.games_list = QListWidget()
        self.games_list.itemSelectionChanged.connect(self._show_selected)
        self.games_list.itemDoubleClicked.connect(lambda _item: self._launch_selected())
        self.games_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.games_list.customContextMenuRequested.connect(self._show_game_context_menu)
        self.games_list.setToolTip("右键游戏可执行启动、修正、收藏等操作")
        self.games_list.setViewMode(QListWidget.IconMode)
        self.games_list.setGridSize(QSize(380, 364))
        self.games_list.setWordWrap(True)
        self.games_list.setSpacing(24)
        self.games_list.setUniformItemSizes(False)

        self._library_stack.addWidget(self._game_paged_grid)
        self._library_stack.addWidget(self.games_list)
        root.addWidget(self._library_stack, 1)

        actions = QHBoxLayout()
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
        self.status.setObjectName("statusBar")
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

    def refresh_games(self) -> None:
        self._refresh_startup_state()
        self._refresh_user_picker()
        self.games_cache = self.db.list_games(self.current_user_id)
        self._apply_filters()

    def _refresh_startup_state(self) -> None:
        enabled = self.system_service.is_startup_enabled()
        self.act_startup.setChecked(enabled)
        self.act_startup.setText(f"开机启动: {'ON' if enabled else 'OFF'}")

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

    def open_play_history(self) -> None:
        if self._play_history_window is None:
            self._play_history_window = PlayHistoryWindow(self)
        self._play_history_window.reload()
        self._play_history_window.show()
        self._play_history_window.raise_()
        self._play_history_window.activateWindow()

    def _open_log_window(self) -> None:
        from app.ui.dialogs.log_window import LogWindow
        log_window = LogWindow.get_instance(self)
        log_window.show()
        log_window.raise_()
        log_window.activateWindow()

    def open_game_detail(self, game_id: int) -> None:
        GameDetailDialog(self, game_id).exec()

    def open_save_manager(self, game_id: int) -> None:
        from app.ui.dialogs.save_manager_window import SaveManagerWindow

        SaveManagerWindow(self, game_id).show()

    def _open_selected_game_detail(self) -> None:
        game = self._selected_game()
        if game is None:
            self.status.setText("请先选择一个游戏")
            return
        self.open_game_detail(game.id)

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

        detail_action = QAction(self)
        detail_action.setShortcut("Ctrl+I")
        detail_action.triggered.connect(self._open_selected_game_detail)
        self.addAction(detail_action)

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
        if self._play_history_window is not None:
            self._play_history_window.reload()

    def _add_user(self) -> None:
        name, ok = QInputDialog.getText(self, "新建本地用户", "用户名")
        if not ok or not name.strip():
            return
        try:
            user_id = self.db.create_user(name.strip())
            self.current_user_id = user_id
            self.db.switch_user(user_id)
            self.refresh_games()
            if self._play_history_window is not None:
                self._play_history_window.reload()
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

    def _ensure_toast(self) -> QLabel:
        if getattr(self, "_toast_label", None) is None:
            label = QLabel(self)
            label.setObjectName("appToast")
            label.setAlignment(Qt.AlignCenter)
            label.setVisible(False)
            label.setWordWrap(True)
            label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self._toast_effect = QGraphicsOpacityEffect(label)
            label.setGraphicsEffect(self._toast_effect)
            self._toast_anim = QPropertyAnimation(self._toast_effect, b"opacity", self)
            self._toast_timer = QTimer(self)
            self._toast_timer.setSingleShot(True)
            self._toast_timer.timeout.connect(self._fade_out_toast)
            self._toast_label = label
        return self._toast_label

    _TOAST_COLORS = {
        "info": ("#2D6CDF", "#FFFFFF"),
        "success": ("#1F9D63", "#FFFFFF"),
        "warning": ("#C9871A", "#FFFFFF"),
        "error": ("#C0392B", "#FFFFFF"),
    }

    def show_toast(self, message: str, level: str = "info", *, duration_ms: int = 2600) -> None:
        if not message:
            return
        label = self._ensure_toast()
        bg, fg = self._TOAST_COLORS.get(level, self._TOAST_COLORS["info"])
        label.setStyleSheet(
            f"QLabel#appToast {{ background: {bg}; color: {fg};"
            "border-radius: 10px; padding: 10px 18px; font-size: 13px;"
            "font-weight: 600; }"
        )
        label.setText(message)
        label.adjustSize()
        label.setMaximumWidth(max(360, self.width() - 80))
        label.adjustSize()
        self._position_toast()
        label.setVisible(True)
        label.raise_()
        self._toast_anim.stop()
        self._toast_anim.setDuration(180)
        self._toast_anim.setStartValue(0.0)
        self._toast_anim.setEndValue(1.0)
        self._toast_anim.start()
        self._toast_timer.start(duration_ms)

    def _fade_out_toast(self) -> None:
        label = getattr(self, "_toast_label", None)
        if label is None or not label.isVisible():
            return
        self._toast_anim.stop()
        self._toast_anim.setDuration(280)
        self._toast_anim.setStartValue(1.0)
        self._toast_anim.setEndValue(0.0)
        try:
            self._toast_anim.finished.disconnect()
        except RuntimeError:
            pass
        self._toast_anim.finished.connect(lambda: label.setVisible(False))
        self._toast_anim.start()

    def _position_toast(self) -> None:
        label = getattr(self, "_toast_label", None)
        if label is None:
            return
        x = (self.width() - label.width()) // 2
        y = self.height() - label.height() - 56
        label.move(max(8, x), max(8, y))

    def show_error(self, title: str, message: str, suggestion: str = "") -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Critical)
        box.setWindowTitle(title)
        box.setText(message)
        if suggestion:
            box.setInformativeText(f"建议：{suggestion}")
        box.setStandardButtons(QMessageBox.Ok)
        box.exec()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_toast()

    def _apply_styles(self) -> None:
        from app.ui.theme_manager import ThemeManager
        theme_manager = ThemeManager()
        self.setStyleSheet(theme_manager.get_stylesheet())
        # 重新应用特殊按钮的样式（全局样式表会覆盖）
        if hasattr(self, 'btn_random'):
            self._style_random_button()
        if hasattr(self, 'btn_history'):
            self._style_history_button()

    def _load_theme_preferences(self) -> None:
        """从数据库加载主题偏好设置"""
        from app.ui.theme_manager import ThemeManager
        
        try:
            preferences = self.db.get_ui_preferences()
            theme_manager = ThemeManager()
            theme_manager.load_from_dict(preferences)
        except Exception as e:
            print(f"Failed to load theme preferences: {e}")

    def _open_theme_settings(self) -> None:
        """打开主题设置对话框"""
        from app.ui.dialogs.theme_settings_dialog import ThemeSettingsDialog
        
        dialog = ThemeSettingsDialog(self)
        dialog.theme_changed.connect(self._apply_theme)
        dialog.exec()

    def _apply_theme(self) -> None:
        """应用主题到整个界面"""
        from app.ui.theme_manager import ThemeManager
        theme_manager = ThemeManager()

        # 获取新的样式表
        new_stylesheet = theme_manager.get_stylesheet()

        # 先清空现有样式再应用新样式，确保生效
        self.setStyleSheet("")
        self.setStyleSheet(new_stylesheet)

        # 重新应用特殊按钮的样式（全局样式表会覆盖）
        if hasattr(self, 'btn_random'):
            self._style_random_button()
        if hasattr(self, 'btn_history'):
            self._style_history_button()

        # 强制刷新
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
        
        # 刷新所有子窗口
        if hasattr(self, '_play_history_window') and self._play_history_window:
            self._play_history_window.setStyleSheet(new_stylesheet)
        if hasattr(self, '_save_manager_window') and self._save_manager_window:
            self._save_manager_window.setStyleSheet(new_stylesheet)

    def _open_settings(self) -> None:
        """打开综合设置对话框"""
        from app.ui.dialogs import SettingsDialog
        
        dialog = SettingsDialog(self.db, self)
        dialog.settings_changed.connect(self._on_settings_changed)
        dialog.exec()
    
    def _resolve_project_dir(self) -> Path:
        """Program / repository root for opening in the file manager."""
        from app.services.paths import dev_repo_root

        root = dev_repo_root()
        if root is not None:
            return root
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
        return Path(__file__).resolve().parent.parent.parent

    def _show_help(self) -> None:
        """显示使用帮助"""
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser

        from app.ui.dialogs.game_detail_dialog import reveal_in_explorer

        dialog = QDialog(self)
        dialog.setWindowTitle("使用帮助")
        dialog.setMinimumSize(560, 520)
        layout = QVBoxLayout(dialog)

        project_dir = self._resolve_project_dir()
        shortcut_row = QHBoxLayout()
        btn_open_project = QPushButton("📁 打开项目目录")
        btn_open_project.setToolTip(
            f"在资源管理器中打开程序所在目录\n{project_dir}"
        )
        btn_open_data = QPushButton("💾 打开数据目录")
        btn_open_data.setToolTip(
            f"封面、存档备份与数据库所在目录\n{self.db.base_dir}"
        )

        def _open_dir(path: Path, *, title: str) -> None:
            try:
                reveal_in_explorer(str(path), select_file=False)
            except FileNotFoundError:
                QMessageBox.warning(dialog, title, f"目录不存在：\n{path}")

        btn_open_project.clicked.connect(
            lambda: _open_dir(project_dir, title="打开项目目录")
        )
        btn_open_data.clicked.connect(
            lambda: _open_dir(self.db.base_dir, title="打开数据目录")
        )
        shortcut_row.addWidget(btn_open_project)
        shortcut_row.addWidget(btn_open_data)
        shortcut_row.addStretch()
        layout.addLayout(shortcut_row)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml("""
        <style>
            body { font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif; color: #C8D0DC; }
            h2 { color: #6A9FD8; font-size: 16px; border-bottom: 1px solid #3D4759; padding-bottom: 4px; }
            h3 { color: #8AB4E0; font-size: 13px; margin-top: 14px; }
            p, li { font-size: 12px; line-height: 1.6; }
            ul, ol { padding-left: 20px; }
            .shortcut { background: #2E3644; padding: 2px 6px; border-radius: 3px; font-family: monospace; }
            .version { color: #8AB4E0; font-size: 13px; margin-bottom: 8px; }
        </style>
        <p class="version"><b>Local Galgame Manager v2.0.11</b></p>

        <h2>快速入门</h2>
        <ol>
            <li><b>添加目录</b> — 「导入管理」→「添加目录」，选择游戏根目录</li>
            <li><b>导入游戏</b> — 「导入游戏」→「全量扫描」或「扫描并 VNDB 导入」</li>
            <li><b>启动游戏</b> — 双击卡片；右键可选 LE 转区 / 管理员启动</li>
        </ol>

        <h2>工具栏（分组）</h2>
        <h3>搜索与筛选</h3>
        <ul>
            <li><b>搜索框</b> — 中/英/日关键词；下拉可复用历史记录</li>
            <li><b>筛选</b> — 全部 / 仅收藏 / 已游玩 / 未游玩</li>
            <li><b>排序</b> — 默认、添加时间、最近游玩、游玩次数、名称等</li>
        </ul>
        <h3>导入管理</h3>
        <ul>
            <li><b>添加目录</b> — 加入扫描范围</li>
            <li><b>导入游戏</b> — 全量扫描、增量扫描、扫描并 VNDB 导入</li>
            <li><b>VNDB 导入</b> — 对现有库补全元数据与封面</li>
            <li><b>刷新</b> — 重新加载列表与筛选结果</li>
        </ul>
        <h3>视图与浏览</h3>
        <ul>
            <li><b>网格 / 列表</b> — 切换视图；底部分页显示总数与页码，可跳转</li>
            <li><b>🎲 随机</b> — 从当前列表随机选一款，支持「换一个」</li>
            <li><b>📜 历史记录</b> — 游玩历史独立窗口</li>
            <li><b>📋 日志</b> — 查看运行日志</li>
        </ul>

        <h2>「更多」菜单</h2>
        <ul>
            <li><b>管理目录 / 数据管理</b> — 扫描路径与从库删除游戏</li>
            <li><b>导出 / 恢复备份</b> — 库与设置 zip 备份</li>
            <li><b>开机启动 / 启动前备份</b> — 可点击切换 ON/OFF</li>
            <li><b>游戏详情 / 游玩历史</b> — 元数据与记录</li>
            <li><b>🔧 工具箱</b> — HBE 解密、自动化解压、插件、LE、2DFan 线索库与爬虫</li>
            <li><b>⚙ 设置 / 🎨 界面设置</b> — 启动方式、封面策略、主题等</li>
        </ul>

        <h2>工具箱（简要）</h2>
        <ul>
            <li><b>HBE 解密</b> — 离线解密 Hexo Blog Encrypt HTML（单文件 / 批量）</li>
            <li><b>自动化解压</b> — 监控目录、扫描压缩包并解压整理；支持进度与停止</li>
            <li><b>插件管理</b> — 扫描 / 启动链路上的扩展钩子</li>
        </ul>

        <h2>右键菜单</h2>
        <ul>
            <li><b>启动 / LE 转区 / 管理员启动</b></li>
            <li><b>游戏详情 / 存档管理 / 收藏</b></li>
            <li><b>编辑名称·路径 / 封面 / 分类 / 桌面快捷方式</b></li>
            <li><b>从库中删除</b> — 可选同时删除安装文件夹（二次确认）</li>
        </ul>

        <h2>快捷键</h2>
        <ul>
            <li><span class="shortcut">双击</span> 启动游戏</li>
            <li><span class="shortcut">右键</span> 上下文菜单</li>
            <li><span class="shortcut">Ctrl+F</span> 聚焦搜索框</li>
            <li><span class="shortcut">Ctrl+I</span> 打开游戏详情</li>
        </ul>

        <h2>设置说明</h2>
        <ul>
            <li><b>双击打开方式</b> — 普通 / 强制 LE / 智能（记住上次）</li>
            <li><b>封面策略</b> — 仅本地 / 本地优先 / 网图优先</li>
            <li><b>LE 路径</b> — 「更多」→「工具箱」→「Locale 模拟器 (LE)…」</li>
        </ul>

        <h2>常见问题</h2>
        <ul>
            <li><b>游戏未识别？</b> — 确认目录含 .exe，重新全量扫描</li>
            <li><b>启动 exe 不对？</b> — 右键「编辑名称/路径」</li>
            <li><b>封面不显示？</b> — 调整封面策略或右键重新获取</li>
            <li><b>解压/扫描看似卡住？</b> — 查看进度条与日志；大压缩包耗时较长属正常</li>
            <li><b>LE 转区灰色？</b> — 先在工具箱中配置 LEProc.exe</li>
        </ul>

        <p style="color: #5A6474; margin-top: 16px;">
        项目主页：<a href="https://github.com/chunyangluo/Local-Galgame-Manager" style="color: #6A9FD8;">GitHub</a>
        · 完整手册见仓库 <code>docs/USER_GUIDE.md</code>
        </p>
        """)
        layout.addWidget(browser)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok)
        btn_box.accepted.connect(dialog.accept)
        layout.addWidget(btn_box)

        dialog.exec()
    
    def _on_settings_changed(self) -> None:
        """设置改变后的回调"""
        # 刷新封面获取模式
        self.cover_fetch_mode = self.db.get_cover_fetch_mode()
        self.cover_manager.cover_fetch_mode = self.cover_fetch_mode
        self._apply_cover_fetch_mode_ui()
        
        # 刷新自动备份设置
        self.auto_backup_before_launch = self.db.get_auto_backup_before_launch()
        self._apply_auto_backup_launch_ui()
        
        # 刷新LE可用状态
        self.status.setText("设置已更新")

    def _random_pick_game(self) -> None:
        """从过滤后的游戏列表中随机选择一个游戏（完全独立的真随机）"""
        if not self.filtered_games:
            QMessageBox.information(self, "随机选择", "当前没有可选择的游戏")
            return

        import random
        selected = random.choice(self.filtered_games)

        # 在列表/网格中选中并高亮闪烁
        if self._is_grid_view:
            self._game_paged_grid.select_game_by_id(selected.id)
            # 触发卡片闪烁高亮动画
            for slot in self._game_paged_grid._slots:
                if slot.game_id == selected.id:
                    slot.start_highlight_flash(flashes=10, interval_ms=140)
                    break
        else:
            for i in range(self.games_list.count()):
                item = self.games_list.item(i)
                if item.data(Qt.UserRole) == selected.id:
                    item.setSelected(True)
                    self.games_list.scrollToItem(item)
                    # 列表视图闪烁高亮
                    self._flash_list_item(item)
                    break

        msg = f"🎲 随机选择了「{selected.name}」"
        self.status.setText(msg)

        self._highlight_random_game(selected, len(self.filtered_games) - 1)

    def _flash_list_item(self, item) -> None:
        """在列表视图中闪烁高亮指定项"""
        list_widget = self.games_list
        original_bg = list_widget.palette().color(list_widget.backgroundRole()).name()
        highlight_color = "rgba(168, 85, 247, 0.3)"  # 紫色高亮
        normal_color = "transparent"

        flash_count = [0]
        flash_max = 8

        def do_flash():
            if flash_count[0] >= flash_max:
                item.setBackground(QColor(normal_color))
                return
            if flash_count[0] % 2 == 0:
                item.setBackground(QColor(168, 85, 247, 80))
            else:
                item.setBackground(QColor(normal_color))
            flash_count[0] += 1
            QTimer.singleShot(140, do_flash)

        do_flash()

    def _highlight_random_game(self, game: GameRecord, total_count: int) -> None:
        """为随机选中的游戏创建一个醒目的弹出对话框，支持换一个功能"""
        import sys

        # 播放系统提示音
        try:
            if sys.platform == "win32":
                import winsound
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass

        try:
            dialog = QDialog(self)
            dialog.setWindowTitle("🎲 随机选择")
            dialog.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
            dialog.setFixedSize(420, 560)
            dialog.setStyleSheet(f"""
                QDialog {{
                    background: qlineargradient(
                        x1:0, y1:0, x2:1, y2:1,
                        stop:0 #1a1a2e, stop:0.5 #16213e, stop:1 #1a1a2e
                    );
                    border: 3px solid #FFD700;
                    border-radius: 16px;
                }}
            """)

            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(32, 28, 32, 28)
            layout.setSpacing(16)

            # 标题 — 带脉冲动画
            title_label = QLabel("🎉 随机选中！")
            title_label.setAlignment(Qt.AlignCenter)
            title_label.setStyleSheet("""
                QLabel {
                    color: #FFD700;
                    font-size: 26px;
                    font-weight: bold;
                }
            """)
            layout.addWidget(title_label)

            # 标题脉冲动画
            title_anim = QPropertyAnimation(title_label, b"windowOpacity")
            title_anim.setDuration(800)
            title_anim.setStartValue(1.0)
            title_anim.setEndValue(0.6)
            title_anim.setEasingCurve(QEasingCurve.InOutSine)
            title_anim.setLoopCount(-1)
            title_anim.start()

            # 封面区域
            cover_label = QLabel()
            cover_label.setFixedSize(360, 240)
            cover_label.setAlignment(Qt.AlignCenter)
            cover_label.setStyleSheet("""
                QLabel {
                    background: #2a2a4a;
                    border-radius: 12px;
                    border: 2px solid #FFD700;
                }
            """)
            layout.addWidget(cover_label, 0, Qt.AlignCenter)

            # 游戏名称
            name_label = QLabel()
            name_label.setAlignment(Qt.AlignCenter)
            name_label.setWordWrap(True)
            name_label.setStyleSheet("""
                QLabel {
                    color: #FFFFFF;
                    font-size: 22px;
                    font-weight: bold;
                    padding: 8px;
                }
            """)
            layout.addWidget(name_label)

            # 游戏信息
            info_layout = QHBoxLayout()
            info_layout.setSpacing(20)

            vndb_label = QLabel()
            vndb_label.setStyleSheet("QLabel { color: #8FA8D0; font-size: 14px; }")
            info_layout.addWidget(vndb_label)

            play_count_label = QLabel()
            play_count_label.setStyleSheet("QLabel { color: #8FA8D0; font-size: 14px; }")
            info_layout.addWidget(play_count_label)
            layout.addLayout(info_layout)

            # 游戏总数提示
            count_label = QLabel()
            count_label.setAlignment(Qt.AlignCenter)
            count_label.setStyleSheet("""
                QLabel {
                    color: #9AB8D0;
                    font-size: 14px;
                }
            """)
            layout.addWidget(count_label)

            # 操作按钮
            button_layout = QHBoxLayout()
            button_layout.setSpacing(10)

            launch_btn = QPushButton("▶ 启动游戏")
            launch_btn.setFixedHeight(44)
            launch_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #4CAF50, stop:1 #45a049);
                    color: white;
                    font-size: 14px;
                    font-weight: bold;
                    border: none;
                    border-radius: 8px;
                    padding: 10px 20px;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #5CBF60, stop:1 #55b059);
                }
                QPushButton:pressed {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #3CAF40, stop:1 #35a039);
                }
            """)
            button_layout.addWidget(launch_btn)

            shuffle_btn = QPushButton("🔀 换一个")
            shuffle_btn.setFixedHeight(44)
            shuffle_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #6C5CE7, stop:1 #A855F7);
                    color: white;
                    font-size: 14px;
                    font-weight: bold;
                    border: none;
                    border-radius: 8px;
                    padding: 10px 20px;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #7C6CF7, stop:1 #B865FF);
                }
                QPushButton:pressed {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #5B4BD6, stop:1 #9340E0);
                }
            """)
            button_layout.addWidget(shuffle_btn)

            details_btn = QPushButton("ℹ 详情")
            details_btn.setFixedHeight(44)
            details_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #607D8B, stop:1 #506D7B);
                    color: white;
                    font-size: 14px;
                    font-weight: bold;
                    border: none;
                    border-radius: 8px;
                    padding: 10px 20px;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #708D9B, stop:1 #607D8B);
                }
            """)
            button_layout.addWidget(details_btn)

            close_btn = QPushButton("关闭")
            close_btn.setFixedHeight(44)
            close_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #555555, stop:1 #444444);
                    color: white;
                    font-size: 14px;
                    font-weight: bold;
                    border: none;
                    border-radius: 8px;
                    padding: 10px 20px;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #666666, stop:1 #555555);
                }
            """)
            close_btn.clicked.connect(dialog.close)
            button_layout.addWidget(close_btn)

            layout.addLayout(button_layout)

            def update_game(new_game: GameRecord):
                """更新对话框显示的游戏信息"""
                nonlocal game
                game = new_game

                from PySide6.QtGui import QPixmap, QImage

                # 更新封面
                from PIL import Image
                from io import BytesIO
                cover_path = Path(game.cover_path) if game.cover_path else None
                if cover_path and cover_path.exists():
                    try:
                        img = Image.open(cover_path)
                        img.thumbnail((360, 240), Image.LANCZOS)
                        buf = BytesIO()
                        img.save(buf, format='PNG')
                        qimg = QImage.fromData(buf.getvalue())
                        pixmap = QPixmap.fromImage(qimg)
                        cover_label.setPixmap(pixmap)
                        cover_label.setScaledContents(True)
                    except Exception:
                        cover_label.setText("暂无封面")
                        cover_label.setPixmap(QPixmap())
                else:
                    cover_label.setText("暂无封面")
                    cover_label.setPixmap(QPixmap())

                # 更新名称
                name_label.setText(game.name)

                # 更新信息
                vndb_label.setText(f"VNDB ID: {game.vndb_id or '未关联'}")
                play_count_label.setText(f"游玩次数: {game.play_count}")

                # 更新选中状态
                if self._is_grid_view:
                    self._game_paged_grid.select_game_by_id(game.id)
                    for slot in self._game_paged_grid._slots:
                        if slot.game_id == game.id:
                            slot.start_highlight_flash(flashes=6, interval_ms=140)
                            break
                else:
                    for i in range(self.games_list.count()):
                        item = self.games_list.item(i)
                        if item.data(Qt.UserRole) == game.id:
                            item.setSelected(True)
                            self.games_list.scrollToItem(item)
                            self._flash_list_item(item)
                            break

                self.status.setText(f"🎲 随机选择了「{game.name}」")

            def on_shuffle():
                """换一个随机游戏"""
                if not self.filtered_games:
                    return
                import random
                new_game = random.choice(self.filtered_games)
                update_game(new_game)
                # 播放提示音
                try:
                    if sys.platform == "win32":
                        import winsound
                        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                except Exception:
                    pass

            def on_launch():
                """启动游戏并关闭对话框"""
                self.launch_game_by_id(game.id)
                dialog.close()

            def on_details():
                """显示游戏详情"""
                self.open_game_detail(game.id)

            launch_btn.clicked.connect(on_launch)
            shuffle_btn.clicked.connect(on_shuffle)
            details_btn.clicked.connect(on_details)

            # 初始化显示第一个游戏
            update_game(game)

            # 居中显示
            dialog.move(self.geometry().center() - dialog.rect().center())

            # 入场动画：从透明渐显
            dialog.setWindowOpacity(0.0)
            show_anim = QPropertyAnimation(dialog, b"windowOpacity")
            show_anim.setDuration(300)
            show_anim.setStartValue(0.0)
            show_anim.setEndValue(1.0)
            show_anim.setEasingCurve(QEasingCurve.InOutCubic)

            dialog.show()
            show_anim.start()

            dialog.exec()

            # 停止动画
            title_anim.stop()

            # 对话框关闭后再次在网格中选中
            if self._is_grid_view and hasattr(self, '_game_paged_grid'):
                self._game_paged_grid.select_game_by_id(game.id)

        except Exception as e:
            print(f"ERROR in _highlight_random_game: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
