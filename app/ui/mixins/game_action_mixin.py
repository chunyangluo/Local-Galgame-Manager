from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QPoint, Qt
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

    def _toggle_hidden(self) -> None:
        game = self._selected_game()
        if game is None:
            return
        self._toggle_hidden_for_record(game)

    def _toggle_hidden_for_record(self, game: GameRecord) -> None:
        new_hidden = not game.hidden
        self.db.set_hidden(self.current_user_id, game.id, new_hidden)
        self.refresh_games()
        if new_hidden:
            self.status.setText(f"已隐藏: {game.name}")
        else:
            self.status.setText(f"已取消隐藏: {game.name}")

    def _apply_show_hidden_games_ui(self) -> None:
        show = bool(self.show_hidden_games)
        self.act_show_hidden.setChecked(show)
        tag = "ON" if show else "OFF"
        self.act_show_hidden.setText(f"👁 显示隐藏游戏: {tag}")
        self.act_show_hidden.setToolTip(
            f"当前: {'已显示' if show else '已隐藏'} — 点击切换"
        )

    def _toggle_show_hidden_games(self) -> None:
        self.show_hidden_games = not self.show_hidden_games
        self._apply_show_hidden_games_ui()
        self._apply_filters()
        self.status.setText(
            "已显示隐藏游戏" if self.show_hidden_games else "已隐藏列表中的隐藏游戏"
        )

    def _fix_launch_exe(self) -> None:
        game = self._selected_game()
        if game is None:
            return
        self._fix_launch_exe_for_record(game)

    def _fix_launch_exe_for_record(self, game: GameRecord) -> None:
        from PySide6.QtWidgets import QFileDialog

        is_video = getattr(game, "content_type", "game") == "video"
        title = "选择视频文件" if is_video else "选择启动程序"
        file_filter = (
            "Videos (*.mp4 *.mkv *.avi *.wmv *.flv *.mov *.webm *.m4v *.ts *.m2ts);;All (*.*)"
            if is_video
            else "Executable (*.exe)"
        )
        file_path, _ = QFileDialog.getOpenFileName(
            self, title, game.root_dir, file_filter
        )
        if not file_path:
            return
        self.db.update_game_identity(game.id, game.name, file_path)
        self.refresh_games()
        self.status.setText(f"已更新{'视频文件' if is_video else '启动程序'}: {Path(file_path).name}")

    def _edit_game_identity(self) -> None:
        game = self._selected_game()
        if game is None:
            return
        self.edit_game_identity_for_game_id(game.id)

    def edit_game_identity_for_game_id(self, game_id: int, parent=None) -> None:
        from PySide6.QtWidgets import QDialog, QWidget
        from app.ui.dialog_presenter import exec_child_dialog
        from app.ui.dialogs import EditGameDialog

        game = self.db.get_game_by_id(self.current_user_id, game_id)
        if game is None:
            owner: QWidget = parent if parent is not None else self
            QMessageBox.warning(owner, "未找到游戏", "该游戏记录不存在。")
            return
        owner = parent if parent is not None else self
        dialog = EditGameDialog(game, owner)
        if exec_child_dialog(owner, dialog) != QDialog.DialogCode.Accepted:
            return
        new_name, new_launch_exe = dialog.values()
        if not new_name:
            QMessageBox.warning(owner, "输入无效", "游戏名不能为空。")
            return
        if not new_launch_exe:
            QMessageBox.warning(owner, "输入无效", "启动路径不能为空。")
            return
        if not Path(new_launch_exe).exists():
            label = "视频文件" if getattr(game, "content_type", "game") == "video" else "启动路径"
            QMessageBox.warning(owner, "路径无效", f"{label}不存在，请重新选择。")
            return
        self.db.update_game_identity(game_id, new_name, new_launch_exe)
        self.refresh_games()
        self.status.setText("已更新视频名称与文件路径" if getattr(game, "content_type", "game") == "video" else "已更新游戏名称与启动路径")

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
        if getattr(game, "content_type", "game") == "video":
            self.status.setText("视频条目不参与在线封面重新获取，可手动设置封面")
            return
        if self.retry_cover_for_game_id(game.id):
            self.status.setText("正在后台重新获取封面...")

    def _create_shortcut(self) -> None:
        game = self._selected_game()
        if game is None:
            return
        self._create_shortcut_for_record(game)

    def _create_shortcut_for_record(self, game: GameRecord) -> None:
        if getattr(game, "content_type", "game") == "video":
            self.status.setText("视频条目请通过系统播放器或文件关联打开")
            return
        shortcut = self.system_service.create_desktop_shortcut(game.name, game.launch_exe)
        self.status.setText(f"快捷方式已创建: {shortcut}")

    def _backup(self) -> None:
        try:
            archive = self.backup_service.export_backup(self.db.db_path)
        except Exception as exc:
            self.status.setText("备份失败")
            self._notify_error("备份失败", str(exc), "请检查目标磁盘空间与写入权限后重试。")
            return
        self.status.setText(f"备份完成: {archive}")
        self._notify_toast("备份完成", "success")

    def _restore(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        archive_path, _ = QFileDialog.getOpenFileName(self, "选择备份文件", "", "Zip (*.zip)")
        if not archive_path:
            return
        try:
            self.db.close()
            try:
                self.backup_service.import_backup(Path(archive_path), self.db.db_path)
            finally:
                self.db.reopen()
            self.refresh_games()
            self.status.setText("恢复成功")
            self._notify_toast("恢复成功", "success")
        except Exception as exc:
            if self.db.conn is None:
                try:
                    self.db.reopen()
                except Exception:
                    pass
            self._notify_error(
                "恢复失败",
                str(exc),
                "请确认所选 zip 为本程序导出的备份文件，且未被占用。",
            )

    def _notify_toast(self, message: str, level: str = "info") -> None:
        fn = getattr(self, "show_toast", None)
        if callable(fn):
            fn(message, level)

    def _notify_error(self, title: str, message: str, suggestion: str = "") -> None:
        fn = getattr(self, "show_error", None)
        if callable(fn):
            fn(title, message, suggestion)
        else:
            QMessageBox.critical(self, title, message)

    def _toggle_startup(self) -> None:
        enabled = self.system_service.is_startup_enabled()
        try:
            self.system_service.set_startup(not enabled)
            self._refresh_startup_state()
            self.status.setText("已更新开机自启设置")
        except PermissionError:
            QMessageBox.warning(
                self, "权限不足",
                "无法修改开机启动项。\n\n请以管理员身份运行本程序后重试。",
            )
        except Exception as exc:
            QMessageBox.critical(self, "设置失败", str(exc))

    def _apply_auto_backup_launch_ui(self) -> None:
        enabled = bool(self.auto_backup_before_launch)
        self.act_auto_backup.setChecked(enabled)
        tag = "ON" if enabled else "OFF"
        self.act_auto_backup.setText(f"💾 启动前备份: {tag}")
        self.act_auto_backup.setToolTip(
            f"当前: {'已开启' if enabled else '已关闭'} — 点击切换"
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

        self.plugin_manager.set_plugin_configs(self.db.get_plugin_configs())
        self.plugin_manager.reload(disabled_plugins=self._disabled_plugins)
        dialog = PluginSettingsDialog(
            load_info=self.plugin_manager.load_info,
            disabled_names=self._disabled_plugins,
            plugin_dir=self.plugin_manager.plugin_dir,
            plugin_manager=self.plugin_manager,
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        new_disabled = set(dialog.disabled_names())
        if new_disabled == self._disabled_plugins:
            return
        self._disabled_plugins = new_disabled
        self.db.set_disabled_plugins(sorted(self._disabled_plugins))
        self.plugin_manager.set_plugin_configs(self.db.get_plugin_configs())
        self.plugin_manager.reload(disabled_plugins=self._disabled_plugins)
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
        from app.ui.dialogs.twodfan_library_dialog import TwodfanLibraryDialog

        dlg = TwodfanLibraryDialog(self)
        dlg.exec()

    def _open_hbe_decrypt_dialog(self) -> None:
        from app.ui.dialogs.hbe_decrypt_dialog import HbeDecryptDialog

        HbeDecryptDialog(self).exec()

    def _open_auto_extract_dialog(self) -> None:
        from app.ui.dialogs.auto_extract_dialog import AutoExtractDialog

        AutoExtractDialog(self).exec()

    def _open_fdm_dialog(self) -> None:
        from app.ui.dialogs.fdm_dialog import FdmDialog

        FdmDialog(self).exec()

    def _open_quick_workflow(self) -> None:
        from app.ui.dialogs.quick_workflow_dialog import QuickWorkflowDialog

        if getattr(self, "_scan_running", False) or getattr(self, "_vndb_worker", None) is not None:
            QMessageBox.information(self, "任务运行中", "请等待当前扫描或导入任务完成后再启动一键工作流。")
            return
        dlg = QuickWorkflowDialog(self, parent=self)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.exec()

    def _start_twodfan_crawl(self) -> None:
        from app.ui.dialogs.twodfan_crawl_dialog import TwodfanCrawlDialog
        from app.services.paths import default_twodfan_sqlite_path

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
        is_video = getattr(game, "content_type", "game") == "video"

        # ===== 第一组：启动操作（高频）=====
        launch_action = menu.addAction("▶️ 播放视频" if is_video else "▶️ 启动游戏")
        launch_action.triggered.connect(
            lambda checked=False, gid=game.id: self.launch_game_by_id(gid, message_parent=self)
        )
        launch_action.setToolTip("用系统默认播放器打开视频" if is_video else "正常启动游戏")

        if is_video:
            open_location_action = menu.addAction("📂 打开所在位置")
            open_location_action.triggered.connect(
                lambda checked=False, g=game: self._open_video_location(g)
            )
            open_location_action.setToolTip("在资源管理器中打开视频所在位置")
        else:
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

            debug_action = menu.addAction("🔧 调试启动")
            debug_action.triggered.connect(
                lambda checked=False, gid=game.id: self.debug_launch_game(gid, parent=self)
            )
            debug_action.setToolTip("测试游戏能否启动，显示详细诊断信息（退出码、运行时长、建议等）")

        menu.addSeparator()

        # ===== 第二组：信息管理（高频）=====
        detail_action = menu.addAction("ℹ️ 游戏详情")
        detail_action.triggered.connect(lambda checked=False, gid=game.id: self.open_game_detail(gid))
        detail_action.setToolTip("查看游戏详细信息")

        if not is_video:
            save_mgr_action = menu.addAction("💾 存档管理")
            save_mgr_action.triggered.connect(lambda checked=False, gid=game.id: self.open_save_manager(gid))
            save_mgr_action.setToolTip("管理游戏存档备份与还原")

        fav_text = "⭐ 取消收藏" if game.favorite else "☆ 收藏"
        fav_action = menu.addAction(fav_text)
        fav_action.triggered.connect(lambda checked=False, g=game: self._toggle_favorite_for_record(g))
        fav_action.setToolTip("将游戏加入/移出收藏")

        hide_text = "👁 取消隐藏" if game.hidden else "🙈 隐藏游戏"
        hide_action = menu.addAction(hide_text)
        hide_action.triggered.connect(lambda checked=False, g=game: self._toggle_hidden_for_record(g))
        hide_action.setToolTip("从列表中隐藏/显示该游戏（Ctrl+H）")

        menu.addSeparator()

        # ===== 第三组：编辑信息（二级菜单）=====
        edit_submenu = menu.addMenu("✏️ 编辑信息")
        
        edit_name_action = edit_submenu.addAction("编辑名称/路径")
        edit_name_action.triggered.connect(
            lambda checked=False, gid=game.id: self.edit_game_identity_for_game_id(gid)
        )

        if not is_video:
            edit_title_action = edit_submenu.addAction("选择标题")
            edit_title_action.triggered.connect(
                lambda checked=False, gid=game.id: self.open_game_detail(gid)
            )
            edit_title_action.setToolTip("从候选标题中选择游戏名称")

        cover_action = edit_submenu.addAction("设置封面")
        cover_action.triggered.connect(
            lambda checked=False, gid=game.id: self.set_custom_cover_for_game_id(gid)
        )

        if not is_video:
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
        if not is_video:
            shortcut_action = menu.addAction("🔗 创建桌面快捷方式")
            shortcut_action.triggered.connect(
                lambda checked=False, g=game: self._create_shortcut_for_record(g)
            )
            shortcut_action.setToolTip("在桌面创建游戏快捷方式")

        menu.addSeparator()

        delete_action = menu.addAction("🗑️ 从库中删除")
        delete_action.triggered.connect(
            lambda checked=False, g=game: self._delete_game_from_library_for_record(g)
        )
        delete_action.setToolTip("从库中删除；可在确认框中勾选是否一并删除安装文件夹")

        menu.exec(menu_anchor if menu_anchor is not None else QCursor.pos())

    def _open_video_location(self, game: GameRecord) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        path = Path(game.launch_exe)
        target = path.parent if path.is_file() else Path(game.root_dir)
        if not target.exists():
            QMessageBox.warning(self, "无法打开", "视频文件或所在目录不存在。")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(target.resolve()))):
            QMessageBox.warning(self, "无法打开", "系统未关联打开方式。")

    def _open_game_data_manager(self) -> None:
        from app.ui.dialogs.game_data_manager_dialog import GameDataManagerDialog

        GameDataManagerDialog(self).exec()

    def _delete_game_from_library_for_record(self, game: GameRecord) -> bool:
        """Remove game from library. Returns True if deleted successfully."""
        from app.services.game_delete_service import confirm_delete_game, delete_game_from_library

        decision = confirm_delete_game(
            self, self.db, game.name, install_dir=game.root_dir
        )
        if decision is None:
            return False
        try:
            name = delete_game_from_library(
                self.db,
                game.id,
                delete_install_folder=decision.delete_install_folder,
            )
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "删除失败", str(exc))
            self.refresh_games()
            return False
        self.refresh_games()
        if decision.delete_install_folder:
            self.status.setText(f"已删除库记录及安装目录：{name}")
        else:
            self.status.setText(f"已从库中删除：{name}")
        return True
