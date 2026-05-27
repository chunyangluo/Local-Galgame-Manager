from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QSize, QThread, QThreadPool, QTimer, Qt, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QAction, QCloseEvent, QIcon, QCursor, QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
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

        self._load_theme_preferences()
        self._build_ui()
        self._setup_tray()
        self.refresh_games()
        QTimer.singleShot(1500, self._startup_auto_fix_covers)
        if self.db.list_scan_roots():
            self.status.setText('已加载扫描目录，点击"全量扫描"开始更新游戏库')


    def _polish_toolbar_control(self, widget: QWidget) -> None:
        widget.setCursor(Qt.PointingHandCursor)

    def _style_random_button(self) -> None:
        """为随机按钮设置醒目的渐变样式和脉冲动画"""
        btn = self.btn_random

        # 渐变背景 + 突出样式
        self._random_btn_style_normal = """
            QPushButton {
                color: #FFFFFF;
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #6C5CE7, stop:0.5 #A855F7, stop:1 #EC4899
                );
                border: 2px solid #A855F7;
                border-radius: 10px;
                padding: 7px 16px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #7C6CF7, stop:0.5 #B865FF, stop:1 #FC5CA9
                );
                border: 2px solid #C084FC;
            }
            QPushButton:pressed {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #5B4BD6, stop:0.5 #9340E0, stop:1 #D63D88
                );
                border: 2px solid #9333EA;
            }
        """
        self._random_btn_style_glow = """
            QPushButton {
                color: #FFFFFF;
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #7C6CF7, stop:0.5 #B865FF, stop:1 #FC5CA9
                );
                border: 2px solid #D8B4FE;
                border-radius: 10px;
                padding: 7px 16px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #8C7CFF, stop:0.5 #C875FF, stop:1 #FF6CB9
                );
                border: 2px solid #E9D5FF;
            }
            QPushButton:pressed {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #5B4BD6, stop:0.5 #9340E0, stop:1 #D63D88
                );
                border: 2px solid #9333EA;
            }
        """
        btn.setStyleSheet(self._random_btn_style_normal)

        # 脉冲动画：定时切换 normal/glow 样式
        self._random_glow_phase = False
        self._random_glow_timer = QTimer(self)
        self._random_glow_timer.timeout.connect(self._toggle_random_glow)
        self._random_glow_timer.start(1200)

    def _toggle_random_glow(self) -> None:
        """切换随机按钮的脉冲发光状态"""
        self._random_glow_phase = not self._random_glow_phase
        if self._random_glow_phase:
            self.btn_random.setStyleSheet(self._random_btn_style_glow)
        else:
            self.btn_random.setStyleSheet(self._random_btn_style_normal)

    def _build_more_menu(self) -> QMenu:
        menu = QMenu(self)

        self.act_manage_roots = QAction("管理目录…", self)
        self.act_manage_roots.triggered.connect(self._manage_scan_roots)
        self.act_manage_roots.setToolTip("查看、删除或清空已添加的扫描目录")
        menu.addAction(self.act_manage_roots)

        act_add_user = QAction("新建用户", self)
        act_add_user.triggered.connect(self._add_user)
        act_add_user.setToolTip("创建并切换到新的本地用户")
        menu.addAction(act_add_user)

        menu.addSeparator()

        act_backup = QAction("导出备份", self)
        act_backup.triggered.connect(self._backup)
        act_backup.setToolTip("备份游戏库与设置到 zip")
        menu.addAction(act_backup)

        act_restore = QAction("恢复备份", self)
        act_restore.triggered.connect(self._restore)
        act_restore.setToolTip("从备份 zip 恢复数据")
        menu.addAction(act_restore)

        menu.addSeparator()

        act_history = QAction("游玩历史…", self)
        act_history.triggered.connect(self.open_play_history)
        act_history.setToolTip("独立窗口：全部游玩记录、筛选、清空")
        menu.addAction(act_history)

        act_game_detail = QAction("游戏详情…", self)
        act_game_detail.triggered.connect(self._open_selected_game_detail)
        act_game_detail.setToolTip("完整元数据、游玩记录、文件夹与调试信息")
        menu.addAction(act_game_detail)

        menu.addSeparator()

        act_le = QAction("Locale Emulator (LE)…", self)
        act_le.triggered.connect(self._open_locale_emulator_settings)
        act_le.setToolTip("配置 LEProc.exe，用于「LE 转区启动」")
        menu.addAction(act_le)

        act_twodfan = QAction("2DFan线索库…", self)
        act_twodfan.triggered.connect(self._open_twodfan_library_dialog)
        act_twodfan.setToolTip("配置存档路径线索库")
        menu.addAction(act_twodfan)

        act_twodfan_crawl = QAction("2DFan 一键爬取…", self)
        act_twodfan_crawl.triggered.connect(self._start_twodfan_crawl)
        act_twodfan_crawl.setToolTip("从 2dfan.com 爬取存档位置线索，自动配置线索库")
        menu.addAction(act_twodfan_crawl)

        menu.addSeparator()

        self.act_startup = QAction("开机启动", self)
        self.act_startup.setCheckable(True)
        self.act_startup.triggered.connect(self._toggle_startup)
        self.act_startup.setToolTip("是否随 Windows 登录自动启动本程序")
        menu.addAction(self.act_startup)

        self.act_auto_backup = QAction("启动前备份", self)
        self.act_auto_backup.setCheckable(True)
        self.act_auto_backup.triggered.connect(self._toggle_auto_backup_before_launch)
        self.act_auto_backup.setToolTip("启动游戏前自动备份已配置的存档目录")
        menu.addAction(self.act_auto_backup)

        self._apply_auto_backup_launch_ui()

        menu.addSeparator()

        act_settings = QAction("设置…", self)
        act_settings.triggered.connect(self._open_settings)
        act_settings.setToolTip("综合设置：启动方式、备份、封面等")
        menu.addAction(act_settings)

        act_theme = QAction("界面设置…", self)
        act_theme.triggered.connect(self._open_theme_settings)
        act_theme.setToolTip("自定义主题、字体、颜色")
        menu.addAction(act_theme)

        menu.addSeparator()

        act_plugins = QAction("插件管理…", self)
        act_plugins.triggered.connect(self._open_plugin_settings)
        act_plugins.setToolTip("启用或禁用扫描结果插件")
        menu.addAction(act_plugins)

        return menu

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # ── 单行扁平工具栏 ──
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        toolbar.setContentsMargins(8, 6, 8, 6)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索游戏（中/英/日）")
        self.search_input.setFixedWidth(200)
        self.search_input.textChanged.connect(self._apply_filters)
        toolbar.addWidget(self.search_input)

        self.favorite_only = QCheckBox("仅收藏")
        self.favorite_only.stateChanged.connect(self._apply_filters)
        toolbar.addWidget(self.favorite_only)

        toolbar.addSpacing(8)

        self.btn_add_root = QPushButton("添加目录")
        self.btn_add_root.clicked.connect(self._add_scan_root)
        self.btn_add_root.setToolTip("选择一个游戏根目录加入扫描范围")
        toolbar.addWidget(self.btn_add_root)
        self._polish_toolbar_control(self.btn_add_root)

        self.btn_scan = QToolButton()
        self.btn_scan.setText("导入游戏")
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
        self.btn_scan.setMenu(scan_menu)
        toolbar.addWidget(self.btn_scan)
        self._polish_toolbar_control(self.btn_scan)

        self.btn_vndb_import = QPushButton("VNDB 导入")
        self.btn_vndb_import.clicked.connect(self._vndb_import_from_existing)
        self.btn_vndb_import.setToolTip("对当前库批量匹配 VNDB / Bangumi 元数据与封面")
        toolbar.addWidget(self.btn_vndb_import)
        self._polish_toolbar_control(self.btn_vndb_import)

        toolbar.addSpacing(8)

        self.btn_toggle_view = QPushButton("网格视图")
        self.btn_toggle_view.clicked.connect(self._toggle_view_mode)
        self.btn_toggle_view.setCheckable(True)
        self.btn_toggle_view.setChecked(True)
        self.btn_toggle_view.setProperty("active", True)
        self.btn_toggle_view.setToolTip("切换网格 / 列表视图")
        toolbar.addWidget(self.btn_toggle_view)
        self._polish_toolbar_control(self.btn_toggle_view)

        self.btn_random = QPushButton("🎲 随机")
        self.btn_random.clicked.connect(self._random_pick_game)
        self.btn_random.setToolTip("从列表中随机选择一个游戏")
        toolbar.addWidget(self.btn_random)
        self._polish_toolbar_control(self.btn_random)
        self._style_random_button()

        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.clicked.connect(self.refresh_games)
        self.btn_refresh.setToolTip("重新从数据库加载列表与筛选结果")
        toolbar.addWidget(self.btn_refresh)
        self._polish_toolbar_control(self.btn_refresh)

        toolbar.addStretch(1)

        self.user_picker = QComboBox()
        self.user_picker.setMinimumWidth(160)
        self.user_picker.currentIndexChanged.connect(self._switch_user_from_picker)
        self.user_picker.setToolTip("切换当前本地用户")
        toolbar.addWidget(self.user_picker)

        self.btn_more = QToolButton()
        self.btn_more.setText("⚙ 设置")
        self.btn_more.setPopupMode(QToolButton.InstantPopup)
        self.btn_more.setToolTip("设置与更多功能")
        self.btn_more.setMenu(self._build_more_menu())
        toolbar.addWidget(self.btn_more)
        self._polish_toolbar_control(self.btn_more)

        self.btn_help = QPushButton("Help")
        self.btn_help.clicked.connect(self._show_help)
        self.btn_help.setToolTip("使用帮助")
        toolbar.addWidget(self.btn_help)

        root.addLayout(toolbar)

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
        from app.ui.theme_manager import ThemeManager
        theme_manager = ThemeManager()
        self.setStyleSheet(theme_manager.get_stylesheet())
        # 重新应用随机按钮的特殊样式（全局样式表会覆盖）
        if hasattr(self, 'btn_random'):
            self._style_random_button()

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

        # 重新应用随机按钮的特殊样式（全局样式表会覆盖）
        if hasattr(self, 'btn_random'):
            self._style_random_button()

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
    
    def _show_help(self) -> None:
        """显示使用帮助"""
        from PySide6.QtWidgets import QDialog, QTextBrowser, QDialogButtonBox
        
        dialog = QDialog(self)
        dialog.setWindowTitle("使用帮助")
        dialog.setMinimumSize(520, 480)
        layout = QVBoxLayout(dialog)
        
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml("""
        <style>
            body { font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif; color: #C8D0DC; }
            h2 { color: #6A9FD8; font-size: 16px; border-bottom: 1px solid #3D4759; padding-bottom: 4px; }
            h3 { color: #8AB4E0; font-size: 13px; }
            p, li { font-size: 12px; line-height: 1.6; }
            ul { padding-left: 20px; }
            .shortcut { background: #2E3644; padding: 2px 6px; border-radius: 3px; font-family: monospace; }
        </style>
        <h2>快速入门</h2>
        <ol>
            <li><b>添加目录</b> — 点击「添加目录」，选择你的游戏根目录</li>
            <li><b>导入游戏</b> — 点击「导入游戏」→「全量扫描」，自动识别目录下的游戏</li>
            <li><b>启动游戏</b> — 双击游戏卡片即可启动</li>
        </ol>
        
        <h2>工具栏功能</h2>
        <ul>
            <li><b>搜索框</b> — 输入关键词实时筛选游戏</li>
            <li><b>仅收藏</b> — 只显示已收藏的游戏</li>
            <li><b>添加目录</b> — 添加新的游戏扫描目录</li>
            <li><b>导入游戏</b> — 全量扫描或增量扫描新游戏</li>
            <li><b>VNDB导入</b> — 从VNDB/Bangumi批量获取封面和元数据</li>
            <li><b>网格/列表视图</b> — 切换显示模式</li>
            <li><b>🎲随机</b> — 随机选一个游戏，支持换一个重新随机</li>
        </ul>
        
        <h2>右键菜单</h2>
        <ul>
            <li><b>启动游戏</b> — 正常启动</li>
            <li><b>LE转区启动</b> — 通过Locale Emulator转区运行（需先配置LE路径）</li>
            <li><b>管理员启动</b> — 以管理员权限运行</li>
            <li><b>游戏详情</b> — 查看完整信息和游玩记录</li>
            <li><b>存档管理</b> — 备份/还原存档</li>
            <li><b>收藏</b> — 收藏/取消收藏</li>
            <li><b>编辑名称/路径</b> — 修改游戏名称或启动exe路径</li>
            <li><b>封面 → 设置封面</b> — 手动选择本地图片作为封面</li>
            <li><b>封面 → 重新获取封面</b> — 从VNDB重新下载封面</li>
            <li><b>创建桌面快捷方式</b> — 在桌面生成快捷方式</li>
            <li><b>分配分类</b> — 将游戏归入自定义分类</li>
        </ul>
        
        <h2>快捷键</h2>
        <ul>
            <li><span class="shortcut">双击</span> 启动游戏</li>
            <li><span class="shortcut">右键</span> 打开上下文菜单</li>
            <li><span class="shortcut">Ctrl+F</span> 聚焦搜索框</li>
            <li><span class="shortcut">Ctrl+I</span> 打开游戏详情</li>
        </ul>
        
        <h2>设置说明</h2>
        <ul>
            <li><b>双击打开方式</b> — 可选「普通启动」「强制LE转区」「智能模式（记住上次）」</li>
            <li><b>封面策略</b> — 「仅本地」只使用本地图片；「本地优先」优先本地；「网图优先」优先VNDB</li>
            <li><b>LE路径</b> — 在「更多」→「设置」中配置LEProc.exe路径</li>
        </ul>
        
        <h2>常见问题</h2>
        <ul>
            <li><b>游戏没有被识别？</b> — 确保目录下有.exe文件，尝试重新扫描</li>
            <li><b>启动exe不对？</b> — 右键→「编辑名称/路径」修改启动路径</li>
            <li><b>封面不显示？</b> — 切换封面策略为「本地优先」或右键→「封面」→「重新获取」</li>
            <li><b>LE转区启动灰色？</b> — 需先在设置中配置LEProc.exe路径</li>
        </ul>
        
        <p style="color: #5A6474; margin-top: 16px;">
        项目主页：<a href="https://github.com/chunyangluo/Local-Galgame-Manager" style="color: #6A9FD8;">GitHub</a>
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
