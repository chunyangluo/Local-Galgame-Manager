from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QSize, QThread, QThreadPool, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QInputDialog,
    QListWidget,
)

from app.core.cover_manager import CoverManager
from app.core.launcher import GameLauncher
from app.core.scanner import GameScanner
from app.data.database import Database, GameRecord
from app.ui.dialogs import ScanRootsDialog
from app.ui.game_detail_dialog import GameDetailDialog
from app.ui.paged_game_grid import PagedGameGridView
from app.ui.play_history_window import PlayHistoryWindow
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
        self._cover_retry_failed: set[int] = set()
        self._cover_retry_startup_running = False
        self._cover_retry_startup_total = 0
        self._cover_retry_startup_done = 0
        self._cover_retry_startup_success = 0
        self._play_history_window: PlayHistoryWindow | None = None

        self._build_ui()
        self._setup_tray()
        self.refresh_games()
        QTimer.singleShot(1500, self._startup_auto_fix_covers)
        if self.db.list_scan_roots():
            self.status.setText('已加载扫描目录，点击"全量扫描"开始更新游戏库')

    def _make_toolbar_group(self, title: str, *, tier: str = "primary") -> tuple[QWidget, QHBoxLayout]:
        wrapper = QWidget()
        wrapper.setProperty("toolbarGroup", True)
        wrapper.setProperty("toolbarTier", tier)
        outer = QHBoxLayout(wrapper)
        outer.setContentsMargins(10, 8, 12, 8)
        outer.setSpacing(10)
        title_lbl = QLabel(title)
        title_lbl.setObjectName("toolbarSectionLabel")
        inner = QHBoxLayout()
        inner.setSpacing(8)
        outer.addWidget(title_lbl, 0, Qt.AlignVCenter)
        outer.addLayout(inner, 1)
        return wrapper, inner

    def _polish_toolbar_control(self, widget: QWidget) -> None:
        widget.setCursor(Qt.PointingHandCursor)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        row_primary = QHBoxLayout()
        row_primary.setSpacing(12)

        wrap_find, lay_find = self._make_toolbar_group("找游戏", tier="primary")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索游戏（中/英/日）")
        self.search_input.textChanged.connect(self._apply_filters)
        lay_find.addWidget(self.search_input, 1)
        self.favorite_only = QCheckBox("仅收藏")
        self.favorite_only.stateChanged.connect(self._apply_filters)
        lay_find.addWidget(self.favorite_only)
        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.clicked.connect(self.refresh_games)
        self.btn_refresh.setToolTip("重新从数据库加载列表与筛选结果")
        lay_find.addWidget(self.btn_refresh)
        self._polish_toolbar_control(self.btn_refresh)
        row_primary.addWidget(wrap_find, 3)

        wrap_lib, lay_lib = self._make_toolbar_group("库", tier="primary")
        self.btn_add_root = QPushButton("添加目录")
        self.btn_add_root.clicked.connect(self._add_scan_root)
        self.btn_add_root.setToolTip("选择一个游戏根目录加入扫描范围")
        lay_lib.addWidget(self.btn_add_root)

        self.btn_manage_roots = QPushButton("管理目录")
        self.btn_manage_roots.clicked.connect(self._manage_scan_roots)
        self.btn_manage_roots.setToolTip("查看、删除或清空已添加的扫描目录")
        lay_lib.addWidget(self.btn_manage_roots)

        self.btn_scan = QPushButton("全量扫描")
        self.btn_scan.clicked.connect(self._scan_all)
        self.btn_scan.setToolTip("重新扫描所有已配置目录并同步游戏列表")
        lay_lib.addWidget(self.btn_scan)

        self.btn_vndb_import = QPushButton("VNDB 导入")
        self.btn_vndb_import.clicked.connect(self._vndb_import_from_existing)
        self.btn_vndb_import.setToolTip("对当前库批量匹配 VNDB / Bangumi 元数据与封面")
        lay_lib.addWidget(self.btn_vndb_import)
        for w in (self.btn_add_root, self.btn_manage_roots, self.btn_scan, self.btn_vndb_import):
            self._polish_toolbar_control(w)
        row_primary.addWidget(wrap_lib, 4)
        root.addLayout(row_primary)

        row_secondary = QHBoxLayout()
        row_secondary.setSpacing(12)

        wrap_acct, lay_acct = self._make_toolbar_group("账户", tier="secondary")
        self.user_picker = QComboBox()
        self.user_picker.setMinimumWidth(160)
        self.user_picker.currentIndexChanged.connect(self._switch_user_from_picker)
        self.user_picker.setToolTip("切换当前本地用户")
        lay_acct.addWidget(self.user_picker, 1)
        self.btn_add_user = QPushButton("新建用户")
        self.btn_add_user.clicked.connect(self._add_user)
        self.btn_add_user.setToolTip("创建并切换到新的本地用户")
        lay_acct.addWidget(self.btn_add_user)
        self._polish_toolbar_control(self.btn_add_user)
        row_secondary.addWidget(wrap_acct, 2)

        wrap_disp, lay_disp = self._make_toolbar_group("显示", tier="secondary")
        self.btn_toggle_view = QPushButton("网格视图")
        self.btn_toggle_view.clicked.connect(self._toggle_view_mode)
        self.btn_toggle_view.setCheckable(True)
        self.btn_toggle_view.setChecked(True)
        self.btn_toggle_view.setProperty("active", True)
        self.btn_toggle_view.setToolTip("切换网格 / 列表视图")
        lay_disp.addWidget(self.btn_toggle_view)

        self.btn_online_cover = QPushButton("")
        self.btn_online_cover.clicked.connect(self._toggle_online_cover)
        self.btn_online_cover.setToolTip("封面策略：仅本地 / 本地优先 / 网图优先")
        self._apply_cover_fetch_mode_ui()
        lay_disp.addWidget(self.btn_online_cover)
        self._polish_toolbar_control(self.btn_toggle_view)
        self._polish_toolbar_control(self.btn_online_cover)
        self.btn_game_detail = QPushButton("游戏详情")
        self.btn_game_detail.clicked.connect(self._open_selected_game_detail)
        self.btn_game_detail.setToolTip("完整元数据、游玩记录、文件夹与调试信息（Ctrl+I）")
        lay_disp.addWidget(self.btn_game_detail)
        self._polish_toolbar_control(self.btn_game_detail)
        self.btn_play_history = QPushButton("游玩历史")
        self.btn_play_history.clicked.connect(self.open_play_history)
        self.btn_play_history.setToolTip("按时间查看全部游玩记录，支持筛选与批量删除")
        lay_disp.addWidget(self.btn_play_history)
        self._polish_toolbar_control(self.btn_play_history)
        row_secondary.addWidget(wrap_disp, 0)

        wrap_sys, lay_sys = self._make_toolbar_group("系统", tier="secondary")
        self.btn_startup = QPushButton("开机启动: OFF")
        self.btn_startup.setCheckable(True)
        self.btn_startup.clicked.connect(self._toggle_startup)
        self.btn_startup.setToolTip("是否随 Windows 登录自动启动本程序")
        lay_sys.addWidget(self.btn_startup)
        self._polish_toolbar_control(self.btn_startup)
        self.btn_auto_backup_launch = QPushButton("")
        self.btn_auto_backup_launch.setCheckable(True)
        self.btn_auto_backup_launch.clicked.connect(self._toggle_auto_backup_before_launch)
        self.btn_auto_backup_launch.setToolTip("启动游戏前自动备份已配置的存档目录")
        lay_sys.addWidget(self.btn_auto_backup_launch)
        self._polish_toolbar_control(self.btn_auto_backup_launch)
        self._apply_auto_backup_launch_ui()

        self.btn_more = QToolButton()
        self.btn_more.setText("更多")
        self.btn_more.setPopupMode(QToolButton.InstantPopup)
        self.btn_more.setToolTip("备份、恢复、插件、Locale Emulator、2DFan 线索库等不常用功能")
        self._polish_toolbar_control(self.btn_more)
        more_menu = QMenu(self.btn_more)
        act_backup = QAction("导出备份", self)
        act_backup.triggered.connect(self._backup)
        act_backup.setToolTip("备份游戏库与设置到 zip")
        more_menu.addAction(act_backup)
        act_restore = QAction("恢复备份", self)
        act_restore.triggered.connect(self._restore)
        act_restore.setToolTip("从备份 zip 恢复数据")
        more_menu.addAction(act_restore)
        more_menu.addSeparator()
        act_plugins = QAction("插件管理…", self)
        act_plugins.triggered.connect(self._open_plugin_settings)
        act_plugins.setToolTip("启用或禁用扫描结果插件")
        more_menu.addAction(act_plugins)
        more_menu.addSeparator()
        act_history = QAction("游玩历史…", self)
        act_history.triggered.connect(self.open_play_history)
        act_history.setToolTip("独立窗口：全部游玩记录、筛选、清空")
        more_menu.addAction(act_history)
        more_menu.addSeparator()
        act_le = QAction("Locale Emulator (LE)…", self)
        act_le.triggered.connect(self._open_locale_emulator_settings)
        act_le.setToolTip("配置 LEProc.exe，用于「LE 转区启动」Galgame")
        more_menu.addAction(act_le)
        more_menu.addSeparator()
        act_twodfan = QAction("2DFan 线索库与爬虫…", self)
        act_twodfan.triggered.connect(self._open_twodfan_library_dialog)
        act_twodfan.setToolTip(
            "配置本仓库 tools/2dfan-save-crawler 生成的 SQLite；存档管理「自动发现」会合并其中的路径线索"
        )
        more_menu.addAction(act_twodfan)
        self.btn_more.setMenu(more_menu)
        lay_sys.addWidget(self.btn_more)
        row_secondary.addWidget(wrap_sys, 0)
        row_secondary.addStretch(1)
        root.addLayout(row_secondary)

        self.empty_hint = QLabel(
            "还没有游戏？在第一行「库」分组中点击【添加目录】导入游戏文件夹\n"
            ">> 点击【添加目录】开始导入 <<"
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
        self.btn_startup.setChecked(enabled)
        self.btn_startup.setText(f"开机启动: {'ON' if enabled else 'OFF'}")

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

    def open_game_detail(self, game_id: int) -> None:
        GameDetailDialog(self, game_id).exec()

    def open_save_manager(self, game_id: int) -> None:
        from app.ui.save_manager_window import SaveManagerWindow

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

    def _apply_styles(self) -> None:
        self.setStyleSheet(MAIN_WINDOW_STYLESHEET)
