from __future__ import annotations

from enum import Enum
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.data.database import GameRecord


class CoverPlaceholderState(Enum):
    LOADING = "loading"
    CACHING = "caching"
    MISSING = "missing"
    FAILED = "failed"


class TwoLineElideLabel(QLabel):
    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._raw_text = text
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._line_height = self.fontMetrics().lineSpacing()
        self.setMinimumHeight(self._line_height * 2)
        self.setMaximumHeight(self._line_height * 2 + 4)
        self.setText(text)

    def setText(self, text: str) -> None:
        self._raw_text = text
        super().setText(self._build_two_line_elided_text())
        self.setToolTip(text)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        super().setText(self._build_two_line_elided_text())

    def _build_two_line_elided_text(self) -> str:
        text = self._raw_text.strip()
        if not text:
            return ""
        width = max(80, self.contentsRect().width() - 2)
        metrics = QFontMetrics(self.font())
        first_line = ""
        second_line = ""
        idx = 0
        for idx, ch in enumerate(text):
            trial = first_line + ch
            if metrics.horizontalAdvance(trial) > width:
                break
            first_line = trial
        else:
            return text
        remaining = text[idx:]
        for ch in remaining:
            trial = second_line + ch
            if metrics.horizontalAdvance(trial) > width:
                second_line = metrics.elidedText(second_line + ch, Qt.ElideRight, width)
                break
            second_line = trial
        if not second_line:
            second_line = metrics.elidedText(remaining, Qt.ElideRight, width)
        return f"{first_line}\n{second_line}"


