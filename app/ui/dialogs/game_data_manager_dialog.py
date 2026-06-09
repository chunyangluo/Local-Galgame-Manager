"""Comprehensive data management: database records + file system management."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.data.database import GameRecord
from app.services.game_delete_service import (
    confirm_delete_game,
    delete_game_from_library,
    set_skip_delete_game_confirm,
)

if TYPE_CHECKING:
    from app.ui.main_window import MainWindow

log = logging.getLogger(__name__)


def _fmt_size(size_bytes: int) -> str:
    """Format bytes to human-readable size."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def _dir_size(path: Path) -> int:
    """Calculate total size of a directory recursively."""
    total = 0
    try:
        for entry in os.scandir(path):
            if entry.is_file():
                total += entry.stat().st_size
            elif entry.is_dir():
                total += _dir_size(Path(entry.path))
    except (PermissionError, OSError):
        pass
    return total


def _count_files(path: Path) -> int:
    """Count files in a directory recursively."""
    count = 0
    try:
        for entry in os.scandir(path):
            if entry.is_file():
                count += 1
            elif entry.is_dir():
                count += _count_files(Path(entry.path))
    except (PermissionError, OSError):
        pass
    return count


class _ScanWorkerSignals(QObject):
    finished = Signal(dict)  # {dir_path: (size, file_count)}


class _ScanWorker(QThread):
    """Background worker to scan directory sizes."""

    def __init__(self, dirs: list[Path], parent: QObject | None = None):
        super().__init__(parent)
        self._dirs = dirs
        self.signals = _ScanWorkerSignals(parent)

    def run(self) -> None:
        result = {}
        for d in self._dirs:
            if d.is_dir():
                size = _dir_size(d)
                count = _count_files(d)
                result[str(d)] = (size, count)
        self.signals.finished.emit(result)


