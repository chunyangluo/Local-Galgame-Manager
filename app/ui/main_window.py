from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QInputDialog,
    QPushButton,
    QComboBox,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from app.core.cover_manager import CoverManager
from app.core.launcher import GameLauncher
from app.core.scanner import GameScanner
from app.data.database import Database, GameRecord
from app.services.backup_service import BackupService
from app.services.search_service import SearchService
from app.services.system_service import SystemService


class EditGameDialog(QDialog):
    def __init__(self, game: GameRecord, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("编辑游戏信息")
        self.resize(650, 150)

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
        path, _ = QFileDialog.getOpenFileName(self, "选择启动程序", "", "Executable (*.exe)")
        if path:
            self.launch_input.setText(path)

    def values(self) -> tuple[str, str]:
        return self.name_input.text().strip(), self.launch_input.text().strip()


class MainWindow(QMainWindow):
    def __init__(self, data_dir: Path) -> None:
        super().__init__()
        self.setWindowTitle("Local Galgame Manager")
        self.resize(1100, 700)

        self.db = Database(data_dir)
        self.current_user_id = self.db.ensure_default_user()
        self.scanner = GameScanner()
        self.launcher = GameLauncher()
        self.cover_manager = CoverManager(data_dir / "covers")
        self.system_service = SystemService(data_dir)
        self.backup_service = BackupService(data_dir)
        self.search_service = SearchService()

        self.games_cache: list[GameRecord] = []
        self.tray_icon: QSystemTrayIcon | None = None
        self._allow_close = False

        self._build_ui()
        self._setup_tray()
        self.refresh_games()
        if self.db.list_scan_roots():
            self._scan_all()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        toolbar = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索游戏（中/英/日）")
        self.search_input.textChanged.connect(self._apply_filters)
        toolbar.addWidget(self.search_input, 3)

        self.favorite_only = QCheckBox("仅收藏")
        self.favorite_only.stateChanged.connect(self._apply_filters)
        toolbar.addWidget(self.favorite_only)

        self.btn_add_root = QPushButton("添加扫描目录")
        self.btn_add_root.clicked.connect(self._add_scan_root)
        toolbar.addWidget(self.btn_add_root)

        self.btn_scan = QPushButton("全量扫描")
        self.btn_scan.clicked.connect(self._scan_all)
        toolbar.addWidget(self.btn_scan)

        self.btn_backup = QPushButton("导出备份")
        self.btn_backup.clicked.connect(self._backup)
        toolbar.addWidget(self.btn_backup)

        self.btn_restore = QPushButton("恢复备份")
        self.btn_restore.clicked.connect(self._restore)
        toolbar.addWidget(self.btn_restore)

        self.btn_startup = QPushButton("开机自启: 关闭")
        self.btn_startup.clicked.connect(self._toggle_startup)
        toolbar.addWidget(self.btn_startup)

        self.user_picker = QComboBox()
        self.user_picker.currentIndexChanged.connect(self._switch_user_from_picker)
        toolbar.addWidget(self.user_picker)

        self.btn_add_user = QPushButton("新建用户")
        self.btn_add_user.clicked.connect(self._add_user)
        toolbar.addWidget(self.btn_add_user)

        root.addLayout(toolbar)

        self.games_list = QListWidget()
        self.games_list.itemSelectionChanged.connect(self._show_selected)
        root.addWidget(self.games_list, 1)

        actions = QHBoxLayout()
        self.btn_launch = QPushButton("启动游戏")
        self.btn_launch.clicked.connect(self._launch_selected)
        actions.addWidget(self.btn_launch)

        self.btn_admin_launch = QPushButton("管理员启动")
        self.btn_admin_launch.clicked.connect(lambda: self._launch_selected(as_admin=True))
        actions.addWidget(self.btn_admin_launch)

        self.btn_fix_launch = QPushButton("修正启动EXE")
        self.btn_fix_launch.clicked.connect(self._fix_launch_exe)
        actions.addWidget(self.btn_fix_launch)

        self.btn_edit_identity = QPushButton("编辑名称/启动路径")
        self.btn_edit_identity.clicked.connect(self._edit_game_identity)
        actions.addWidget(self.btn_edit_identity)

        self.btn_toggle_fav = QPushButton("收藏/取消收藏")
        self.btn_toggle_fav.clicked.connect(self._toggle_favorite)
        actions.addWidget(self.btn_toggle_fav)

        self.btn_category = QPushButton("新建分类")
        self.btn_category.clicked.connect(self._create_category)
        actions.addWidget(self.btn_category)

        self.btn_assign_category = QPushButton("分配分类")
        self.btn_assign_category.clicked.connect(self._assign_categories)
        actions.addWidget(self.btn_assign_category)

        self.btn_set_cover = QPushButton("设置封面")
        self.btn_set_cover.clicked.connect(self._set_custom_cover)
        actions.addWidget(self.btn_set_cover)

        self.btn_shortcut = QPushButton("创建桌面快捷方式")
        self.btn_shortcut.clicked.connect(self._create_shortcut)
        actions.addWidget(self.btn_shortcut)

        root.addLayout(actions)
        self.status = QLabel("就绪")
        self.status.setAlignment(Qt.AlignLeft)
        root.addWidget(self.status)

    def _setup_tray(self) -> None:
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon())
        menu = self.tray_icon.contextMenu() or self._create_tray_menu()
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _create_tray_menu(self):
        from PySide6.QtWidgets import QMenu

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

    def _scan_all(self) -> None:
        roots = self.db.list_scan_roots()
        imported = 0
        valid_dirs: set[str] = set()
        for root in roots:
            for result in self.scanner.scan_root(root):
                cover = self.cover_manager.find_cover(result.game_dir)
                self.db.upsert_game(result.game_name, result.game_dir, result.launch_exe, cover)
                valid_dirs.add(result.game_dir)
                imported += 1
        removed = self.db.delete_games_not_in_scan(roots, valid_dirs)
        self.refresh_games()
        self.status.setText(f"扫描完成，导入/更新 {imported} 个条目，清理 {removed} 个旧条目")

    def refresh_games(self) -> None:
        self._refresh_startup_state()
        self._refresh_user_picker()
        self.games_cache = self.db.list_games(self.current_user_id)
        self._apply_filters()

    def _refresh_startup_state(self) -> None:
        enabled = self.system_service.is_startup_enabled()
        self.btn_startup.setText(f"开机自启: {'开启' if enabled else '关闭'}")

    def _refresh_user_picker(self) -> None:
        users = self.db.list_users()
        self.user_picker.blockSignals(True)
        self.user_picker.clear()
        for uid, name in users:
            self.user_picker.addItem(name, uid)
        index = self.user_picker.findData(self.current_user_id)
        if index >= 0:
            self.user_picker.setCurrentIndex(index)
        self.user_picker.blockSignals(False)

    def _apply_filters(self) -> None:
        filtered = self.search_service.filter_games(
            self.games_cache,
            query=self.search_input.text(),
            only_favorite=self.favorite_only.isChecked(),
        )
        self.games_list.clear()
        for game in filtered:
            marker = "★ " if game.favorite else ""
            self.games_list.addItem(f"{marker}{game.name} | 启动次数: {game.play_count}")
        self.status.setText(f"共 {len(filtered)} / {len(self.games_cache)} 个游戏")

    def _selected_game(self) -> GameRecord | None:
        index = self.games_list.currentRow()
        if index < 0:
            return None
        filtered = self.search_service.filter_games(
            self.games_cache,
            query=self.search_input.text(),
            only_favorite=self.favorite_only.isChecked(),
        )
        if index >= len(filtered):
            return None
        return filtered[index]

    def _show_selected(self) -> None:
        game = self._selected_game()
        if game is None:
            return
        self.status.setText(
            f"{game.name} | 最近游玩: {game.last_played_at or '无'} | 分类: {game.categories or '无'}"
        )

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