class GameCardWidget(QWidget):
    retry_cover_requested = Signal(int)
    cover_add_requested = Signal(int)

    def __init__(self, game: GameRecord, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._game = game
        self._retry_emitted = False
        self._force_no_cover = False
        self._cover_loading = False
        self._placeholder_state: CoverPlaceholderState | None = CoverPlaceholderState.LOADING
        self._retry_timer = QTimer(self)
        self._retry_timer.setSingleShot(True)
        self._retry_timer.timeout.connect(self._emit_retry_request)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        self.cover = QLabel()
        self.cover.setObjectName("gameCover")
        self.cover.setFixedSize(168, 252)
        self.cover.setAlignment(Qt.AlignCenter)
        self.cover.setMouseTracking(True)
        self.cover.installEventFilter(self)
        self._apply_cover(game.cover_path, game.image_url)
        root.addWidget(self.cover, 0, Qt.AlignHCenter)

        text_widget = QWidget()
        text_widget.setObjectName("gameTextBlock")
        text_col = QVBoxLayout()
        text_widget.setLayout(text_col)
        text_col.setContentsMargins(10, 6, 10, 10)
        text_col.setSpacing(3)
        self.title = TwoLineElideLabel(game.name)
        self.title.setObjectName("gameTitle")
        text_col.addWidget(self.title, 1)

        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.setSpacing(6)
        self.favorite_badge = QLabel()
        self.favorite_badge.setObjectName("gameMeta")
        meta_row.addWidget(self.favorite_badge)
        self.content_badge = QLabel()
        self.content_badge.setObjectName("gameMeta")
        meta_row.addWidget(self.content_badge)
        meta_row.addStretch(1)
        self.play_count = QLabel()
        self.play_count.setObjectName("gameMeta")
        self.play_count.setAlignment(Qt.AlignRight | Qt.AlignBottom)
        meta_row.addWidget(self.play_count)
        text_col.addLayout(meta_row)
        root.addWidget(text_widget, 1)

        self.update_meta(game)

    def update_meta(self, game: GameRecord) -> None:
        self._game = game
        count = int(game.play_count or 0)
        is_video = getattr(game, "content_type", "game") == "video"
        self.content_badge.setText("视频" if is_video else "")
        self.content_badge.setToolTip("视频内容" if is_video else "")
        self.content_badge.setVisible(is_video)
        if is_video:
            self.play_count.setText(f"▶ × {count}")
        else:
            self.play_count.setText(f"🎮 × {count}")
        if count == 0:
            self.play_count.setToolTip("打开次数：0（尚未打开）" if is_video else "游玩次数：0（尚未记录游玩）")
        elif count == 1:
            self.play_count.setToolTip("打开次数：1 次" if is_video else "游玩次数：1 次")
        else:
            self.play_count.setToolTip(f"打开次数：{count} 次" if is_video else f"游玩次数：{count} 次")
        if game.favorite:
            self.favorite_badge.setText("⭐")
            self.favorite_badge.setToolTip("已收藏（Ctrl+D 可切换）")
            self.favorite_badge.show()
        else:
            self.favorite_badge.setText("☆")
            self.favorite_badge.setToolTip("未收藏（Ctrl+D 可收藏）")
            self.favorite_badge.show()

    def set_cover_loading(self, loading: bool) -> None:
        self._cover_loading = loading
        if loading:
            self._show_placeholder(CoverPlaceholderState.CACHING, subtitle="获取封面中…")
        elif self._placeholder_state == CoverPlaceholderState.CACHING:
            self._apply_cover(self._game.cover_path, self._game.image_url)

    def eventFilter(self, obj, event) -> bool:
        if obj is self.cover:
            if event.type() == event.Type.Enter:
                self._update_cover_hover_tooltip()
            elif event.type() == event.Type.MouseButtonPress:
                if (
                    event.button() == Qt.MouseButton.LeftButton
                    and self._placeholder_state
                    in (CoverPlaceholderState.MISSING, CoverPlaceholderState.FAILED)
                    and not self._cover_loading
                ):
                    self.cover_add_requested.emit(self._game.id)
                    return True
        return super().eventFilter(obj, event)

    def _update_cover_hover_tooltip(self) -> None:
        if self._cover_loading or self._placeholder_state == CoverPlaceholderState.CACHING:
            self.cover.setToolTip("正在获取或缓存封面，请稍候…")
            return
        if self._placeholder_state == CoverPlaceholderState.MISSING:
            self.cover.setToolTip("暂无封面\n点击添加自定义封面")
            return
        if self._placeholder_state == CoverPlaceholderState.FAILED:
            self.cover.setToolTip("封面获取失败\n点击添加封面，或右键「重新获取封面」")
            return
        if self._placeholder_state == CoverPlaceholderState.LOADING:
            self.cover.setToolTip("正在加载封面…")
            return
        self.cover.setToolTip("")

    def _apply_cover(self, cover_path: str | None, image_url: str | None = None) -> None:
        if self._cover_loading:
            self._show_placeholder(CoverPlaceholderState.CACHING, subtitle="获取封面中…")
            return
        self._show_placeholder(CoverPlaceholderState.LOADING)
        if cover_path:
            path = Path(cover_path)
            if path.exists():
                pix = QPixmap(str(path))
                if not pix.isNull():
                    scaled = self._scale_and_center_crop(pix, self.cover.size())
                    self.cover.setPixmap(self._with_bottom_gradient(scaled))
                    self._placeholder_state = None
                    self.cover.setCursor(Qt.CursorShape.ArrowCursor)
                    self._update_cover_hover_tooltip()
                    return
        if image_url and image_url.startswith(("http://", "https://")):
            if self._force_no_cover:
                self._show_placeholder(CoverPlaceholderState.FAILED)
                return
            self._show_placeholder(
                CoverPlaceholderState.CACHING, subtitle="等待下载封面…"
            )
            if not self._retry_emitted:
                self._retry_emitted = True
                self._retry_timer.start(120)
            return
        self._show_placeholder(CoverPlaceholderState.MISSING)

    def force_no_cover_placeholder(self) -> None:
        self._force_no_cover = True
        self._cover_loading = False
        self._apply_cover(self._game.cover_path, self._game.image_url)

    def _show_placeholder(
        self, state: CoverPlaceholderState, *, subtitle: str = ""
    ) -> None:
        self._placeholder_state = state
        self.cover.setPixmap(self._build_placeholder_cover(state, subtitle))
        self.cover.setCursor(
            Qt.CursorShape.PointingHandCursor
            if state in (CoverPlaceholderState.MISSING, CoverPlaceholderState.FAILED)
            else Qt.CursorShape.ArrowCursor
        )
        self._update_cover_hover_tooltip()

    def _emit_retry_request(self) -> None:
        self.retry_cover_requested.emit(self._game.id)

    def _scale_and_center_crop(self, source: QPixmap, target_size: QSize) -> QPixmap:
        target_w = max(1, target_size.width())
        target_h = max(1, target_size.height())
        expanded = source.scaled(
            QSize(target_w, target_h),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        crop_x = max(0, (expanded.width() - target_w) // 2)
        crop_y = max(0, (expanded.height() - target_h) // 2)
        return expanded.copy(crop_x, crop_y, target_w, target_h)

    def _placeholder_copy(self, state: CoverPlaceholderState) -> tuple[str, str]:
        if state == CoverPlaceholderState.LOADING:
            return "加载中", "请稍候"
        if state == CoverPlaceholderState.CACHING:
            return "封面获取中", "联网缓存"
        if state == CoverPlaceholderState.FAILED:
            return "封面不可用", "点击添加"
        return "暂无封面", "点击添加"

    def _build_placeholder_cover(
        self, state: CoverPlaceholderState, subtitle: str = ""
    ) -> QPixmap:
        title, default_sub = self._placeholder_copy(state)
        sub = subtitle or default_sub
        size = self.cover.size()
        pix = QPixmap(size)
        gradient = QLinearGradient(0, 0, 0, size.height())
        gradient.setColorAt(0.0, QColor("#323E52"))
        gradient.setColorAt(0.35, QColor("#2A3448"))
        gradient.setColorAt(0.7, QColor("#232C3C"))
        gradient.setColorAt(1.0, QColor("#1C2430"))
        pix.fill(QColor("#1C2430"))
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(pix.rect(), gradient)

        # subtle grid texture
        painter.setPen(QPen(QColor(255, 255, 255, 18), 1))
        step = 24
        for x in range(0, size.width(), step):
            painter.drawLine(x, 0, x, size.height())
        for y in range(0, size.height(), step):
            painter.drawLine(0, y, size.width(), y)

        painter.setPen(QPen(QColor("#4A5D78"), 1, Qt.PenStyle.DashLine))
        painter.drawRoundedRect(6, 6, size.width() - 12, size.height() - 12, 10, 10)

        # game icon silhouette
        cx, cy = size.width() // 2, size.height() // 2 - 18
        painter.setBrush(QColor(255, 255, 255, 28))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(cx - 36, cy - 22, 72, 44, 10, 10)
        painter.drawEllipse(cx - 14, cy - 36, 28, 28)

        title_font = QFont(painter.font())
        title_font.setPointSize(11)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QPen(QColor("#C5D0E0")))
        title_rect = pix.rect().adjusted(8, size.height() - 72, -8, -40)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, title)

        sub_font = QFont(painter.font())
        sub_font.setPointSize(9)
        painter.setFont(sub_font)
        painter.setPen(QPen(QColor("#7E92AB")))
        sub_rect = pix.rect().adjusted(8, size.height() - 38, -8, -12)
        painter.drawText(sub_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, sub)

        if self._cover_loading or state == CoverPlaceholderState.CACHING:
            painter.setPen(QPen(QColor("#5B9BFF"), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(
                cx - 20, cy + 28, 40, 40, 30 * 16, 300 * 16
            )

        painter.end()
        return self._with_bottom_gradient(pix)

    def _with_bottom_gradient(self, pixmap: QPixmap) -> QPixmap:
        output = QPixmap(pixmap)
        painter = QPainter(output)
        gradient = QLinearGradient(0, 0, 0, output.height())
        gradient.setColorAt(0.0, QColor(0, 0, 0, 0))
        gradient.setColorAt(0.75, QColor(0, 0, 0, 45))
        gradient.setColorAt(1.0, QColor(0, 0, 0, 85))
        painter.fillRect(output.rect(), gradient)
        painter.end()
        return output
