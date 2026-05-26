"""Paged game grid: adaptive columns (flow layout), fixed rows per page, snap scroll."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QContextMenuEvent, QMouseEvent, QWheelEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLayoutItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.data.database import GameRecord
from app.ui.game_card_widget import GameCardWidget


ROWS_PER_PAGE = 2

CARD_W = 200
CARD_H = 360
MIN_CARD_W = 160
MAX_CARD_W = 240
H_GAP = 16
V_GAP = 16
PAGE_PAD = 16


def _cols_for_inner_width(inner_w: int) -> int:
    min_slot = MIN_CARD_W + H_GAP
    max_slot = MAX_CARD_W + H_GAP
    
    if inner_w < MIN_CARD_W:
        return 1
    
    max_cols = (inner_w + H_GAP) // min_slot
    
    return max(1, max_cols)


def _card_width_for_cols(inner_w: int, cols: int) -> int:
    if cols <= 0:
        return CARD_W
    total_gap = (cols - 1) * H_GAP
    available = inner_w - total_gap
    card_w = available // cols
    return max(MIN_CARD_W, min(MAX_CARD_W, card_w))


def _full_page_height(card_h: int = CARD_H) -> int:
    return PAGE_PAD * 2 + ROWS_PER_PAGE * card_h + (ROWS_PER_PAGE - 1) * V_GAP


def _page_height_for_count(count: int, cols: int, card_h: int = CARD_H) -> int:
    if count <= 0:
        return _full_page_height(card_h)
    rows = min(ROWS_PER_PAGE, (count + cols - 1) // cols)
    return PAGE_PAD * 2 + rows * card_h + max(0, rows - 1) * V_GAP


class FlowLayout(QLayout):
    """Left-to-right flow with wrapping (same-size items assumed)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._h_explicit = -1
        self._v_explicit = -1

    def setHorizontalSpacing(self, spacing: int) -> None:
        self._h_explicit = spacing

    def setVerticalSpacing(self, spacing: int) -> None:
        self._v_explicit = spacing

    def horizontalSpacing(self) -> int:
        return self._h_explicit

    def verticalSpacing(self) -> int:
        return self._v_explicit

    def addItem(self, item: QLayoutItem) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> QLayoutItem | None:
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientations:
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for it in self._items:
            size = size.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _h_space(self) -> int:
        s = self.horizontalSpacing()
        return s if s >= 0 else self.spacing()

    def _v_space(self) -> int:
        s = self.verticalSpacing()
        return s if s >= 0 else self.spacing()

    def _do_layout(self, rect: QRect, *, test_only: bool) -> int:
        left, top, right, bottom = self.getContentsMargins()
        eff = rect.adjusted(left, top, -right, -bottom)
        x = eff.x()
        y = eff.y()
        line_h = 0
        hx = self._h_space()
        vy = self._v_space()

        for it in self._items:
            w = it.widget()
            if w is None:
                continue
            next_x = x + w.width() + hx
            if next_x - hx > eff.right() + 1 and line_h > 0:
                x = eff.x()
                y = y + line_h + vy
                next_x = x + w.width() + hx
                line_h = 0

            if not test_only:
                it.setGeometry(QRect(QPoint(x, y), w.size()))

            x = next_x
            line_h = max(line_h, w.height())

        y += line_h
        return y - rect.y() + top + bottom


class _SnapScrollArea(QScrollArea):
    def __init__(self, host: "PagedGameGridView") -> None:
        super().__init__()
        self._host = host

    def wheelEvent(self, event: QWheelEvent) -> None:
        dy = event.angleDelta().y()
        if dy == 0:
            event.ignore()
            return
        direction = 1 if dy < 0 else -1
        self._host._scroll_by_page_step(direction)
        event.accept()


class _CardSlot(QFrame):
    clicked = Signal(int)
    double_clicked = Signal(int)
    menu_requested = Signal(int, QPoint)

    def __init__(self, game_id: int, card: GameCardWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._game_id = game_id
        self.setObjectName("gameCardSlot")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(card, 0, Qt.AlignCenter)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._game_id)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit(self._game_id)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        self.menu_requested.emit(self._game_id, event.globalPos())
        event.accept()

    def set_slot_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    @property
    def game_id(self) -> int:
        return self._game_id


