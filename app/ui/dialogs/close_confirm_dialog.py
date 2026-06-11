"""Close main window: minimize to tray or quit entirely."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)


class CloseWindowConfirmDialog(QDialog):
    ACTION_TRAY = "tray"
    ACTION_QUIT = "quit"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("关闭窗口")
        self.setFixedWidth(360)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        title = QLabel("窗口已最小化至托盘")
        title.setStyleSheet("font-size: 13px; font-weight: 600;")
        layout.addWidget(title)

        self._tray_radio = QRadioButton("继续后台运行")
        self._quit_radio = QRadioButton("直接退出程序")
        self._tray_radio.setChecked(True)
        layout.addWidget(self._tray_radio)
        layout.addWidget(self._quit_radio)

        self._remember = QCheckBox("记住我的选择")
        self._remember.setToolTip("勾选后，下次点击关闭按钮将直接执行所选操作")
        layout.addWidget(self._remember)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("确定")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_action(self) -> str:
        return self.ACTION_QUIT if self._quit_radio.isChecked() else self.ACTION_TRAY

    def remember_choice(self) -> bool:
        return self._remember.isChecked()
