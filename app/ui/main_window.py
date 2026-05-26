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

        self._load_theme_preferences()
        self._build_ui()
        self._setup_tray()
        self.refresh_games()
        QTimer.singleShot(1500, self._startup_auto_fix_covers)
        if self.db.list_scan_roots():
            self.status.setText('已加载扫描目录，点击"全量扫描"开始更新游戏库')


    def _polish_toolbar_control(self, widget: QWidget) -> None:
        widget.setCursor(Qt.PointingHandCursor)

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

        self._random_excluded_ids: set[int] = set()

        self.btn_random = QPushButton("🎲 随机")
        self.btn_random.clicked.connect(self._random_pick_game)
        self.btn_random.setToolTip("从列表中随机选择一个游戏")
        toolbar.addWidget(self.btn_random)
        self._polish_toolbar_control(self.btn_random)

        self.btn_online_cover = QPushButton("")
        self.btn_online_cover.clicked.connect(self._toggle_online_cover)
        self.btn_online_cover.setToolTip("封面策略：仅本地 / 本地优先 / 网图优先")
        self._apply_cover_fetch_mode_ui()
        toolbar.addWidget(self.btn_online_cover)
        self._polish_toolbar_control(self.btn_online_cover)

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
            <li><b>🎲随机</b> — 随机选一个游戏，再按从剩余中选</li>
            <li><b>封面策略</b> — 切换封面获取方式（仅本地/本地优先/网图优先）</li>
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
        """从过滤后的游戏列表中随机选择一个游戏"""
        if not self.filtered_games:
            QMessageBox.information(self, "随机选择", "当前没有可选择的游戏")
            return
        
        # 获取可用游戏（排除已选过的）
        available = [g for g in self.filtered_games if g.id not in self._random_excluded_ids]
        
        if not available:
            # 所有游戏都已选择过，重置排除列表
            self._random_excluded_ids.clear()
            available = list(self.filtered_games)
        
        import random
        selected = random.choice(available)
        self._random_excluded_ids.add(selected.id)
        
        # 选中文本框中的游戏并滚动到可见位置
        if self._is_grid_view:
            self._game_paged_grid.select_game_by_id(selected.id)
        else:
            for i in range(self.games_list.count()):
                item = self.games_list.item(i)
                if item.data(Qt.UserRole) == selected.id:
                    item.setSelected(True)
                    self.games_list.scrollToItem(item)
                    break
        
        # 更新状态栏
        remaining = len(available) - 1
        msg = f"🎲 随机选择了「{selected.custom_name or selected.name}」"
        if remaining > 0:
            msg += f"，还有 {remaining} 个游戏可选"
        else:
            msg += "，所有游戏已选完，点击重置"
        self.status.setText(msg)
        
        # 显示游戏信息
        QMessageBox.information(
            self,
            "随机选择",
            f"选中了：{selected.custom_name or selected.name}\n\n"
            f"剩余可选：{remaining} 个游戏\n"
            f"（再次点击从剩余游戏中选择）"
        )
