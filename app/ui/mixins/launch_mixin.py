from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtCore import QThreadPool, Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from app.workers import LaunchGameTask


class LaunchMixin:
    _launch_pool: QThreadPool
    db: object
    launcher: object
    current_user_id: int
    auto_backup_before_launch: bool
    status: object

    def is_locale_emulator_usable(self) -> bool:
        if sys.platform != "win32":
            return False
        p = self.db.get_locale_emulator_leproc_path().strip()
        if not p:
            return False
        path = Path(p)
        return path.is_file() and path.name.lower() == "leproc.exe"

    def launch_game_by_id(
        self,
        game_id: int,
        *,
        as_admin: bool = False,
        locale_emulator: bool = False,
        message_parent=None,
    ) -> None:
        from PySide6.QtWidgets import QWidget

        parent = self._message_box_parent(message_parent)
        game = self.db.get_game_by_id(self.current_user_id, game_id)
        if game is None:
            QMessageBox.warning(parent, "未找到游戏", "该游戏记录不存在。")
            return
        if locale_emulator:
            if not self.is_locale_emulator_usable():
                r = QMessageBox.question(
                    parent,
                    "未配置 Locale Emulator",
                    "使用 LE 转区前，需要指定本机安装目录里的 LEProc.exe。\n\n"
                    "是否现在打开「Locale Emulator (LE)…」进行配置？\n\n"
                    "安装包下载：\n"
                    "https://github.com/xupefei/Locale-Emulator/releases",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if r == QMessageBox.StandardButton.Yes:
                    self._open_locale_emulator_settings()
                return
        le_path = self.db.get_locale_emulator_leproc_path().strip() if locale_emulator else ""
        if self.auto_backup_before_launch:
            self._auto_backup_save_before_launch(game)
        uid = self.current_user_id
        self.status.setText(
            f"正在通过 LE 启动: {game.name}…" if locale_emulator else f"正在启动: {game.name}…"
        )
        QApplication.processEvents()
        log = logging.getLogger(__name__)
        log.info(
            "Launch queued game_id=%s le=%s admin=%s exe=%s",
            game_id,
            locale_emulator,
            as_admin,
            game.launch_exe,
        )
        task = LaunchGameTask(
            self.launcher,
            launch_exe=game.launch_exe,
            locale_emulator=locale_emulator,
            le_proc_path=le_path,
            as_admin=as_admin,
            game_id=game.id,
            game_name=game.name,
            signal_parent=self,
        )
        task.signals.finished.connect(
            lambda gid, dur, name, u=uid, mp=message_parent: self._on_game_launch_finished(
                u, mp, gid, dur, name
            ),
            Qt.QueuedConnection,
        )
        task.signals.failed.connect(
            lambda msg, mp=message_parent: self._on_game_launch_failed(mp, msg),
            Qt.QueuedConnection,
        )
        self._launch_pool.start(task)

    def _on_game_launch_finished(
        self,
        user_id: int,
        message_parent,
        game_id: int,
        duration: int,
        game_name: str,
    ) -> None:
        parent = self._message_box_parent(message_parent)
        try:
            self.db.record_play(user_id, game_id, duration)
            self.refresh_games()
            self.status.setText(f"已退出: {game_name}，本次时长 {duration}s")
        except Exception as exc:
            logging.getLogger(__name__).exception("record_play after launch")
            QMessageBox.critical(parent, "记录游玩失败", str(exc))

    def _on_game_launch_failed(self, message_parent, message: str) -> None:
        parent = self._message_box_parent(message_parent)
        self.status.setText("启动失败")
        QMessageBox.critical(parent, "启动失败", message)

    def _launch_selected(self, as_admin: bool = False) -> None:
        game = self._selected_game()
        if game is None:
            return
        self.launch_game_by_id(game.id, as_admin=as_admin)

    def _open_locale_emulator_settings(self) -> None:
        from PySide6.QtWidgets import QMessageBox
        from app.ui.dialogs import LocaleEmulatorSettingsDialog

        cur = self.db.get_locale_emulator_leproc_path()
        dlg = LocaleEmulatorSettingsDialog(cur, self)
        if dlg.exec() != QDialog.Accepted:
            return
        path = dlg.leproc_path()
        if path:
            if not Path(path).is_file():
                QMessageBox.warning(self, "路径无效", "未找到该文件，请重新选择 LEProc.exe。")
                return
            if Path(path).name.lower() != "leproc.exe":
                QMessageBox.warning(
                    self,
                    "文件名无效",
                    "请选择 Locale Emulator 安装目录中的 LEProc.exe。",
                )
                return
        self.db.set_locale_emulator_leproc_path(path)
        self.status.setText("已保存 Locale Emulator 路径" if path else "已清除 Locale Emulator 配置")
