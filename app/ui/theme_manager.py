from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

ThemeType = Literal["light", "dark", "custom"]


@dataclass
class ThemeConfig:
    """主题配置类"""
    theme_type: ThemeType = "dark"
    accent_color: str = "#7FA7D9"
    accent_light: str = "#8FB4FF"
    accent_dark: str = "#3B4A66"
    primary_bg: str = "#1A1E25"
    secondary_bg: str = "#232831"
    tertiary_bg: str = "#2C3138"
    card_bg: str = "#252B34"
    border_color: str = "#3E4552"
    text_primary: str = "#F2F4F7"
    text_secondary: str = "#DCE3EE"
    text_tertiary: str = "#8B96AA"
    text_disabled: str = "#6B7280"
    button_bg: str = "#3A3F46"
    button_hover: str = "#454B55"
    button_pressed: str = "#2F343B"
    success_color: str = "#4ADE80"
    warning_color: str = "#FBBF24"
    error_color: str = "#F87171"
    font_family: str = "Segoe UI, Microsoft YaHei, sans-serif"
    font_size_small: int = 11
    font_size_normal: int = 13
    font_size_large: int = 15


@dataclass
class PresetTheme:
    """预设主题类"""
    name: str
    display_name: str
    description: str
    theme_type: ThemeType
    accent_color: str
    primary_bg: str
    secondary_bg: str
    tertiary_bg: str
    card_bg: str
    border_color: str
    text_primary: str
    text_secondary: str
    text_tertiary: str
    button_bg: str
    button_hover: str
    button_pressed: str


