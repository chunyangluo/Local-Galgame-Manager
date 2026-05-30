"""Application display name and window/taskbar icon."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QWidget

APP_DISPLAY_NAME = "本地 Galgame 管理器"
APP_ENGLISH_NAME = "Local Galgame Manager"

_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
_ICON_ICO = _ASSETS_DIR / "app_icon.ico"
_ICON_PNG = _ASSETS_DIR / "app_icon.png"


def app_icon_path() -> Path | None:
    """Return best available icon file path."""
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "app" / "assets" / "app_icon.ico")
        candidates.append(Path(meipass) / "app" / "assets" / "app_icon.png")
    candidates.extend((_ICON_ICO, _ICON_PNG))
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable))
    for path in candidates:
        if path.is_file():
            return path
    return None


def load_app_icon() -> QIcon:
    """Load application icon for window, tray, and dialogs."""
    if getattr(sys, "frozen", False):
        exe_icon = QIcon(str(sys.executable))
        if not exe_icon.isNull():
            return exe_icon
    path = app_icon_path()
    if path is not None:
        icon = QIcon(str(path))
        if not icon.isNull():
            return icon
    return QIcon()


def setup_app_branding(app: QApplication) -> QIcon:
    """Apply display name and default icon to the QApplication."""
    app.setApplicationName(APP_DISPLAY_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    icon = load_app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    return icon


def apply_window_icon(widget: QWidget, icon: QIcon | None = None) -> None:
    ic = icon if icon is not None and not icon.isNull() else load_app_icon()
    if not ic.isNull():
        widget.setWindowIcon(ic)
