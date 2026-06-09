from __future__ import annotations

MAIN_WINDOW_STYLESHEET = """
QMainWindow {
    background: #181C22;
}

QWidget {
    font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
    color: #DCE3EE;
}

/* ===== 按钮：全局标准化 ===== */
QPushButton {
    color: #F2F4F7;
    background: #2E3644;
    border: 1px solid #3D4759;
    border-radius: 6px;
    padding: 8px 14px;
    font-size: 12px;
    font-weight: 600;
    min-height: 30px;
}
QPushButton:hover {
    background: #3A4558;
    border-color: #6A9FD8;
    color: #FFFFFF;
}
QPushButton:pressed {
    background: #232A35;
    border-color: #4A7AB5;
    color: #FFFFFF;
}
QPushButton:disabled {
    color: #6B7585;
    background: #252A32;
    border: 1px solid #333A46;
}
QPushButton:focus {
    border-color: #6A9FD8;
    outline: none;
}
QPushButton[active="true"] {
    color: #FFFFFF;
    background: #3A5A8A;
    border: 2px solid #6A9FD8;
}
QPushButton[highlighted="true"] {
    color: #FFFFFF;
    border: 2px solid #E8B84D;
    background: #4A3D22;
}

/* 操作类按钮：启动/保存/确认 */
QPushButton[btnRole="primary"] {
    color: #FFFFFF;
    background: #3B82F6;
    border: 1px solid #2563EB;
    font-weight: 700;
}
QPushButton[btnRole="primary"]:hover {
    background: #2563EB;
    border-color: #1D4ED8;
}
QPushButton[btnRole="primary"]:pressed {
    background: #1D4ED8;
}
QPushButton[btnRole="primary"]:disabled {
    color: #94A3B8;
    background: #1E3A5F;
    border-color: #2563EB;
}

/* 危险类按钮：删除/重置 */
QPushButton[btnRole="danger"] {
    color: #FFFFFF;
    background: #DC2626;
    border: 1px solid #B91C1C;
    font-weight: 700;
}
QPushButton[btnRole="danger"]:hover {
    background: #B91C1C;
    border-color: #991B1B;
}
QPushButton[btnRole="danger"]:pressed {
    background: #991B1B;
}
QPushButton[btnRole="danger"]:disabled {
    color: #94A3B8;
    background: #5C1A1A;
    border-color: #7F1D1D;
}

/* 辅助类按钮：刷新/复制/打开目录 */
QPushButton[btnRole="secondary"] {
    color: #E8ECF2;
    background: #374151;
    border: 1px solid #4B5563;
}
QPushButton[btnRole="secondary"]:hover {
    background: #4B5563;
    border-color: #6B7280;
}
QPushButton[btnRole="secondary"]:pressed {
    background: #1F2937;
}
QPushButton[btnRole="secondary"]:disabled {
    color: #6B7280;
    background: #1F2937;
    border-color: #374151;
}

QToolButton {
    color: #F2F4F7;
    background: #2E3644;
    border: 1px solid #3D4759;
    border-radius: 6px;
    padding: 8px 14px;
    font-size: 12px;
    font-weight: 600;
    min-height: 30px;
}
QToolButton:hover {
    background: #3A4558;
    border-color: #6A9FD8;
    color: #FFFFFF;
}
QToolButton:pressed {
    background: #232A35;
    border-color: #4A7AB5;
    color: #FFFFFF;
}
QToolButton:disabled {
    color: #6B7585;
    background: #252A32;
    border: 1px solid #333A46;
}
QToolButton::menu-indicator {
    subcontrol-origin: padding;
    subcontrol-position: right center;
    right: 6px;
    width: 10px;
}

/* ===== 输入框 ===== */
QLineEdit {
    color: #F2F4F7;
    background: #232A35;
    border: 1px solid #3D4759;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
    min-height: 30px;
}
QLineEdit:focus {
    border-color: #6A9FD8;
}
QLineEdit::placeholder {
    color: #5A6474;
}

QComboBox {
    color: #F2F4F7;
    background: #232A35;
    border: 1px solid #3D4759;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
    min-height: 30px;
}
QComboBox:hover {
    border-color: #6A9FD8;
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
QComboBox QAbstractItemView {
    color: #F2F4F7;
    background: #2A3040;
    border: 1px solid #3D4759;
    selection-background-color: #3A5A8A;
    selection-color: #FFFFFF;
}

QCheckBox {
    color: #DCE3EE;
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
QCheckBox::indicator:hover {
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
    border-color: #6A9FD8;
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

QScrollBar:horizontal {
    height: 6px;
    background: transparent;
    border-radius: 3px;
}
QScrollBar::handle:horizontal {
    background: rgba(90, 100, 120, 0.6);
    border-radius: 3px;
    min-width: 20px;
}
QScrollBar::handle:horizontal:hover {
    background: rgba(110, 125, 155, 0.8);
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

/* ===== 工具提示 ===== */
QToolTip {
    color: #F2F4F7;
    background: #2A3040;
    border: 1px solid #3D4759;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
}

/* ===== 进度条 ===== */
QProgressBar {
    color: #F2F4F7;
    background: #232A35;
    border: 1px solid #3D4759;
    border-radius: 6px;
    padding: 1px;
    text-align: center;
    font-size: 11px;
    font-weight: 600;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #5B9BFF, stop:1 #6A9FD8);
    border-radius: 4px;
}

/* ===== 菜单 ===== */
QMenu {
    color: #F2F4F7;
    background: #2A3040;
    border: 1px solid #3D4759;
    border-radius: 8px;
    padding: 4px;
}
QMenu::item {
    padding: 8px 20px;
    border-radius: 4px;
    color: #F2F4F7;
}
QMenu::item:hover {
    background: #3A5A8A;
    color: #FFFFFF;
}
QMenu::item:selected {
    background: #3A5A8A;
    color: #FFFFFF;
}
QMenu::separator {
    height: 1px;
    background: #3D4759;
    margin: 4px 8px;
}

/* ===== 对话框 ===== */
QGroupBox {
    color: #DCE3EE;
    border: 1px solid #3D4759;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 16px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #DCE3EE;
}

QDialogButtonBox QPushButton {
    min-width: 80px;
    color: #F2F4F7;
    font-weight: 600;
}

/* ===== Tab Widget ===== */
QTabWidget::pane {
    border: 1px solid #3D4759;
    border-radius: 6px;
    background: #1C2028;
}
QTabBar::tab {
    color: #8B96AA;
    background: #252A35;
    border: 1px solid #3D4759;
    border-bottom: none;
    padding: 6px 16px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}
QTabBar::tab:selected {
    color: #F2F4F7;
    background: #2E3644;
    border-color: #6A9FD8;
}
QTabBar::tab:hover:!selected {
    color: #DCE3EE;
    background: #2E3644;
}

/* ===== Spin Box ===== */
QSpinBox {
    color: #F2F4F7;
    background: #232A35;
    border: 1px solid #3D4759;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 12px;
    min-height: 28px;
}
QSpinBox:focus {
    border-color: #6A9FD8;
}
QSpinBox::up-button, QSpinBox::down-button {
    background: #2E3644;
    border: none;
    width: 16px;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {
    background: #3A4558;
}
QSpinBox::up-arrow {
    width: 8px;
    height: 8px;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid #8B96AA;
}
QSpinBox::down-arrow {
    width: 8px;
    height: 8px;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #8B96AA;
}

/* ===== Text Edit / Plain Text Edit ===== */
QTextEdit {
    color: #DCE3EE;
    background: #1C2028;
    border: 1px solid #3D4759;
    border-radius: 6px;
    font-size: 12px;
}
QPlainTextEdit {
    color: #DCE3EE;
    background: #1C2028;
    border: 1px solid #3D4759;
    border-radius: 6px;
    font-size: 12px;
}

/* ===== Table Widget ===== */
QTableWidget {
    color: #DCE3EE;
    background: #1C2028;
    border: 1px solid #3D4759;
    border-radius: 6px;
    gridline-color: #2E3644;
    font-size: 12px;
}
QTableWidget::item {
    padding: 4px 8px;
}
QTableWidget::item:selected {
    background: #3A5A8A;
    color: #FFFFFF;
}
QHeaderView::section {
    color: #DCE3EE;
    background: #252A35;
    border: 1px solid #3D4759;
    padding: 6px 8px;
    font-weight: 600;
    font-size: 12px;
}

/* ===== Slider ===== */
QSlider::groove:horizontal {
    height: 4px;
    background: #2E3644;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #6A9FD8;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
QSlider::handle:horizontal:hover {
    background: #8AB4E0;
}
QSlider::sub-page:horizontal {
    background: #6A9FD8;
    border-radius: 2px;
}

/* ===== Date Edit ===== */
QDateEdit {
    color: #F2F4F7;
    background: #232A35;
    border: 1px solid #3D4759;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 12px;
    min-height: 28px;
}
QDateEdit:focus {
    border-color: #6A9FD8;
}
"""
