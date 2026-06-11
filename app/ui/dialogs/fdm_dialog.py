"""Free Download Manager (FDM) — open app or enqueue download URL."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.services.fdm_service import (
    UI_PREF_FDM_EXE_PATH,
    add_download_task,
    open_fdm,
    resolve_fdm_exe,
)
from app.services.fdm_service import FdmNotFoundError

if TYPE_CHECKING:
    from app.ui.main_window import MainWindow


class FdmDialog(QDialog):
    def __init__(self, main: MainWindow, parent: QWidget | None = None) -> None:
        super().__init__(parent if parent is not None else main)
        self._main = main
        self.setWindowTitle("Free Download Manager")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        hint = QLabel(
            "通过 FDM 下载 galgame 资源包。可仅打开 FDM，或粘贴链接后自动新建下载任务。"
            '<br><span style="color:#93A1B6;font-size:11px;">'
            '未安装 FDM？<a href="https://www.freedownloadmanager.org/zh/">官方中文站下载</a>'
            "</span>"
        )
        hint.setTextFormat(Qt.TextFormat.RichText)
        hint.setOpenExternalLinks(True)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QFormLayout()
        path_row = QHBoxLayout()
        self._fdm_path = QLineEdit()
        self._fdm_path.setPlaceholderText("留空则使用默认安装路径")
        path_row.addWidget(self._fdm_path, 1)
        btn_browse = QPushButton("浏览…")
        btn_browse.clicked.connect(self._browse_fdm)
        path_row.addWidget(btn_browse)
        btn_save_path = QPushButton("保存")
        btn_save_path.clicked.connect(self._save_path)
        path_row.addWidget(btn_save_path)
        form.addRow("fdm.exe：", path_row)

        url_row = QHBoxLayout()
        self._url = QLineEdit()
        self._url.setPlaceholderText("https://…")
        url_row.addWidget(self._url, 1)
        btn_paste = QPushButton("粘贴")
        btn_paste.clicked.connect(self._paste_url)
        url_row.addWidget(btn_paste)
        form.addRow("下载链接：", url_row)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        self._btn_open = QPushButton("打开 FDM")
        self._btn_open.clicked.connect(self._on_open_fdm)
        btn_row.addWidget(self._btn_open)
        self._btn_add = QPushButton("添加下载任务")
        self._btn_add.setProperty("btnKind", "primary")
        self._btn_add.clicked.connect(self._on_add_task)
        btn_row.addWidget(self._btn_add)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        box = QDialogButtonBox(QDialogButtonBox.Close)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

        self._load_path()

    def _custom_path(self) -> str | None:
        text = self._fdm_path.text().strip()
        return text or None

    def _load_path(self) -> None:
        prefs = self._main.db.get_ui_preferences()
        saved = str(prefs.get(UI_PREF_FDM_EXE_PATH, "") or "").strip()
        if saved:
            self._fdm_path.setText(saved)
            return
        try:
            self._fdm_path.setPlaceholderText(str(resolve_fdm_exe()))
        except FdmNotFoundError:
            pass

    def _save_path(self) -> None:
        prefs = dict(self._main.db.get_ui_preferences())
        text = self._fdm_path.text().strip()
        if text:
            prefs[UI_PREF_FDM_EXE_PATH] = text
        else:
            prefs.pop(UI_PREF_FDM_EXE_PATH, None)
        self._main.db.set_ui_preferences(prefs)
        self._main.status.setText("已保存 FDM 路径")

    def _browse_fdm(self) -> None:
        start = self._fdm_path.text().strip() or r"C:\Program Files\Softdeluxe"
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 fdm.exe",
            start,
            "Free Download Manager (fdm.exe)",
        )
        if path:
            self._fdm_path.setText(path)

    def _paste_url(self) -> None:
        clip = QGuiApplication.clipboard()
        if clip is not None:
            text = clip.text().strip()
            if text:
                self._url.setText(text)

    def _on_open_fdm(self) -> None:
        try:
            open_fdm(custom_path=self._custom_path())
            self._main.status.setText("已启动 Free Download Manager")
        except (FdmNotFoundError, OSError) as exc:
            QMessageBox.warning(self, "无法启动 FDM", str(exc))

    def _on_add_task(self) -> None:
        try:
            add_download_task(self._url.text(), custom_path=self._custom_path())
            self._main.status.setText("已发送到 FDM 下载队列")
            self.accept()
        except ValueError as exc:
            QMessageBox.information(self, "链接无效", str(exc))
        except (FdmNotFoundError, OSError) as exc:
            QMessageBox.warning(self, "添加失败", str(exc))
