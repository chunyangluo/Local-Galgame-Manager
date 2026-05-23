"""Single-game detail dialog: metadata, play history, filesystem actions, debug."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
)

from app.data.database import Database, GameRecord, PlayRecordEntry

if TYPE_CHECKING:
    from app.ui.main_window import MainWindow


def reveal_in_explorer(path_str: str, *, select_file: bool = False) -> None:
    """Open folder in the system file manager; optionally select a file (Windows/macOS)."""
    path = Path(path_str).resolve()
    if not path.exists():
        raise FileNotFoundError(str(path))
    if sys.platform == "win32":
        import os
        import subprocess

        if select_file and path.is_file():
            subprocess.Popen(["explorer", "/select,", str(path)])
        else:
            folder = path if path.is_dir() else path.parent
            os.startfile(str(folder))
    elif sys.platform == "darwin":
        import subprocess

        if select_file and path.is_file():
            subprocess.Popen(["open", "-R", str(path)])
        else:
            folder = path if path.is_dir() else path.parent
            subprocess.Popen(["open", str(folder)])
    else:
        import subprocess

        folder = path if path.is_dir() else path.parent
        subprocess.Popen(["xdg-open", str(folder)])


def _fmt_duration(sec: int) -> str:
    if sec < 0:
        sec = 0
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    if h:
        return f"{h}时{m}分{s}秒"
    if m:
        return f"{m}分{s}秒"
    return f"{s}秒"


def _fmt_total_seconds(sec: int) -> str:
    return _fmt_duration(sec) + f"（共 {sec} 秒）"


class GameDetailDialog(QDialog):
    def __init__(self, main: MainWindow, game_id: int) -> None:
        super().__init__(main)
        self._main = main
        self._game_id = game_id
        self.setWindowTitle("游戏详情")
        self.resize(920, 680)

        root = QVBoxLayout(self)

        top = QHBoxLayout()
        self._cover = QLabel()
        self._cover.setFixedSize(200, 300)
        self._cover.setAlignment(Qt.AlignCenter)
        self._cover.setStyleSheet("background:#252C36;border-radius:8px;")
        top.addWidget(self._cover)

        meta_col = QVBoxLayout()
        self._title = QLabel()
        self._title.setWordWrap(True)
        self._title.setStyleSheet("font-size:16px;font-weight:600;color:#F3F6FB;")
        meta_col.addWidget(self._title)

        self._subtitle = QLabel()
        self._subtitle.setWordWrap(True)
        self._subtitle.setStyleSheet("color:#93A1B6;font-size:11px;")
        meta_col.addWidget(self._subtitle)

        self._rating_line = QLabel()
        self._rating_line.setWordWrap(True)
        meta_col.addWidget(self._rating_line)

        self._platforms_line = QLabel()
        self._platforms_line.setWordWrap(True)
        meta_col.addWidget(self._platforms_line)

        self._languages_line = QLabel()
        self._languages_line.setWordWrap(True)
        meta_col.addWidget(self._languages_line)

        self._meta_line = QLabel()
        self._meta_line.setWordWrap(True)
        self._meta_line.setStyleSheet("color:#7FA7D9;font-size:11px;")
        meta_col.addWidget(self._meta_line)

        self._play_summary = QLabel()
        self._play_summary.setWordWrap(True)
        meta_col.addWidget(self._play_summary)

        meta_col.addStretch(1)
        top.addLayout(meta_col, 1)
        root.addLayout(top)

        desc_label = QLabel("简介")
        desc_label.setStyleSheet("font-weight:600;")
        root.addWidget(desc_label)
        self._description = QTextEdit()
        self._description.setReadOnly(True)
        self._description.setMinimumHeight(120)
        self._description.setPlaceholderText("（无描述）")
        root.addWidget(self._description, 1)

        hist_box = QGroupBox("游玩记录")
        hist_layout = QVBoxLayout(hist_box)
        self._history_table = QTableWidget(0, 4)
        self._history_table.setHorizontalHeaderLabels(["开始时间", "结束时间", "时长", "秒数"])
        self._history_table.horizontalHeader().setStretchLastSection(True)
        self._history_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._history_table.setSelectionBehavior(QTableWidget.SelectRows)
        hist_layout.addWidget(self._history_table)
        root.addWidget(hist_box, 1)

        launch_row = QHBoxLayout()
        self._btn_run = QPushButton("启动游戏")
        self._btn_run.setToolTip("普通方式启动（退出后写入游玩记录）")
        self._btn_run.clicked.connect(self._on_run_game)
        launch_row.addWidget(self._btn_run)
        self._btn_run_le = QPushButton("LE 转区启动")
        self._btn_run_le.setToolTip(
            "使用 Locale Emulator (LEProc)；在「更多 → Locale Emulator (LE)…」中配置路径"
        )
        self._btn_run_le.clicked.connect(self._on_run_game_le)
        launch_row.addWidget(self._btn_run_le)
        launch_row.addStretch(1)
        root.addLayout(launch_row)

        btn_row = QHBoxLayout()
        self._btn_root = QPushButton("打开游戏目录")
        self._btn_root.clicked.connect(self._on_open_root)
        btn_row.addWidget(self._btn_root)

        self._btn_launch = QPushButton("打开启动文件所在位置")
        self._btn_launch.clicked.connect(self._on_open_launch_dir)
        btn_row.addWidget(self._btn_launch)

        self._btn_meta = QPushButton("重新获取元数据 (VNDB)")
        self._btn_meta.clicked.connect(self._on_refresh_meta)
        btn_row.addWidget(self._btn_meta)

        self._btn_cover = QPushButton("重新获取封面")
        self._btn_cover.clicked.connect(self._on_refresh_cover)
        btn_row.addWidget(self._btn_cover)

        self._btn_edit = QPushButton("编辑名称 / 启动")
        self._btn_edit.clicked.connect(self._on_edit_identity)
        btn_row.addWidget(self._btn_edit)

        self._btn_custom_cover = QPushButton("设置自定义封面")
        self._btn_custom_cover.clicked.connect(self._on_set_custom_cover)
        btn_row.addWidget(self._btn_custom_cover)

        self._btn_save_mgr = QPushButton("存档管理…")
        self._btn_save_mgr.setToolTip(
            "指定存档目录、备份与还原 ZIP；可配置全局 2DFan 线索库并在「自动发现」中合并社区路径"
        )
        self._btn_save_mgr.clicked.connect(self._on_open_save_manager)
        btn_row.addWidget(self._btn_save_mgr)

        self._btn_reload = QPushButton("刷新")
        self._btn_reload.clicked.connect(self.reload_from_db)
        btn_row.addWidget(self._btn_reload)

        root.addLayout(btn_row)

        debug_box = QGroupBox("调试信息（数据库原始字段与元数据）")
        debug_layout = QVBoxLayout(debug_box)
        self._debug = QPlainTextEdit()
        self._debug.setReadOnly(True)
        self._debug.setMaximumBlockCount(2000)
        self._debug.setMinimumHeight(140)
        debug_layout.addWidget(self._debug)
        dbg_btn = QHBoxLayout()
        copy_dbg = QPushButton("复制调试信息")
        copy_dbg.clicked.connect(self._copy_debug)
        dbg_btn.addWidget(copy_dbg)
        dbg_btn.addStretch(1)
        debug_layout.addLayout(dbg_btn)
        root.addWidget(debug_box)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._game: GameRecord | None = None
        self.reload_from_db()

    def _db(self) -> Database:
        return self._main.db

    def _user_id(self) -> int:
        return self._main.current_user_id

    def reload_from_db(self) -> None:
        game = self._db().get_game_by_id(self._user_id(), self._game_id)
        if game is None:
            QMessageBox.warning(self, "记录不存在", "该游戏可能已被删除。")
            self.reject()
            return
        self._game = game
        self._apply_game(game)
        self._btn_run_le.setEnabled(self._main.is_locale_emulator_usable())
        raw = self._db().get_game_storage_debug(self._game_id)
        lines = []
        if raw:
            for k in sorted(raw.keys()):
                v = raw[k]
                lines.append(f"{k}: {v if v is not None else ''}")
        lines.append("")
        lines.append("--- 当前界面使用的 GameRecord（含 custom 合并后）---")
        lines.append(f"id: {game.id}")
        lines.append(f"name (effective): {game.name}")
        lines.append(f"root_dir: {game.root_dir}")
        lines.append(f"launch_exe (effective): {game.launch_exe}")
        lines.append(f"cover_path (effective): {game.cover_path}")
        lines.append(f"custom_save_root: {game.custom_save_root or '（未指定）'}")
        lines.append(f"vndb_id: {game.vndb_id}")
        lines.append(f"image_url: {game.image_url}")
        lines.append(f"source: {game.source}")
        lines.append(f"title_original: {game.title_original}")
        lines.append(f"title_localized: {game.title_localized}")
        lines.append(f"rating: {game.rating}")
        lines.append(f"platforms: {game.platforms}")
        lines.append(f"languages: {game.languages}")
        if game.screenshots_json:
            lines.append(f"screenshots_json (len): {len(game.screenshots_json)}")
        lep = self._db().get_locale_emulator_leproc_path()
        lines.append(f"locale_emulator_leproc_path: {lep or '（未配置）'}")
        self._debug.setPlainText("\n".join(lines))

        records = self._db().list_play_records(self._user_id(), self._game_id)
        self._fill_history(records)

    def _apply_game(self, game: GameRecord) -> None:
        self.setWindowTitle(f"游戏详情 — {game.name}")
        self._title.setText(game.name)
        sub = []
        if game.title_original:
            sub.append(f"原名: {game.title_original}")
        if game.title_localized:
            sub.append(f"译名: {game.title_localized}")
        self._subtitle.setText(" ｜ ".join(sub) if sub else "（无 VNDB 标题信息）")

        rating_txt = (
            f"评分: {float(game.rating):.2f}" if game.rating is not None else "评分: —"
        )
        self._rating_line.setText(rating_txt)

        self._platforms_line.setText(f"平台: {game.platforms or '—'}")
        self._languages_line.setText(f"语言: {game.languages or '—'}")

        self._meta_line.setText(
            f"VNDB ID: {game.vndb_id or '—'} ｜ 数据来源: {game.source or '—'} ｜ 分类: {game.categories or '—'}"
        )
        last = game.last_played_at or "无"
        self._play_summary.setText(
            f"最近游玩: {last} ｜ 次数: {game.play_count} ｜ 累计: {_fmt_total_seconds(game.total_play_seconds)}"
        )

        self._description.setPlainText(game.description or "")

        pix = QPixmap()
        if game.cover_path:
            p = Path(game.cover_path)
            if p.exists():
                pix = QPixmap(str(p))
        if pix.isNull():
            self._cover.setText("无封面")
            self._cover.setPixmap(QPixmap())
        else:
            self._cover.setText("")
            scaled = pix.scaled(
                self._cover.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self._cover.setPixmap(scaled)

    def _fill_history(self, records: list[PlayRecordEntry]) -> None:
        self._history_table.setRowCount(0)
        self._history_table.setRowCount(len(records))
        for row, rec in enumerate(records):
            self._history_table.setItem(row, 0, QTableWidgetItem(rec.started_at))
            self._history_table.setItem(row, 1, QTableWidgetItem(rec.ended_at or "—"))
            self._history_table.setItem(row, 2, QTableWidgetItem(_fmt_duration(rec.duration_seconds)))
            self._history_table.setItem(row, 3, QTableWidgetItem(str(rec.duration_seconds)))
        self._history_table.resizeColumnsToContents()

    def _copy_debug(self) -> None:
        QApplication.clipboard().setText(self._debug.toPlainText())
        self._main.status.setText("已复制调试信息到剪贴板")

    def _on_open_root(self) -> None:
        if not self._game:
            return
        try:
            reveal_in_explorer(self._game.root_dir, select_file=False)
        except FileNotFoundError as exc:
            QMessageBox.warning(self, "无法打开", str(exc))

    def _on_run_game(self) -> None:
        self._main.launch_game_by_id(self._game_id, message_parent=self)
        self.reload_from_db()

    def _on_run_game_le(self) -> None:
        self._main.launch_game_by_id(
            self._game_id, locale_emulator=True, message_parent=self
        )
        self.reload_from_db()

    def _on_open_launch_dir(self) -> None:
        if not self._game:
            return
        p = Path(self._game.launch_exe)
        if not p.exists():
            QMessageBox.warning(self, "路径不存在", f"启动文件不存在:\n{p}")
            return
        try:
            reveal_in_explorer(str(p), select_file=True)
        except OSError as exc:
            QMessageBox.warning(self, "无法打开", str(exc))

    def _on_refresh_meta(self) -> None:
        self._main.run_vndb_import_for_game_id(
            self._game_id,
            on_finished=self.reload_from_db,
        )

    def _on_refresh_cover(self) -> None:
        if self._main.retry_cover_for_game_id(self._game_id):
            self._main.status.setText("正在后台重新获取封面…")
        self.reload_from_db()

    def _on_edit_identity(self) -> None:
        self._main.edit_game_identity_for_game_id(self._game_id)
        self.reload_from_db()

    def _on_set_custom_cover(self) -> None:
        from app.ui.dialogs.custom_cover_manager_dialog import CustomCoverManagerDialog
        
        dialog = CustomCoverManagerDialog(
            self._main,
            self._game_id,
            self._game.name,
            self._game.root_dir,
            self._game.cover_path
        )
        if dialog.exec():
            self.reload_from_db()

    def _on_open_save_manager(self) -> None:
        self._main.open_save_manager(self._game_id)
