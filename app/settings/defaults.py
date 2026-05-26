"""默认设置值模块"""

from __future__ import annotations


# 双击打开游戏的方式
class DoubleClickAction:
    NORMAL = "normal"       # 普通启动
    FORCE_LE = "force_le"  # 强制使用LE转区
    SMART = "smart"         # 智能模式（记住上一次）

    @staticmethod
    def get_label(action: str) -> str:
        labels = {
            DoubleClickAction.NORMAL: "普通启动",
            DoubleClickAction.FORCE_LE: "强制使用LE转区",
            DoubleClickAction.SMART: "智能模式（记住上次）",
        }
        return labels.get(action, "普通启动")

    @staticmethod
    def get_description(action: str) -> str:
        descriptions = {
            DoubleClickAction.NORMAL: "直接启动游戏exe",
            DoubleClickAction.FORCE_LE: "强制使用Locale Emulator转区启动",
            DoubleClickAction.SMART: "自动使用上一次启动该游戏的方式",
        }
        return descriptions.get(action, "")


# 启动模式
class LaunchMode:
    NORMAL = "normal"  # 普通启动
    LE = "le"          # LE转区启动


# 封面获取策略
class CoverFetchMode:
    LOCAL_ONLY = "local_only"
    LOCAL_PREFER = "local_prefer"
    ONLINE_PREFER = "online_prefer"

    @staticmethod
    def get_label(mode: str) -> str:
        labels = {
            CoverFetchMode.LOCAL_ONLY: "仅本地封面",
            CoverFetchMode.LOCAL_PREFER: "本地优先",
            CoverFetchMode.ONLINE_PREFER: "网图优先",
        }
        return labels.get(mode, "本地优先")


# 默认设置
DEFAULT_SETTINGS = {
    # 启动设置
    "double_click_action": DoubleClickAction.NORMAL,
    "last_launch_mode": LaunchMode.NORMAL,
    "auto_backup_before_launch": False,
    
    # 封面设置
    "cover_fetch_mode": CoverFetchMode.LOCAL_PREFER,
    
    # 界面设置
    "ui_preferences": {},
    
    # 系统设置
    "locale_emulator_leproc_path": "",
    "twodfan_hints_db_path": "",
}


def get_default_settings() -> dict:
    """获取默认设置的深拷贝"""
    import copy
    return copy.deepcopy(DEFAULT_SETTINGS)
