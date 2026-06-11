from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.data.database import GameRecord


class EditGameDialog(QDialog):
    def __init__(self, game: GameRecord, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._is_video = getattr(game, "content_type", "game") == "video"
        self.setWindowTitle("编辑视频信息" if self._is_video else "编辑游戏信息")
        self.resize(650, 150)
        self._default_browse_dir = game.root_dir
        launch_parent = Path(game.launch_exe).parent
        if launch_parent.exists():
            self._default_browse_dir = str(launch_parent)

        layout = QFormLayout(self)

        self.name_input = QLineEdit(game.name)
        layout.addRow("视频名" if self._is_video else "游戏名", self.name_input)

        launch_row = QHBoxLayout()
        self.launch_input = QLineEdit(game.launch_exe)
        launch_row.addWidget(self.launch_input, 1)
        browse_btn = QPushButton("浏览")
        browse_btn.clicked.connect(self._browse_entry)
        launch_row.addWidget(browse_btn)

        launch_wrapper = QWidget()
        launch_wrapper.setLayout(launch_row)
        layout.addRow("视频文件" if self._is_video else "启动路径", launch_wrapper)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse_entry(self) -> None:
        title = "选择视频文件" if self._is_video else "选择启动程序"
        file_filter = (
            "Videos (*.mp4 *.mkv *.avi *.wmv *.flv *.mov *.webm *.m4v *.ts *.m2ts);;All (*.*)"
            if self._is_video
            else "Executable (*.exe)"
        )
        path, _ = QFileDialog.getOpenFileName(
            self,
            title,
            self._default_browse_dir,
            file_filter,
        )
        if path:
            self.launch_input.setText(path)
            parent = str(Path(path).parent)
            self._default_browse_dir = parent

    def values(self) -> tuple[str, str]:
        return self.name_input.text().strip(), self.launch_input.text().strip()
