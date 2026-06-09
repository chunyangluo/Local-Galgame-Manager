"""Single-game detail dialog: metadata, play history, filesystem actions, debug."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QMimeData
from PySide6.QtGui import QPixmap, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
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
    QWidget,
    QSizePolicy,
)

from app.data.database import Database, GameRecord, PlayRecordEntry

if TYPE_CHECKING:
    from app.ui.main_window import MainWindow


def launch_executable(exe_path: str | Path) -> None:
    """Start an .exe with its install folder as working directory (legacy installers)."""
    import os

    exe = Path(exe_path).resolve()
    if not exe.is_file():
        raise FileNotFoundError(str(exe))
    work_dir = str(exe.parent)
    if sys.platform == "win32":
        import ctypes

        rc = ctypes.windll.shell32.ShellExecuteW(  # type: ignore[attr-defined]
            None,
            "open",
            str(exe),
            None,
            work_dir,
            1,
        )
        if int(rc) <= 32:
            raise OSError(f"无法启动程序 (ShellExecute 错误码 {int(rc)})")
    else:
        env = os.environ.copy()
        env["PATH"] = work_dir + os.pathsep + env.get("PATH", "")
        import subprocess

        subprocess.Popen([str(exe)], cwd=work_dir, env=env)


def reveal_in_explorer(path_str: str, *, select_file: bool = False) -> None:
    """Open folder in the system file manager; optionally select a file (Windows/macOS)."""
    path = Path(path_str).resolve()
    if not path.exists():
        raise FileNotFoundError(str(path))
    if sys.platform == "win32":
        import os
        import subprocess

        if select_file and path.is_file():
            # /select, 与路径必须在同一参数内，否则含空格或 [] 的路径会解析失败
            subprocess.Popen(["explorer", "/select," + os.path.normpath(str(path))])
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


def _fmt_datetime(dt_str: str) -> str:
    """Convert ISO datetime to local format."""
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return dt_str


class GameDetailDialog(QDialog):
    def __init__(self, main: MainWindow, game_id: int) -> None:
        super().__init__(main)
        self._main = main
        self._game_id = game_id
        self.setWindowTitle("游戏详情")
        self.resize(920, 680)
        self.setStyleSheet("""
            QGroupBox { font-weight: 600; margin-top: 8px; }
        """)

        root = QVBoxLayout(self)

        top_bar = QHBoxLayout()
        top_bar.addStretch(1)
        
        self._close_btn = QPushButton("✕")
        self._close_btn.setStyleSheet("""
            QPushButton { 
                border: none; 
                padding: 4px 8px; 
                font-size: 16px;
            }
        """)
        self._close_btn.clicked.connect(self.reject)
        top_bar.addWidget(self._close_btn)
        root.addLayout(top_bar)

        top = QHBoxLayout()
        self._cover = QLabel()
        self._cover.setFixedSize(200, 300)
        self._cover.setAlignment(Qt.AlignCenter)
        self._cover.setStyleSheet("border-radius:8px;")
        self._cover.setAcceptDrops(True)
        self._cover.dragEnterEvent = self._on_cover_drag_enter
        self._cover.dropEvent = self._on_cover_drop
        self._cover.setToolTip("拖拽图片到此处更换封面")
        top.addWidget(self._cover)

        meta_col = QVBoxLayout()
        self._title = QLabel()
        self._title.setWordWrap(True)
        self._title.setStyleSheet("font-size:16px;font-weight:600;")
        meta_col.addWidget(self._title)

        meta_grid = QWidget()
        meta_grid_layout = QVBoxLayout(meta_grid)
        
        self._meta_items = []
        
        self._title_original = QLabel()
        self._meta_items.append(self._title_original)
        meta_grid_layout.addWidget(self._title_original)
        
        self._title_localized = QLabel()
        self._meta_items.append(self._title_localized)
        meta_grid_layout.addWidget(self._title_localized)
        
        self._rating_line = QLabel()
        self._meta_items.append(self._rating_line)
        meta_grid_layout.addWidget(self._rating_line)
        
        self._platforms_line = QLabel()
        self._meta_items.append(self._platforms_line)
        meta_grid_layout.addWidget(self._platforms_line)
        
        self._languages_line = QLabel()
        self._meta_items.append(self._languages_line)
        meta_grid_layout.addWidget(self._languages_line)

        # LE profile selector
        le_profile_row = QHBoxLayout()
        le_profile_label = QLabel("LE 转区配置:")
        le_profile_row.addWidget(le_profile_label)
        self._le_profile_combo = QComboBox()
        self._le_profile_combo.addItem("不使用", "")
        self._le_profile_combo.addItem("ja-JP (日语)", "ja-JP")
        self._le_profile_combo.addItem("zh-CN (简体中文)", "zh-CN")
        self._le_profile_combo.addItem("zh-TW (繁体中文)", "zh-TW")
        self._le_profile_combo.addItem("ko-KR (韩语)", "ko-KR")
        self._le_profile_combo.currentIndexChanged.connect(self._on_le_profile_changed)
        le_profile_row.addWidget(self._le_profile_combo)
        le_profile_row.addStretch(1)
        meta_grid_layout.addLayout(le_profile_row)

        meta_grid_layout.addStretch(1)
        meta_col.addWidget(meta_grid)

        self._meta_source = QLabel()
        self._meta_source.setObjectName("gameMetaSource")
        self._meta_source.setToolTip("数据来源说明")
        meta_col.addWidget(self._meta_source)

        self._play_summary = QLabel()
        self._play_summary.setWordWrap(True)
        meta_col.addWidget(self._play_summary)

        meta_col.addStretch(1)
        top.addLayout(meta_col, 1)
        root.addLayout(top)

        desc_box = QGroupBox("简介")
        desc_layout = QVBoxLayout(desc_box)
        self._description = QTextEdit()
        self._description.setReadOnly(True)
        self._description.setMinimumHeight(120)
        self._description.setPlaceholderText("暂无简介，点击下方「刷新元数据」获取")
        desc_layout.addWidget(self._description, 1)
        
        self._refresh_meta_hint = QLabel()
        self._refresh_meta_hint.setAlignment(Qt.AlignCenter)
        desc_layout.addWidget(self._refresh_meta_hint)
        root.addWidget(desc_box, 1)

        hist_box = QGroupBox("游玩记录")
        hist_layout = QVBoxLayout(hist_box)
        self._history_table = QTableWidget(0, 3)
        self._history_table.setHorizontalHeaderLabels(["开始时间", "结束时间", "时长"])
        self._history_table.horizontalHeader().setStretchLastSection(True)
        self._history_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._history_table.setSelectionBehavior(QTableWidget.SelectRows)
        hist_layout.addWidget(self._history_table)
        root.addWidget(hist_box, 1)

        btn_group1 = QHBoxLayout()
        btn_group1.setSpacing(8)
        
        self._btn_run = QPushButton("▶️ 启动游戏")
        self._btn_run.setProperty("btnRole", "primary")
        self._btn_run.setToolTip("普通方式启动（退出后写入游玩记录）")
        self._btn_run.clicked.connect(self._on_run_game)
        btn_group1.addWidget(self._btn_run)

        self._btn_run_le = QPushButton("🌐 LE 转区启动")
        self._btn_run_le.setProperty("btnRole", "primary")
        self._btn_run_le.setToolTip(
            "使用 Locale Emulator (LEProc)；在「更多 → Locale Emulator (LE)…」中配置路径"
        )
        self._btn_run_le.clicked.connect(self._on_run_game_le)
        btn_group1.addWidget(self._btn_run_le)

        self._btn_debug = QPushButton("🔧 调试启动")
        self._btn_debug.setToolTip("测试游戏能否启动，显示详细诊断信息（退出码、运行时长、建议等）")
        self._btn_debug.clicked.connect(self._on_debug_launch)
        btn_group1.addWidget(self._btn_debug)
        
        btn_group1.addStretch(1)
        root.addLayout(btn_group1)

        btn_group2 = QHBoxLayout()
        btn_group2.setSpacing(8)

        self._btn_save_mgr = QPushButton("💾 存档管理")
        self._btn_save_mgr.setToolTip(
            "指定存档目录、备份与还原 ZIP；可配置全局 2DFan 线索库并在「自动发现」中合并社区路径"
        )
        self._btn_save_mgr.clicked.connect(self._on_open_save_manager)
        btn_group2.addWidget(self._btn_save_mgr)

        self._btn_edit = QPushButton("✏️ 编辑名称/路径")
        self._btn_edit.clicked.connect(self._on_edit_identity)
        btn_group2.addWidget(self._btn_edit)

        self._btn_select_title = QPushButton("📝 选择标题")
        self._btn_select_title.setToolTip("从候选标题中选择游戏名称")
        self._btn_select_title.clicked.connect(self._on_select_title)
        btn_group2.addWidget(self._btn_select_title)

        btn_group2.addStretch(1)
        root.addLayout(btn_group2)

        btn_group3 = QHBoxLayout()
        btn_group3.setSpacing(8)

        self._btn_root = QPushButton("📂 打开游戏目录")
        self._btn_root.setProperty("btnRole", "secondary")
        self._btn_root.clicked.connect(self._on_open_root)
        btn_group3.addWidget(self._btn_root)

        self._btn_launch = QPushButton("🔍 打开启动文件")
        self._btn_launch.setProperty("btnRole", "secondary")
        self._btn_launch.clicked.connect(self._on_open_launch_dir)
        btn_group3.addWidget(self._btn_launch)

        btn_group3.addStretch(1)
        root.addLayout(btn_group3)

        btn_group4 = QHBoxLayout()
        btn_group4.setSpacing(8)

        self._btn_meta = QPushButton("🔄 刷新元数据")
        self._btn_meta.setToolTip("从 VNDB 获取游戏元数据和封面")
        self._btn_meta.clicked.connect(self._on_refresh_meta)
        btn_group4.addWidget(self._btn_meta)

        self._btn_custom_cover = QPushButton("🖼️ 设置自定义封面")
        self._btn_custom_cover.clicked.connect(self._on_set_custom_cover)
        btn_group4.addWidget(self._btn_custom_cover)

        self._btn_reload = QPushButton("🔃 刷新")
        self._btn_reload.clicked.connect(self.reload_from_db)
        btn_group4.addWidget(self._btn_reload)

        self._btn_delete = QPushButton("🗑️ 从库中删除")
        self._btn_delete.setProperty("btnRole", "danger")
        self._btn_delete.setToolTip(
            "移除库内记录；可在确认框中勾选是否同时删除安装文件夹"
        )
        self._btn_delete.clicked.connect(self._on_delete_from_library)
        btn_group4.addWidget(self._btn_delete)

        btn_group4.addStretch(1)
        root.addLayout(btn_group4)

        self._debug_box = QGroupBox("调试信息")
        self._debug_box.setCheckable(True)
        self._debug_box.setChecked(False)
        debug_layout = QVBoxLayout(self._debug_box)
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
        root.addWidget(self._debug_box)

        self._status_label = QLabel()
        self._status_label.setObjectName("statusBar")
        self._status_label.setAlignment(Qt.AlignCenter)
        root.addWidget(self._status_label)

        self._game: GameRecord | None = None
        self._is_loading = False
        self._le_profile_loading = False
        self.reload_from_db()

    def _db(self) -> Database:
        return self._main.db

    def _user_id(self) -> int:
        return self._main.current_user_id

    def _set_status(self, text: str) -> None:
        self._status_label.setText(text)
        QApplication.processEvents()

    def _clear_status(self) -> None:
        self._status_label.setText("")

    def reload_from_db(self) -> None:
        game = self._db().get_game_by_id(self._user_id(), self._game_id)
        if game is None:
            QMessageBox.warning(self, "记录不存在", "该游戏可能已被删除。")
            self.reject()
            return
        self._game = game
        self._apply_game(game)
        self._btn_run_le.setEnabled(self._main.is_locale_emulator_usable())

        # Set LE profile combo box
        self._le_profile_loading = True
        if hasattr(self._db(), 'get_game_le_profile'):
            current_profile = self._db().get_game_le_profile(self._game_id)
        else:
            current_profile = ""
        # Find matching index
        idx = self._le_profile_combo.findData(current_profile)
        if idx >= 0:
            self._le_profile_combo.setCurrentIndex(idx)
        else:
            self._le_profile_combo.setCurrentIndex(0)
        self._le_profile_loading = False

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

        self._title_original.setText(f'<span class="meta-label">原名:</span> <span class="meta-value">{game.title_original or "<span class=\'missing\'>未获取</span>"}</span>')
        self._title_localized.setText(f'<span class="meta-label">译名:</span> <span class="meta-value">{game.title_localized or "<span class=\'missing\'>未获取</span>"}</span>')
        
        if game.rating is not None:
            self._rating_line.setText(f'<span class="meta-label">评分:</span> <span class="meta-value">{float(game.rating):.2f}</span>')
        else:
            self._rating_line.setText('<span class="meta-label">评分:</span> <span class="missing">未获取</span>')
        
        self._platforms_line.setText(f'<span class="meta-label">平台:</span> <span class="meta-value">{game.platforms or "<span class=\'missing\'>未获取</span>"}</span>')
        self._languages_line.setText(f'<span class="meta-label">语言:</span> <span class="meta-value">{game.languages or "<span class=\'missing\'>未获取</span>"}</span>')

        source_text = ""
        if game.source == "vndb":
            source_text = f'<span title="来自 VNDB 数据库">📦 数据来源: VNDB</span>'
        elif game.source:
            source_text = f"📦 数据来源: {game.source}"
        else:
            source_text = '<span class="missing">📦 数据来源: 未获取</span>'
        
        vndb_text = f"VNDB ID: {game.vndb_id or '未获取'}"
        cat_text = f"分类: {game.categories or '未设置'}"
        self._meta_source.setText(f"{vndb_text} ｜ {source_text} ｜ {cat_text}")

        last_played = _fmt_datetime(game.last_played_at) if game.last_played_at else "无"
        duration_text = _fmt_duration(game.total_play_seconds)
        self._play_summary.setText(
            f"最近游玩: {last_played} ｜ 次数: {game.play_count} ｜ 累计: {duration_text}"
        )
        self._play_summary.setToolTip(f"累计游玩 {game.total_play_seconds} 秒")

        desc = game.description or ""
        if desc:
            self._description.setPlainText(desc)
            self._refresh_meta_hint.setText("")
        else:
            self._description.setPlainText("")
            self._refresh_meta_hint.setText('<a href="refresh">点击「刷新元数据」获取游戏简介</a>')
            self._refresh_meta_hint.linkActivated.connect(lambda: self._on_refresh_meta())

        pix = QPixmap()
        if game.cover_path:
            p = Path(game.cover_path)
            if p.exists():
                pix = QPixmap(str(p))
        if pix.isNull():
            self._cover.setText("无封面\n拖拽图片到此处")
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
            self._history_table.setItem(row, 0, QTableWidgetItem(_fmt_datetime(rec.started_at)))
            end_time = _fmt_datetime(rec.ended_at) if rec.ended_at else "—"
            self._history_table.setItem(row, 1, QTableWidgetItem(end_time))
            duration = _fmt_duration(rec.duration_seconds)
            item = QTableWidgetItem(duration)
            item.setToolTip(f"{rec.duration_seconds} 秒")
            self._history_table.setItem(row, 2, item)
        self._history_table.resizeColumnsToContents()

    def _copy_debug(self) -> None:
        QApplication.clipboard().setText(self._debug.toPlainText())
        self._main.status.setText("已复制调试信息到剪贴板")

    def _on_le_profile_changed(self, index: int) -> None:
        """Save LE profile selection to database and generate/remove .le.config."""
        if self._le_profile_loading:
            return
        if not self._game:
            return
        profile = self._le_profile_combo.itemData(index) or ""
        if hasattr(self._db(), 'set_game_le_profile'):
            self._db().set_game_le_profile(self._game_id, profile)
        # Generate or remove .le.config accordingly
        try:
            from app.services.le_config_service import ensure_le_config, remove_le_config
            if profile:
                leproc_path = self._db().get_locale_emulator_leproc_path().strip() if hasattr(self._db(), 'get_locale_emulator_leproc_path') else ""
                ensure_le_config(self._game.launch_exe, profile, leproc_path=leproc_path)
            else:
                remove_le_config(self._game.launch_exe)
        except Exception:
            pass
        self._set_status(f"LE 转区配置已更新: {self._le_profile_combo.currentText()}")

    def _on_delete_from_library(self) -> None:
        if not self._game:
            return
        if self._main._delete_game_from_library_for_record(self._game):
            self.accept()

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

    def _on_debug_launch(self) -> None:
        self._main.debug_launch_game(self._game_id, parent=self)

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
        if self._is_loading:
            return
        self._is_loading = True
        self._btn_meta.setEnabled(False)
        self._set_status("正在从 VNDB 获取元数据...")
        
        def on_finished():
            self._is_loading = False
            self._btn_meta.setEnabled(True)
            self.reload_from_db()
            self._set_status("元数据刷新完成")
            QTimer.singleShot(3000, self._clear_status)
        
        from PySide6.QtCore import QTimer
        self._main.run_vndb_import_for_game_id(
            self._game_id,
            on_finished=on_finished,
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

    def _on_select_title(self) -> None:
        if not self._game:
            return

        candidates: list[tuple[str, str]] = []
        seen = set()

        raw = self._db().get_game_storage_debug(self._game_id)
        if raw:
            custom_name = str(raw.get("custom_name", "")).strip()
            if custom_name and custom_name not in seen:
                candidates.append((custom_name, "用户自定义"))
                seen.add(custom_name)

        if self._game.window_title and self._game.window_title not in seen:
            candidates.append((self._game.window_title, "窗口标题"))
            seen.add(self._game.window_title)

        if self._game.name and self._game.name not in seen:
            candidates.append((self._game.name, "目录名"))
            seen.add(self._game.name)

        if self._game.title_original and self._game.title_original not in seen:
            candidates.append((self._game.title_original, "VNDB 原名"))
            seen.add(self._game.title_original)

        if self._game.title_localized and self._game.title_localized not in seen:
            candidates.append((self._game.title_localized, "VNDB 译名"))
            seen.add(self._game.title_localized)

        if not candidates:
            QMessageBox.information(self, "无候选标题", "当前没有可选择的候选标题。")
            return

        from app.ui.dialogs.title_selector_dialog import TitleSelectorDialog

        selected = TitleSelectorDialog.get_title(
            current_name=self._game.name,
            candidates=candidates,
            parent=self,
        )

        if selected:
            self._db().update_game_identity(self._game_id, selected, self._game.launch_exe)
            QMessageBox.information(self, "标题已更新", f"已将游戏名称设置为：{selected}")
            self.reload_from_db()
            self._main.refresh_games()

    def _on_open_save_manager(self) -> None:
        self._main.open_save_manager(self._game_id)

    def _on_cover_drag_enter(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._cover.setStyleSheet("background:#3B82F6;border:2px dashed #60A5FA;border-radius:8px;")

    def _on_cover_drop(self, event: QDropEvent) -> None:
        self._cover.setStyleSheet("background:#252C36;border-radius:8px;")
        if not event.mimeData().hasUrls():
            return
        
        urls = event.mimeData().urls()
        if not urls:
            return
        
        file_path = Path(urls[0].toLocalFile())
        if not file_path.exists() or not file_path.is_file():
            QMessageBox.warning(self, "无效文件", "请拖拽有效的图片文件")
            return
        
        ext = file_path.suffix.lower()
        if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
            QMessageBox.warning(self, "格式不支持", "仅支持 JPG、PNG、WebP、GIF 格式")
            return
        
        from app.ui.dialogs.custom_cover_manager_dialog import CustomCoverManagerDialog
        dialog = CustomCoverManagerDialog(
            self._main,
            self._game_id,
            self._game.name,
            self._game.root_dir,
            str(file_path)
        )
        if dialog.exec():
            self.reload_from_db()
