"""Save manager window with async backup/restore progress."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.services.paths import (
    default_twodfan_sqlite_path,
    existing_twodfan_sqlite_files,
    twodfan_crawler_dir,
    twodfan_crawler_readme,
)
from app.services.twodfan_hints import twodfan_db_stats

from app.data.database import Database
from app.services.save_archive_service import (
    clear_directory_contents,
    directory_has_files,
    sha256_file,
    unzip_safely_with_progress,
    zip_directory_with_progress,
)
from app.services.save_path_resolver import resolve_save_path_candidates
from app.ui.dialogs.game_detail_dialog import reveal_in_explorer

if TYPE_CHECKING:
    from app.ui.main_window import MainWindow


def _slug_filename(name: str, max_len: int = 40) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name.strip())
    cleaned = cleaned.strip(" .") or "game"
    return cleaned[:max_len]


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.2f} MB"


class _SaveTaskSignals(QObject):
    progress = Signal(int, int, str)
    finished = Signal(object)
    failed = Signal(str)


class _BackupTask(QRunnable):
    def __init__(self, save_root: Path, zip_path: Path) -> None:
        super().__init__()
        self.signals = _SaveTaskSignals()
        self._save_root = save_root
        self._zip_path = zip_path

    def run(self) -> None:  # type: ignore[override]
        try:
            size = zip_directory_with_progress(
                self._save_root,
                self._zip_path,
                progress_cb=lambda d, t, n: self.signals.progress.emit(d, t, f"打包: {n}"),
            )
            checksum = sha256_file(self._zip_path)
            self.signals.finished.emit({"size": size, "checksum": checksum})
        except Exception as exc:  # pragma: no cover
            self.signals.failed.emit(str(exc))


class _RestoreTask(QRunnable):
    def __init__(
        self,
        *,
        backup_zip: Path,
        expected_sha256: str | None,
        dest_dir: Path,
        guard_zip: Path | None,
    ) -> None:
        super().__init__()
        self.signals = _SaveTaskSignals()
        self._backup_zip = backup_zip
        self._expected_sha256 = expected_sha256
        self._dest_dir = dest_dir
        self._guard_zip = guard_zip

    def run(self) -> None:  # type: ignore[override]
        try:
            if self._expected_sha256:
                actual = sha256_file(self._backup_zip)
                if actual != self._expected_sha256.lower():
                    raise ValueError(
                        "备份文件校验不通过，已阻止还原。\n"
                        f"期望: {self._expected_sha256}\n实际: {actual}"
                    )

            guard_result: dict[str, object] | None = None
            if self._guard_zip is not None:
                guard_size = zip_directory_with_progress(
                    self._dest_dir,
                    self._guard_zip,
                    progress_cb=lambda d, t, n: self.signals.progress.emit(
                        int(d * 40 / max(1, t)),
                        100,
                        f"保护备份: {n}",
                    ),
                )
                guard_hash = sha256_file(self._guard_zip)
                guard_result = {
                    "zip_path": str(self._guard_zip.resolve()),
                    "size": guard_size,
                    "checksum": guard_hash,
                }

            clear_directory_contents(self._dest_dir)
            unzip_safely_with_progress(
                self._backup_zip,
                self._dest_dir,
                progress_cb=lambda d, t, n: self.signals.progress.emit(
                    40 + int(d * 60 / max(1, t)),
                    100,
                    f"还原: {n}",
                ),
            )
            self.signals.finished.emit({"guard": guard_result})
        except Exception as exc:  # pragma: no cover
            self.signals.failed.emit(str(exc))


class SaveManagerWindow(QDialog):
    """Non-modal-friendly dialog: set ``Qt.Window`` from caller if desired."""

    def __init__(self, main: MainWindow, game_id: int) -> None:
        super().__init__(main)
        self._main = main
        self._game_id = game_id
        self._pool = QThreadPool(self)
        self._busy = False
        self._pending_backup: tuple[str, Path] | None = None
        self._pending_restore_guard_label: str | None = None
        self.setWindowTitle("存档管理")
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setModal(False)
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.resize(720, 520)

        root = QVBoxLayout(self)
        hint = QLabel(
            "在此指定<strong>本游戏</strong>的存档根目录，并可备份 / 还原 ZIP。"
            "点「自动发现」会合并<strong>内置规则</strong>与（若已配置）<strong>2DFan 线索库</strong>里"
            "能对应到本游戏、且路径在您电脑上真实存在的文件夹。"
        )
        hint.setWordWrap(True)
        hint.setTextFormat(Qt.TextFormat.RichText)
        hint.setStyleSheet("font-size:12px;")
        root.addWidget(hint)

        tw_group = QGroupBox("2DFan 线索库（全局 · 与仓库内爬虫联动）")
        tw_group.setStyleSheet("QGroupBox { font-weight: 600; margin-top: 8px; }")
        tw_lay = QVBoxLayout(tw_group)
        tw_intro = QLabel(
            "线索来自本仓库 <code>tools/2dfan-save-crawler</code> 生成的 SQLite，与当前游戏无关，"
            "保存后对所有游戏的「自动发现」生效。"
        )
        tw_intro.setWordWrap(True)
        tw_intro.setTextFormat(Qt.TextFormat.RichText)
        tw_intro.setStyleSheet("font-size:11px;")
        tw_lay.addWidget(tw_intro)

        tw_row = QHBoxLayout()
        tw_row.addWidget(QLabel("SQLite"))
        self._twodfan_edit = QLineEdit()
        self._twodfan_edit.setPlaceholderText("推荐：…/tools/2dfan-save-crawler/data/2dfan_saves.sqlite3")
        tw_row.addWidget(self._twodfan_edit, 1)
        self._btn_twodfan_browse = QPushButton("浏览…")
        self._btn_twodfan_browse.clicked.connect(self._browse_twodfan_db)
        tw_row.addWidget(self._btn_twodfan_browse)
        self._btn_twodfan_save = QPushButton("保存全局")
        self._btn_twodfan_save.setToolTip("写入本程序设置，供所有游戏自动发现使用")
        self._btn_twodfan_save.clicked.connect(self._persist_twodfan_db)
        tw_row.addWidget(self._btn_twodfan_save)
        self._btn_twodfan_hub = QPushButton("完整设置…")
        self._btn_twodfan_hub.setToolTip("打开与主窗口「更多」菜单相同的线索库向导（统计、打开爬虫目录与 README）")
        self._btn_twodfan_hub.clicked.connect(self._open_twodfan_library_dialog)
        tw_row.addWidget(self._btn_twodfan_hub)
        tw_lay.addLayout(tw_row)

        self._twodfan_stats = QLabel("")
        self._twodfan_stats.setWordWrap(True)
        self._twodfan_stats.setStyleSheet("font-size:11px;")
        tw_lay.addWidget(self._twodfan_stats)

        tw_links = QHBoxLayout()
        self._btn_twodfan_suggest = QPushButton("填入推荐路径")
        self._btn_twodfan_suggest.setToolTip("填入本仓库爬虫默认输出路径（文件可尚未生成）")
        self._btn_twodfan_suggest.clicked.connect(self._twodfan_fill_suggested_path)
        tw_links.addWidget(self._btn_twodfan_suggest)
        self._btn_twodfan_open_tool = QPushButton("打开爬虫目录")
        self._btn_twodfan_open_tool.clicked.connect(self._twodfan_open_crawler_dir)
        tw_links.addWidget(self._btn_twodfan_open_tool)
        self._btn_twodfan_readme = QPushButton("打开爬虫 README")
        self._btn_twodfan_readme.clicked.connect(self._twodfan_open_readme)
        tw_links.addWidget(self._btn_twodfan_readme)
        tw_links.addStretch(1)
        tw_lay.addLayout(tw_links)
        root.addWidget(tw_group)

        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("存档路径"))
        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("选择或粘贴存档根目录…")
        path_row.addWidget(self._path_edit, 1)
        self._btn_browse = QPushButton("浏览…")
        self._btn_browse.clicked.connect(self._browse_save_root)
        path_row.addWidget(self._btn_browse)
        self._btn_save_path = QPushButton("保存路径")
        self._btn_save_path.setToolTip("写入数据库，与扫描/VNDB 无关")
        self._btn_save_path.clicked.connect(self._persist_save_root)
        path_row.addWidget(self._btn_save_path)
        self._btn_auto_detect = QPushButton("自动发现")
        self._btn_auto_detect.setToolTip(
            "按置信度列出本机已存在的候选目录；含内置规则、启发式扫描及 2DFan 线索（若已配置且可匹配）"
        )
        self._btn_auto_detect.clicked.connect(self._auto_detect_save_root)
        path_row.addWidget(self._btn_auto_detect)
        root.addLayout(path_row)

        act_row = QHBoxLayout()
        self._btn_open = QPushButton("打开存档目录")
        self._btn_open.clicked.connect(self._open_save_dir)
        act_row.addWidget(self._btn_open)
        self._btn_backup = QPushButton("备份为 ZIP")
        self._btn_backup.setToolTip("将当前存档目录打包到数据目录")
        self._btn_backup.clicked.connect(self._backup_zip)
        act_row.addWidget(self._btn_backup)
        self._btn_restore = QPushButton("还原到选中备份")
        self._btn_restore.setToolTip("覆盖前先自动备份当前存档，再解压所选 ZIP")
        self._btn_restore.clicked.connect(self._restore_from_selection)
        act_row.addWidget(self._btn_restore)
        act_row.addStretch(1)
        root.addLayout(act_row)

        prog_row = QHBoxLayout()
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setVisible(False)
        prog_row.addWidget(self._progress, 1)
        self._progress_label = QLabel("")
        self._progress_label.setStyleSheet("font-size:11px;")
        prog_row.addWidget(self._progress_label)
        root.addLayout(prog_row)

        root.addWidget(QLabel("备份列表"))
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["时间", "名称", "大小"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        root.addWidget(self._table, 1)

        btn_row = QHBoxLayout()
        self._btn_rename = QPushButton("重命名所选")
        self._btn_rename.clicked.connect(self._rename_selected)
        btn_row.addWidget(self._btn_rename)
        self._btn_delete = QPushButton("删除所选")
        self._btn_delete.clicked.connect(self._delete_selected)
        btn_row.addWidget(self._btn_delete)
        self._btn_refresh = QPushButton("刷新")
        self._btn_refresh.clicked.connect(self.reload_all)
        btn_row.addWidget(self._btn_refresh)
        btn_row.addStretch(1)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

        self.reload_all()

    def _db(self) -> Database:
        return self._main.db

    def _user_id(self) -> int:
        return self._main.current_user_id

    def _backup_root(self) -> Path:
        return self._db().base_dir / "save-backups" / str(self._user_id()) / str(self._game_id)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        for w in (
            self._btn_browse,
            self._btn_save_path,
            self._btn_auto_detect,
            self._btn_open,
            self._btn_backup,
            self._btn_restore,
            self._btn_rename,
            self._btn_delete,
            self._btn_refresh,
            self._path_edit,
            self._table,
            self._twodfan_edit,
            self._btn_twodfan_browse,
            self._btn_twodfan_save,
            self._btn_twodfan_hub,
            self._btn_twodfan_suggest,
            self._btn_twodfan_open_tool,
            self._btn_twodfan_readme,
        ):
            w.setEnabled(not busy)
        self._progress.setVisible(busy)
        if not busy:
            self._progress.setValue(0)
            self._progress_label.setText("")

    def _on_task_progress(self, done: int, total: int, title: str) -> None:
        if total <= 0:
            return
        pct = int(done * 100 / total)
        self._progress.setValue(max(0, min(100, pct)))
        self._progress_label.setText(title[:60])

    def _on_task_failed(self, title: str, message: str) -> None:
        self._set_busy(False)
        self._pending_backup = None
        self._pending_restore_guard_label = None
        QMessageBox.critical(self, title, message)

    def reload_all(self) -> None:
        game = self._db().get_game_by_id(self._user_id(), self._game_id)
        if game is None:
            QMessageBox.warning(self, "记录不存在", "该游戏可能已被删除。")
            self.close()
            return
        self.setWindowTitle(f"存档管理 — {game.name}")
        self._path_edit.setText((game.custom_save_root or "").strip())
        self._twodfan_edit.setText(self._db().get_twodfan_hints_db_path())
        self._refresh_twodfan_stats()

        rows = self._db().list_save_backups(self._user_id(), self._game_id)
        self._table.setRowCount(len(rows))
        for i, rec in enumerate(rows):
            t_item = QTableWidgetItem(rec.created_at.replace("T", " ")[:19])
            t_item.setData(Qt.ItemDataRole.UserRole, rec.id)
            self._table.setItem(i, 0, t_item)
            self._table.setItem(i, 1, QTableWidgetItem(rec.label))
            self._table.setItem(i, 2, QTableWidgetItem(_fmt_size(rec.size_bytes)))
        self._table.resizeColumnsToContents()

    def _current_save_root(self) -> Path | None:
        raw = self._path_edit.text().strip()
        if not raw:
            return None
        return Path(raw)

    def _refresh_twodfan_stats(self) -> None:
        raw = self._twodfan_edit.text().strip()
        if not raw:
            self._twodfan_stats.setText(
                "状态：未配置线索库。可点「填入推荐路径」或主界面「更多 → 2DFan 线索库与爬虫…」。"
            )
            return
        p = Path(raw)
        if not p.is_file():
            self._twodfan_stats.setText("状态：文件尚不存在。请先在 tools/2dfan-save-crawler 运行爬虫生成 SQLite。")
            return
        stats = twodfan_db_stats(p)
        if stats is None:
            self._twodfan_stats.setText("状态：无法读取（可能不是爬虫生成的库）。")
            return
        np, nh = stats
        self._twodfan_stats.setText(f"状态：已就绪 — 下载页 {np} 条，存档线索 {nh} 条。")

    def _open_twodfan_library_dialog(self) -> None:
        from app.ui.dialogs.twodfan_library_dialog import TwodfanLibraryDialog

        dlg = TwodfanLibraryDialog(self._main)
        dlg.exec()
        self._twodfan_edit.setText(self._db().get_twodfan_hints_db_path())
        self._refresh_twodfan_stats()

    def _twodfan_fill_suggested_path(self) -> None:
        cand = default_twodfan_sqlite_path()
        if cand is not None:
            self._twodfan_edit.setText(str(cand))
            self._refresh_twodfan_stats()
            return
        found = existing_twodfan_sqlite_files()
        if found:
            self._twodfan_edit.setText(str(found[0]))
            self._refresh_twodfan_stats()
            return
        QMessageBox.information(
            self,
            "未找到爬虫目录",
            "未检测到本仓库下的 tools/2dfan-save-crawler。\n请手动浏览选择已生成的 .sqlite3，或从源码目录启动本程序。",
        )

    def _twodfan_open_crawler_dir(self) -> None:
        d = twodfan_crawler_dir()
        if d is None:
            QMessageBox.information(
                self,
                "未找到爬虫目录",
                "未检测到 tools/2dfan-save-crawler。\n请确认从克隆仓库根目录运行本程序。",
            )
            return
        try:
            reveal_in_explorer(str(d))
        except OSError as e:
            QMessageBox.warning(self, "无法打开", str(e))

    def _twodfan_open_readme(self) -> None:
        p = twodfan_crawler_readme()
        if p is None or not p.is_file():
            QMessageBox.information(self, "无 README", "未找到 tools/2dfan-save-crawler/README.md。")
            return
        url = QUrl.fromLocalFile(str(p.resolve()))
        if not QDesktopServices.openUrl(url):
            QMessageBox.warning(self, "无法打开", "系统未关联打开方式，请手动打开 README.md。")

    def _browse_twodfan_db(self) -> None:
        start = self._twodfan_edit.text().strip() or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 2DFan 线索 SQLite",
            start,
            "SQLite (*.sqlite3 *.db);;All (*.*)",
        )
        if path:
            self._twodfan_edit.setText(path)
            self._refresh_twodfan_stats()

    def _persist_twodfan_db(self) -> None:
        if self._busy:
            return
        raw = self._twodfan_edit.text().strip()
        if raw and not Path(raw).is_file():
            QMessageBox.warning(self, "文件不存在", "请确认 SQLite 文件路径正确。")
            return
        self._db().set_twodfan_hints_db_path(raw)
        self._refresh_twodfan_stats()
        QMessageBox.information(
            self,
            "已保存",
            "2DFan 线索库路径已写入全局设置。\n下方「自动发现」将尝试合并该库中的路径（需与本游戏名能对上，且目录真实存在）。",
        )

    def _browse_save_root(self) -> None:
        start = self._path_edit.text().strip() or str(Path.home())
        d = QFileDialog.getExistingDirectory(self, "选择存档根目录", start)
        if d:
            self._path_edit.setText(d)

    def _persist_save_root(self) -> None:
        if self._busy:
            return
        p = self._current_save_root()
        if p is not None and not p.is_dir():
            QMessageBox.warning(self, "路径无效", "所选路径不是已存在的文件夹。")
            return
        self._db().set_game_custom_save_root(self._game_id, str(p) if p is not None else "")
        self._main.refresh_games()
        QMessageBox.information(self, "已保存", "存档路径已写入数据库。")

    def _auto_detect_save_root(self) -> None:
        if self._busy:
            return
        game = self._db().get_game_by_id(self._user_id(), self._game_id)
        if game is None:
            QMessageBox.warning(self, "记录不存在", "该游戏可能已被删除。")
            return
        tdb = self._db().get_twodfan_hints_db_path().strip()
        rows = resolve_save_path_candidates(
            game,
            max_results=8,
            twodfan_hints_db_path=tdb or None,
        )
        if not rows:
            msg = "当前未发现本机已存在的候选存档目录（内置规则、启发式与 2DFan 均已考虑）。\n\n"
            if not tdb:
                msg += (
                    "您尚未配置 2DFan 线索库。若使用本仓库内的爬虫，可在上方「填入推荐路径」并保存，"
                    "或从主界面「更多 → 2DFan 线索库与爬虫…」完成向导。\n\n"
                )
            else:
                msg += f"已配置线索库：\n{tdb}\n"
                stats = twodfan_db_stats(tdb)
                if stats is not None:
                    np, nh = stats
                    msg += f"库内统计：下载页 {np} 条，线索 {nh} 条。\n"
                    if np == 0:
                        msg += "库为空：请在本机终端进入 tools/2dfan-save-crawler 运行爬虫更新数据。\n"
                    else:
                        msg += (
                            "若库有数据但仍无候选，多为标题对不上或线索里的路径在您电脑上不存在；"
                            "可对照 README 检查网络抓取是否成功（如 HTTP 403）。\n"
                        )
                msg += "\n"
            msg += "您仍可手动「浏览…」选择存档文件夹，再点「保存路径」。"
            QMessageBox.information(self, "未找到候选路径", msg)
            return
        n_2dfan = sum(1 for c in rows if c.source == "2dfan")
        hint_line = ""
        if n_2dfan:
            hint_line = f"其中 {n_2dfan} 条来自 2DFan 线索库（标记为 [2DFan]）。\n"
        labels = []
        for c in rows:
            tag = "[2DFan] " if c.source == "2dfan" else ""
            reason = (c.reason or "").replace("\n", " ")
            if len(reason) > 100:
                reason = reason[:97] + "…"
            labels.append(f"{tag}[{c.confidence}] {c.path}  ({c.source}: {reason})")
        picked, ok = QInputDialog.getItem(
            self,
            "选择推荐存档路径",
            hint_line + "按置信度排序；选中后可再点「打开存档目录」验证，最后「保存路径」写入本游戏。",
            labels,
            0,
            False,
        )
        if not ok or not picked:
            return
        idx = labels.index(picked)
        self._path_edit.setText(str(rows[idx].path))

    def _open_save_dir(self) -> None:
        if self._busy:
            return
        p = self._current_save_root()
        if p is None or not p.is_dir():
            QMessageBox.warning(self, "无法打开", "请先指定并保存有效的存档目录。")
            return
        try:
            reveal_in_explorer(str(p))
        except OSError as e:
            QMessageBox.warning(self, "无法打开", str(e))

    def _selected_backup_id(self) -> int | None:
        r = self._table.currentRow()
        if r < 0:
            return None
        it = self._table.item(r, 0)
        if it is None:
            return None
        raw = it.data(Qt.ItemDataRole.UserRole)
        return int(raw) if raw is not None else None

    def _backup_zip(self) -> None:
        if self._busy:
            return
        root = self._current_save_root()
        if root is None or not root.is_dir():
            QMessageBox.warning(self, "无法备份", "请先指定并保存有效的存档目录。")
            return
        if not directory_has_files(root):
            QMessageBox.information(self, "跳过", "存档目录为空，未生成备份。")
            return
        default_label = f"备份 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        label, ok = QInputDialog.getText(self, "备份名称", "显示名称（可留空使用默认）:", text=default_label)
        if not ok:
            return
        label = label.strip() or default_label
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._backup_root().mkdir(parents=True, exist_ok=True)
        zip_path = self._backup_root() / f"{stamp}_{_slug_filename(label)}.zip"
        self._pending_backup = (label, zip_path)
        task = _BackupTask(root, zip_path)
        task.signals.progress.connect(self._on_task_progress, Qt.QueuedConnection)
        task.signals.failed.connect(
            lambda msg: self._on_task_failed("备份失败", msg), Qt.QueuedConnection
        )
        task.signals.finished.connect(self._on_backup_finished, Qt.QueuedConnection)
        self._set_busy(True)
        self._progress_label.setText("开始备份…")
        self._pool.start(task)

    def _on_backup_finished(self, payload: object) -> None:
        self._set_busy(False)
        pending = self._pending_backup
        self._pending_backup = None
        if pending is None:
            return
        label, zip_path = pending
        data = payload if isinstance(payload, dict) else {}
        size = int(data.get("size", 0))
        checksum = str(data.get("checksum", "")) or None
        self._db().insert_save_backup(
            self._user_id(),
            self._game_id,
            label,
            str(zip_path.resolve()),
            size,
            checksum_sha256=checksum,
        )
        self.reload_all()
        QMessageBox.information(self, "完成", f"已保存：\n{zip_path}")

    def _restore_from_selection(self) -> None:
        if self._busy:
            return
        bid = self._selected_backup_id()
        if bid is None:
            QMessageBox.information(self, "提示", "请先在列表中选择一条备份。")
            return
        rec = self._db().get_save_backup(self._user_id(), bid)
        if rec is None:
            QMessageBox.warning(self, "无效", "找不到所选备份。")
            return
        zp = Path(rec.zip_path)
        if not zp.is_file():
            QMessageBox.warning(self, "文件缺失", f"ZIP 不存在或已被移动：\n{zp}")
            return
        dest = self._current_save_root()
        if dest is None or not dest.is_dir():
            QMessageBox.warning(self, "无法还原", "请先指定并保存有效的存档目录。")
            return

        r = QMessageBox.question(
            self,
            "确认还原",
            f"将把「{rec.label}」解压到：\n{dest}\n\n"
            "当前目录内文件将被清空后覆盖；操作前会自动再打包一份当前存档。\n\n"
            "是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if r != QMessageBox.StandardButton.Yes:
            return

        guard_zip: Path | None = None
        if directory_has_files(dest):
            guard_dir = self._backup_root()
            guard_dir.mkdir(parents=True, exist_ok=True)
            gstamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            guard_zip = guard_dir / f"{gstamp}_restore_guard.zip"
            self._pending_restore_guard_label = (
                f"还原前自动备份 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        else:
            self._pending_restore_guard_label = None

        task = _RestoreTask(
            backup_zip=zp,
            expected_sha256=rec.checksum_sha256,
            dest_dir=dest,
            guard_zip=guard_zip,
        )
        task.signals.progress.connect(self._on_task_progress, Qt.QueuedConnection)
        task.signals.failed.connect(
            lambda msg: self._on_task_failed("还原失败", msg), Qt.QueuedConnection
        )
        task.signals.finished.connect(self._on_restore_finished, Qt.QueuedConnection)
        self._set_busy(True)
        self._progress_label.setText("开始还原…")
        self._pool.start(task)

    def _on_restore_finished(self, payload: object) -> None:
        self._set_busy(False)
        data = payload if isinstance(payload, dict) else {}
        guard = data.get("guard")
        if isinstance(guard, dict) and self._pending_restore_guard_label:
            self._db().insert_save_backup(
                self._user_id(),
                self._game_id,
                self._pending_restore_guard_label,
                str(guard.get("zip_path", "")),
                int(guard.get("size", 0)),
                checksum_sha256=(str(guard.get("checksum", "")) or None),
            )
        self._pending_restore_guard_label = None
        self.reload_all()
        QMessageBox.information(self, "完成", "还原已完成。")

    def _rename_selected(self) -> None:
        if self._busy:
            return
        bid = self._selected_backup_id()
        if bid is None:
            QMessageBox.information(self, "提示", "请先选择一条备份。")
            return
        rec = self._db().get_save_backup(self._user_id(), bid)
        if rec is None:
            return
        text, ok = QInputDialog.getText(self, "重命名", "新的显示名称:", text=rec.label)
        if not ok:
            return
        if not self._db().update_save_backup_label(self._user_id(), bid, text):
            QMessageBox.warning(self, "失败", "无法更新该记录。")
            return
        self.reload_all()

    def _delete_selected(self) -> None:
        if self._busy:
            return
        bid = self._selected_backup_id()
        if bid is None:
            QMessageBox.information(self, "提示", "请先选择一条备份。")
            return
        if QMessageBox.question(self, "确认删除", "将删除数据库记录及对应 ZIP 文件。") != QMessageBox.Yes:
            return
        zp = self._db().delete_save_backup_row(self._user_id(), bid)
        if zp:
            try:
                Path(zp).unlink(missing_ok=True)
            except OSError:
                pass
        self.reload_all()