class PagedGameGridView(QWidget):
    """Adaptive columns (flow), fixed rows per page, snap to page tops."""

    selection_changed = Signal()
    double_clicked = Signal(int)
    context_menu_requested = Signal(int, QPoint)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._games: list[GameRecord] = []
        self._slots: list[_CardSlot] = []
        self._selected_id: int | None = None
        self._cover_retry_failed: set[int] = set()
        self._on_retry_cover: Callable[[int], None] = lambda _gid: None

        self._page_starts: list[int] = []
        self._page_heights: list[int] = []
        self._cols: int = 1
        self._current_card_w = CARD_W
        self._rebuild_timer = QTimer(self)
        self._rebuild_timer.setSingleShot(True)
        self._rebuild_timer.setInterval(80)
        self._rebuild_timer.timeout.connect(self._rebuild_pages)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        self._scroll = _SnapScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setMinimumHeight(_full_page_height())

        self._content = QWidget()
        self._content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._vlayout = QVBoxLayout(self._content)
        self._vlayout.setContentsMargins(0, 0, 0, 0)
        self._vlayout.setSpacing(0)
        self._scroll.setWidget(self._content)
        self._scroll.viewport().installEventFilter(self)
        root.addWidget(self._scroll, 1)

        self._snap_timer = QTimer(self)
        self._snap_timer.setSingleShot(True)
        self._snap_timer.setInterval(80)
        self._snap_timer.timeout.connect(self._snap_scroll_to_page)
        self._scroll.verticalScrollBar().valueChanged.connect(self._on_scroll_value_changed)

        nav = QHBoxLayout()
        nav.setSpacing(10)
        self._btn_prev = QPushButton("上一页")
        self._btn_prev.setToolTip("向上翻一整页（行数固定，列数随窗口宽度变化）")
        self._btn_prev.clicked.connect(self._go_prev_page)
        nav.addWidget(self._btn_prev)
        self._btn_next = QPushButton("下一页")
        self._btn_next.setToolTip("向下翻一整页")
        self._btn_next.clicked.connect(self._go_next_page)
        nav.addWidget(self._btn_next)
        nav.addStretch(1)
        self._page_label = QLabel("")
        self._page_label.setObjectName("gridPageLabel")
        nav.addWidget(self._page_label)
        root.addLayout(nav)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore[override]
        if obj is self._scroll.viewport() and event.type() == QEvent.Type.Resize:
            if self._games:
                self._rebuild_timer.start()
        return super().eventFilter(obj, event)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if self._games:
            self._rebuild_timer.start()

    def page_height_px(self) -> int:
        return _full_page_height()

    def selected_game_id(self) -> int | None:
        return self._selected_id

    def has_games(self) -> bool:
        return len(self._games) > 0

    def set_focus_chain(self) -> None:
        self._scroll.setFocus()

    def set_games(
        self,
        games: list[GameRecord],
        *,
        cover_retry_failed: set[int],
        on_retry_cover: Callable[[int], None],
    ) -> None:
        self._games = list(games)
        self._cover_retry_failed = set(cover_retry_failed)
        self._on_retry_cover = on_retry_cover
        self._selected_id = None
        self._scroll.verticalScrollBar().setValue(0)
        if not self._games:
            self._clear_content()
            self._page_starts = []
            self._page_heights = []
            self._page_label.setText("")
            self._btn_prev.setEnabled(False)
            self._btn_next.setEnabled(False)
            self.selection_changed.emit()
            return
        self._rebuild_pages()
        self.selection_changed.emit()

    def _slots_per_page(self) -> int:
        return max(1, self._cols * ROWS_PER_PAGE)

    def _clear_content(self) -> None:
        while self._vlayout.count():
            item = self._vlayout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._slots.clear()

    def _rebuild_pages(self) -> None:
        if not self._games:
            self._clear_content()
            return

        bar = self._scroll.verticalScrollBar()
        ratio = bar.value() / max(1, bar.maximum())

        page_w = max(self._scroll.viewport().width(), CARD_W + 2 * PAGE_PAD)
        inner_w = page_w - 2 * PAGE_PAD
        self._cols = _cols_for_inner_width(inner_w)
        self._current_card_w = _card_width_for_cols(inner_w, self._cols)
        spp = self._slots_per_page()
        n = len(self._games)
        num_pages = (n + spp - 1) // spp

        self._clear_content()

        self._page_starts = []
        self._page_heights = []
        y = 0

        card_ratio = CARD_H / CARD_W
        card_h = int(self._current_card_w * card_ratio)

        for p in range(num_pages):
            start = p * spp
            chunk = self._games[start : start + spp]
            h = _page_height_for_count(len(chunk), self._cols, card_h)

            page = QWidget()
            page.setFixedSize(page_w, h)
            flow = FlowLayout(page)
            flow.setContentsMargins(PAGE_PAD, PAGE_PAD, PAGE_PAD, PAGE_PAD)
            flow.setHorizontalSpacing(H_GAP)
            flow.setVerticalSpacing(V_GAP)

            for game in chunk:
                card = GameCardWidget(game)
                card.setFixedSize(self._current_card_w, card_h)
                if game.id in self._cover_retry_failed:
                    card.force_no_cover_placeholder()
                card.retry_cover_requested.connect(self._on_retry_cover)
                slot = _CardSlot(game.id, card, page)
                slot.setFixedSize(self._current_card_w, card_h)
                slot.clicked.connect(self._on_slot_clicked)
                slot.double_clicked.connect(self.double_clicked.emit)
                slot.menu_requested.connect(self.context_menu_requested.emit)
                self._slots.append(slot)
                flow.addWidget(slot)

            self._vlayout.addWidget(page)

            self._page_starts.append(y)
            self._page_heights.append(h)
            y += h

        total_h = y
        vp_h = max(1, self._scroll.viewport().height())
        if self._page_starts:
            last_top = self._page_starts[-1]
            pad_bottom = max(0, last_top + vp_h - total_h)
            if pad_bottom > 0:
                tail = QWidget()
                tail.setFixedHeight(pad_bottom)
                tail.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                self._vlayout.addWidget(tail)
                total_h += pad_bottom

        self._content.setMinimumHeight(total_h)
        self._content.setMaximumHeight(total_h)
        self._content.setMinimumWidth(page_w)

        max_v = max(0, total_h - self._scroll.viewport().height())
        bar.blockSignals(True)
        bar.setValue(int(ratio * max_v))
        bar.blockSignals(False)
        self._apply_scrollbar_steps()
        self._snap_scroll_to_page()
        self._update_nav_state()
        self._restore_selection_styles()

    def _apply_scrollbar_steps(self) -> None:
        bar = self._scroll.verticalScrollBar()
        if not self._page_heights:
            return
        step = min(self._page_heights)
        mx = max(self._page_heights)
        bar.setSingleStep(step)
        bar.setPageStep(mx)

    def _page_index_for_value(self, v: int) -> int:
        if not self._page_starts:
            return 0
        for i in range(len(self._page_starts) - 1, -1, -1):
            if v >= self._page_starts[i]:
                return i
        return 0

    def _snap_scroll_to_page(self) -> None:
        bar = self._scroll.verticalScrollBar()
        if not self._page_starts or not self._games:
            return
        v = bar.value()
        max_v = bar.maximum()
        # nearest page top
        best_i = 0
        best_d = abs(v - self._page_starts[0])
        for i, s in enumerate(self._page_starts):
            d = abs(v - s)
            if d < best_d:
                best_d = d
                best_i = i
        target = self._page_starts[best_i]
        target = max(0, min(target, max_v))
        if target != v:
            bar.setValue(target)
        self._update_nav_state()

    def _scroll_by_page_step(self, direction: int) -> None:
        bar = self._scroll.verticalScrollBar()
        if not self._page_starts:
            return
        i = self._page_index_for_value(bar.value())
        # direction > 0: angleDelta.y() < 0 → 内容向下滚 → 下一页
        if direction > 0:
            ni = min(len(self._page_starts) - 1, i + 1)
        else:
            ni = max(0, i - 1)
        bar.setValue(self._page_starts[ni])

    def _on_scroll_value_changed(self, _value: int) -> None:
        self._snap_timer.start()
        self._update_page_label_only()

    def _update_page_label_only(self) -> None:
        if not self._games or not self._page_starts:
            self._page_label.setText("")
            return
        bar = self._scroll.verticalScrollBar()
        cur = self._page_index_for_value(bar.value()) + 1
        total = len(self._page_starts)
        cur = max(1, min(cur, total))
        spp = self._slots_per_page()
        self._page_label.setText(
            f"第 {cur} / {total} 页 · 每页最多 {spp} 个（{ROWS_PER_PAGE} 行 × {self._cols} 列）"
        )

    def _update_nav_state(self) -> None:
        self._update_page_label_only()
        if not self._games:
            self._btn_prev.setEnabled(False)
            self._btn_next.setEnabled(False)
            return
        cur_i = self._page_index_for_value(self._scroll.verticalScrollBar().value())
        last_i = len(self._page_starts) - 1
        self._btn_prev.setEnabled(cur_i > 0)
        self._btn_next.setEnabled(last_i >= 0 and cur_i < last_i)

    def _go_prev_page(self) -> None:
        self._scroll_by_page_step(-1)
        self._snap_scroll_to_page()

    def _go_next_page(self) -> None:
        self._scroll_by_page_step(1)
        self._snap_scroll_to_page()

    def select_game_by_id(self, game_id: int) -> None:
        """通过游戏ID选择游戏并滚动到可见位置"""
        # 找到游戏所在的页
        spp = self._slots_per_page()
        for idx, game in enumerate(self._games):
            if game.id == game_id:
                target_page = idx // spp
                # 滚动到目标页
                if target_page < len(self._page_starts):
                    self._scroll.verticalScrollBar().setValue(self._page_starts[target_page])
                # 选择游戏
                self._selected_id = game_id
                self._restore_selection_styles()
                self._update_nav_state()
                self.selection_changed.emit()
                break

    def _on_slot_clicked(self, game_id: int) -> None:
        self._selected_id = game_id
        self._restore_selection_styles()
        self._update_nav_state()
        self.selection_changed.emit()

    def _restore_selection_styles(self) -> None:
        sid = self._selected_id
        for slot in self._slots:
            slot.set_slot_selected(sid is not None and slot.game_id == sid)
