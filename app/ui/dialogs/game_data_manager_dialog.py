"""Library data management: browse and delete games from the database."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.data.database import GameRecord
from app.services.game_delete_service import (
    confirm_delete_game,
    delete_game_from_library,
    set_skip_delete_game_confirm,
)

if TYPE_CHECKING:
    from app.ui.main_window import MainWindow


class GameDataManagerDialog(QDialog):
    def __init__(self, main: MainWindow) -> None:
        super().__init__(main)
        self._main = main
        self.setWindowTitle("数据管理")
        self.resize(860, 480)

        root = QVBoxLayout(self)
        hint = QLabel(
            "在此管理游戏库中的条目。默认只删除库内记录与软件缓存；"
            "可在下方勾选「同时删除安装文件夹」以一并删除磁盘上的游戏目录。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#93A1B6;font-size:12px;")
        root.addWidget(hint)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["名称", "安装目录", "游玩次数", "总时长", "收藏"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSortingEnabled(True)
        root.addWidget(self._table, 1)

        row = QHBoxLayout()
        self._chk_delete_install = QCheckBox("同时删除安装文件夹")
        self._chk_delete_install.setChecked(False)
        self._chk_delete_install.setToolTip(
            "勾选后，删除时将一并移除选中游戏的安装目录（不可恢复）。"
            "若已关闭删除确认弹窗，仍会针对此项弹出额外确认。"
        )
        row.addWidget(self._chk_delete_install)

        self._btn_delete = QPushButton("删除选中游戏")
        self._btn_delete.setProperty("btnRole", "danger")
        self._btn_delete.setToolTip("从库中移除选中条目（首次会二次确认）")
        self._btn_delete.clicked.connect(self._delete_selected)
        row.addWidget(self._btn_delete)

        self._btn_refresh = QPushButton("刷新列表")
        self._btn_refresh.clicked.connect(self._reload)
        row.addWidget(self._btn_refresh)

        self._btn_reset_confirm = QPushButton("恢复删除确认")
        self._btn_reset_confirm.setToolTip("重新启用删除游戏时的二次确认对话框")
        self._btn_reset_confirm.clicked.connect(self._reset_delete_confirm)
        row.addWidget(self._btn_reset_confirm)

        row.addStretch(1)
        root.addLayout(row)

        close_box = QDialogButtonBox(QDialogButtonBox.Close)
        close_box.rejected.connect(self.reject)
        root.addWidget(close_box)

        self._reload()

    def _db(self):
        return self._main.db

    def _user_id(self) -> int:
        return self._main.current_user_id

    def _reload(self) -> None:
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

    def _selected_game(self) -> GameRecord | None:
        r = self._table.currentRow()
        if r < 0:
            return None
        it = self._table.item(r, 0)
        if it is None:
            return None
        gid = it.data(Qt.ItemDataRole.UserRole)
        if gid is None:
            return None
        return self._db().get_game_by_id(self._user_id(), int(gid))

    def _delete_selected(self) -> None:
        game = self._selected_game()
        if game is None:
            QMessageBox.information(self, "未选择", "请先在列表中选中要删除的游戏。")
            return
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
        self._reload()

    def _reset_delete_confirm(self) -> None:
        set_skip_delete_game_confirm(self._db(), False)
        QMessageBox.information(self, "已恢复", "删除游戏时将再次显示确认对话框。")
