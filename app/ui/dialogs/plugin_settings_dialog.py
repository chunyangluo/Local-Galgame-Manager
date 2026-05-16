from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.plugins.manager import PluginLoadInfo, PluginLoadStatus


class PluginSettingsDialog(QDialog):
    _STATUS_LABELS = {
        PluginLoadStatus.LOADED: "✓ 已加载",
        PluginLoadStatus.DISABLED: "○ 已禁用",
        PluginLoadStatus.FAILED: "✗ 加载失败",
    }
    _STATUS_COLORS = {
        PluginLoadStatus.LOADED: QColor("#6ECF8A"),
        PluginLoadStatus.DISABLED: QColor("#8B95A5"),
        PluginLoadStatus.FAILED: QColor("#E8605D"),
    }

    def __init__(
        self,
        load_info: list[PluginLoadInfo],
        disabled_names: set[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("插件管理")
        self.resize(620, 420)
        self._load_info = load_info
        self._disabled_names = disabled_names

        root = QVBoxLayout(self)
        hint = QLabel("勾选表示启用；取消勾选表示禁用。红色表示加载失败。")
        root.addWidget(hint)

        self.list_widget = QListWidget()
        root.addWidget(self.list_widget, 1)

        self._populate_list()

        self._detail_label = QLabel("")
        self._detail_label.setWordWrap(True)
        self._detail_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self._detail_label)

        self.list_widget.currentRowChanged.connect(self._on_row_changed)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _populate_list(self) -> None:
        for info in self._load_info:
            label = f"{info.name}  [{self._STATUS_LABELS[info.status]}]  ({info.source})"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, info)
            color = self._STATUS_COLORS[info.status]
            item.setForeground(color)

            if info.status == PluginLoadStatus.FAILED:
                item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Unchecked)
            elif info.status == PluginLoadStatus.DISABLED:
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Unchecked)
            else:
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked)

            self.list_widget.addItem(item)

    def _on_row_changed(self, row: int) -> None:
        if row < 0:
            self._detail_label.clear()
            return
        item = self.list_widget.item(row)
        info: PluginLoadInfo = item.data(Qt.UserRole)
        if info.status == PluginLoadStatus.FAILED and info.error:
            self._detail_label.setText(f"错误详情: {info.error}")
            self._detail_label.setStyleSheet("color: #E8605D;")
        elif info.status == PluginLoadStatus.DISABLED:
            self._detail_label.setText("此插件已被禁用，勾选即可启用")
            self._detail_label.setStyleSheet("color: #8B95A5;")
        else:
            source_text = "内置插件" if info.source == "builtin" else "第三方插件"
            self._detail_label.setText(f"来源: {source_text}")
            self._detail_label.setStyleSheet("color: #6ECF8A;")

    def disabled_names(self) -> list[str]:
        disabled: list[str] = []
        for idx in range(self.list_widget.count()):
            item = self.list_widget.item(idx)
            info: PluginLoadInfo = item.data(Qt.UserRole)
            if info.status == PluginLoadStatus.FAILED:
                continue
            if item.checkState() != Qt.Checked:
                disabled.append(info.name)
        return disabled
