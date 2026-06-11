"""Helpers for correct child-dialog stacking above modal or auxiliary parents."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QDialog, QWidget

_DEFAULT_OFFSET = QPoint(40, 40)


def _offset_child_position(parent: QWidget, child: QDialog, offset: QPoint | None = None) -> None:
    off = offset if offset is not None else _DEFAULT_OFFSET
    parent_geo = parent.frameGeometry()
    child.adjustSize()
    child.move(parent_geo.topLeft() + off)


def present_auxiliary_dialog(parent: QWidget, dlg: QDialog, *, offset: QPoint | None = None) -> None:
    """Show a non-blocking tool window above ``parent`` (modal to ``parent`` only)."""
    dlg.setWindowModality(Qt.WindowModality.WindowModal)
    dlg.setWindowFlag(Qt.WindowType.Window, True)
    _offset_child_position(parent, dlg, offset)
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()


def exec_child_dialog(parent: QWidget, dlg: QDialog, *, offset: QPoint | None = None) -> int:
    """Run a modal child dialog stacked above ``parent``."""
    dlg.setWindowModality(Qt.WindowModality.WindowModal)
    _offset_child_position(parent, dlg, offset)
    dlg.raise_()
    dlg.activateWindow()
    return dlg.exec()
