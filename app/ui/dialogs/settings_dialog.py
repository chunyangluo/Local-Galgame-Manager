"""综合设置对话框 - 系统性整合软件设置功能"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.settings import CoverFetchMode, DoubleClickAction


class SettingsDialog(QDialog):
    """综合设置对话框"""
    
    settings_changed = Signal()
    
    def __init__(self, db, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self._loading = True  # 防止加载时触发信号写入
        self.setWindowTitle("设置")
        self.setMinimumSize(500, 450)
        self._init_ui()
        self._load_settings()
        self._loading = False
    
    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        
        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        scroll_layout = QVBoxLayout(content)
        
        # ========== 启动设置 ==========
        launch_group = QGroupBox("启动设置")
        launch_layout = QFormLayout(launch_group)
        
        # 双击打开方式
        self._double_click_combo = QComboBox()
        self._double_click_combo.addItems([
            "普通启动 - 直接启动游戏exe",
            "强制使用LE转区 - 始终使用Locale Emulator",
            "智能模式 - 记住上一次启动方式",
        ])
        self._double_click_combo.currentIndexChanged.connect(self._on_double_click_changed)
        launch_layout.addRow("双击打开游戏:", self._double_click_combo)
        
        # LE说明
        le_note = QLabel("提示：智能模式会自动使用上一次启动该游戏的方式。\n"
                         "LE转区需要先在下方「系统设置」中配置Locale Emulator路径。")
        le_note.setStyleSheet("color: #93A1B6; font-size: 11px;")
        launch_layout.addRow("", le_note)
        
        # 自动备份
        self._auto_backup_check = QCheckBox("启动游戏前自动备份存档")
        self._auto_backup_check.stateChanged.connect(self._on_auto_backup_changed)
        launch_layout.addRow("", self._auto_backup_check)
        
        scroll_layout.addWidget(launch_group)
        
        # ========== 封面设置 ==========
        cover_group = QGroupBox("封面设置")
        cover_layout = QFormLayout(cover_group)
        
        self._cover_mode_combo = QComboBox()
        self._cover_mode_combo.addItems([
            "仅本地封面",
            "本地优先（本地有则用本地）",
            "网图优先（优先从VNDB获取）",
        ])
        self._cover_mode_combo.currentIndexChanged.connect(self._on_cover_mode_changed)
        cover_layout.addRow("封面获取策略:", self._cover_mode_combo)
        
        scroll_layout.addWidget(cover_group)
        
        # ========== 系统设置 ==========
        system_group = QGroupBox("系统设置")
        system_layout = QFormLayout(system_group)
        
        # Locale Emulator路径
        le_layout = QHBoxLayout()
        self._le_path_edit = QLineEdit()
        self._le_path_edit.setPlaceholderText("选择LEProc.exe路径...")
        self._le_path_edit.editingFinished.connect(self._on_le_path_editing_finished)
        le_layout.addWidget(self._le_path_edit)
        btn_browse_le = QPushButton("浏览...")
        btn_browse_le.setProperty("btnRole", "secondary")
        btn_browse_le.clicked.connect(self._browse_le_path)
        le_layout.addWidget(btn_browse_le)
        system_layout.addRow("Locale Emulator:", le_layout)
        
        le_status = QLabel("用于「LE转区启动」，留空则关闭LE功能")
        le_status.setStyleSheet("color: #93A1B6; font-size: 11px;")
        system_layout.addRow("", le_status)
        
        # 2DFan线索库路径
        hints_layout = QHBoxLayout()
        self._hints_path_edit = QLineEdit()
        self._hints_path_edit.setPlaceholderText("选择2DFan SQLite数据库路径...")
        self._hints_path_edit.editingFinished.connect(self._on_hints_path_editing_finished)
        hints_layout.addWidget(self._hints_path_edit)
        btn_browse_hints = QPushButton("浏览...")
        btn_browse_hints.setProperty("btnRole", "secondary")
        btn_browse_hints.clicked.connect(self._browse_hints_path)
        hints_layout.addWidget(btn_browse_hints)
        system_layout.addRow("2DFan线索库:", hints_layout)
        
        hints_note = QLabel("用于存档自动发现，可与 tools/2dfan-save-crawler 共用数据库")
        hints_note.setStyleSheet("color: #93A1B6; font-size: 11px;")
        system_layout.addRow("", hints_note)
        
        scroll_layout.addWidget(system_group)
        
        # ========== 界面设置 ==========
        ui_group = QGroupBox("界面设置")
        ui_layout = QVBoxLayout(ui_group)
        
        btn_theme = QPushButton("主题与外观...")
        btn_theme.clicked.connect(self._open_theme_settings)
        ui_layout.addWidget(btn_theme)
        
        scroll_layout.addWidget(ui_group)
        
        # 添加弹簧
        scroll_layout.addStretch()
        
        scroll.setWidget(content)
        layout.addWidget(scroll)
        
        # ========== 底部按钮 ==========
        button_box = QDialogButtonBox()
        
        btn_reset = QPushButton("恢复默认设置")
        btn_reset.setProperty("btnRole", "danger")
        btn_reset.clicked.connect(self._reset_to_defaults)
        
        btn_ok = QPushButton("确定")
        btn_ok.setProperty("btnRole", "primary")
        btn_ok.clicked.connect(self.accept)
        
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        
        button_box.addButton(btn_reset, QDialogButtonBox.ResetRole)
        button_box.addButton(btn_ok, QDialogButtonBox.AcceptRole)
        button_box.addButton(btn_cancel, QDialogButtonBox.RejectRole)
        
        layout.addWidget(button_box)
    
    def _load_settings(self) -> None:
        """从数据库加载设置（不触发信号写入）"""
        self._loading = True
        
        # 双击打开方式
        action = self._db.get_double_click_action()
        if action == DoubleClickAction.NORMAL:
            self._double_click_combo.setCurrentIndex(0)
        elif action == DoubleClickAction.FORCE_LE:
            self._double_click_combo.setCurrentIndex(1)
        elif action == DoubleClickAction.SMART:
            self._double_click_combo.setCurrentIndex(2)
        
        # 自动备份
        self._auto_backup_check.setChecked(self._db.get_auto_backup_before_launch())
        
        # 封面策略
        mode = self._db.get_cover_fetch_mode()
        if mode == CoverFetchMode.LOCAL_ONLY:
            self._cover_mode_combo.setCurrentIndex(0)
        elif mode == CoverFetchMode.LOCAL_PREFER:
            self._cover_mode_combo.setCurrentIndex(1)
        elif mode == CoverFetchMode.ONLINE_PREFER:
            self._cover_mode_combo.setCurrentIndex(2)
        
        # LE路径
        self._le_path_edit.setText(self._db.get_locale_emulator_leproc_path())
        
        # 2DFan路径
        self._hints_path_edit.setText(self._db.get_twodfan_hints_db_path())
        
        self._loading = False
    
    def _on_double_click_changed(self, index: int) -> None:
        """双击打开方式改变"""
        if self._loading:
            return
        actions = [
            DoubleClickAction.NORMAL,
            DoubleClickAction.FORCE_LE,
            DoubleClickAction.SMART,
        ]
        if 0 <= index < len(actions):
            self._db.set_double_click_action(actions[index])
            self.settings_changed.emit()
    
    def _on_auto_backup_changed(self, state: int) -> None:
        """自动备份设置改变"""
        if self._loading:
            return
        self._db.set_auto_backup_before_launch(bool(state))
        self.settings_changed.emit()
    
    def _on_cover_mode_changed(self, index: int) -> None:
        """封面策略改变"""
        if self._loading:
            return
        modes = [CoverFetchMode.LOCAL_ONLY, CoverFetchMode.LOCAL_PREFER, CoverFetchMode.ONLINE_PREFER]
        if 0 <= index < len(modes):
            self._db.set_cover_fetch_mode(modes[index])
            self.settings_changed.emit()
    
    def _on_le_path_editing_finished(self) -> None:
        """LE路径编辑完成时保存"""
        if self._loading:
            return
        self._db.set_locale_emulator_leproc_path(self._le_path_edit.text())
        self.settings_changed.emit()
    
    def _on_hints_path_editing_finished(self) -> None:
        """2DFan路径编辑完成时保存"""
        if self._loading:
            return
        self._db.set_twodfan_hints_db_path(self._hints_path_edit.text())
        self.settings_changed.emit()
    
    def _browse_le_path(self) -> None:
        """浏览LE路径"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择Locale Emulator", "", "LEProc.exe (LEProc.exe)"
        )
        if path:
            self._le_path_edit.setText(path)
            self._db.set_locale_emulator_leproc_path(path)
            self.settings_changed.emit()
    
    def _browse_hints_path(self) -> None:
        """浏览2DFan路径"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择2DFan数据库", "", "SQLite Database (*.db *.sqlite)"
        )
        if path:
            self._hints_path_edit.setText(path)
            self._db.set_twodfan_hints_db_path(path)
            self.settings_changed.emit()
    
    def _open_theme_settings(self) -> None:
        """打开主题设置对话框"""
        from app.ui.dialogs import ThemeSettingsDialog
        dialog = ThemeSettingsDialog(self)
        dialog.theme_changed.connect(self.settings_changed.emit)
        dialog.exec()
    
    def _reset_to_defaults(self) -> None:
        """恢复默认设置"""
        reply = QMessageBox.question(
            self,
            "恢复默认设置",
            "确定要恢复所有设置为默认值吗？\n\n此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        
        if reply == QMessageBox.Yes:
            from app.settings import get_default_settings
            defaults = get_default_settings()
            
            self._db.set_double_click_action(defaults["double_click_action"])
            self._db.set_last_launch_mode(defaults["last_launch_mode"])
            self._db.set_auto_backup_before_launch(defaults["auto_backup_before_launch"])
            self._db.set_cover_fetch_mode(defaults["cover_fetch_mode"])
            self._db.set_locale_emulator_leproc_path(defaults["locale_emulator_leproc_path"])
            self._db.set_twodfan_hints_db_path(defaults["twodfan_hints_db_path"])
            
            # 重新加载界面
            self._load_settings()
            self.settings_changed.emit()
            
            QMessageBox.information(self, "恢复成功", "所有设置已恢复为默认值。")
