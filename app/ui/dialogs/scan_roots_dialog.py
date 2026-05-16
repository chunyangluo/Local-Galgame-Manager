from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.data.database import Database


class ScanRootsDialog(QDialog):
    def __init__(self, db: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("扫描路径管理")
        self.resize(760, 420)

        root = QVBoxLayout(self)
        self.list_widget = QListWidget()
        root.addWidget(self.list_widget, 1)

        buttons = QHBoxLayout()
        self.btn_add = QPushButton("添加路径")
        self.btn_add.clicked.connect(self._add_root)
        buttons.addWidget(self.btn_add)

        self.btn_remove = QPushButton("删除选中")
        self.btn_remove.clicked.connect(self._remove_selected)
        buttons.addWidget(self.btn_remove)

        self.btn_clear = QPushButton("清空全部")
        self.btn_clear.clicked.connect(self._clear_all)
        buttons.addWidget(self.btn_clear)
        buttons.addStretch(1)
        root.addLayout(buttons)

        close_buttons = QDialogButtonBox(QDialogButtonBox.Close)
        close_buttons.rejected.connect(self.reject)
        close_buttons.accepted.connect(self.accept)
        root.addWidget(close_buttons)

        self._refresh()

    def _refresh(self) -> None:
        self.list_widget.clear()
        for path in self.db.list_scan_roots():
            self.list_widget.addItem(path)

    def _add_root(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择游戏根目录")
        if not directory:
            return
        self.db.add_scan_root(directory)
        self._refresh()

    def _remove_selected(self) -> None:
        item = self.list_widget.currentItem()
        if item is None:
            return
        self.db.remove_scan_root(item.text())
        self._refresh()

    def _clear_all(self) -> None:
        if QMessageBox.question(self, "确认", "确定清空所有扫描路径吗？") != QMessageBox.Yes:
            return
        for path in self.db.list_scan_roots():
            self.db.remove_scan_root(path)
        self._refresh()