class GameDataManagerDialog(QDialog):
    def __init__(self, main: MainWindow) -> None:
        super().__init__(main)
        self._main = main
        self.setWindowTitle("数据管理")
        self.resize(920, 640)
        self._scan_worker = None

        root = QVBoxLayout(self)

        self._tabs = QTabWidget()
        root.addWidget(self._tabs, 1)

        self._build_database_tab()
        self._build_file_manager_tab()

        close_box = QDialogButtonBox(QDialogButtonBox.Close)
        close_box.rejected.connect(self.reject)
        root.addWidget(close_box)

    # ---- Database Tab ----

    def _build_database_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        hint = QLabel(
            "管理游戏库中的条目。默认只删除库内记录与软件缓存；"
            "可在下方勾选「同时删除安装文件夹」以一并删除磁盘上的游戏目录。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#93A1B6;font-size:12px;")
        layout.addWidget(hint)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["名称", "安装目录", "游玩次数", "总时长", "收藏"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSortingEnabled(True)
        layout.addWidget(self._table, 1)

        row = QHBoxLayout()
        self._chk_delete_install = QCheckBox("同时删除安装文件夹")
        self._chk_delete_install.setChecked(False)
        self._chk_delete_install.setToolTip(
            "勾选后，删除时将一并移除选中游戏的安装目录（不可恢复）。"
        )
        row.addWidget(self._chk_delete_install)

        self._btn_delete = QPushButton("删除选中游戏")
        self._btn_delete.setProperty("btnRole", "danger")
        self._btn_delete.clicked.connect(self._delete_selected)
        row.addWidget(self._btn_delete)

        self._btn_refresh = QPushButton("刷新列表")
        self._btn_refresh.clicked.connect(self._reload_db)
        row.addWidget(self._btn_refresh)

        self._btn_reset_confirm = QPushButton("恢复删除确认")
        self._btn_reset_confirm.setToolTip("重新启用删除游戏时的二次确认对话框")
        self._btn_reset_confirm.clicked.connect(self._reset_delete_confirm)
        row.addWidget(self._btn_reset_confirm)

        self._btn_clean_dead = QPushButton("清理死链接")
        self._btn_clean_dead.setToolTip("检测并清理文件夹已不存在的游戏记录")
        self._btn_clean_dead.clicked.connect(self._clean_dead_links)
        row.addWidget(self._btn_clean_dead)

        row.addStretch(1)
        layout.addLayout(row)

        self._tabs.addTab(tab, "数据库管理")
        self._reload_db()

    # ---- File Manager Tab ----

    def _build_file_manager_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        hint = QLabel(
            "管理程序涉及的所有游戏数据文件。可查看各目录占用空间，"
            "选择并删除不需要的文件，或一键清空归档目录。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#93A1B6;font-size:12px;")
        layout.addWidget(hint)

        # Directory overview
        self._dir_group = QGroupBox("目录概览")
        dir_layout = QVBoxLayout(self._dir_group)

        self._dir_tree = QTreeWidget()
        self._dir_tree.setHeaderLabels(["目录", "路径", "大小", "文件数"])
        self._dir_tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._dir_tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self._dir_tree.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._dir_tree.header().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._dir_tree.setSortingEnabled(True)
        dir_layout.addWidget(self._dir_tree)

        dir_btn_row = QHBoxLayout()
        self._btn_scan_dirs = QPushButton("扫描目录大小")
        self._btn_scan_dirs.clicked.connect(self._scan_directory_sizes)
        dir_btn_row.addWidget(self._btn_scan_dirs)

        self._dir_progress = QProgressBar()
        self._dir_progress.setMaximumHeight(6)
        self._dir_progress.setTextVisible(False)
        self._dir_progress.setVisible(False)
        dir_btn_row.addWidget(self._dir_progress, 1)

        dir_layout.addLayout(dir_btn_row)
        layout.addWidget(self._dir_group)

        # File browser for selected directory
        self._file_group = QGroupBox("文件浏览（双击目录展开，右键可删除）")
        file_layout = QVBoxLayout(self._file_group)

        self._file_tree = QTreeWidget()
        self._file_tree.setHeaderLabels(["名称", "大小", "类型"])
        self._file_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self._file_tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._file_tree.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._file_tree.setSortingEnabled(True)
        self._file_tree.itemDoubleClicked.connect(self._on_file_double_clicked)
        file_layout.addWidget(self._file_tree, 1)

        file_btn_row = QHBoxLayout()

        self._btn_open_dir = QPushButton("打开目录")
        self._btn_open_dir.clicked.connect(self._open_selected_dir)
        file_btn_row.addWidget(self._btn_open_dir)

        self._btn_delete_files = QPushButton("删除选中文件/文件夹")
        self._btn_delete_files.setProperty("btnRole", "danger")
        self._btn_delete_files.clicked.connect(self._delete_selected_files)
        file_btn_row.addWidget(self._btn_delete_files)

        self._btn_clear_archive = QPushButton("一键清空归档目录")
        self._btn_clear_archive.setProperty("btnRole", "danger")
        self._btn_clear_archive.setToolTip("清空 _archive 目录中的所有文件（解压后的原始压缩包）")
        self._btn_clear_archive.clicked.connect(self._clear_archive_dir)
        file_btn_row.addWidget(self._btn_clear_archive)

        self._btn_clear_failed = QPushButton("一键清空失败目录")
        self._btn_clear_failed.setProperty("btnRole", "danger")
        self._btn_clear_failed.setToolTip("清空 _failed 目录中的所有文件（解压失败的压缩包）")
        self._btn_clear_failed.clicked.connect(self._clear_failed_dir)
        file_btn_row.addWidget(self._btn_clear_failed)

        file_btn_row.addStretch(1)
        file_layout.addLayout(file_btn_row)
        layout.addWidget(self._file_group, 1)

        self._tabs.addTab(tab, "文件管理")

        # Populate directory overview
        self._populate_dir_overview()

    # ---- Database Tab Methods ----

    def _db(self):
        return self._main.db

    def _user_id(self) -> int:
        return self._main.current_user_id

    def _reload_db(self) -> None:
        games = self._db().list_games(self._user_id())
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(games))
        for i, g in enumerate(games):
            self._set_row(i, g)
        self._table.setSortingEnabled(True)
        if games:
            self._table.selectRow(0)

    def _set_row(self, row: int, game: GameRecord) -> None:
        name_item = QTableWidgetItem(game.name)
        name_item.setData(Qt.ItemDataRole.UserRole, game.id)
        self._table.setItem(row, 0, name_item)
        self._table.setItem(row, 1, QTableWidgetItem(game.root_dir))
        self._table.setItem(row, 2, QTableWidgetItem(str(game.play_count)))
        total = game.total_play_seconds
        if total >= 3600:
            dur = f"{total // 3600}时{(total % 3600) // 60}分"
        elif total >= 60:
            dur = f"{total // 60}分{total % 60}秒"
        else:
            dur = f"{total}秒"
        self._table.setItem(row, 3, QTableWidgetItem(dur))
        self._table.setItem(row, 4, QTableWidgetItem("是" if game.favorite else ""))

    def _selected_games(self) -> list[GameRecord]:
        """Return all selected game records."""
        rows = set(idx.row() for idx in self._table.selectedIndexes())
        result = []
        for r in rows:
            it = self._table.item(r, 0)
            if it is None:
                continue
            gid = it.data(Qt.ItemDataRole.UserRole)
            if gid is None:
                continue
            game = self._db().get_game_by_id(self._user_id(), int(gid))
            if game:
                result.append(game)
        return result

    def _delete_selected(self) -> None:
        games = self._selected_games()
        if not games:
            QMessageBox.information(self, "未选择", "请先在列表中选中要删除的游戏。")
            return

        if len(games) == 1:
            game = games[0]
            decision = confirm_delete_game(
                self,
                self._db(),
                game.name,
                install_dir=game.root_dir,
                fallback_delete_install=self._chk_delete_install.isChecked(),
            )
            if decision is None:
                return
            try:
                name = delete_game_from_library(
                    self._db(),
                    game.id,
                    delete_install_folder=decision.delete_install_folder,
                )
            except (ValueError, OSError) as exc:
                QMessageBox.warning(self, "删除失败", str(exc))
                self._main.refresh_games()
                return
            self._main.refresh_games()
            if decision.delete_install_folder:
                self._main.status.setText(f"已删除库记录及安装目录：{name}")
            else:
                self._main.status.setText(f"已从库中删除：{name}")
        else:
            # Batch delete
            delete_install = self._chk_delete_install.isChecked()
            msg = f"确定要删除选中的 {len(games)} 个游戏吗？"
            if delete_install:
                msg += "\n\n⚠️ 已勾选「同时删除安装文件夹」，游戏目录将被永久删除！"
            reply = QMessageBox.question(
                self, "批量删除确认", msg,
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

            success = 0
            failed = 0
            for game in games:
                try:
                    delete_game_from_library(
                        self._db(), game.id,
                        delete_install_folder=delete_install,
                    )
                    success += 1
                except Exception:
                    failed += 1

            self._main.refresh_games()
            self._main.status.setText(
                f"批量删除完成：成功 {success}，失败 {failed}"
            )

        self._reload_db()

    def _reset_delete_confirm(self) -> None:
        set_skip_delete_game_confirm(self._db(), False)
        QMessageBox.information(self, "已恢复", "删除游戏时将再次显示确认对话框。")

    def _clean_dead_links(self) -> None:
        """Detect and clean up games whose folders no longer exist."""
        dead_games = self._db().list_dead_games()
        if not dead_games:
            QMessageBox.information(self, "无死链接", "所有游戏的文件夹均存在，无需清理。")
            return

        count = len(dead_games)
        names = [g.name or g.root_dir for g in dead_games[:15]]
        name_list = "\n".join(f"  • {n}" for n in names)
        if count > 15:
            name_list += f"\n  … 还有 {count - 15} 个"

        msg = (
            f"检测到 {count} 个游戏的文件夹已不存在：\n\n"
            f"{name_list}\n\n"
            f"选择清理方式：\n"
            f"• 「清理」— 删除无自定义数据的死链接\n"
            f"• 「全部清理」— 删除所有死链接（含自定义数据）\n"
            f"• 「取消」— 不清理"
        )

        box = QMessageBox(self)
        box.setWindowTitle(f"清理死链接（{count} 个）")
        box.setText(msg)
        btn_clean = box.addButton("清理（保留自定义数据）", QMessageBox.AcceptRole)
        btn_clean_all = box.addButton("全部清理", QMessageBox.DestructiveRole)
        btn_cancel = box.addButton("取消", QMessageBox.RejectRole)
        box.exec()

        clicked = box.clickedButton()
        if clicked == btn_cancel:
            return

        keep_custom = clicked == btn_clean
        ids = [g.id for g in dead_games]
        removed = self._db().remove_games_by_ids(ids, keep_custom=keep_custom)
        kept = count - removed

        log.info("Cleaned %d dead links from data manager (%d kept)", removed, kept)

        self._main.refresh_games()
        self._reload_db()

        result_msg = f"已清理 {removed} 个死链接"
        if kept:
            result_msg += f"，保留 {kept} 个含自定义数据的记录"
        self._main.status.setText(result_msg)
        QMessageBox.information(self, "清理完成", result_msg)

    # ---- File Manager Tab Methods ----

    def _get_managed_directories(self) -> list[tuple[str, Path]]:
        """Return list of (label, path) for all managed directories."""
        dirs: list[tuple[str, Path]] = []

        # Auto-extract directories
        try:
            from app.services.auto_extract_service import read_directory_config
            config = read_directory_config()
            label_map = {
                "watch": "监控目录 (watch)",
                "target": "解压目标 ( target)",
                "archive": "归档目录 (archive)",
                "failed": "失败目录 (failed)",
                "temp": "临时目录 (temp)",
                "game_save": "存档目录 (game_save)",
            }
            for key, label in label_map.items():
                path_str = config.get(key, "")
                if path_str:
                    dirs.append((label, Path(path_str)))
        except Exception:
            pass

        # App data directories
        try:
            from app.services.app_data_dir import get_app_data_dir
            data_dir = get_app_data_dir()
            dirs.append(("应用数据目录", data_dir))
            dirs.append(("封面缓存", data_dir / "covers"))
            dirs.append(("日志目录", data_dir / "logs"))
            dirs.append(("存档备份", data_dir / "save-backups"))
        except Exception:
            pass

        # Game install directories from scan roots
        try:
            roots = self._db().list_scan_roots()
            for root in roots:
                dirs.append(("扫描根目录", Path(root)))
        except Exception:
            pass

        return dirs

    def _populate_dir_overview(self) -> None:
        """Populate the directory overview tree (without sizes)."""
        self._dir_tree.clear()
        dirs = self._get_managed_directories()
        for label, path in dirs:
            item = QTreeWidgetItem([label, str(path), "—", "—"])
            item.setData(0, Qt.ItemDataRole.UserRole, str(path))
            exists = path.is_dir()
            if not exists:
                item.setForeground(0, Qt.gray)
                item.setText(2, "不存在")
            self._dir_tree.addTopLevelItem(item)

    def _scan_directory_sizes(self) -> None:
        """Scan all managed directories for sizes in background."""
        if self._scan_worker is not None:
            return

        dirs = self._get_managed_directories()
        existing = [p for _, p in dirs if p.is_dir()]

        self._btn_scan_dirs.setEnabled(False)
        self._dir_progress.setVisible(True)
        self._dir_progress.setRange(0, 0)  # Indeterminate

        self._scan_worker = _ScanWorker(existing, self)
        self._scan_worker.signals.finished.connect(self._on_dir_scan_finished)
        self._scan_worker.start()

    def _on_dir_scan_finished(self, result: dict) -> None:
        """Handle directory scan completion."""
        self._btn_scan_dirs.setEnabled(True)
        self._dir_progress.setVisible(False)
        self._scan_worker = None

        # Update tree items
        for i in range(self._dir_tree.topLevelItemCount()):
            item = self._dir_tree.topLevelItem(i)
            path = item.data(0, Qt.ItemDataRole.UserRole)
            if path in result:
                size, count = result[path]
                item.setText(2, _fmt_size(size))
                item.setText(3, str(count))

        log.info("Directory scan completed: %d directories", len(result))

    def _on_file_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Double-click a directory in the file tree to expand it."""
        path_data = item.data(0, Qt.ItemDataRole.UserRole)
        if path_data and Path(path_data).is_dir():
            self._load_file_tree(Path(path_data))

    def _load_file_tree(self, directory: Path) -> None:
        """Load files from a directory into the file tree."""
        self._file_tree.clear()
        self._file_group.setTitle(f"文件浏览 — {directory}")

        if not directory.is_dir():
            return

        try:
            entries = sorted(directory.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except (PermissionError, OSError) as e:
            QMessageBox.warning(self, "无法访问", f"无法读取目录:\n{e}")
            return

        for entry in entries:
            try:
                if entry.is_dir():
                    child_count = _count_files(entry)
                    size = _dir_size(entry)
                    item = QTreeWidgetItem([
                        f"📁 {entry.name}",
                        _fmt_size(size),
                        f"文件夹 ({child_count} 文件)",
                    ])
                    item.setData(0, Qt.ItemDataRole.UserRole, str(entry))
                    item.setData(0, Qt.ItemDataRole.UserRole + 1, "dir")
                else:
                    stat = entry.stat()
                    suffix = entry.suffix.upper().lstrip(".") if entry.suffix else "文件"
                    item = QTreeWidgetItem([
                        f"📄 {entry.name}",
                        _fmt_size(stat.st_size),
                        suffix,
                    ])
                    item.setData(0, Qt.ItemDataRole.UserRole, str(entry))
                    item.setData(0, Qt.ItemDataRole.UserRole + 1, "file")
                self._file_tree.addTopLevelItem(item)
            except (PermissionError, OSError):
                pass

    def _open_selected_dir(self) -> None:
        """Open the selected directory in system file explorer."""
        # Try file tree first
        item = self._file_tree.currentItem()
        if item:
            path_data = item.data(0, Qt.ItemDataRole.UserRole)
            if path_data:
                path = Path(path_data)
                if path.is_dir():
                    self._reveal(path)
                    return

        # Try directory overview tree
        item = self._dir_tree.currentItem()
        if item:
            path_data = item.data(0, Qt.ItemDataRole.UserRole)
            if path_data:
                path = Path(path_data)
                if path.is_dir():
                    self._reveal(path)
                    return

        # If nothing selected, load the first directory from overview
        item = self._dir_tree.topLevelItem(0)
        if item:
            path_data = item.data(0, Qt.ItemDataRole.UserRole)
            if path_data:
                path = Path(path_data)
                if path.is_dir():
                    self._reveal(path)

    def _reveal(self, path: Path) -> None:
        """Reveal path in system file explorer."""
        try:
            from app.utils.file_ops import reveal_in_explorer
            reveal_in_explorer(str(path))
        except Exception as e:
            QMessageBox.warning(self, "无法打开", f"无法在资源管理器中打开:\n{e}")

    def _delete_selected_files(self) -> None:
        """Delete selected files/folders from the file tree."""
        items = self._file_tree.selectedItems()
        if not items:
            # Try from directory overview
            item = self._dir_tree.currentItem()
            if item:
                items = [item]
            else:
                QMessageBox.information(self, "未选择", "请先选择要删除的文件或文件夹。")
                return

        paths = []
        for item in items:
            path_data = item.data(0, Qt.ItemDataRole.UserRole)
            if path_data:
                p = Path(path_data)
                if p.exists():
                    paths.append(p)

        if not paths:
            QMessageBox.information(self, "未选择", "选中的项目不存在于磁盘上。")
            return

        # Calculate total size
        total_size = 0
        for p in paths:
            if p.is_dir():
                total_size += _dir_size(p)
            else:
                try:
                    total_size += p.stat().st_size
                except OSError:
                    pass

        msg = f"确定要永久删除以下 {len(paths)} 个项目吗？\n\n"
        for p in paths[:10]:
            msg += f"  • {p.name}\n"
        if len(paths) > 10:
            msg += f"  … 还有 {len(paths) - 10} 个\n"
        msg += f"\n总大小: {_fmt_size(total_size)}\n\n⚠️ 此操作不可恢复！"

        reply = QMessageBox.critical(
            self, "确认删除", msg,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        success = 0
        failed = 0
        for p in paths:
            try:
                if p.is_dir():
                    shutil.rmtree(p)
                else:
                    p.unlink()
                success += 1
                log.info("Deleted: %s", p)
            except Exception as e:
                failed += 1
                log.warning("Failed to delete %s: %s", p, e)

        QMessageBox.information(
            self, "删除完成",
            f"成功删除 {success} 个项目" + (f"，失败 {failed} 个" if failed else ""),
        )
        self._main.status.setText(f"已删除 {success} 个文件/文件夹")

        # Refresh views
        self._populate_dir_overview()
        # Refresh file tree if it was showing a directory
        title = self._file_group.title()
        if "—" in title:
            dir_path = title.split("—", 1)[1].strip()
            if Path(dir_path).is_dir():
                self._load_file_tree(Path(dir_path))

    def _clear_archive_dir(self) -> None:
        """Clear all files from the archive directory."""
        archive_dir = self._get_config_dir("archive")
        if not archive_dir or not archive_dir.is_dir():
            QMessageBox.information(self, "目录不存在", "归档目录不存在或未配置。")
            return

        size = _dir_size(archive_dir)
        count = _count_files(archive_dir)

        if count == 0:
            QMessageBox.information(self, "目录为空", "归档目录中没有文件。")
            return

        reply = QMessageBox.critical(
            self, "确认清空归档目录",
            f"将删除归档目录中的所有文件（解压后的原始压缩包）：\n\n"
            f"  路径: {archive_dir}\n"
            f"  文件数: {count}\n"
            f"  总大小: {_fmt_size(size)}\n\n"
            f"⚠️ 此操作不可恢复！确定要继续吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self._clear_directory(archive_dir, "归档")

    def _clear_failed_dir(self) -> None:
        """Clear all files from the failed directory."""
        failed_dir = self._get_config_dir("failed")
        if not failed_dir or not failed_dir.is_dir():
            QMessageBox.information(self, "目录不存在", "失败目录不存在或未配置。")
            return

        size = _dir_size(failed_dir)
        count = _count_files(failed_dir)

        if count == 0:
            QMessageBox.information(self, "目录为空", "失败目录中没有文件。")
            return

        reply = QMessageBox.critical(
            self, "确认清空失败目录",
            f"将删除失败目录中的所有文件（解压失败的压缩包）：\n\n"
            f"  路径: {failed_dir}\n"
            f"  文件数: {count}\n"
            f"  总大小: {_fmt_size(size)}\n\n"
            f"⚠️ 此操作不可恢复！确定要继续吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self._clear_directory(failed_dir, "失败")

    def _get_config_dir(self, key: str) -> Path | None:
        """Get a configured directory path by key."""
        try:
            from app.services.auto_extract_service import read_directory_config
            config = read_directory_config()
            path_str = config.get(key, "")
            return Path(path_str) if path_str else None
        except Exception:
            return None

    def _clear_directory(self, directory: Path, label: str) -> None:
        """Delete all contents of a directory."""
        success = 0
        failed = 0
        errors: list[str] = []

        log.info("Clearing %s directory: %s", label, directory)

        try:
            entries = list(directory.iterdir())
        except (PermissionError, OSError) as e:
            QMessageBox.warning(self, "清空失败", f"无法读取目录:\n{directory}\n{e}")
            return

        if not entries:
            QMessageBox.information(self, "目录为空", f"{label}目录中没有文件。")
            return

        for entry in entries:
            try:
                if entry.is_dir():
                    shutil.rmtree(entry)
                else:
                    entry.unlink()
                success += 1
            except PermissionError as e:
                failed += 1
                err_msg = f"权限不足: {entry.name} — {e}"
                errors.append(err_msg)
                log.warning("Failed to delete %s: %s", entry, e)
            except Exception as e:
                failed += 1
                err_msg = f"{entry.name} — {e}"
                errors.append(err_msg)
                log.warning("Failed to delete %s: %s", entry, e)

        # Build result message
        msg = f"{label}目录已清空：删除 {success} 项"
        if failed:
            msg += f"，失败 {failed} 项"
        msg += f"\n路径: {directory}"

        if errors:
            msg += "\n\n失败详情："
            for err in errors[:10]:
                msg += f"\n  • {err}"
            if len(errors) > 10:
                msg += f"\n  … 还有 {len(errors) - 10} 个"

        if failed > 0 and success == 0:
            QMessageBox.critical(self, "清空失败", msg)
        elif failed > 0:
            QMessageBox.warning(self, "部分失败", msg)
        else:
            QMessageBox.information(self, "清空完成", msg)

        self._main.status.setText(f"已清空{label}目录：删除 {success} 项")
        log.info("Cleared %s directory: %d items deleted, %d failed", label, success, failed)

        # Refresh views
        self._populate_dir_overview()
        title = self._file_group.title()
        if "—" in title:
            dir_path = title.split("—", 1)[1].strip()
            if Path(dir_path) == directory:
                self._load_file_tree(directory)
