from __future__ import annotations

MAIN_WINDOW_STYLESHEET = """
QMainWindow {
    background: #181C22;
}

QWidget {
    font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
    color: #DCE3EE;
}

/* ===== 按钮 ===== */
QPushButton {
    color: #E8ECF2;
    background: #2E3644;
    border: 1px solid #3D4759;
    border-radius: 6px;
    padding: 5px 12px;
    font-size: 12px;
    font-weight: 500;
    min-height: 28px;
}
QPushButton:hover {
    background: #3A4558;
    border-color: #5A6A82;
}
QPushButton:pressed {
    background: #232A35;
    border-color: #3D4759;
}
QPushButton:disabled {
    color: #6B7585;
    background: #252A32;
    border: 1px solid #333A46;
}
QPushButton[active="true"] {
    color: #F2F4F7;
    background: #3A5A8A;
    border: 1px solid #6A9FD8;
}
QPushButton[highlighted="true"] {
    border: 1px solid #E8B84D;
    background: #4A3D22;
}

QToolButton {
    color: #E8ECF2;
    background: #2E3644;
    border: 1px solid #3D4759;
    border-radius: 6px;
    padding: 5px 12px;
    font-size: 12px;
    font-weight: 500;
    min-height: 28px;
}
QToolButton:hover {
    background: #3A4558;
    border-color: #5A6A82;
}
QToolButton:pressed {
    background: #232A35;
    border-color: #3D4759;
}
QToolButton::menu-indicator {
    subcontrol-origin: padding;
    subcontrol-position: right center;
    right: 6px;
    width: 10px;
}

/* ===== 输入框 ===== */
QLineEdit {
    color: #E8ECF2;
    background: #232A35;
    border: 1px solid #3D4759;
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 12px;
    min-height: 28px;
}
QLineEdit:focus {
    border-color: #6A9FD8;
}
QLineEdit::placeholder {
    color: #5A6474;
}

QComboBox {
    color: #E8ECF2;
    background: #232A35;
    border: 1px solid #3D4759;
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 12px;
    min-height: 28px;
}
QComboBox:hover {
    border-color: #5A6A82;
}
QComboBox:focus {
    border-color: #6A9FD8;
}
QComboBox::drop-down {
    border: none;
    background: transparent;
}
QComboBox::down-arrow {
    image: url(:/icons/down_arrow.png);
    width: 14px;
    height: 14px;
}

QCheckBox {
    color: #C8D0DC;
    font-size: 12px;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    background: #232A35;
    border: 1px solid #3D4759;
}
QCheckBox::indicator:checked {
    background: #6A9FD8;
    border-color: #6A9FD8;
}

/* ===== 列表 ===== */
QListWidget {
    border: 1px solid #2E3644;
    border-radius: 8px;
    padding: 6px;
    background: #1C2028;
    outline: none;
}
QListWidget::item {
    background: #252A35;
    border: 1px solid #333A46;
    border-radius: 8px;
    margin: 3px;
    padding: 6px;
}
QListWidget::item:hover {
    background: #2E3644;
    border-color: #4A5568;
}
QListWidget::item:selected {
    background: #2E4468;
    border-color: #6A9FD8;
}

/* ===== 标签 ===== */
QLabel {
    color: #C8D0DC;
}
QLabel[guided="true"] {
    color: #E8B84D;
}
QLabel#gameTitle {
    color: #F0F3F8;
    font-size: 13px;
    font-weight: 600;
}
QLabel#gameMeta {
    color: #7A8699;
    font-size: 10px;
}
QLabel#gameMetaSource {
    color: #6A9FD8;
    font-size: 10px;
}
QLabel#statusBar {
    color: #5A6474;
    font-size: 11px;
    padding: 2px 6px;
    background: transparent;
}

/* ===== 游戏卡片 ===== */
QFrame#gameCardSlot {
    background: #22272F;
    border: 1px solid #333A46;
    border-radius: 10px;
}
QFrame#gameCardSlot:hover {
    border: 1px solid #6A9FD8;
    background: #283040;
}
QFrame#gameCardSlot[selected="true"] {
    background: #283040;
    border: 2px solid #6A9FD8;
}

QWidget#gameTextBlock {
    background: transparent;
    padding: 6px 8px;
}

QLabel#gameCover {
    background: transparent;
    border: none;
    border-radius: 6px;
}

QLabel#gridPageLabel {
    color: #5A6474;
    font-size: 11px;
}

/* ===== 滚动条 ===== */
QScrollArea {
    border: none;
    background: transparent;
}
QScrollArea QWidget {
    background: transparent;
}

QScrollBar:vertical {
    width: 6px;
    background: transparent;
    border-radius: 3px;
}
QScrollBar::handle:vertical {
    background: rgba(90, 100, 120, 0.6);
    border-radius: 3px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background: rgba(110, 125, 155, 0.8);
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

/* ===== 进度条 ===== */
QProgressBar {
    color: #C8D0DC;
    background: #232A35;
    border: 1px solid #3D4759;
    border-radius: 4px;
    padding: 1px;
    text-align: center;
    font-size: 11px;
}
QProgressBar::chunk {
    background: #6A9FD8;
    border-radius: 3px;
}

/* ===== 菜单 ===== */
QMenu {
    color: #E8ECF2;
    background: #2A3040;
    border: 1px solid #3D4759;
    border-radius: 8px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 20px;
    border-radius: 4px;
}
QMenu::item:hover {
    background: #3A4558;
}
QMenu::item:selected {
    background: #3A4558;
}
QMenu::separator {
    height: 1px;
    background: #3D4759;
    margin: 4px 8px;
}

/* ===== 对话框 ===== */
QGroupBox {
    color: #C8D0DC;
    border: 1px solid #3D4759;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 16px;
    font-weight: 500;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}

QDialogButtonBox QPushButton {
    min-width: 80px;
}
"""
