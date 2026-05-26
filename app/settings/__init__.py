"""设置模块 - 统一管理应用设置"""

from __future__ import annotations

from app.settings.defaults import (
    CoverFetchMode,
    DEFAULT_SETTINGS,
    DoubleClickAction,
    LaunchMode,
    get_default_settings,
)
from app.settings.settings_manager import SettingsManager

__all__ = [
    "SettingsManager",
    "DoubleClickAction",
    "LaunchMode",
    "CoverFetchMode",
    "DEFAULT_SETTINGS",
    "get_default_settings",
]
