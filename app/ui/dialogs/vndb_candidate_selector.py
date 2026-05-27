from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.services.vndb_service import VndbRecord


class VndbCandidateSelector(QDialog):
    def __init__(
        self,
        query: str,
        candidates: list[VndbRecord],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"选择 VNDB 条目 - {query}")
        self.resize(680, 520)
        self._selected_record: VndbRecord | None = None

        layout = QVBoxLayout(self)

        title_label = QLabel(f"找到 {len(candidates)} 个匹配结果，请选择正确的游戏：")
        layout.addWidget(title_label)

        self._list_widget = QListWidget()
        self._list_widget.setSelectionMode(QListWidget.SingleSelection)
        self._list_widget.currentItemChanged.connect(self._on_selection_changed)
        layout.addWidget(self._list_widget, 1)

        self._detail_panel = QWidget()
        detail_layout = QHBoxLayout(self._detail_panel)
        
        self._cover_label = QLabel()
        self._cover_label.setFixedSize(150, 200)
        self._cover_label.setAlignment(Qt.AlignCenter)
        self._cover_label.setStyleSheet("background:#252C36;border-radius:8px;")
        detail_layout.addWidget(self._cover_label)

        info_layout = QVBoxLayout()
        self._title_label = QLabel()
        self._title_label.setStyleSheet("font-size:14px;font-weight:600;color:#F3F6FB;")
        info_layout.addWidget(self._title_label)

        self._original_label = QLabel()
        self._original_label.setStyleSheet("font-size:12px;color:#93A1B6;")
        info_layout.addWidget(self._original_label)

        self._rating_label = QLabel()
        self._rating_label.setStyleSheet("font-size:12px;color:#7FA7D9;")
        info_layout.addWidget(self._rating_label)

        self._platforms_label = QLabel()
        self._platforms_label.setStyleSheet("font-size:12px;color:#7FA7D9;")
        info_layout.addWidget(self._platforms_label)

        self._languages_label = QLabel()
        self._languages_label.setStyleSheet("font-size:12px;color:#7FA7D9;")
        info_layout.addWidget(self._languages_label)

        self._description_label = QLabel()
        self._description_label.setWordWrap(True)
        self._description_label.setStyleSheet("font-size:12px;color:#C8D0DC;margin-top:8px;")
        info_layout.addWidget(self._description_label)

        info_layout.addStretch(1)
        detail_layout.addLayout(info_layout, 1)
        layout.addWidget(self._detail_panel)

        buttons = QDialogButtonBox()
        self._ok_btn = QPushButton("确认选择")
        self._ok_btn.setProperty("btnRole", "primary")
        self._ok_btn.setEnabled(False)
        self._ok_btn.clicked.connect(self.accept)
        
        skip_btn = QPushButton("跳过此项")
        skip_btn.setProperty("btnRole", "secondary")
        skip_btn.clicked.connect(self.reject)

        buttons.addButton(self._ok_btn, QDialogButtonBox.AcceptRole)
        buttons.addButton(skip_btn, QDialogButtonBox.RejectRole)
        layout.addWidget(buttons)

        self._network_manager = QNetworkAccessManager(self)

        for idx, record in enumerate(candidates):
            item = QListWidgetItem()
            item.setText(f"{idx + 1}. {record.title_localized or record.title_original or record.vndb_id}")
            item.setData(Qt.UserRole, record)
            self._list_widget.addItem(item)

    def _on_selection_changed(self, current: QListWidgetItem | None, _) -> None:
        if current is None:
            self._selected_record = None
            self._ok_btn.setEnabled(False)
            return

        record: VndbRecord = current.data(Qt.UserRole)
        self._selected_record = record
        self._ok_btn.setEnabled(True)

        self._title_label.setText(record.title_localized or "无译名")
        self._original_label.setText(f"原名: {record.title_original or '未知'}")
        self._rating_label.setText(f"评分: {float(record.rating):.2f}/10" if record.rating else "评分: 未获取")
        self._platforms_label.setText(f"平台: {record.platforms or '未获取'}")
        self._languages_label.setText(f"语言: {record.languages or '未获取'}")
        desc = record.description or "暂无简介"
        self._description_label.setText(desc[:300] + "..." if len(desc) > 300 else desc)

        if record.image_url:
            self._load_cover(record.image_url)
        else:
            self._cover_label.setPixmap(QPixmap())
            self._cover_label.setText("无封面")

    def _load_cover(self, url: str) -> None:
        request = QNetworkRequest(QUrl(url))
        reply = self._network_manager.get(request)
        reply.finished.connect(lambda: self._on_cover_loaded(reply))

    def _on_cover_loaded(self, reply) -> None:
        try:
            data = reply.readAll()
            pixmap = QPixmap()
            if pixmap.loadFromData(data):
                scaled = pixmap.scaled(
                    self._cover_label.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
                self._cover_label.setPixmap(scaled)
                self._cover_label.setText("")
            else:
                self._cover_label.setText("加载失败")
        except Exception:
            self._cover_label.setText("加载失败")
        finally:
            reply.deleteLater()

    def get_selected(self) -> VndbRecord | None:
        return self._selected_record

    @staticmethod
    def select_candidate(
        query: str,
        candidates: list[VndbRecord],
        parent: QWidget | None = None,
    ) -> VndbRecord | None:
        if not candidates:
            return None
        dialog = VndbCandidateSelector(query, candidates, parent)
        if dialog.exec():
            return dialog.get_selected()
        return None
