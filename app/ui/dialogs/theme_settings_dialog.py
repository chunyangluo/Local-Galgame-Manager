from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
    QLabel,
    QPushButton,
    QComboBox,
    QSpinBox,
    QColorDialog,
    QGroupBox,
    QGridLayout,
    QCheckBox,
    QScrollArea,
    QSlider,
)

from app.ui.theme_manager import ThemeManager, ThemeType, PresetThemes


class ThemeSettingsDialog(QDialog):
    """主题设置对话框 - 增强版"""
    
    theme_changed = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("界面个性化设置")
        self.setMinimumWidth(700)
        self.setMinimumHeight(600)
        
        self._theme_manager = ThemeManager()
        self._original_config = self._theme_manager.to_dict().copy()
        self._current_preset_name = None  # 当前选中的预设主题
        
        self._setup_ui()
        self._load_current_settings()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # 滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_area.setWidget(scroll_content)
        
        # 预设主题选择
        preset_group = QGroupBox("预设主题（一键切换）")
        preset_layout = QVBoxLayout(preset_group)
        
        # 深色主题预设
        dark_label = QLabel("深色主题：")
        dark_label.setStyleSheet("font-weight: bold;")
        preset_layout.addWidget(dark_label)
        
        dark_row = QHBoxLayout()
        for preset in [p for p in PresetThemes.ALL_PRESETS if p.theme_type == "dark"]:
            btn = self._create_preset_button(preset)
            dark_row.addWidget(btn)
        dark_row.addStretch(1)
        preset_layout.addLayout(dark_row)
        
        # 浅色主题预设
        light_label = QLabel("浅色主题：")
        light_label.setStyleSheet("font-weight: bold;")
        preset_layout.addWidget(light_label)
        
        light_row = QHBoxLayout()
        for preset in [p for p in PresetThemes.ALL_PRESETS if p.theme_type == "light"]:
            btn = self._create_preset_button(preset)
            light_row.addWidget(btn)
        light_row.addStretch(1)
        preset_layout.addLayout(light_row)
        
        scroll_layout.addWidget(preset_group)
        
        # 主题类型选择
        theme_group = QGroupBox("自定义调整")
        theme_layout = QHBoxLayout(theme_group)
        
        self._theme_combo = QComboBox()
        self._theme_combo.addItems(["深色模式", "浅色模式", "自定义模式"])
        self._theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        self._theme_combo.setFixedWidth(200)
        theme_layout.addWidget(self._theme_combo)
        theme_layout.addStretch(1)
        
        scroll_layout.addWidget(theme_group)
        
        # 预览区域
        preview_group = QGroupBox("实时预览")
        preview_layout = QHBoxLayout(preview_group)
        self._preview_widget = _ThemePreviewWidget()
        preview_layout.addWidget(self._preview_widget)
        
        scroll_layout.addWidget(preview_group)
        
        # 强调色设置
        accent_group = QGroupBox("强调色")
        accent_layout = QVBoxLayout(accent_group)
        
        # 当前强调色预览和选择
        accent_row = QHBoxLayout()
        self._accent_color_label = QLabel()
        self._accent_color_label.setFixedSize(50, 50)
        self._accent_color_label.setStyleSheet("border-radius: 10px; border: 2px solid #555;")
        accent_row.addWidget(self._accent_color_label)
        
        accent_picker_button = QPushButton("选择颜色")
        accent_picker_button.clicked.connect(self._pick_accent_color)
        accent_picker_button.setFixedWidth(120)
        accent_row.addWidget(accent_picker_button)
        
        accent_row.addStretch(1)
        accent_layout.addLayout(accent_row)
        
        # 预设颜色
        preset_row = QHBoxLayout()
        preset_colors = [
            "#7FA7D9", "#FF6B6B", "#4ADE80", "#FBBF24", 
            "#A78BFA", "#FB7185", "#06B6D4", "#84CC16",
            "#F97316", "#EC4899", "#14B8A6", "#6366F1"
        ]
        self._preset_buttons = []
        for color in preset_colors:
            btn = QPushButton()
            btn.setFixedSize(32, 32)
            btn.setStyleSheet(f"background-color: {color}; border-radius: 8px; border: 2px solid transparent;")
            btn.clicked.connect(lambda checked, c=color: self._set_accent_color(c))
            btn.setToolTip(color)
            self._preset_buttons.append(btn)
            preset_row.addWidget(btn)
        
        preset_row.addStretch(1)
        accent_layout.addLayout(preset_row)
        
        scroll_layout.addWidget(accent_group)
        
        # 自定义颜色（高级选项）
        custom_color_group = QGroupBox("自定义颜色（高级）")
        custom_color_layout = QGridLayout(custom_color_group)
        
        self._color_pickers = {}
        
        # 背景色
        self._add_color_picker(custom_color_layout, "primary_bg", "主背景色", 0)
        self._add_color_picker(custom_color_layout, "secondary_bg", "次背景色", 1)
        self._add_color_picker(custom_color_layout, "tertiary_bg", "三级背景色", 2)
        self._add_color_picker(custom_color_layout, "card_bg", "卡片背景色", 3)
        
        # 文字色
        self._add_color_picker(custom_color_layout, "text_primary", "主要文字色", 4)
        self._add_color_picker(custom_color_layout, "text_secondary", "次要文字色", 5)
        self._add_color_picker(custom_color_layout, "text_tertiary", "三级文字色", 6)
        self._add_color_picker(custom_color_layout, "border_color", "边框颜色", 7)
        
        scroll_layout.addWidget(custom_color_group)
        
        # 字体设置
        font_group = QGroupBox("字体设置")
        font_layout = QGridLayout(font_group)
        
        font_layout.addWidget(QLabel("字体:"), 0, 0)
        self._font_combo = QComboBox()
        self._font_combo.addItems([
            "Segoe UI, Microsoft YaHei, sans-serif",
            "Microsoft YaHei, sans-serif",
            "SimHei, sans-serif",
            "SimSun, serif",
            "Arial, sans-serif",
            "Times New Roman, serif",
            "Consolas, monospace",
            "Noto Sans SC, sans-serif",
            "PingFang SC, sans-serif",
        ])
        font_layout.addWidget(self._font_combo, 0, 1)
        
        font_layout.addWidget(QLabel("小号字体大小:"), 1, 0)
        self._font_small_spin = QSpinBox()
        self._font_small_spin.setRange(8, 20)
        font_layout.addWidget(self._font_small_spin, 1, 1)
        
        font_layout.addWidget(QLabel("正常字体大小:"), 2, 0)
        self._font_normal_spin = QSpinBox()
        self._font_normal_spin.setRange(10, 24)
        font_layout.addWidget(self._font_normal_spin, 2, 1)
        
        font_layout.addWidget(QLabel("大号字体大小:"), 3, 0)
        self._font_large_spin = QSpinBox()
        self._font_large_spin.setRange(12, 28)
        font_layout.addWidget(self._font_large_spin, 3, 1)
        
        scroll_layout.addWidget(font_group)
        
        # 布局设置
        layout_group = QGroupBox("布局设置")
        layout_layout = QVBoxLayout(layout_group)
        
        self._compact_mode_check = QCheckBox("紧凑模式（减少间距）")
        layout_layout.addWidget(self._compact_mode_check)
        
        self._card_view_check = QCheckBox("卡片视图圆角")
        self._card_view_check.setChecked(True)
        layout_layout.addWidget(self._card_view_check)
        
        # 圆角大小滑块
        corner_row = QHBoxLayout()
        corner_row.addWidget(QLabel("圆角大小:"))
        self._corner_slider = QSlider(Qt.Horizontal)
        self._corner_slider.setRange(0, 20)
        self._corner_slider.setValue(8)
        self._corner_slider.setFixedWidth(200)
        corner_row.addWidget(self._corner_slider)
        self._corner_label = QLabel("8px")
        self._corner_label.setFixedWidth(50)
        corner_row.addWidget(self._corner_label)
        corner_row.addStretch(1)
        self._corner_slider.valueChanged.connect(lambda v: self._corner_label.setText(f"{v}px"))
        layout_layout.addLayout(corner_row)
        
        scroll_layout.addWidget(layout_group)
        
        # 界面效果
        effect_group = QGroupBox("界面效果")
        effect_layout = QVBoxLayout(effect_group)
        
        self._animation_check = QCheckBox("启用动画效果")
        self._animation_check.setChecked(True)
        effect_layout.addWidget(self._animation_check)
        
        self._shadow_check = QCheckBox("启用阴影效果")
        self._shadow_check.setChecked(True)
        effect_layout.addWidget(self._shadow_check)
        
        # 透明度设置
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(QLabel("窗口透明度:"))
        self._opacity_slider = QSlider(Qt.Horizontal)
        self._opacity_slider.setRange(70, 100)
        self._opacity_slider.setValue(100)
        self._opacity_slider.setFixedWidth(200)
        opacity_row.addWidget(self._opacity_slider)
        self._opacity_label = QLabel("100%")
        self._opacity_label.setFixedWidth(50)
        opacity_row.addWidget(self._opacity_label)
        opacity_row.addStretch(1)
        self._opacity_slider.valueChanged.connect(lambda v: self._opacity_label.setText(f"{v}%"))
        effect_layout.addLayout(opacity_row)
        
        scroll_layout.addWidget(effect_group)
        
        layout.addWidget(scroll_area)
        
        # 按钮
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.RestoreDefaults
        )
        button_box.accepted.connect(self._apply_settings)
        button_box.rejected.connect(self._restore_original)
        button_box.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self._restore_defaults)
        layout.addWidget(button_box)
        
        # 连接信号以实时更新
        self._theme_combo.currentIndexChanged.connect(self._update_preview)
        self._font_combo.currentTextChanged.connect(self._update_preview)
        self._font_small_spin.valueChanged.connect(self._update_preview)
        self._font_normal_spin.valueChanged.connect(self._update_preview)
        self._font_large_spin.valueChanged.connect(self._update_preview)
        self._compact_mode_check.stateChanged.connect(self._update_preview)
        self._corner_slider.valueChanged.connect(self._update_preview)
    
    def _create_preset_button(self, preset):
        """创建预设主题按钮"""
        btn = QPushButton()
        btn.setFixedSize(60, 80)
        btn.setToolTip(f"{preset.display_name}\n{preset.description}")
        
        # 创建按钮的样式，显示主题颜色预览
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {preset.secondary_bg};
                border: 2px solid {preset.border_color};
                border-radius: 8px;
                padding: 4px;
                text-align: bottom;
            }}
            QPushButton:hover {{
                border-color: {preset.accent_color};
            }}
        """)
        
        # 在按钮上显示主题名称
        btn.setText(preset.display_name[:4])
        btn.clicked.connect(lambda checked, p=preset: self._apply_preset(p))
        
        return btn
    
    def _apply_preset(self, preset):
        """应用预设主题"""
        # 直接修改 ThemeManager 的配置
        self._theme_manager.apply_preset(preset)
        self._current_preset_name = preset.name
        
        # 更新自定义颜色显示
        config = self._theme_manager.config
        color_fields = [
            "primary_bg", "secondary_bg", "tertiary_bg", "card_bg",
            "text_primary", "text_secondary", "text_tertiary", "border_color"
        ]
        for field in color_fields:
            if field in self._color_pickers:
                color_label, _ = self._color_pickers[field]
                color = getattr(config, field)
                color_label.setStyleSheet(f"background-color: {color}; border-radius: 6px; border: 1px solid #555;")
        
        # 更新强调色显示
        self._accent_color_label.setStyleSheet(f"background-color: {preset.accent_color}; border-radius: 10px; border: 2px solid #555;")
        
        # 更新主题类型选择（同步到下拉框）
        theme_map = {"dark": 0, "light": 1, "custom": 2}
        self._theme_combo.setCurrentIndex(theme_map.get(preset.theme_type, 2))
        
        # 强制刷新预览
        self._preview_widget.set_theme("")
        self._preview_widget.set_theme(self._theme_manager.get_stylesheet())
    
    def _add_color_picker(self, layout, key, label, row):
        """添加颜色选择器"""
        label_widget = QLabel(label)
        layout.addWidget(label_widget, row, 0)
        
        color_label = QLabel()
        color_label.setFixedSize(32, 32)
        color_label.setStyleSheet("border-radius: 6px; border: 1px solid #555;")
        layout.addWidget(color_label, row, 1)
        
        button = QPushButton("选择")
        button.setFixedWidth(80)
        button.clicked.connect(lambda checked, k=key, cl=color_label: self._pick_custom_color(k, cl))
        layout.addWidget(button, row, 2)
        
        self._color_pickers[key] = (color_label, button)
    
    def _load_current_settings(self):
        config = self._theme_manager.config
        
        # 加载预设主题名称
        try:
            if hasattr(self.parent(), 'db'):
                prefs = self.parent().db.get_ui_preferences()
                self._current_preset_name = prefs.get("preset_theme")
        except:
            self._current_preset_name = None
        
        # 主题类型
        theme_map = {"dark": 0, "light": 1, "custom": 2}
        self._theme_combo.setCurrentIndex(theme_map.get(config.theme_type, 0))
        
        # 强调色
        self._set_accent_color(config.accent_color)
        
        # 自定义颜色
        color_fields = [
            "primary_bg", "secondary_bg", "tertiary_bg", "card_bg",
            "text_primary", "text_secondary", "text_tertiary", "border_color"
        ]
        for field in color_fields:
            color_label, _ = self._color_pickers[field]
            color = getattr(config, field)
            color_label.setStyleSheet(f"background-color: {color}; border-radius: 6px; border: 1px solid #555;")
        
        # 字体
        index = self._font_combo.findText(config.font_family)
        if index >= 0:
            self._font_combo.setCurrentIndex(index)
        
        self._font_small_spin.setValue(config.font_size_small)
        self._font_normal_spin.setValue(config.font_size_normal)
        self._font_large_spin.setValue(config.font_size_large)
        
        self._update_preview()
    
    def _on_theme_changed(self, index):
        themes: list[ThemeType] = ["dark", "light", "custom"]
        theme_type = themes[index]
        self._theme_manager.set_theme(theme_type)
        
        # 更新自定义颜色显示
        config = self._theme_manager.config
        color_fields = [
            "primary_bg", "secondary_bg", "tertiary_bg", "card_bg",
            "text_primary", "text_secondary", "text_tertiary", "border_color"
        ]
        for field in color_fields:
            color_label, _ = self._color_pickers[field]
            color = getattr(config, field)
            color_label.setStyleSheet(f"background-color: {color}; border-radius: 6px; border: 1px solid #555;")
        
        self._update_preview()
    
    def _pick_accent_color(self):
        color = QColorDialog.getColor(
            QColor(self._theme_manager.config.accent_color),
            self,
            "选择强调色",
            QColorDialog.ShowAlphaChannel
        )
        if color.isValid():
            self._set_accent_color(color.name())
    
    def _set_accent_color(self, color: str):
        self._theme_manager.set_accent_color(color)
        self._accent_color_label.setStyleSheet(f"background-color: {color}; border-radius: 10px; border: 2px solid #555;")
        
        # 更新预设按钮高亮
        for btn in self._preset_buttons:
            btn_style = btn.styleSheet()
            if color.lower() in btn_style.lower():
                btn.setStyleSheet(f"background-color: {color}; border-radius: 8px; border: 2px solid #FFF;")
            else:
                btn_style = btn_style.replace("border: 2px solid #FFF", "border: 2px solid transparent")
                btn.setStyleSheet(btn_style)
        
        self._update_preview()
    
    def _pick_custom_color(self, field, color_label):
        current_color = getattr(self._theme_manager.config, field)
        color = QColorDialog.getColor(
            QColor(current_color),
            self,
            f"选择颜色",
            QColorDialog.ShowAlphaChannel
        )
        if color.isValid():
            setattr(self._theme_manager.config, field, color.name())
            color_label.setStyleSheet(f"background-color: {color.name()}; border-radius: 6px; border: 1px solid #555;")
            self._theme_manager._notify_listeners()
            self._update_preview()
    
    def _update_preview(self):
        """更新预览"""
        self._preview_widget.set_theme(self._theme_manager.get_stylesheet())
    
    def _apply_settings(self):
        """应用设置"""
        from app.ui.theme_manager import ThemeManager
        
        # 确保字体设置应用到 ThemeManager
        self._theme_manager.set_font_family(self._font_combo.currentText())
        self._theme_manager.set_font_sizes(
            self._font_small_spin.value(),
            self._font_normal_spin.value(),
            self._font_large_spin.value()
        )
        
        # 获取当前配置并保存
        config_data = self._theme_manager.to_dict()
        config_data["preset_theme"] = self._current_preset_name
        
        # 立即应用样式到主窗口
        if self.parent():
            self.parent()._apply_theme()
        
        # 保存到数据库
        self._save_to_database()
        
        # 设置窗口透明度
        opacity = self._opacity_slider.value() / 100.0
        if self.parent():
            self.parent().setWindowOpacity(opacity)
        
        self.accept()
    
    def _restore_original(self):
        self._theme_manager.load_from_dict(self._original_config)
        self._load_current_settings()
        self.reject()
    
    def _restore_defaults(self):
        # 应用默认预设主题
        self._theme_manager.apply_preset(PresetThemes.DEFAULT_DARK)
        self._current_preset_name = PresetThemes.DEFAULT_DARK.name
        self._theme_manager.set_font_family("Segoe UI, Microsoft YaHei, sans-serif")
        self._theme_manager.set_font_sizes(11, 13, 15)
        self._load_current_settings()
        self._update_preview()
    
    def _save_to_database(self):
        """保存主题设置到数据库"""
        if hasattr(self.parent(), 'db'):
            # 保存配置，包含预设主题名称
            data = self._theme_manager.to_dict()
            data["preset_theme"] = self._current_preset_name
            self.parent().db.set_ui_preferences(data)


class _ThemePreviewWidget(QWidget):
    """主题预览小部件"""
    
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(150)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # 工具栏预览
        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(8, 8, 8, 8)
        
        btn1 = QPushButton("按钮1")
        btn2 = QPushButton("按钮2")
        combo = QComboBox()
        combo.addItems(["选项1", "选项2"])
        edit = QLabel("搜索框")
        
        toolbar_layout.addWidget(btn1)
        toolbar_layout.addWidget(btn2)
        toolbar_layout.addWidget(combo)
        toolbar_layout.addWidget(edit)
        toolbar_layout.addStretch()
        
        # 内容预览
        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(8, 8, 8, 8)
        
        card = QWidget()
        card.setFixedSize(100, 100)
        card.setObjectName("gameCardSlot")
        content_layout.addWidget(card)
        
        text_block = QWidget()
        text_block_layout = QVBoxLayout(text_block)
        title = QLabel("游戏标题")
        title.setObjectName("gameTitle")
        meta = QLabel("元数据信息")
        meta.setObjectName("gameMeta")
        text_block_layout.addWidget(title)
        text_block_layout.addWidget(meta)
        content_layout.addWidget(text_block)
        content_layout.addStretch()
        
        layout.addWidget(toolbar)
        layout.addWidget(content)
    
    def set_theme(self, stylesheet: str):
        self.setStyleSheet(stylesheet)
