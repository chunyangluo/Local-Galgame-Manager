from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFontMetrics, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.data.database import GameRecord


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

    def __init__(self, game: GameRecord, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._game = game
        self._retry_emitted = False
        self._force_no_cover = False
        self._retry_timer = QTimer(self)
        self._retry_timer.setSingleShot(True)
        self._retry_timer.timeout.connect(self._emit_retry_request)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        self.cover = QLabel()
        self.cover.setObjectName("gameCover")
        # Use near 2:3 portrait slot to better fit VNDB/Bangumi covers.
        self.cover.setFixedSize(168, 252)
        self.cover.setAlignment(Qt.AlignCenter)
        self._apply_cover(game.cover_path, game.image_url)
        root.addWidget(self.cover, 0, Qt.AlignHCenter)

        text_widget = QWidget()
        text_widget.setObjectName("gameTextBlock")
        text_col = QVBoxLayout()
        text_widget.setLayout(text_col)
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setContentsMargins(10, 6, 10, 10)
        text_col.setSpacing(3)
        self.title = TwoLineElideLabel(game.name)
        self.title.setObjectName("gameTitle")
        text_col.addWidget(self.title, 1)

        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.setSpacing(6)
        meta_row.addStretch(1)
        self.play_count = QLabel(f"🎮 × {game.play_count}")
        self.play_count.setObjectName("gameMeta")
        self.play_count.setAlignment(Qt.AlignRight | Qt.AlignBottom)
        source = self._cover_source_label(game.cover_path, game.image_url)
        self.cover_source = QLabel(source)
        self.cover_source.setObjectName("gameMetaSource")
        self.cover_source.setAlignment(Qt.AlignLeft | Qt.AlignBottom)
        meta_row.addWidget(self.cover_source)
        meta_row.addStretch(1)
        meta_row.addWidget(self.play_count)
        text_col.addLayout(meta_row)
        root.addWidget(text_widget, 1)

    def _apply_cover(self, cover_path: str | None, image_url: str | None = None) -> None:
        # Show a deterministic state before trying actual image loading.
        self.cover.setPixmap(self._build_placeholder_cover("加载中"))
        if cover_path:
            path = Path(cover_path)
            if path.exists():
                pix = QPixmap(str(path))
                if not pix.isNull():
                    scaled = self._scale_and_center_crop(pix, self.cover.size())
                    self.cover.setPixmap(self._with_bottom_gradient(scaled))
                    return
        # IMPORTANT: never request network images on UI thread.
        # VNDB images should be pre-cached by worker threads during import.
        # If cache is missing, keep placeholder to avoid UI freeze.
        if image_url and image_url.startswith(("http://", "https://")):
            if self._force_no_cover:
                self.cover.setPixmap(self._build_placeholder_cover("NO COVER"))
                return
            self.cover.setPixmap(self._build_placeholder_cover("等待缓存"))
            if not self._retry_emitted:
                self._retry_emitted = True
                self._retry_timer.start(120)
            return
        self.cover.setPixmap(self._build_placeholder_cover("NO COVER"))

    def force_no_cover_placeholder(self) -> None:
        self._force_no_cover = True
        self._apply_cover(self._game.cover_path, self._game.image_url)

    def _emit_retry_request(self) -> None:
        self.retry_cover_requested.emit(self._game.id)

    def _scale_and_center_crop(self, source: QPixmap, target_size: QSize) -> QPixmap:
        """Scale to cover target rect, then crop center region."""
        target_w = max(1, target_size.width())
        target_h = max(1, target_size.height())
        expanded = source.scaled(
            QSize(target_w, target_h),
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation,
        )
        crop_x = max(0, (expanded.width() - target_w) // 2)
        crop_y = max(0, (expanded.height() - target_h) // 2)
        return expanded.copy(crop_x, crop_y, target_w, target_h)

    def _build_placeholder_cover(self, label: str = "NO COVER") -> QPixmap:
        size = self.cover.size()
        pix = QPixmap(size)
        # 渐变背景
        gradient = QLinearGradient(0, 0, 0, size.height())
        gradient.setColorAt(0.0, QColor("#2A3242"))
        gradient.setColorAt(1.0, QColor("#1C2230"))
        pix.fill(QColor("#1C2230"))
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(pix.rect(), gradient)
        # 虚线边框
        painter.setPen(QPen(QColor("#3D4A5C"), 1, Qt.DashLine))
        painter.drawRoundedRect(4, 4, size.width() - 8, size.height() - 8, 8, 8)
        # 图标文字
        painter.setPen(QPen(QColor("#6B7D94"), 1))
        font = painter.font()
        font.setPointSize(11)
        painter.setFont(font)
        painter.drawText(pix.rect(), Qt.AlignCenter, label)
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

    def _cover_source_label(self, cover_path: str | None, image_url: str | None = None) -> str:
        if not cover_path and image_url:
            return "VNDB"
        if not cover_path:
            return "默认"
        normalized = cover_path.replace("\\", "/").lower()
        if normalized.startswith("http://") or normalized.startswith("https://"):
            return "VNDB"
        if "/covers/vndb/" in normalized:
            return "VNDB"
        if "/covers/online/" in normalized:
            return "在线"
        return "本地"
