"""标题选择对话框：让用户从多个候选标题中选择游戏名称。"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QLabel,
    QSizePolicy,
    QDialogButtonBox,
)
from PySide6.QtCore import Qt, Signal


class TitleSelectorDialog(QDialog):
    """让用户从多个候选标题中选择游戏名称。"""

    title_selected = Signal(str)

    def __init__(
        self,
        current_name: str,
        candidates: list[tuple[str, str]],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("选择游戏标题")
        self.resize(500, 350)

        self._current_name = current_name
        self._candidates = candidates
        self._selected_title = ""

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # 提示信息
        hint_label = QLabel(
            "请选择一个合适的游戏标题。选中的标题将作为自定义名称保存，优先级最高。"
        )
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)

        # 当前名称显示
        current_label = QLabel(f"<b>当前名称：</b>{self._current_name}")
        layout.addWidget(current_label)

        # 候选列表
        self._list_widget = QListWidget()
        self._list_widget.setSelectionMode(QListWidget.SingleSelection)
        self._list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)

        for title, source in self._candidates:
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, source)
            item.setToolTip(f"来源：{source}")
            # 当前名称高亮显示
            if title == self._current_name:
                item.setBackground(Qt.lightGray)
            self._list_widget.addItem(item)

        if self._list_widget.count() > 0:
            self._list_widget.setCurrentRow(0)

        layout.addWidget(self._list_widget)

        # 按钮
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal,
            self,
        )
        button_box.accepted.connect(self._on_ok)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        self._selected_title = item.text()
        self.accept()

    def _on_ok(self) -> None:
        current_item = self._list_widget.currentItem()
        if current_item:
            self._selected_title = current_item.text()
        self.accept()

    def selected_title(self) -> str:
        return self._selected_title

    @staticmethod
    def get_title(
        current_name: str,
        candidates: list[tuple[str, str]],
        parent=None,
    ) -> str | None:
        """
        弹出对话框让用户选择标题。

        Args:
            current_name: 当前游戏名称
            candidates: 候选标题列表，格式为 [(title, source), ...]
            parent: 父窗口

        Returns:
            用户选择的标题，或 None（取消）
        """
        dialog = TitleSelectorDialog(current_name, candidates, parent)
        if dialog.exec() == QDialog.Accepted:
            return dialog.selected_title()
        return None
