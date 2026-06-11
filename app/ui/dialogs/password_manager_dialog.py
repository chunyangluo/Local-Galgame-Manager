"""密码本管理对话框 — 添加、删除、置顶、排序、查看统计。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services import auto_extract_service as aes


class PasswordManagerDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("密码本管理")
        self.resize(560, 480)
        self._build_ui()
        self._refresh()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # 说明
        info = QLabel(
            "管理解压密码本。密码按优先级从上到下尝试：置顶密码 > 按成功次数降序。"
            "解压时先尝试无密码，再按此顺序逐个尝试。"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#93A1B6;font-size:11px;")
        root.addWidget(info)

        # 密码表格
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["密码", "成功次数", "置顶"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        root.addWidget(self._table, 1)

        # 添加行
        add_row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText("输入新密码")
        self._input.returnPressed.connect(self._add_password)
        add_row.addWidget(self._input, 1)
        btn_add = QPushButton("添加")
        btn_add.clicked.connect(self._add_password)
        add_row.addWidget(btn_add)
        root.addLayout(add_row)

        # 操作按钮行
        btn_row = QHBoxLayout()

        btn_up = QPushButton("上移")
        btn_up.clicked.connect(self._move_up)
        btn_row.addWidget(btn_up)

        btn_down = QPushButton("下移")
        btn_down.clicked.connect(self._move_down)
        btn_row.addWidget(btn_down)

        btn_pin = QPushButton("置顶/取消置顶")
        btn_pin.clicked.connect(self._toggle_pin)
        btn_row.addWidget(btn_pin)

        btn_row.addStretch()

        btn_clear = QPushButton("清空统计")
        btn_clear.clicked.connect(self._clear_stats)
        btn_row.addWidget(btn_clear)

        btn_del = QPushButton("删除")
        btn_del.setStyleSheet("color:#EF4444;")
        btn_del.clicked.connect(self._delete_password)
        btn_row.addWidget(btn_del)

        root.addLayout(btn_row)

        # 关闭按钮
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        root.addWidget(sep)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        root.addWidget(btn_close)

    # --------------------------------------------------------------- 数据

    def _refresh(self) -> None:
        """刷新表格数据。"""
        try:
            items = aes.get_passwords_with_stats()
        except Exception:
            items = []

        self._table.setRowCount(len(items))
        for row, item in enumerate(items):
            pwd = item["password"]
            count = item["success_count"]
            pinned = item["is_pinned"]

            pwd_item = QTableWidgetItem(pwd or "(空)")
            pwd_item.setData(Qt.UserRole, pwd)
            self._table.setItem(row, 0, pwd_item)

            # 成功次数
            count_item = QTableWidgetItem(str(count))
            count_item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(row, 1, count_item)

            # 置顶标记
            pin_item = QTableWidgetItem("是" if pinned else "")
            pin_item.setTextAlignment(Qt.AlignCenter)
            if pinned:
                pin_item.setForeground(Qt.darkGreen)
            self._table.setItem(row, 2, pin_item)

    def _selected_password(self) -> str | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self._table.item(rows[0].row(), 0)
        return item.data(Qt.UserRole) if item else None

    # --------------------------------------------------------------- 操作

    def _add_password(self) -> None:
        pwd = self._input.text().strip()
        if not pwd:
            return
        try:
            ok, msg = aes.add_password(pwd)
        except Exception as e:
            QMessageBox.warning(self, "错误", str(e))
            return
        if ok:
            self._input.clear()
            self._refresh()
        else:
            QMessageBox.information(self, "提示", msg)

    def _delete_password(self) -> None:
        pwd = self._selected_password()
        if pwd is None:
            QMessageBox.information(self, "提示", "请先选择一行")
            return
        reply = QMessageBox.question(
            self, "确认删除", f"确定要删除密码「{pwd}」吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            ok, msg = aes.remove_password(pwd)
        except Exception as e:
            QMessageBox.warning(self, "错误", str(e))
            return
        if ok:
            self._refresh()
        else:
            QMessageBox.information(self, "提示", msg)

    def _toggle_pin(self) -> None:
        pwd = self._selected_password()
        if pwd is None:
            QMessageBox.information(self, "提示", "请先选择一行")
            return
        # 查当前是否置顶
        try:
            items = aes.get_passwords_with_stats()
        except Exception:
            return
        is_pinned = any(p["password"] == pwd and p["is_pinned"] for p in items)
        try:
            ok, msg = aes.set_password_pinned(pwd, not is_pinned)
        except Exception as e:
            QMessageBox.warning(self, "错误", str(e))
            return
        if ok:
            self._refresh()
        else:
            QMessageBox.information(self, "提示", msg)

    def _move_up(self) -> None:
        pwd = self._selected_password()
        if pwd is None:
            QMessageBox.information(self, "提示", "请先选择一行")
            return
        try:
            aes.move_password(pwd, -1)
        except Exception:
            return
        self._refresh()
        # 重新选中
        self._select_by_pwd(pwd)

    def _move_down(self) -> None:
        pwd = self._selected_password()
        if pwd is None:
            QMessageBox.information(self, "提示", "请先选择一行")
            return
        try:
            aes.move_password(pwd, 1)
        except Exception:
            return
        self._refresh()
        self._select_by_pwd(pwd)

    def _clear_stats(self) -> None:
        reply = QMessageBox.question(
            self, "确认清空", "确定要清空所有密码的使用统计吗？\n此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            aes.clear_password_stats()
        except Exception as e:
            QMessageBox.warning(self, "错误", str(e))
            return
        self._refresh()

    def _select_by_pwd(self, pwd: str) -> None:
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item and item.data(Qt.UserRole) == pwd:
                self._table.selectRow(row)
                break
