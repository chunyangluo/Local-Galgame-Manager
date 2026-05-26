"""设置管理器 - 统一管理所有应用设置"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.data.database import Database

from app.settings.defaults import (
    CoverFetchMode,
    DEFAULT_SETTINGS,
    DoubleClickAction,
    LaunchMode,
    get_default_settings,
)


class SettingsManager:
    """统一的应用设置管理器"""
    
    _instance: "SettingsManager | None" = None
    
    def __init__(self, db: "Database") -> None:
        self._db = db
    
    @classmethod
    def get_instance(cls, db: "Database | None" = None) -> "SettingsManager":
        """获取单例实例"""
        if cls._instance is None:
            if db is None:
                raise ValueError("SettingsManager 需要数据库实例初始化")
            cls._instance = cls(db)
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """重置单例（用于切换用户等场景）"""
        cls._instance = None
    
    # ========== 启动设置 ==========
    
    def get_double_click_action(self) -> str:
        """获取双击打开游戏的方式"""
        return self._db.get_double_click_action()
    
    def set_double_click_action(self, action: str) -> None:
        """设置双击打开游戏的方式"""
        self._db.set_double_click_action(action)
    
    def get_last_launch_mode(self) -> str:
        """获取上一次启动模式"""
        return self._db.get_last_launch_mode()
    
    def set_last_launch_mode(self, mode: str) -> None:
        """设置上一次启动模式"""
        self._db.set_last_launch_mode(mode)
    
    def get_auto_backup_before_launch(self) -> bool:
        """获取启动前自动备份设置"""
        return self._db.get_auto_backup_before_launch()
    
    def set_auto_backup_before_launch(self, enabled: bool) -> None:
        """设置启动前自动备份"""
        self._db.set_auto_backup_before_launch(enabled)
    
    # ========== 封面设置 ==========
    
    def get_cover_fetch_mode(self) -> str:
        """获取封面获取策略"""
        return self._db.get_cover_fetch_mode()
    
    def set_cover_fetch_mode(self, mode: str) -> None:
        """设置封面获取策略"""
        self._db.set_cover_fetch_mode(mode)
    
    # ========== 界面设置 ==========
    
    def get_ui_preferences(self) -> dict:
        """获取界面偏好设置"""
        return self._db.get_ui_preferences()
    
    def set_ui_preferences(self, preferences: dict) -> None:
        """设置界面偏好"""
        self._db.set_ui_preferences(preferences)
    
    # ========== 系统设置 ==========
    
    def get_locale_emulator_path(self) -> str:
        """获取Locale Emulator路径"""
        return self._db.get_locale_emulator_leproc_path()
    
    def set_locale_emulator_path(self, path: str) -> None:
        """设置Locale Emulator路径"""
        self._db.set_locale_emulator_leproc_path(path)
    
    def get_twodfan_hints_db_path(self) -> str:
        """获取2DFan线索库路径"""
        return self._db.get_twodfan_hints_db_path()
    
    def set_twodfan_hints_db_path(self, path: str) -> None:
        """设置2DFan线索库路径"""
        self._db.set_twodfan_hints_db_path(path)
    
    def get_disabled_plugins(self) -> list[str]:
        """获取禁用的插件列表"""
        return self._db.get_disabled_plugins()
    
    def set_disabled_plugins(self, plugins: list[str]) -> None:
        """设置禁用的插件列表"""
        self._db.set_disabled_plugins(plugins)
    
    # ========== 恢复默认 ==========
    
    def reset_to_defaults(self) -> None:
        """恢复所有设置为默认值"""
        # 启动设置
        self._db.set_double_click_action(DEFAULT_SETTINGS["double_click_action"])
        self._db.set_last_launch_mode(DEFAULT_SETTINGS["last_launch_mode"])
        self._db.set_auto_backup_before_launch(DEFAULT_SETTINGS["auto_backup_before_launch"])
        
        # 封面设置
        self._db.set_cover_fetch_mode(DEFAULT_SETTINGS["cover_fetch_mode"])
        
        # 界面设置
        self._db.set_ui_preferences(DEFAULT_SETTINGS["ui_preferences"])
        
        # 系统设置
        self._db.set_locale_emulator_path(DEFAULT_SETTINGS["locale_emulator_leproc_path"])
        self._db.set_twodfan_hints_db_path(DEFAULT_SETTINGS["twodfan_hints_db_path"])
    
    # ========== 便捷方法 ==========
    
    def is_le_available(self) -> bool:
        """检查LE是否可用"""
        path = self.get_locale_emulator_path()
        if not path:
            return False
        return Path(path).exists()
    
    def should_use_le_for_game(self, game_id: int | None = None) -> bool:
        """判断是否应该使用LE启动
        
        Args:
            game_id: 游戏ID（智能模式下会检查该游戏的上次启动记录）
            
        Returns:
            是否使用LE启动
        """
        action = self.get_double_click_action()
        
        if action == DoubleClickAction.FORCE_LE:
            return True
        elif action == DoubleClickAction.NORMAL:
            return False
        elif action == DoubleClickAction.SMART:
            # 智能模式：使用上一次启动的方式
            mode = self.get_last_launch_mode()
            return mode == LaunchMode.LE
        
        return False
