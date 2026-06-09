"""Secondary confirmation before removing a game from the library."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class DeleteGameConfirmDialog(QDialog):
    def __init__(
        self,
        game_name: str,
        *,
        install_dir: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("确认删除游戏")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)

        title = QLabel(f"确定从库中删除「{game_name}」吗？")
        title.setWordWrap(True)
        title.setStyleSheet("font-size: 13px; font-weight: 600;")
        layout.addWidget(title)

        detail = QLabel(
            "将删除本软件中的记录（元数据、收藏、游玩记录、存档备份列表等）"
            "及软件内的封面/存档备份缓存。"
        )
        detail.setWordWrap(True)
        layout.addWidget(detail)

        self._delete_install_check = QCheckBox("同时删除游戏安装文件夹（不可恢复）")
        self._delete_install_check.setChecked(False)
        if install_dir:
            self._delete_install_check.setToolTip(install_dir)
            path_label = QLabel(f"安装目录：{install_dir}")
            path_label.setWordWrap(True)
            layout.addWidget(path_label)
        else:
            self._delete_install_check.setEnabled(False)
            self._delete_install_check.setToolTip("安装目录不存在，无法删除磁盘文件")
        layout.addWidget(self._delete_install_check)

        self._skip_check = QCheckBox("下次不再提示")
        self._skip_check.setChecked(False)
        self._skip_check.setToolTip("勾选后，之后删除游戏将不再弹出此确认框（仍可在数据管理中勾选删除安装文件夹）")
        layout.addWidget(self._skip_check)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No
        )
        buttons.button(QDialogButtonBox.StandardButton.Yes).setText("删除")
        buttons.button(QDialogButtonBox.StandardButton.Yes).setProperty("btnRole", "danger")
        buttons.button(QDialogButtonBox.StandardButton.No).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def delete_install_folder(self) -> bool:
        return self._delete_install_check.isChecked()

    def dont_ask_again(self) -> bool:
        return self._skip_check.isChecked()
