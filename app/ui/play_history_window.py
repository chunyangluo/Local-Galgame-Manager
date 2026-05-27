"""Global play history: all sessions for current user, filterable, with launch / detail actions."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QDate, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.data.database import PlayHistoryRow

if TYPE_CHECKING:
    from app.ui.main_window import MainWindow


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


def _fmt_started(iso: str) -> str:
    try:
        s = iso.replace("Z", "").split("+")[0]
        if len(s) >= 19:
            s = s[:19]
        dt = datetime.fromisoformat(s)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso[:16] if len(iso) > 16 else iso


def _thumb_pixmap(cover_path: str | None, image_url: str | None, target: QSize) -> QPixmap:
    """Load local cover only (same policy as library cards: no network on UI thread)."""
    if cover_path:
        p = Path(cover_path)
        if p.exists():
            pm = QPixmap(str(p))
            if not pm.isNull():
                return pm.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    pm = QPixmap(target)
    pm.fill(QColor("#252C36"))
    painter = QPainter(pm)
    painter.setPen(QPen(QColor("#465061"), 1))
    painter.drawRect(0, 0, target.width() - 1, target.height() - 1)
    painter.setPen(QPen(QColor("#90A0B8"), 1))
    hint = "等待缓存" if image_url and str(image_url).startswith(("http://", "https://")) else "无"
    painter.drawText(pm.rect(), Qt.AlignCenter, hint)
    painter.end()
    return pm


class PlayHistoryRowWidget(QWidget):
    """One row: cover, text, launch / LE / detail (used inside scroll area so clicks always work)."""

    def __init__(
        self,
        row: PlayHistoryRow,
        main: MainWindow,
        *,
        on_after_launch,
        show_le_launch: bool,
    ) -> None:
        super().__init__()
        self._row = row
        self._main = main
        self._on_after_launch = on_after_launch

        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(12)

        thumb_size = QSize(56, 84)
        cover = QLabel()
        cover.setFixedSize(thumb_size)
        cover.setPixmap(_thumb_pixmap(row.cover_path, row.image_url, thumb_size))
        cover.setAlignment(Qt.AlignCenter)
        outer.addWidget(cover)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        name = QLabel(row.game_name)
        name.setStyleSheet("font-weight:600;font-size:13px;color:#F3F6FB;")
        name.setWordWrap(True)
        text_col.addWidget(name)

        meta = QLabel(f"{_fmt_started(row.started_at)}  ·  时长 {_fmt_duration(row.duration_seconds)}")
        meta.setStyleSheet("color:#93A1B6;font-size:11px;")
        meta.setWordWrap(True)
        text_col.addWidget(meta)
        text_col.addStretch(1)
        outer.addLayout(text_col, 1)

        btn_launch = QPushButton("▶ 启动")
        btn_launch.setToolTip("启动该游戏（退出后写入新游玩记录）")
        btn_launch.setAutoDefault(False)
        btn_launch.setDefault(False)
        btn_launch.setStyleSheet("""
            QPushButton {
                background: #3A5A8A;
                border: 1px solid #5A8AC8;
                border-radius: 6px;
                padding: 6px 14px;
                color: #F0F3F8;
                font-weight: 600;
                font-size: 12px;
                min-width: 60px;
            }
            QPushButton:hover {
                background: #4A6AB8;
                border-color: #7AA8D8;
            }
            QPushButton:pressed {
                background: #2A4A7A;
            }
        """)
        btn_launch.clicked.connect(self._do_launch)
        outer.addWidget(btn_launch, 0, Qt.AlignVCenter)

        if show_le_launch:
            btn_le = QPushButton("🌐 LE")
            btn_le.setToolTip("Locale Emulator 转区启动")
            btn_le.setAutoDefault(False)
            btn_le.setDefault(False)
            btn_le.setStyleSheet("""
                QPushButton {
                    background: #5A6A4A;
                    border: 1px solid #7A8A6A;
                    border-radius: 6px;
                    padding: 6px 14px;
                    color: #E8F0E0;
                    font-weight: 600;
                    font-size: 12px;
                    min-width: 50px;
                }
                QPushButton:hover {
                    background: #6A7A5A;
                    border-color: #9AB88A;
                }
                QPushButton:pressed {
                    background: #4A5A3A;
                }
            """)
            btn_le.clicked.connect(self._do_launch_le)
            outer.addWidget(btn_le, 0, Qt.AlignVCenter)

        btn_detail = QPushButton("ℹ 详情")
        btn_detail.setToolTip("打开游戏详情页")
        btn_detail.setAutoDefault(False)
        btn_detail.setDefault(False)
        btn_detail.setStyleSheet("""
            QPushButton {
                background: #4A5568;
                border: 1px solid #6A7588;
                border-radius: 6px;
                padding: 6px 14px;
                color: #C8D0DC;
                font-weight: 500;
                font-size: 12px;
                min-width: 60px;
            }
            QPushButton:hover {
                background: #5A6578;
                border-color: #8A95A8;
            }
            QPushButton:pressed {
                background: #3A4558;
            }
        """)
        btn_detail.clicked.connect(lambda: self._main.open_game_detail(self._row.game_id))
        outer.addWidget(btn_detail, 0, Qt.AlignVCenter)

    def _dialog_parent(self) -> QWidget:
        win = self.window()
        if win is not None and win is not self._main:
            return win
        return self._main

    def _do_launch(self) -> None:
        self._main.launch_game_by_id(self._row.game_id, message_parent=self._dialog_parent())
        self._on_after_launch()

    def _do_launch_le(self) -> None:
        self._main.launch_game_by_id(
            self._row.game_id,
            locale_emulator=True,
            message_parent=self._dialog_parent(),
        )
        self._on_after_launch()


class PlayHistoryEntryRow(QWidget):
    """Checkbox + row content (for bulk delete without QListWidget item widgets)."""

    def __init__(
        self,
        row: PlayHistoryRow,
        main: MainWindow,
        *,
        on_after_launch,
        show_le_launch: bool,
        zebra: bool,
    ) -> None:
        super().__init__()
        self.record_id = row.record_id
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 8, 4)
        lay.setSpacing(8)
        self._check = QCheckBox()
        self._check.setToolTip("勾选后可用下方「清空选中记录」删除本条")
        lay.addWidget(self._check, 0, Qt.AlignTop | Qt.AlignHCenter)
        inner = PlayHistoryRowWidget(
            row, main, on_after_launch=on_after_launch, show_le_launch=show_le_launch
        )
        inner.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        lay.addWidget(inner, 1)
        bg = "#2A313A" if zebra else "#252B33"
        self.setStyleSheet(
            f"background-color: {bg}; border: 1px solid #3A4250; border-radius: 8px;"
        )

    def is_marked_for_delete(self) -> bool:
        return self._check.isChecked()


_DURATION_PRESETS: list[tuple[str, int | None, int | None]] = [
    ("全部时长", None, None),
    ("少于 15 分钟", None, 899),
    ("15 分钟 – 1 小时", 900, 3599),
    ("1 – 3 小时", 3600, 10799),
    ("超过 3 小时", 10800, None),
]


class PlayHistoryWindow(QMainWindow):
    """Standalone window listing all play sessions for the current user."""

    def __init__(self, main: MainWindow) -> None:
        super().__init__(main)
        self._main = main
        self.setWindowTitle("游玩历史")
        self.resize(960, 640)
        self.setMinimumSize(720, 420)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        filters = QHBoxLayout()
        filters.addWidget(QLabel("游戏"))
        self._game_combo = QComboBox()
        self._game_combo.setMinimumWidth(220)
        filters.addWidget(self._game_combo)

        self._date_check = QCheckBox("按日期")
        filters.addWidget(self._date_check)
        self._date_from = QDateEdit()
        self._date_from.setCalendarPopup(True)
        self._date_from.setDisplayFormat("yyyy-MM-dd")
        self._date_to = QDateEdit()
        self._date_to.setCalendarPopup(True)
        self._date_to.setDisplayFormat("yyyy-MM-dd")
        today = QDate.currentDate()
        self._date_from.setDate(today.addDays(-365))
        self._date_to.setDate(today)
        filters.addWidget(QLabel("从"))
        filters.addWidget(self._date_from)
        filters.addWidget(QLabel("至"))
        filters.addWidget(self._date_to)

        filters.addWidget(QLabel("时长"))
        self._dur_combo = QComboBox()
        for label, _a, _b in _DURATION_PRESETS:
            self._dur_combo.addItem(label)
        filters.addWidget(self._dur_combo)

        btn_apply = QPushButton("应用筛选")
        btn_apply.clicked.connect(self.reload)
        filters.addWidget(btn_apply)
        btn_reset = QPushButton("重置筛选")
        btn_reset.clicked.connect(self._reset_filters)
        filters.addWidget(btn_reset)
        filters.addStretch(1)
        root.addLayout(filters)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._rows_host = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_host)
        self._rows_layout.setContentsMargins(4, 4, 4, 4)
        self._rows_layout.setSpacing(6)
        self._rows_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._scroll.setWidget(self._rows_host)
        root.addWidget(self._scroll, 1)

        actions = QHBoxLayout()
        self._btn_clear_sel = QPushButton("清空选中记录")
        self._btn_clear_sel.setToolTip("删除左侧已勾选条目对应的游玩记录")
        self._btn_clear_sel.clicked.connect(self._clear_selected)
        actions.addWidget(self._btn_clear_sel)
        self._btn_clear_all = QPushButton("清空全部记录")
        self._btn_clear_all.clicked.connect(self._clear_all)
        actions.addWidget(self._btn_clear_all)
        self._btn_refresh = QPushButton("刷新")
        self._btn_refresh.clicked.connect(self.reload)
        actions.addWidget(self._btn_refresh)
        actions.addStretch(1)
        self._count_label = QLabel()
        actions.addWidget(self._count_label)
        root.addLayout(actions)

    def _clear_row_widgets(self) -> None:
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _reset_filters(self) -> None:
        self._game_combo.setCurrentIndex(0)
        today = QDate.currentDate()
        self._date_from.setDate(today.addDays(-365))
        self._date_to.setDate(today)
        self._date_check.setChecked(False)
        self._dur_combo.setCurrentIndex(0)
        self.reload()

    def _current_game_filter(self) -> int | None:
        data = self._game_combo.currentData()
        return int(data) if data is not None else None

    def _duration_filter(self) -> tuple[int | None, int | None]:
        idx = self._dur_combo.currentIndex()
        if idx < 0 or idx >= len(_DURATION_PRESETS):
            return None, None
        _label, lo, hi = _DURATION_PRESETS[idx]
        return lo, hi

    def _populate_game_combo(self) -> None:
        prev = self._game_combo.currentData()
        self._game_combo.blockSignals(True)
        self._game_combo.clear()
        self._game_combo.addItem("全部游戏", None)
        games = sorted(
            self._main.db.list_games(self._main.current_user_id),
            key=lambda g: g.name.lower(),
        )
        sel_index = 0
        for g in games:
            self._game_combo.addItem(g.name, g.id)
            if prev is not None and int(g.id) == int(prev):
                sel_index = self._game_combo.count() - 1
        self._game_combo.setCurrentIndex(sel_index)
        self._game_combo.blockSignals(False)

    def reload(self) -> None:
        self._populate_game_combo()
        game_id = self._current_game_filter()
        date_from: str | None = None
        date_to: str | None = None
        if self._date_check.isChecked():
            date_from = self._date_from.date().toString("yyyy-MM-dd")
            date_to = self._date_to.date().toString("yyyy-MM-dd")
        dmin, dmax = self._duration_filter()
        rows = self._main.db.list_all_play_records(
            self._main.current_user_id,
            game_id=game_id,
            date_from=date_from,
            date_to=date_to,
            min_duration_seconds=dmin,
            max_duration_seconds=dmax,
        )
        self._clear_row_widgets()
        show_le = self._main.is_locale_emulator_usable()
        for idx, row in enumerate(rows):
            entry = PlayHistoryEntryRow(
                row,
                self._main,
                on_after_launch=self.reload,
                show_le_launch=show_le,
                zebra=bool(idx % 2),
            )
            self._rows_layout.addWidget(entry)
        self._rows_layout.addStretch(1)
        self._count_label.setText(f"共 {len(rows)} 条")

    def _clear_selected(self) -> None:
        ids: list[int] = []
        for i in range(self._rows_layout.count()):
            item = self._rows_layout.itemAt(i)
            w = item.widget()
            if isinstance(w, PlayHistoryEntryRow) and w.is_marked_for_delete():
                ids.append(w.record_id)
        if not ids:
            QMessageBox.information(
                self,
                "游玩历史",
                "请先勾选要删除的记录左侧的复选框，再点「清空选中记录」。",
            )
            return
        r = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除选中的 {len(ids)} 条游玩记录？\n（不会删除游戏库中的游戏）",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if r != QMessageBox.Yes:
            return
        n = self._main.db.delete_play_records_by_ids(self._main.current_user_id, ids)
        self._main.refresh_games()
        self.reload()
        self._main.status.setText(f"已删除 {n} 条游玩记录")

    def _clear_all(self) -> None:
        r = QMessageBox.question(
            self,
            "确认清空",
            "确定清空当前用户的全部游玩记录？\n此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if r != QMessageBox.Yes:
            return
        n = self._main.db.delete_all_play_records(self._main.current_user_id)
        self._main.refresh_games()
        self.reload()
        self._main.status.setText(f"已清空全部游玩记录（{n} 条）")
