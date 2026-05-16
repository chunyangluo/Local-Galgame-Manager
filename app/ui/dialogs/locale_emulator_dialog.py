from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class LocaleEmulatorSettingsDialog(QDialog):
    def __init__(self, current_path: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Locale Emulator (LE)")
        self.resize(640, 220)
        root = QVBoxLayout(self)
        info = QLabel(
            "在本机安装 <a href=\"https://github.com/xupefei/Locale-Emulator/releases\">"
            "Locale Emulator</a> 后，选择其安装目录下的 <b>LEProc.exe</b>。"
            " 启动游戏时可选用「LE 转区启动」；LE 仓库已归档，发行版仍可下载使用。"
        )
        info.setWordWrap(True)
        info.setOpenExternalLinks(True)
        info.setTextInteractionFlags(Qt.TextBrowserInteraction)
        root.addWidget(info)
        row = QHBoxLayout()
        self._path = QLineEdit(current_path)
        self._path.setPlaceholderText(r"例如 C:\LocaleEmulator\LEProc.exe")
        row.addWidget(self._path, 1)
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        root.addLayout(row)
        hint = QLabel("留空并确定表示不使用 LE；之后仅显示普通启动。")
        hint.setStyleSheet("color:#93A1B6;font-size:11px;")
        hint.setWordWrap(True)
        root.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _browse(self) -> None:
        start = self._path.text().strip() or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 LEProc.exe",
            start,
            "LEProc.exe (LEProc.exe)",
        )
        if path:
            self._path.setText(path)

    def leproc_path(self) -> str:
        return self._path.text().strip()