class PresetThemes:
    """预设主题集合"""
    
    # 深色系主题
    DEFAULT_DARK = PresetTheme(
        name="default_dark",
        display_name="默认深色",
        description="经典深蓝色调，适合夜间使用",
        theme_type="dark",
        accent_color="#7FA7D9",
        primary_bg="#1A1E25",
        secondary_bg="#232831",
        tertiary_bg="#2C3138",
        card_bg="#252B34",
        border_color="#3E4552",
        text_primary="#F2F4F7",
        text_secondary="#DCE3EE",
        text_tertiary="#8B96AA",
        button_bg="#3A3F46",
        button_hover="#454B55",
        button_pressed="#2F343B"
    )
    
    EYE_CARE_DARK = PresetTheme(
        name="eye_care_dark",
        display_name="护眼深色",
        description="柔和绿色调，减少视觉疲劳",
        theme_type="dark",
        accent_color="#4ADE80",
        primary_bg="#1A2420",
        secondary_bg="#1F2E28",
        tertiary_bg="#283832",
        card_bg="#233026",
        border_color="#354D40",
        text_primary="#E8F5E9",
        text_secondary="#C8E6C9",
        text_tertiary="#81C784",
        button_bg="#2E3D34",
        button_hover="#3D5045",
        button_pressed="#243029"
    )
    
    WARM_DARK = PresetTheme(
        name="warm_dark",
        display_name="暖色深色",
        description="温暖的橙黄色调，温馨舒适",
        theme_type="dark",
        accent_color="#FBBF24",
        primary_bg="#1F1A18",
        secondary_bg="#2A2420",
        tertiary_bg="#352D28",
        card_bg="#262220",
        border_color="#3D352F",
        text_primary="#F5F0EB",
        text_secondary="#E8DDD5",
        text_tertiary="#C4B5A8",
        button_bg="#3A302A",
        button_hover="#4A3F38",
        button_pressed="#302824"
    )
    
    PINK_DARK = PresetTheme(
        name="pink_dark",
        display_name="粉色深色",
        description="少女粉色系，可爱甜美",
        theme_type="dark",
        accent_color="#FB7185",
        primary_bg="#1F1820",
        secondary_bg="#28202C",
        tertiary_bg="#332836",
        card_bg="#24202A",
        border_color="#3D3048",
        text_primary="#F5F0F5",
        text_secondary="#E8DDE8",
        text_tertiary="#C4A8C4",
        button_bg="#3A2E3A",
        button_hover="#4A3D4A",
        button_pressed="#302430"
    )
    
    PURPLE_DARK = PresetTheme(
        name="purple_dark",
        display_name="紫色深色",
        description="神秘紫色调，优雅高贵",
        theme_type="dark",
        accent_color="#A78BFA",
        primary_bg="#1A1820",
        secondary_bg="#22202C",
        tertiary_bg="#2C2838",
        card_bg="#20202A",
        border_color="#343048",
        text_primary="#F0EDF5",
        text_secondary="#E0DBEC",
        text_tertiary="#B8AED4",
        button_bg="#32304A",
        button_hover="#423F5A",
        button_pressed="#282640"
    )
    
    # 浅色系主题
    DEFAULT_LIGHT = PresetTheme(
        name="default_light",
        display_name="默认浅色",
        description="明亮清爽的浅色主题",
        theme_type="light",
        accent_color="#3B82F6",
        primary_bg="#F8FAFC",
        secondary_bg="#F1F5F9",
        tertiary_bg="#E2E8F0",
        card_bg="#FFFFFF",
        border_color="#CBD5E1",
        text_primary="#1E293B",
        text_secondary="#475569",
        text_tertiary="#94A3B8",
        button_bg="#E2E8F0",
        button_hover="#CBD5E1",
        button_pressed="#94A3B8"
    )
    
    EYE_CARE_LIGHT = PresetTheme(
        name="eye_care_light",
        display_name="护眼浅色",
        description="柔和绿色调，保护眼睛",
        theme_type="light",
        accent_color="#22C55E",
        primary_bg="#F0FDF4",
        secondary_bg="#DCFCE7",
        tertiary_bg="#BBF7D0",
        card_bg="#FFFFFF",
        border_color="#86EFAC",
        text_primary="#14532D",
        text_secondary="#166534",
        text_tertiary="#15803D",
        button_bg="#DCFCE7",
        button_hover="#BBF7D0",
        button_pressed="#86EFAC"
    )
    
    WARM_LIGHT = PresetTheme(
        name="warm_light",
        display_name="暖色浅色",
        description="温暖的橙黄色调，温馨舒适",
        theme_type="light",
        accent_color="#F59E0B",
        primary_bg="#FFFBEB",
        secondary_bg="#FEF3C7",
        tertiary_bg="#FDE68A",
        card_bg="#FFFFFF",
        border_color="#FCD34D",
        text_primary="#78350F",
        text_secondary="#92400E",
        text_tertiary="#B45309",
        button_bg="#FEF3C7",
        button_hover="#FDE68A",
        button_pressed="#FCD34D"
    )
    
    ALL_PRESETS = [
        DEFAULT_DARK,
        EYE_CARE_DARK,
        WARM_DARK,
        PINK_DARK,
        PURPLE_DARK,
        DEFAULT_LIGHT,
        EYE_CARE_LIGHT,
        WARM_LIGHT,
    ]
    
    @classmethod
    def get_by_name(cls, name: str) -> Optional[PresetTheme]:
        """根据名称获取预设主题"""
        for preset in cls.ALL_PRESETS:
            if preset.name == name:
                return preset
        return None


