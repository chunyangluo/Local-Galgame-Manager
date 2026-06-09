"""综合设置对话框 — 左侧导航栏 + 右侧内容区，分门别类整合所有设置。"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.settings import CoverFetchMode, DoubleClickAction
from app.ui.theme_manager import ThemeManager, PresetThemes


# ── 自动检测工具路径 ──

def _auto_detect_leproc() -> str:
    """尝试自动检测 LEProc.exe 路径。"""
    candidates: list[Path] = []
    # 1. 常见安装目录
    for base in [
        Path(os.environ.get("ProgramFiles", "C:\\Program Files")),
        Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs",
    ]:
        if base.exists():
            for d in base.rglob("LEProc.exe"):
                candidates.append(d)
                break
    # 2. 用户桌面 / 下载
    for base in [
        Path(os.environ.get("USERPROFILE", "")) / "Desktop",
        Path(os.environ.get("USERPROFILE", "")) / "Downloads",
    ]:
        if base.exists():
            for d in base.rglob("LEProc.exe"):
                candidates.append(d)
                break
    # 3. D/E 盘常见目录
    for drive in ["D:\\", "E:\\", "F:\\"]:
        for sub in ["Locale Emulator", "LE", "Tools\\Locale Emulator"]:
            p = Path(drive) / sub / "LEProc.exe"
            if p.is_file():
                candidates.append(p)
    return str(candidates[0]) if candidates else ""


def _auto_detect_fdm() -> str:
    """尝试自动检测 fdm.exe 路径。"""
    candidates: list[Path] = []
    for base in [
        Path(os.environ.get("ProgramFiles", "C:\\Program Files")),
        Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs",
    ]:
        if base.exists():
            for d in base.rglob("fdm.exe"):
                candidates.append(d)
                break
    return str(candidates[0]) if candidates else ""


def _auto_detect_2dfan_db() -> str:
    """尝试自动检测 2DFan 线索库数据库。"""
    candidates: list[Path] = []
    for base in [
        Path(os.environ.get("USERPROFILE", "")) / "Downloads",
        Path(os.environ.get("USERPROFILE", "")) / "Desktop",
    ]:
        if base.exists():
            for f in base.rglob("2dfan*.db"):
                candidates.append(f)
                break
    # 应用数据目录
    try:
        from app.services.app_data_dir import get_app_data_dir
        app_data = Path(get_app_data_dir())
        for f in app_data.rglob("2dfan*.db"):
            candidates.append(f)
            break
    except Exception:
        pass
    return str(candidates[0]) if candidates else ""


class SettingsDialog(QDialog):
    """综合设置对话框 — 左侧导航 + 右侧分页"""

    settings_changed = Signal()

    # 导航项: (显示名, 描述, 搜索关键词)
    _PAGES = [
        ("启动", "启动方式、备份、上次模式", "启动 双击 LE 转区 备份 模式"),
        ("封面", "封面获取策略", "封面 VNDB 本地 网图 缩略图"),
        ("外观", "主题、字体、颜色、布局、效果", "外观 主题 字体 颜色 布局 圆角 动画 阴影 透明度 强调色"),
        ("工具路径", "LE、2DFan、FDM 路径配置", "路径 LEProc 2DFan FDM 自动检测"),
        ("高级", "缓存清理、插件、确认框", "高级 缓存 清理 缩略图 插件 确认 删除 密码本"),
    ]

    def __init__(self, db, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self._loading = True
        self.setWindowTitle("设置")
        self.setMinimumSize(760, 600)
        self._theme_manager = ThemeManager()
        self._original_theme_config = self._theme_manager.to_dict().copy()
        self._current_preset_name = None
        self._init_ui()
        self._load_settings()
        self._loading = False

    # ================================================================ UI

    def _init_ui(self) -> None:
        outer_layout = QVBoxLayout(self)

        # ── 顶部搜索框 ──
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("🔍"))
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("搜索设置项…（如：字体、LE、缓存）")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.textChanged.connect(self._on_search)
        search_row.addWidget(self._search_edit, 1)
        outer_layout.addLayout(search_row)

        # ── 中间：左导航 + 右内容 ──
        root = QHBoxLayout()

        self._nav = QListWidget()
        self._nav.setFixedWidth(130)
        self._nav.setCurrentRow(0)
        self._nav.currentRowChanged.connect(self._switch_page)
        for title, _desc, _kw in self._PAGES:
            item = QListWidgetItem(title)
            item.setTextAlignment(Qt.AlignCenter)
            self._nav.addItem(item)
        root.addWidget(self._nav)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_launch_page())
        self._stack.addWidget(self._build_cover_page())
        self._stack.addWidget(self._build_appearance_page())
        self._stack.addWidget(self._build_paths_page())
        self._stack.addWidget(self._build_advanced_page())
        root.addWidget(self._stack, 1)

        outer_layout.addLayout(root)

        # ── 底部按钮 ──
        btn_row = QHBoxLayout()
        btn_reset = QPushButton("恢复默认设置")
        btn_reset.setProperty("btnRole", "danger")
        btn_reset.clicked.connect(self._reset_to_defaults)
        btn_row.addWidget(btn_reset)
        btn_row.addStretch()
        btn_ok = QPushButton("确定")
        btn_ok.setProperty("btnRole", "primary")
        btn_ok.clicked.connect(self._on_accept)
        btn_row.addWidget(btn_ok)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        outer_layout.addLayout(btn_row)

    def _switch_page(self, row: int) -> None:
        if 0 <= row < self._stack.count():
            self._stack.setCurrentIndex(row)

    def _on_search(self, text: str) -> None:
        """搜索设置项，匹配导航名/描述/关键词，跳转到对应页面。"""
        text = text.strip().lower()
        if not text:
            return
        for i, (_title, desc, kw) in enumerate(self._PAGES):
            combined = f"{_title} {desc} {kw}".lower()
            if text in combined:
                self._nav.setCurrentRow(i)
                return

    # ── 页面1: 启动 ──
    def _build_launch_page(self) -> QWidget:
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content)

        grp = QGroupBox("启动设置")
        form = QFormLayout(grp)

        self._double_click_combo = QComboBox()
        self._double_click_combo.addItems([
            "普通启动 — 直接启动游戏 exe",
            "强制 LE 转区 — 始终使用 Locale Emulator",
            "智能模式 — 记住上一次启动方式",
        ])
        self._double_click_combo.currentIndexChanged.connect(self._on_double_click_changed)
        form.addRow("双击打开游戏:", self._double_click_combo)

        note = QLabel("智能模式会自动使用上一次启动该游戏的方式。\n"
                      "LE 转区需先在「工具路径」页配置 LEProc.exe。")
        note.setStyleSheet("color:#93A1B6;font-size:11px;")
        note.setWordWrap(True)
        form.addRow("", note)

        self._auto_backup_check = QCheckBox("启动游戏前自动备份存档")
        self._auto_backup_check.stateChanged.connect(self._on_auto_backup_changed)
        form.addRow("", self._auto_backup_check)

        layout.addWidget(grp)

        # 上次启动模式
        mode_grp = QGroupBox("上次启动模式")
        mode_layout = QVBoxLayout(mode_grp)
        self._last_mode_label = QLabel("—")
        self._last_mode_label.setStyleSheet("font-size:13px;font-weight:bold;")
        mode_layout.addWidget(self._last_mode_label)
        mode_note = QLabel("智能模式会参考此值决定是否使用 LE 转区。")
        mode_note.setStyleSheet("color:#93A1B6;font-size:11px;")
        mode_note.setWordWrap(True)
        mode_layout.addWidget(mode_note)
        btn_reset_mode = QPushButton("重置为「普通启动」")
        btn_reset_mode.clicked.connect(self._reset_last_launch_mode)
        mode_layout.addWidget(btn_reset_mode)
        layout.addWidget(mode_grp)

        layout.addStretch()
        scroll.setWidget(content)

        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        return page

    # ── 页面2: 封面 ──
    def _build_cover_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        grp = QGroupBox("封面设置")
        form = QFormLayout(grp)

        self._cover_mode_combo = QComboBox()
        self._cover_mode_combo.addItems([
            "仅本地封面",
            "本地优先（本地有则用本地）",
            "网图优先（优先从 VNDB 获取）",
        ])
        self._cover_mode_combo.currentIndexChanged.connect(self._on_cover_mode_changed)
        form.addRow("封面获取策略:", self._cover_mode_combo)

        cover_note = QLabel(
            "仅本地：不联网获取封面，仅使用本地文件。\n"
            "本地优先：优先使用本地封面，无则从 VNDB 下载。\n"
            "网图优先：优先使用 VNDB 封面，本地仅作回退。"
        )
        cover_note.setStyleSheet("color:#93A1B6;font-size:11px;")
        cover_note.setWordWrap(True)
        form.addRow("", cover_note)

        layout.addWidget(grp)
        layout.addStretch()
        return page

    # ── 页面3: 外观 ──
    def _build_appearance_page(self) -> QWidget:
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content)

        # 即时预览提示
        preview_hint = QLabel("💡 修改即时预览 — 调整颜色/字体后主窗口实时更新")
        preview_hint.setStyleSheet(
            "background:#2a3a4a;color:#7FA7D9;padding:8px 12px;border-radius:6px;font-size:12px;"
        )
        preview_hint.setWordWrap(True)
        layout.addWidget(preview_hint)

        # 预设主题
        preset_grp = QGroupBox("预设主题")
        preset_layout = QVBoxLayout(preset_grp)
        dark_row = QHBoxLayout()
        dark_label = QLabel("深色:")
        dark_label.setFixedWidth(40)
        dark_row.addWidget(dark_label)
        for p in PresetThemes.ALL_PRESETS:
            if p.theme_type == "dark":
                btn = self._make_preset_btn(p)
                dark_row.addWidget(btn)
        dark_row.addStretch()
        preset_layout.addLayout(dark_row)

        light_row = QHBoxLayout()
        light_label = QLabel("浅色:")
        light_label.setFixedWidth(40)
        light_row.addWidget(light_label)
        for p in PresetThemes.ALL_PRESETS:
            if p.theme_type == "light":
                btn = self._make_preset_btn(p)
                light_row.addWidget(btn)
        light_row.addStretch()
        preset_layout.addLayout(light_row)
        layout.addWidget(preset_grp)

        # 强调色
        accent_grp = QGroupBox("强调色")
        accent_layout = QVBoxLayout(accent_grp)
        accent_row = QHBoxLayout()
        self._accent_label = QLabel()
        self._accent_label.setFixedSize(36, 36)
        self._accent_label.setStyleSheet("border-radius:8px;border:2px solid #555;")
        accent_row.addWidget(self._accent_label)
        btn_pick = QPushButton("选择颜色")
        btn_pick.clicked.connect(self._pick_accent_color)
        accent_row.addWidget(btn_pick)
        accent_row.addStretch()
        accent_layout.addLayout(accent_row)

        preset_colors = [
            "#7FA7D9", "#FF6B6B", "#4ADE80", "#FBBF24",
            "#A78BFA", "#FB7185", "#06B6D4", "#84CC16",
            "#F97316", "#EC4899", "#14B8A6", "#6366F1",
        ]
        color_row = QHBoxLayout()
        self._preset_color_btns = []
        for c in preset_colors:
            btn = QPushButton()
            btn.setFixedSize(28, 28)
            btn.setStyleSheet(f"background-color:{c};border-radius:6px;border:2px solid transparent;")
            btn.clicked.connect(lambda _, cc=c: self._set_accent_color(cc))
            self._preset_color_btns.append(btn)
            color_row.addWidget(btn)
        color_row.addStretch()
        accent_layout.addLayout(color_row)
        layout.addWidget(accent_grp)

        # 字体
        font_grp = QGroupBox("字体")
        font_layout = QGridLayout(font_grp)
        font_layout.addWidget(QLabel("字体:"), 0, 0)
        self._font_combo = QComboBox()
        self._font_combo.addItems([
            "Segoe UI, Microsoft YaHei, sans-serif",
            "Microsoft YaHei, sans-serif",
            "SimHei, sans-serif",
            "SimSun, serif",
            "Arial, sans-serif",
            "Consolas, monospace",
            "Noto Sans SC, sans-serif",
            "PingFang SC, sans-serif",
        ])
        font_layout.addWidget(self._font_combo, 0, 1)

        font_layout.addWidget(QLabel("小号:"), 1, 0)
        self._font_small = QSpinBox()
        self._font_small.setRange(8, 20)
        font_layout.addWidget(self._font_small, 1, 1)

        font_layout.addWidget(QLabel("正常:"), 2, 0)
        self._font_normal = QSpinBox()
        self._font_normal.setRange(10, 24)
        font_layout.addWidget(self._font_normal, 2, 1)

        font_layout.addWidget(QLabel("大号:"), 3, 0)
        self._font_large = QSpinBox()
        self._font_large.setRange(12, 28)
        font_layout.addWidget(self._font_large, 3, 1)
        layout.addWidget(font_grp)

        # 布局
        layout_grp = QGroupBox("布局")
        layout_l = QVBoxLayout(layout_grp)
        self._compact_check = QCheckBox("紧凑模式（减少间距）")
        layout_l.addWidget(self._compact_check)
        self._card_corner_check = QCheckBox("卡片圆角")
        self._card_corner_check.setChecked(True)
        layout_l.addWidget(self._card_corner_check)
        corner_row = QHBoxLayout()
        corner_row.addWidget(QLabel("圆角大小:"))
        self._corner_slider = QSlider(Qt.Horizontal)
        self._corner_slider.setRange(0, 20)
        self._corner_slider.setValue(8)
        self._corner_slider.setFixedWidth(160)
        corner_row.addWidget(self._corner_slider)
        self._corner_label = QLabel("8px")
        self._corner_label.setFixedWidth(40)
        self._corner_slider.valueChanged.connect(lambda v: self._corner_label.setText(f"{v}px"))
        corner_row.addWidget(self._corner_label)
        corner_row.addStretch()
        layout_l.addLayout(corner_row)
        layout.addWidget(layout_grp)

        # 效果
        effect_grp = QGroupBox("界面效果")
        effect_l = QVBoxLayout(effect_grp)
        self._anim_check = QCheckBox("启用动画效果")
        self._anim_check.setChecked(True)
        effect_l.addWidget(self._anim_check)
        self._shadow_check = QCheckBox("启用阴影效果")
        self._shadow_check.setChecked(True)
        effect_l.addWidget(self._shadow_check)
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(QLabel("窗口透明度:"))
        self._opacity_slider = QSlider(Qt.Horizontal)
        self._opacity_slider.setRange(70, 100)
        self._opacity_slider.setValue(100)
        self._opacity_slider.setFixedWidth(160)
        opacity_row.addWidget(self._opacity_slider)
        self._opacity_label = QLabel("100%")
        self._opacity_label.setFixedWidth(40)
        self._opacity_slider.valueChanged.connect(lambda v: self._opacity_label.setText(f"{v}%"))
        opacity_row.addWidget(self._opacity_label)
        opacity_row.addStretch()
        effect_l.addLayout(opacity_row)
        layout.addWidget(effect_grp)

        # 自定义颜色（高级）
        custom_grp = QGroupBox("自定义颜色（高级）")
        custom_layout = QGridLayout(custom_grp)
        self._color_pickers = {}
        fields = [
            ("primary_bg", "主背景色", 0), ("secondary_bg", "次背景色", 1),
            ("tertiary_bg", "三级背景色", 2), ("card_bg", "卡片背景色", 3),
            ("text_primary", "主要文字色", 4), ("text_secondary", "次要文字色", 5),
            ("text_tertiary", "三级文字色", 6), ("border_color", "边框颜色", 7),
        ]
        for key, label, row in fields:
            custom_layout.addWidget(QLabel(label), row, 0)
            cl = QLabel()
            cl.setFixedSize(28, 28)
            cl.setStyleSheet("border-radius:6px;border:1px solid #555;")
            custom_layout.addWidget(cl, row, 1)
            btn = QPushButton("选择")
            btn.setFixedWidth(60)
            btn.clicked.connect(lambda _, k=key, c=cl: self._pick_custom_color(k, c))
            custom_layout.addWidget(btn, row, 2)
            self._color_pickers[key] = (cl, btn)
        layout.addWidget(custom_grp)

        layout.addStretch()
        scroll.setWidget(content)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        return page

    # ── 页面4: 工具路径 ──
    def _build_paths_page(self) -> QWidget:
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content)

        grp = QGroupBox("工具路径配置")
        form = QFormLayout(grp)

        # LE
        le_row = QHBoxLayout()
        self._le_path_edit = QLineEdit()
        self._le_path_edit.setPlaceholderText("选择 LEProc.exe 路径…")
        self._le_path_edit.editingFinished.connect(self._on_le_path_editing_finished)
        le_row.addWidget(self._le_path_edit, 1)
        btn_le_browse = QPushButton("浏览…")
        btn_le_browse.clicked.connect(self._browse_le_path)
        le_row.addWidget(btn_le_browse)
        btn_le_detect = QPushButton("自动检测")
        btn_le_detect.clicked.connect(self._auto_detect_le)
        le_row.addWidget(btn_le_detect)
        form.addRow("Locale Emulator:", le_row)
        le_note = QLabel("用于「LE 转区启动」，留空则关闭 LE 功能")
        le_note.setStyleSheet("color:#93A1B6;font-size:11px;")
        form.addRow("", le_note)

        # 2DFan
        hints_row = QHBoxLayout()
        self._hints_path_edit = QLineEdit()
        self._hints_path_edit.setPlaceholderText("选择 2DFan SQLite 数据库路径…")
        self._hints_path_edit.editingFinished.connect(self._on_hints_path_editing_finished)
        hints_row.addWidget(self._hints_path_edit, 1)
        btn_hints_browse = QPushButton("浏览…")
        btn_hints_browse.clicked.connect(self._browse_hints_path)
        hints_row.addWidget(btn_hints_browse)
        btn_hints_detect = QPushButton("自动检测")
        btn_hints_detect.clicked.connect(self._auto_detect_2dfan)
        hints_row.addWidget(btn_hints_detect)
        form.addRow("2DFan 线索库:", hints_row)
        hints_note = QLabel("用于存档自动发现，可与 tools/2dfan-save-crawler 共用数据库")
        hints_note.setStyleSheet("color:#93A1B6;font-size:11px;")
        form.addRow("", hints_note)

        # FDM
        fdm_row = QHBoxLayout()
        self._fdm_path_edit = QLineEdit()
        self._fdm_path_edit.setPlaceholderText("选择 fdm.exe 路径…")
        self._fdm_path_edit.editingFinished.connect(self._on_fdm_path_editing_finished)
        fdm_row.addWidget(self._fdm_path_edit, 1)
        btn_fdm_browse = QPushButton("浏览…")
        btn_fdm_browse.clicked.connect(self._browse_fdm_path)
        fdm_row.addWidget(btn_fdm_browse)
        btn_fdm_detect = QPushButton("自动检测")
        btn_fdm_detect.clicked.connect(self._auto_detect_fdm)
        fdm_row.addWidget(btn_fdm_detect)
        form.addRow("FDM 下载器:", fdm_row)
        fdm_note = QLabel("Free Download Manager 可执行文件路径，留空则关闭 FDM 功能")
        fdm_note.setStyleSheet("color:#93A1B6;font-size:11px;")
        form.addRow("", fdm_note)

        layout.addWidget(grp)
        layout.addStretch()
        scroll.setWidget(content)

        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        return page

    # ── 页面5: 高级 ──
    def _build_advanced_page(self) -> QWidget:
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content)

        # 缓存/缩略图清理
        cache_grp = QGroupBox("缓存与缩略图")
        cache_layout = QVBoxLayout(cache_grp)

        self._cover_cache_label = QLabel("封面缓存: 计算中…")
        cache_layout.addWidget(self._cover_cache_label)

        self._online_cache_label = QLabel("在线封面缓存: 计算中…")
        cache_layout.addWidget(self._online_cache_label)

        cache_btn_row = QHBoxLayout()
        btn_clean_cover = QPushButton("清理封面缓存")
        btn_clean_cover.clicked.connect(self._clean_cover_cache)
        cache_btn_row.addWidget(btn_clean_cover)

        btn_clean_online = QPushButton("清理在线封面缓存")
        btn_clean_online.clicked.connect(self._clean_online_cache)
        cache_btn_row.addWidget(btn_clean_online)

        btn_clean_all = QPushButton("清理全部缓存")
        btn_clean_all.setProperty("btnRole", "danger")
        btn_clean_all.clicked.connect(self._clean_all_cache)
        cache_btn_row.addWidget(btn_clean_all)

        cache_btn_row.addStretch()
        cache_layout.addLayout(cache_btn_row)

        cache_note = QLabel("清理后下次查看游戏时会重新获取封面，不影响游戏数据。")
        cache_note.setStyleSheet("color:#93A1B6;font-size:11px;")
        cache_note.setWordWrap(True)
        cache_layout.addWidget(cache_note)
        layout.addWidget(cache_grp)

        # 插件管理（内嵌）
        plugin_grp = QGroupBox("插件管理")
        plugin_layout = QVBoxLayout(plugin_grp)
        plugin_hint = QLabel("管理扫描/启动链路上的插件钩子。")
        plugin_hint.setStyleSheet("color:#93A1B6;font-size:11px;")
        plugin_layout.addWidget(plugin_hint)
        btn_plugins = QPushButton("打开插件管理…")
        btn_plugins.clicked.connect(self._open_plugins)
        plugin_layout.addWidget(btn_plugins)
        layout.addWidget(plugin_grp)

        # 扩展工具快捷入口
        tools_grp = QGroupBox("扩展工具")
        tools_layout = QVBoxLayout(tools_grp)
        tools_hint = QLabel("独立工具模块，也可从主菜单「更多 → 工具箱」进入。")
        tools_hint.setStyleSheet("color:#93A1B6;font-size:11px;")
        tools_hint.setWordWrap(True)
        tools_layout.addWidget(tools_hint)
        row = QHBoxLayout()
        for label, slot in [
            ("HBE 解密…", self._open_hbe_decrypt),
            ("自动化解压…", self._open_auto_extract),
            ("数据管理…", self._open_data_manager),
            ("密码本…", self._open_password_manager),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            row.addWidget(btn)
        tools_layout.addLayout(row)
        layout.addWidget(tools_grp)

        # 删除确认
        confirm_grp = QGroupBox("确认对话框")
        confirm_layout = QVBoxLayout(confirm_grp)
        self._skip_delete_confirm_check = QCheckBox("删除游戏时跳过确认对话框")
        confirm_layout.addWidget(self._skip_delete_confirm_check)
        confirm_note = QLabel("开启后删除游戏将不再弹出确认提示，请谨慎操作。")
        confirm_note.setStyleSheet("color:#93A1B6;font-size:11px;")
        confirm_layout.addWidget(confirm_note)
        layout.addWidget(confirm_grp)

        layout.addStretch()
        scroll.setWidget(content)

        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        return page

    # ============================================================ 预设主题

    def _make_preset_btn(self, preset) -> QPushButton:
        btn = QPushButton()
        btn.setFixedSize(56, 72)
        btn.setToolTip(f"{preset.display_name}\n{preset.description}")
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color:{preset.secondary_bg};
                border:2px solid {preset.border_color};
                border-radius:8px;color:{preset.text_primary};
                font-weight:700;font-size:11px;
            }}
            QPushButton:hover {{ border-color:{preset.accent_color}; }}
        """)
        btn.setText(preset.display_name[:4])
        btn.clicked.connect(lambda _, p=preset: self._apply_preset(p))
        return btn

    def _apply_preset(self, preset) -> None:
        self._theme_manager.apply_preset(preset)
        self._current_preset_name = preset.name
        self._sync_appearance_ui()
        self._apply_theme_live()

    def _sync_appearance_ui(self) -> None:
        config = self._theme_manager.config
        self._accent_label.setStyleSheet(
            f"background-color:{config.accent_color};border-radius:8px;border:2px solid #555;"
        )
        for key, (cl, _) in self._color_pickers.items():
            color = getattr(config, key, "")
            if color:
                cl.setStyleSheet(f"background-color:{color};border-radius:6px;border:1px solid #555;")

    def _apply_theme_live(self) -> None:
        """即时预览：将主题应用到主窗口。"""
        if self.parent() and hasattr(self.parent(), "_apply_theme"):
            self.parent()._apply_theme()

    # ============================================================ 颜色

    def _pick_accent_color(self) -> None:
        color = QColorDialog.getColor(
            QColor(self._theme_manager.config.accent_color), self, "选择强调色"
        )
        if color.isValid():
            self._set_accent_color(color.name())

    def _set_accent_color(self, color: str) -> None:
        self._theme_manager.set_accent_color(color)
        self._accent_label.setStyleSheet(
            f"background-color:{color};border-radius:8px;border:2px solid #555;"
        )
        self._apply_theme_live()

    def _pick_custom_color(self, field: str, color_label: QLabel) -> None:
        current = getattr(self._theme_manager.config, field, "#000000")
        color = QColorDialog.getColor(QColor(current), self, "选择颜色")
        if color.isValid():
            setattr(self._theme_manager.config, field, color.name())
            color_label.setStyleSheet(
                f"background-color:{color.name()};border-radius:6px;border:1px solid #555;"
            )
            self._apply_theme_live()

    # ============================================================ 自动检测

    def _auto_detect_le(self) -> None:
        path = _auto_detect_leproc()
        if path:
            self._le_path_edit.setText(path)
            self._db.set_locale_emulator_leproc_path(path)
            self.settings_changed.emit()
            QMessageBox.information(self, "检测成功", f"已找到 LEProc.exe:\n{path}")
        else:
            QMessageBox.information(self, "未检测到", "未在常见目录中找到 LEProc.exe，请手动指定。")

    def _auto_detect_2dfan(self) -> None:
        path = _auto_detect_2dfan_db()
        if path:
            self._hints_path_edit.setText(path)
            self._db.set_twodfan_hints_db_path(path)
            self.settings_changed.emit()
            QMessageBox.information(self, "检测成功", f"已找到 2DFan 数据库:\n{path}")
        else:
            QMessageBox.information(self, "未检测到", "未在常见目录中找到 2DFan 数据库，请手动指定。")

    def _auto_detect_fdm(self) -> None:
        path = _auto_detect_fdm()
        if path:
            self._fdm_path_edit.setText(path)
            prefs = dict(self._db.get_ui_preferences())
            prefs["fdm_exe_path"] = path
            self._db.set_ui_preferences(prefs)
            QMessageBox.information(self, "检测成功", f"已找到 fdm.exe:\n{path}")
        else:
            QMessageBox.information(self, "未检测到", "未在常见目录中找到 fdm.exe，请手动指定。")

    # ============================================================ 缓存清理

    def _update_cache_labels(self) -> None:
        """更新缓存大小显示。"""
        try:
            cover_dir = self._db.base_dir / "covers"
            online_dir = cover_dir / "online"
            cover_size = sum(f.stat().st_size for f in cover_dir.rglob("*") if f.is_file()) if cover_dir.exists() else 0
            online_size = sum(f.stat().st_size for f in online_dir.rglob("*") if f.is_file()) if online_dir.exists() else 0
            self._cover_cache_label.setText(f"封面缓存: {cover_size / 1024 / 1024:.1f} MB")
            self._online_cache_label.setText(f"在线封面缓存: {online_size / 1024 / 1024:.1f} MB")
        except Exception:
            self._cover_cache_label.setText("封面缓存: 计算失败")
            self._online_cache_label.setText("在线封面缓存: 计算失败")

    def _clean_cover_cache(self) -> None:
        reply = QMessageBox.question(
            self, "清理封面缓存",
            "确定要清理所有封面缓存吗？\n\n清理后下次查看游戏时会重新获取封面。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        cover_dir = self._db.base_dir / "covers"
        if cover_dir.exists():
            shutil.rmtree(cover_dir, ignore_errors=True)
            cover_dir.mkdir(parents=True, exist_ok=True)
        self._update_cache_labels()
        QMessageBox.information(self, "清理完成", "封面缓存已清理。")

    def _clean_online_cache(self) -> None:
        online_dir = self._db.base_dir / "covers" / "online"
        if online_dir.exists():
            shutil.rmtree(online_dir, ignore_errors=True)
            online_dir.mkdir(parents=True, exist_ok=True)
        self._update_cache_labels()
        QMessageBox.information(self, "清理完成", "在线封面缓存已清理。")

    def _clean_all_cache(self) -> None:
        reply = QMessageBox.question(
            self, "清理全部缓存",
            "确定要清理所有缓存吗？\n\n包括封面缓存、在线封面缓存等。\n清理后下次查看游戏时会重新获取。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        cover_dir = self._db.base_dir / "covers"
        if cover_dir.exists():
            shutil.rmtree(cover_dir, ignore_errors=True)
            cover_dir.mkdir(parents=True, exist_ok=True)
        # __pycache__
        for d in self._db.base_dir.rglob("__pycache__"):
            shutil.rmtree(d, ignore_errors=True)
        self._update_cache_labels()
        QMessageBox.information(self, "清理完成", "全部缓存已清理。")

    # ============================================================ 上次启动模式

    def _reset_last_launch_mode(self) -> None:
        self._db.set_last_launch_mode("normal")
        self._last_mode_label.setText("普通启动")
        self._last_mode_label.setStyleSheet("font-size:13px;font-weight:bold;color:#4ADE80;")
        self.settings_changed.emit()

    # ============================================================ 加载

    def _load_settings(self) -> None:
        self._loading = True

        # 启动
        action = self._db.get_double_click_action()
        idx = [DoubleClickAction.NORMAL, DoubleClickAction.FORCE_LE, DoubleClickAction.SMART].index(action)
        self._double_click_combo.setCurrentIndex(idx)
        self._auto_backup_check.setChecked(self._db.get_auto_backup_before_launch())

        # 上次启动模式
        last_mode = self._db.get_last_launch_mode()
        mode_text = "LE 转区" if last_mode == "le" else "普通启动"
        self._last_mode_label.setText(mode_text)
        self._last_mode_label.setStyleSheet(
            f"font-size:13px;font-weight:bold;color:{'#FF6B6B' if last_mode == 'le' else '#4ADE80'};"
        )

        # 封面
        mode = self._db.get_cover_fetch_mode()
        idx = [CoverFetchMode.LOCAL_ONLY, CoverFetchMode.LOCAL_PREFER, CoverFetchMode.ONLINE_PREFER].index(mode)
        self._cover_mode_combo.setCurrentIndex(idx)

        # 工具路径
        self._le_path_edit.setText(self._db.get_locale_emulator_leproc_path())
        self._hints_path_edit.setText(self._db.get_twodfan_hints_db_path())
        fdm_prefs = self._db.get_ui_preferences()
        self._fdm_path_edit.setText(fdm_prefs.get("fdm_exe_path", ""))

        # 外观
        config = self._theme_manager.config
        self._set_accent_color(config.accent_color)
        fidx = self._font_combo.findText(config.font_family)
        if fidx >= 0:
            self._font_combo.setCurrentIndex(fidx)
        self._font_small.setValue(config.font_size_small)
        self._font_normal.setValue(config.font_size_normal)
        self._font_large.setValue(config.font_size_large)
        self._sync_appearance_ui()

        # 布局/效果
        prefs = self._db.get_ui_preferences()
        self._compact_check.setChecked(prefs.get("compact_mode", False))
        self._card_corner_check.setChecked(prefs.get("card_corner", True))
        self._corner_slider.setValue(prefs.get("corner_radius", 8))
        self._anim_check.setChecked(prefs.get("animation", True))
        self._shadow_check.setChecked(prefs.get("shadow", True))
        self._opacity_slider.setValue(int(prefs.get("opacity", 100)))

        # 高级
        from app.services.game_delete_service import get_skip_delete_game_confirm
        self._skip_delete_confirm_check.setChecked(get_skip_delete_game_confirm(self._db))

        # 预设主题名
        try:
            self._current_preset_name = fdm_prefs.get("preset_theme")
        except Exception:
            self._current_preset_name = None

        # 缓存大小
        self._update_cache_labels()

        self._loading = False

    # ============================================================ 保存

    def _on_accept(self) -> None:
        # 保存外观设置
        self._theme_manager.set_font_family(self._font_combo.currentText())
        self._theme_manager.set_font_sizes(
            self._font_small.value(), self._font_normal.value(), self._font_large.value()
        )
        config_data = self._theme_manager.to_dict()
        config_data["preset_theme"] = self._current_preset_name
        config_data["fdm_exe_path"] = self._fdm_path_edit.text().strip()

        # 布局/效果设置
        prefs = dict(self._db.get_ui_preferences())
        prefs.update(config_data)
        prefs["compact_mode"] = self._compact_check.isChecked()
        prefs["card_corner"] = self._card_corner_check.isChecked()
        prefs["corner_radius"] = self._corner_slider.value()
        prefs["animation"] = self._anim_check.isChecked()
        prefs["shadow"] = self._shadow_check.isChecked()
        self._db.set_ui_preferences(prefs)

        # 高级
        from app.services.game_delete_service import set_skip_delete_game_confirm
        set_skip_delete_game_confirm(self._db, self._skip_delete_confirm_check.isChecked())

        # 应用主题
        if self.parent():
            self.parent()._apply_theme()
            opacity = self._opacity_slider.value() / 100.0
            self.parent().setWindowOpacity(opacity)

        self.settings_changed.emit()
        self.accept()

    # ============================================================ 信号处理

    def _on_double_click_changed(self, index: int) -> None:
        if self._loading:
            return
        actions = [DoubleClickAction.NORMAL, DoubleClickAction.FORCE_LE, DoubleClickAction.SMART]
        if 0 <= index < len(actions):
            self._db.set_double_click_action(actions[index])
            self.settings_changed.emit()

    def _on_auto_backup_changed(self, state: int) -> None:
        if self._loading:
            return
        self._db.set_auto_backup_before_launch(bool(state))
        self.settings_changed.emit()

    def _on_cover_mode_changed(self, index: int) -> None:
        if self._loading:
            return
        modes = [CoverFetchMode.LOCAL_ONLY, CoverFetchMode.LOCAL_PREFER, CoverFetchMode.ONLINE_PREFER]
        if 0 <= index < len(modes):
            self._db.set_cover_fetch_mode(modes[index])
            self.settings_changed.emit()

    def _on_le_path_editing_finished(self) -> None:
        if self._loading:
            return
        self._db.set_locale_emulator_leproc_path(self._le_path_edit.text())
        self.settings_changed.emit()

    def _on_hints_path_editing_finished(self) -> None:
        if self._loading:
            return
        self._db.set_twodfan_hints_db_path(self._hints_path_edit.text())
        self.settings_changed.emit()

    def _on_fdm_path_editing_finished(self) -> None:
        if self._loading:
            return
        prefs = dict(self._db.get_ui_preferences())
        prefs["fdm_exe_path"] = self._fdm_path_edit.text().strip()
        self._db.set_ui_preferences(prefs)

    def _browse_le_path(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择 LEProc.exe", "", "LEProc.exe (LEProc.exe)")
        if path:
            self._le_path_edit.setText(path)
            self._db.set_locale_emulator_leproc_path(path)
            self.settings_changed.emit()

    def _browse_hints_path(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择 2DFan 数据库", "", "SQLite (*.db *.sqlite)")
        if path:
            self._hints_path_edit.setText(path)
            self._db.set_twodfan_hints_db_path(path)
            self.settings_changed.emit()

    def _browse_fdm_path(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择 fdm.exe", "", "fdm.exe (fdm.exe)")
        if path:
            self._fdm_path_edit.setText(path)
            prefs = dict(self._db.get_ui_preferences())
            prefs["fdm_exe_path"] = path
            self._db.set_ui_preferences(prefs)

    # ============================================================ 工具入口

    def _main_window(self):
        w = self.parent()
        while w is not None:
            if hasattr(w, "_open_hbe_decrypt_dialog"):
                return w
            w = w.parent()
        return None

    def _open_hbe_decrypt(self) -> None:
        main = self._main_window()
        if main:
            main._open_hbe_decrypt_dialog()

    def _open_auto_extract(self) -> None:
        main = self._main_window()
        if main:
            main._open_auto_extract_dialog()

    def _open_data_manager(self) -> None:
        main = self._main_window()
        if main:
            main._open_game_data_manager()

    def _open_plugins(self) -> None:
        main = self._main_window()
        if main:
            main._open_plugin_settings()

    def _open_password_manager(self) -> None:
        from app.ui.dialogs.password_manager_dialog import PasswordManagerDialog
        PasswordManagerDialog(self).exec()

    # ============================================================ 重置

    def _reset_to_defaults(self) -> None:
        reply = QMessageBox.question(
            self, "恢复默认设置",
            "确定要恢复所有设置为默认值吗？\n\n此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        from app.settings import get_default_settings
        defaults = get_default_settings()
        self._db.set_double_click_action(defaults["double_click_action"])
        self._db.set_last_launch_mode(defaults["last_launch_mode"])
        self._db.set_auto_backup_before_launch(defaults["auto_backup_before_launch"])
        self._db.set_cover_fetch_mode(defaults["cover_fetch_mode"])
        self._db.set_locale_emulator_leproc_path(defaults["locale_emulator_leproc_path"])
        self._db.set_twodfan_hints_db_path(defaults["twodfan_hints_db_path"])
        self._load_settings()
        self.settings_changed.emit()
        QMessageBox.information(self, "恢复成功", "所有设置已恢复为默认值。")
