from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QPoint
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QInputDialog, QMenu, QMessageBox

from app.data.database import GameRecord
from app.services.save_archive_service import directory_has_files, sha256_file, zip_directory


class GameActionMixin:
    db: object
    current_user_id: int
    games_cache: list
    filtered_games: list
    status: object
    system_service: object
    cover_manager: object

    def _toggle_favorite(self) -> None:
        game = self._selected_game()
        if game is None:
            return
        self._toggle_favorite_for_record(game)

    def _toggle_favorite_for_record(self, game: GameRecord) -> None:
        self.db.set_favorite(self.current_user_id, game.id, not game.favorite)
        self.refresh_games()

    def _fix_launch_exe(self) -> None:
        game = self._selected_game()
        if game is None:
            return
        self._fix_launch_exe_for_record(game)

    def _fix_launch_exe_for_record(self, game: GameRecord) -> None:
        from PySide6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择启动程序", game.root_dir, "Executable (*.exe)"
        )
        if not file_path:
            return
        self.db.update_game_identity(game.id, game.name, file_path)
        self.refresh_games()
        self.status.setText(f"已更新启动程序: {Path(file_path).name}")

    def _edit_game_identity(self) -> None:
        game = self._selected_game()
        if game is None:
            return
        self.edit_game_identity_for_game_id(game.id)

    def edit_game_identity_for_game_id(self, game_id: int) -> None:
        from app.ui.dialogs import EditGameDialog

        game = self.db.get_game_by_id(self.current_user_id, game_id)
        if game is None:
            QMessageBox.warning(self, "未找到游戏", "该游戏记录不存在。")
            return
        dialog = EditGameDialog(game, self)
        if dialog.exec() != 1:
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
        self.db.update_game_identity(game_id, new_name, new_launch_exe)
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
        self._assign_categories_for_record(game)

    def _assign_categories_for_record(self, game: GameRecord) -> None:
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
        self.set_custom_cover_for_game_id(game.id)

    def _retry_selected_cover(self) -> None:
        game = self._selected_game()
        if game is None:
            return
        self._retry_cover_for_record(game)

    def _retry_cover_for_record(self, game: GameRecord) -> None:
        if self.retry_cover_for_game_id(game.id):
            self.status.setText("正在后台重新获取封面...")

    def _create_shortcut(self) -> None:
        game = self._selected_game()
        if game is None:
            return
        self._create_shortcut_for_record(game)

    def _create_shortcut_for_record(self, game: GameRecord) -> None:
        shortcut = self.system_service.create_desktop_shortcut(game.name, game.launch_exe)
        self.status.setText(f"快捷方式已创建: {shortcut}")

    def _backup(self) -> None:
        archive = self.backup_service.export_backup(self.db.db_path)
        self.status.setText(f"备份完成: {archive}")

    def _restore(self) -> None:
        from PySide6.QtWidgets import QFileDialog

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

    def _apply_auto_backup_launch_ui(self) -> None:
        enabled = bool(self.auto_backup_before_launch)
        self.act_auto_backup.setChecked(enabled)
        self.act_auto_backup.setText(
            f"启动前备份: {'ON' if enabled else 'OFF'}"
        )

    def _toggle_auto_backup_before_launch(self) -> None:
        self.auto_backup_before_launch = not self.auto_backup_before_launch
        self.db.set_auto_backup_before_launch(self.auto_backup_before_launch)
        self._apply_auto_backup_launch_ui()
        self.status.setText(
            "已开启启动前自动备份存档" if self.auto_backup_before_launch else "已关闭启动前自动备份存档"
        )

    def _auto_backup_save_before_launch(self, game: GameRecord) -> None:
        raw = (game.custom_save_root or "").strip()
        if not raw:
            return
        save_root = Path(raw)
        if not save_root.is_dir() or not directory_has_files(save_root):
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = (
            self.db.base_dir
            / "save-backups"
            / str(self.current_user_id)
            / str(game.id)
        )
        backup_dir.mkdir(parents=True, exist_ok=True)
        zip_path = backup_dir / f"{stamp}_auto_launch.zip"
        try:
            size = zip_directory(save_root, zip_path)
            checksum = sha256_file(zip_path)
            label = f"启动前自动备份 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            self.db.insert_save_backup(
                self.current_user_id,
                game.id,
                label,
                str(zip_path.resolve()),
                size,
                checksum_sha256=checksum,
            )
        except OSError as exc:
            logging.getLogger(__name__).warning(
                "auto backup before launch failed game_id=%s err=%s", game.id, exc
            )

    def _open_plugin_settings(self) -> None:
        from PySide6.QtWidgets import QDialog
        from app.ui.dialogs import PluginSettingsDialog

        self.plugin_manager.load_all(disabled_plugins=self._disabled_plugins)
        dialog = PluginSettingsDialog(
            load_info=self.plugin_manager.load_info,
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
        failed_count = sum(
            1 for i in self.plugin_manager.load_info if i.status.value == "failed"
        )
        msg = f"插件配置已更新：启用 {enabled_count} / {total_count}"
        if failed_count:
            msg += f"，{failed_count} 个加载失败"
        self.status.setText(msg)

    def _open_twodfan_library_dialog(self) -> None:
        from app.ui.twodfan_library_dialog import TwodfanLibraryDialog

        dlg = TwodfanLibraryDialog(self)
        dlg.exec()

    def _start_twodfan_crawl(self) -> None:
        from app.ui.dialogs.twodfan_crawl_dialog import TwodfanCrawlDialog
        from app.paths import default_twodfan_sqlite_path

        # Auto-configure the hints DB path if not set
        current_path = self.db.get_twodfan_hints_db_path()
        default_path = str(default_twodfan_sqlite_path())
        if not current_path or not current_path.strip():
            self.db.set_twodfan_hints_db_path(default_path)

        dlg = TwodfanCrawlDialog(
            max_pages=0,  # 0 means all pages
            save_only=True,
            parent=self,
        )
        dlg.start()
        dlg.exec()

    def _exec_game_context_menu_for_id(self, game_id: int, menu_anchor: QPoint | None = None) -> None:
        from PySide6.QtGui import QCursor, QIcon

        game = self.db.get_game_by_id(self.current_user_id, game_id)
        if game is None:
            QMessageBox.warning(
                self,
                "未找到游戏",
                f"无法加载该游戏（id={game_id}）。请点「刷新」或重新扫描库。",
            )
            return
        menu = QMenu(self)
        menu.setToolTipsVisible(True)

        # ===== 第一组：启动操作（高频）=====
        launch_action = menu.addAction("▶️ 启动游戏")
        launch_action.triggered.connect(
            lambda checked=False, gid=game.id: self.launch_game_by_id(gid, message_parent=self)
        )
        launch_action.setToolTip("正常启动游戏")

        le_action = menu.addAction("🌐 LE 转区启动")
        le_action.triggered.connect(
            lambda checked=False, gid=game.id: self.launch_game_by_id(
                gid, locale_emulator=True, message_parent=self
            )
        )
        le_usable = self.is_locale_emulator_usable()
        le_action.setEnabled(le_usable)
        if not le_usable:
            le_action.setToolTip("未配置 Locale Emulator，请在「更多」→「设置」中配置")
        else:
            le_action.setToolTip("通过 Locale Emulator 转区运行")

        admin_action = menu.addAction("🛡️ 管理员启动")
        admin_action.triggered.connect(
            lambda checked=False, gid=game.id: self.launch_game_by_id(
                gid, as_admin=True, message_parent=self
            )
        )
        admin_action.setToolTip("以管理员权限启动")

        menu.addSeparator()

        # ===== 第二组：信息管理（高频）=====
        detail_action = menu.addAction("ℹ️ 游戏详情")
        detail_action.triggered.connect(lambda checked=False, gid=game.id: self.open_game_detail(gid))
        detail_action.setToolTip("查看游戏详细信息")

        save_mgr_action = menu.addAction("💾 存档管理")
        save_mgr_action.triggered.connect(lambda checked=False, gid=game.id: self.open_save_manager(gid))
        save_mgr_action.setToolTip("管理游戏存档备份与还原")

        fav_text = "⭐ 取消收藏" if game.favorite else "☆ 收藏"
        fav_action = menu.addAction(fav_text)
        fav_action.triggered.connect(lambda checked=False, g=game: self._toggle_favorite_for_record(g))
        fav_action.setToolTip("将游戏加入/移出收藏")

        menu.addSeparator()

        # ===== 第三组：编辑信息（二级菜单）=====
        edit_submenu = menu.addMenu("✏️ 编辑信息")
        
        edit_name_action = edit_submenu.addAction("编辑名称/路径")
        edit_name_action.triggered.connect(
            lambda checked=False, gid=game.id: self.edit_game_identity_for_game_id(gid)
        )

        edit_title_action = edit_submenu.addAction("选择标题")
        edit_title_action.triggered.connect(
            lambda checked=False, gid=game.id: self.open_game_detail(gid)
        )
        edit_title_action.setToolTip("从候选标题中选择游戏名称")

        cover_action = edit_submenu.addAction("设置封面")
        cover_action.triggered.connect(
            lambda checked=False, gid=game.id: self.set_custom_cover_for_game_id(gid)
        )

        retry_cover_action = edit_submenu.addAction("重新获取封面")
        retry_cover_action.triggered.connect(
            lambda checked=False, g=game: self._retry_cover_for_record(g)
        )

        assign_action = edit_submenu.addAction("分配分类")
        assign_action.triggered.connect(
            lambda checked=False, g=game: self._assign_categories_for_record(g)
        )

        menu.addSeparator()

        # ===== 第四组：其他操作（低频）=====
        shortcut_action = menu.addAction("🔗 创建桌面快捷方式")
        shortcut_action.triggered.connect(
            lambda checked=False, g=game: self._create_shortcut_for_record(g)
        )
        shortcut_action.setToolTip("在桌面创建游戏快捷方式")

        menu.exec(menu_anchor if menu_anchor is not None else QCursor.pos())
