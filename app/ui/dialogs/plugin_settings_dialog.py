from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.plugins.base import PLUGIN_API_VERSION
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
        *,
        plugin_dir: Path | None = None,
        plugin_manager: object | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("插件管理")
        self.resize(720, 480)
        self._load_info = load_info
        self._disabled_names = disabled_names
        self._plugin_dir = plugin_dir
        self._plugin_manager = plugin_manager

        root = QVBoxLayout(self)
        hint = QLabel(
            f"勾选启用插件。当前插件 API v{PLUGIN_API_VERSION}。"
            " 红色为加载失败；可打开插件目录添加插件包后点「重新加载」。"
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        toolbar = QHBoxLayout()
        self._btn_open_dir = QPushButton("打开插件目录")
        self._btn_open_dir.clicked.connect(self._open_plugin_dir)
        toolbar.addWidget(self._btn_open_dir)
        self._btn_doc = QPushButton("查看开发文档")
        self._btn_doc.clicked.connect(self._open_plugin_guide)
        toolbar.addWidget(self._btn_doc)
        self._btn_reload = QPushButton("重新加载")
        self._btn_reload.setToolTip("从磁盘重新扫描插件（保留当前勾选状态）")
        self._btn_reload.clicked.connect(self._reload_plugins)
        toolbar.addWidget(self._btn_reload)
        toolbar.addStretch(1)
        root.addLayout(toolbar)

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
            pkg = "包" if info.package else "文件"
            ver = f"v{info.version}" if info.version else ""
            hooks = ", ".join(info.hooks) if info.hooks else "—"
            label = f"{info.name} {ver}  [{self._STATUS_LABELS[info.status]}]  ({info.source}/{pkg})"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, info)
            item.setForeground(self._STATUS_COLORS[info.status])

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
        info: PluginLoadInfo = self.list_widget.item(row).data(Qt.UserRole)
        lines: list[str] = []
        if info.description:
            lines.append(info.description)
        if info.author:
            lines.append(f"作者: {info.author}")
        if info.hooks:
            lines.append(f"钩子: {', '.join(info.hooks)}")
        if info.path:
            lines.append(f"路径: {info.path}")
        if info.status == PluginLoadStatus.FAILED and info.error:
            lines.append(f"错误: {info.error}")
        self._detail_label.setText("\n".join(lines) if lines else "无详细信息")
        if info.status == PluginLoadStatus.FAILED:
            self._detail_label.setStyleSheet("color: #E8605D;")
        else:
            self._detail_label.setStyleSheet("color: #93A1B6;")

    def _reload_plugins(self) -> None:
        if self._plugin_manager is None:
            QMessageBox.information(self, "提示", "无法重新加载（未绑定插件管理器）。")
            return
        disabled = set(self.disabled_names())
        for info in self._load_info:
            if info.status == PluginLoadStatus.FAILED:
                disabled.add(info.name)
        self._plugin_manager.reload(disabled_plugins=disabled)
        self._load_info = list(self._plugin_manager.load_info)
        self.list_widget.clear()
        self._populate_list()
        QMessageBox.information(self, "已重新加载", "插件列表已刷新。")

    def _open_plugin_dir(self) -> None:
        if self._plugin_dir is None:
            QMessageBox.information(self, "提示", "插件目录不可用。")
            return
        self._plugin_dir.mkdir(parents=True, exist_ok=True)
        path = str(self._plugin_dir.resolve())
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except OSError as exc:
            QMessageBox.warning(self, "无法打开", str(exc))

    def _open_plugin_guide(self) -> None:
        from app.services.paths import dev_repo_root

        root = dev_repo_root()
        guide = (root / "docs" / "PLUGIN_GUIDE.md") if root else None
        if guide is None or not guide.is_file():
            QMessageBox.information(
                self,
                "文档",
                "请参阅仓库 docs/PLUGIN_GUIDE.md（发行版请查看 GitHub 文档）。",
            )
            return
        try:
            if sys.platform == "win32":
                os.startfile(str(guide))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(guide)])
            else:
                subprocess.Popen(["xdg-open", str(guide)])
        except OSError as exc:
            QMessageBox.warning(self, "无法打开", str(exc))

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