class ThemeManager:
    """主题管理器，负责管理和应用主题配置"""
    
    _instance: Optional["ThemeManager"] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._current_config = ThemeConfig()
            cls._instance._listeners = []
        return cls._instance
    
    @property
    def config(self) -> ThemeConfig:
        return self._current_config
    
    def set_theme(self, theme_type: ThemeType):
        """设置预定义主题"""
        self._current_config.theme_type = theme_type
        
        if theme_type == "dark":
            self._apply_dark_theme()
        elif theme_type == "light":
            self._apply_light_theme()
        
        self._notify_listeners()
    
    def _apply_dark_theme(self):
        """应用深色主题"""
        config = self._current_config
        config.primary_bg = "#1A1E25"
        config.secondary_bg = "#232831"
        config.tertiary_bg = "#2C3138"
        config.card_bg = "#252B34"
        config.border_color = "#3E4552"
        config.text_primary = "#F2F4F7"
        config.text_secondary = "#DCE3EE"
        config.text_tertiary = "#8B96AA"
        config.text_disabled = "#6B7280"
        config.button_bg = "#3A3F46"
        config.button_hover = "#454B55"
        config.button_pressed = "#2F343B"
    
    def _apply_light_theme(self):
        """应用浅色主题"""
        config = self._current_config
        config.primary_bg = "#F8FAFC"
        config.secondary_bg = "#F1F5F9"
        config.tertiary_bg = "#E2E8F0"
        config.card_bg = "#FFFFFF"
        config.border_color = "#CBD5E1"
        config.text_primary = "#1E293B"
        config.text_secondary = "#475569"
        config.text_tertiary = "#94A3B8"
        config.text_disabled = "#CBD5E1"
        config.button_bg = "#E2E8F0"
        config.button_hover = "#CBD5E1"
        config.button_pressed = "#94A3B8"
    
    def apply_preset(self, preset: PresetTheme):
        """应用预设主题"""
        config = self._current_config
        config.theme_type = preset.theme_type
        config.accent_color = preset.accent_color
        config.accent_light = self._lighten_color(preset.accent_color, 20)
        config.accent_dark = self._darken_color(preset.accent_color, 30)
        config.primary_bg = preset.primary_bg
        config.secondary_bg = preset.secondary_bg
        config.tertiary_bg = preset.tertiary_bg
        config.card_bg = preset.card_bg
        config.border_color = preset.border_color
        config.text_primary = preset.text_primary
        config.text_secondary = preset.text_secondary
        config.text_tertiary = preset.text_tertiary
        config.button_bg = preset.button_bg
        config.button_hover = preset.button_hover
        config.button_pressed = preset.button_pressed
        
        # 根据背景色深浅设置禁用文字色
        if preset.theme_type == "dark":
            config.text_disabled = self._lighten_color(preset.text_tertiary, -40)
        else:
            config.text_disabled = preset.text_tertiary
        
        self._notify_listeners()
    
    def set_accent_color(self, color: str):
        """设置强调色"""
        self._current_config.accent_color = color
        # 根据主色计算浅色和深色变体
        self._current_config.accent_light = self._lighten_color(color, 20)
        self._current_config.accent_dark = self._darken_color(color, 30)
        self._notify_listeners()
    
    def set_font_sizes(self, small: int, normal: int, large: int):
        """设置字体大小"""
        self._current_config.font_size_small = small
        self._current_config.font_size_normal = normal
        self._current_config.font_size_large = large
        self._notify_listeners()
    
    def set_font_family(self, font_family: str):
        """设置字体族"""
        self._current_config.font_family = font_family
        self._notify_listeners()
    
    def get_stylesheet(self) -> str:
        """生成当前主题的完整样式表"""
        c = self._current_config
        
        return f"""
QPushButton {{
    color: {c.text_primary};
    background-color: {c.button_bg};
    border: 1px solid {c.border_color};
    border-radius: 8px;
    padding: 6px 12px;
    font-family: {c.font_family};
    font-size: {c.font_size_normal}px;
}}
QPushButton:hover {{
    background-color: {c.button_hover};
    border-color: {c.accent_color};
}}
QPushButton:pressed {{
    background-color: {c.button_pressed};
    border-color: {c.accent_dark};
}}
QToolButton {{
    color: {c.text_primary};
    background-color: {c.button_bg};
    border: 1px solid {c.border_color};
    border-radius: 8px;
    padding: 6px 12px;
    font-family: {c.font_family};
    font-size: {c.font_size_normal}px;
}}
QToolButton:hover {{
    background-color: {c.button_hover};
    border-color: {c.accent_color};
}}
QToolButton:pressed {{
    background-color: {c.button_pressed};
    border-color: {c.accent_dark};
}}
QLabel#toolbarSectionLabel {{
    color: {c.text_tertiary};
    font-size: {c.font_size_small}px;
    font-weight: 600;
    min-width: 3.2em;
    font-family: {c.font_family};
}}
QWidget[toolbarGroup="true"] {{
    background-color: {c.secondary_bg};
    border: 1px solid {c.border_color};
    border-radius: 10px;
}}
QWidget[toolbarTier="primary"] {{
    background-color: {c.card_bg};
    border: 1px solid {c.accent_color};
}}
QWidget[toolbarTier="secondary"] {{
    background-color: {c.secondary_bg};
    border: 1px solid {c.border_color};
}}
QPushButton:disabled {{
    color: {c.text_disabled};
    background-color: {c.tertiary_bg};
    border: 1px solid {c.border_color};
}}
QPushButton[highlighted="true"] {{
    border: 2px solid {c.warning_color};
    background-color: {c.accent_dark};
}}
QPushButton[active="true"] {{
    color: {c.text_primary};
    background-color: {c.button_bg};
    border: 2px solid {c.accent_light};
}}
QListWidget {{
    border: 1px solid {c.border_color};
    border-radius: 10px;
    padding: 6px;
    background-color: {c.secondary_bg};
}}
QListWidget::item {{
    background: {c.tertiary_bg};
    border: 1px solid {c.border_color};
    border-radius: 10px;
    margin: 2px;
}}
QListWidget::item:hover {{
    background: {c.card_bg};
    border: 1px solid {c.accent_color};
}}
QListWidget::item:selected {{
    background: {c.accent_dark};
    border: 1px solid {c.accent_color};
}}
QLabel {{
    color: {c.text_secondary};
    font-family: {c.font_family};
    font-size: {c.font_size_normal}px;
}}
QLabel[guided="true"] {{
    color: {c.warning_color};
}}
QLabel#gameTitle {{
    color: {c.text_primary};
    font-size: {c.font_size_large}px;
    font-weight: 600;
}}
QLabel#gameMeta {{
    color: {c.text_tertiary};
    font-size: {c.font_size_small}px;
}}
QLabel#gameMetaSource {{
    color: {c.accent_color};
    font-size: {c.font_size_small}px;
}}
QFrame#gameCardSlot {{
    background: {c.tertiary_bg};
    border: 1px solid {c.border_color};
    border-radius: 10px;
}}
QFrame#gameCardSlot:hover {{
    border: 2px solid {c.accent_color};
}}
QFrame#gameCardSlot[selected="true"] {{
    background: {c.accent_dark};
    border: 2px solid {c.accent_color};
}}
QLabel#gridPageLabel {{
    color: {c.text_tertiary};
    font-size: {c.font_size_small + 1}px;
}}
QWidget#gameTextBlock {{
    background: {c.card_bg};
    border-radius: 8px;
}}
QLabel#gameCover {{
    background: transparent;
    border: none;
    border-radius: 6px;
}}
QLineEdit {{
    color: {c.text_primary};
    background-color: {c.tertiary_bg};
    border: 1px solid {c.border_color};
    border-radius: 8px;
    padding: 6px 10px;
    font-family: {c.font_family};
    font-size: {c.font_size_normal}px;
}}
QLineEdit:focus {{
    border-color: {c.accent_color};
    outline: none;
}}
QComboBox {{
    color: {c.text_primary};
    background-color: {c.tertiary_bg};
    border: 1px solid {c.border_color};
    border-radius: 8px;
    padding: 4px 8px;
    font-family: {c.font_family};
    font-size: {c.font_size_normal}px;
}}
QComboBox:hover {{
    border-color: {c.accent_color};
}}
QComboBox QAbstractItemView {{
    background-color: {c.secondary_bg};
    border: 1px solid {c.border_color};
    selection-background-color: {c.accent_dark};
}}
QCheckBox {{
    color: {c.text_secondary};
    font-family: {c.font_family};
    font-size: {c.font_size_normal}px;
}}
QProgressBar {{
    background-color: {c.tertiary_bg};
    border: 1px solid {c.border_color};
    border-radius: 8px;
    text-align: center;
}}
QProgressBar::chunk {{
    background-color: {c.accent_color};
    border-radius: 6px;
}}
QStatusBar {{
    color: {c.text_tertiary};
    background-color: {c.secondary_bg};
    font-family: {c.font_family};
    font-size: {c.font_size_small}px;
}}
QDialog {{
    background-color: {c.secondary_bg};
    border: 1px solid {c.border_color};
    border-radius: 12px;
}}
QMessageBox {{
    background-color: {c.secondary_bg};
}}
"""
    
    def add_listener(self, callback):
        """添加主题变更监听器"""
        self._notify_listeners()
    
    def _notify_listeners(self):
        """通知所有监听器主题已变更"""
        for callback in self._listeners:
            try:
                callback()
            except Exception:
                pass
    
    def _lighten_color(self, hex_color: str, percent: int) -> str:
        """使颜色变亮（正数）或变暗（负数）"""
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        
        delta = int(2.55 * percent)
        r = max(0, min(255, r + delta))
        g = max(0, min(255, g + delta))
        b = max(0, min(255, b + delta))
        
        return f"#{r:02X}{g:02X}{b:02X}"
    
    def _darken_color(self, hex_color: str, percent: int) -> str:
        """使颜色变暗"""
        return self._lighten_color(hex_color, -percent)
    
    def load_from_dict(self, data: dict):
        """从字典加载配置"""
        config = self._current_config
        
        # 如果有预设主题名称，直接应用预设
        preset_name = data.get("preset_theme")
        if preset_name:
            preset = PresetThemes.get_by_name(preset_name)
            if preset:
                self.apply_preset(preset)
                # 加载字体设置
                config.font_family = data.get("font_family", "Segoe UI, Microsoft YaHei, sans-serif")
                config.font_size_small = data.get("font_size_small", 11)
                config.font_size_normal = data.get("font_size_normal", 13)
                config.font_size_large = data.get("font_size_large", 15)
                return
        
        # 否则加载自定义配置
        config.theme_type = data.get("theme_type", "dark")
        config.accent_color = data.get("accent_color", "#7FA7D9")
        config.font_family = data.get("font_family", "Segoe UI, Microsoft YaHei, sans-serif")
        config.font_size_small = data.get("font_size_small", 11)
        config.font_size_normal = data.get("font_size_normal", 13)
        config.font_size_large = data.get("font_size_large", 15)
        
        # 加载完整颜色配置（如果存在）
        config.primary_bg = data.get("primary_bg", config.primary_bg)
        config.secondary_bg = data.get("secondary_bg", config.secondary_bg)
        config.tertiary_bg = data.get("tertiary_bg", config.tertiary_bg)
        config.card_bg = data.get("card_bg", config.card_bg)
        config.border_color = data.get("border_color", config.border_color)
        config.text_primary = data.get("text_primary", config.text_primary)
        config.text_secondary = data.get("text_secondary", config.text_secondary)
        config.text_tertiary = data.get("text_tertiary", config.text_tertiary)
        config.button_bg = data.get("button_bg", config.button_bg)
        config.button_hover = data.get("button_hover", config.button_hover)
        config.button_pressed = data.get("button_pressed", config.button_pressed)
        
        # 重新计算强调色变体
        config.accent_light = self._lighten_color(config.accent_color, 20)
        config.accent_dark = self._darken_color(config.accent_color, 30)
    
    def to_dict(self) -> dict:
        """导出配置为字典"""
        config = self._current_config
        return {
            "preset_theme": None,  # 将由 save_preset_name 方法设置
            "theme_type": config.theme_type,
            "accent_color": config.accent_color,
            "primary_bg": config.primary_bg,
            "secondary_bg": config.secondary_bg,
            "tertiary_bg": config.tertiary_bg,
            "card_bg": config.card_bg,
            "border_color": config.border_color,
            "text_primary": config.text_primary,
            "text_secondary": config.text_secondary,
            "text_tertiary": config.text_tertiary,
            "button_bg": config.button_bg,
            "button_hover": config.button_hover,
            "button_pressed": config.button_pressed,
            "font_family": config.font_family,
            "font_size_small": config.font_size_small,
            "font_size_normal": config.font_size_normal,
            "font_size_large": config.font_size_large,
        }
    
    def save_preset_name(self, preset_name: str):
        """保存当前预设主题名称"""
        data = self.to_dict()
        data["preset_theme"] = preset_name
        return data
