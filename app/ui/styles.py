from __future__ import annotations

MAIN_WINDOW_STYLESHEET = """
QMainWindow {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1E2329, stop:1 #15191E);
}

QWidget {
    font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
}

QPushButton {
    color: #F2F4F7;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4A5568, stop:1 #2D3748);
    border: 1px solid #4A5568;
    border-radius: 10px;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 500;
    min-height: 32px;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #5A6678, stop:1 #3D4858);
    border-color: #6B788E;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}
QPushButton:pressed {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2D3748, stop:1 #1E2329);
    border-color: #4A5568;
    box-shadow: none;
}

QToolButton {
    color: #F2F4F7;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4A5568, stop:1 #2D3748);
    border: 1px solid #4A5568;
    border-radius: 10px;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 500;
    min-height: 32px;
}
QToolButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #5A6678, stop:1 #3D4858);
    border-color: #6B788E;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}
QToolButton:pressed {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2D3748, stop:1 #1E2329);
    border-color: #4A5568;
}

QLabel#toolbarSectionLabel {
    color: #8B96AA;
    font-size: 11px;
    font-weight: 600;
    min-width: 3.2em;
}

QWidget[toolbarGroup="true"] {
    background: rgba(35, 40, 49, 0.95);
    border: 1px solid #3B4250;
    border-radius: 12px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}
QWidget[toolbarTier="primary"] {
    background: rgba(37, 43, 52, 0.95);
    border: 1px solid #4A5568;
}
QWidget[toolbarTier="secondary"] {
    background: rgba(31, 36, 44, 0.95);
    border: 1px solid #343B48;
}

QPushButton:disabled {
    color: #8A93A5;
    background: #2E3238;
    border: 1px solid #444B57;
}
QPushButton[highlighted="true"] {
    border: 2px solid #FFD166;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #5A4B2F, stop:1 #3D3420);
}
QPushButton[active="true"] {
    color: #F2F4F7;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4A6FA5, stop:1 #2D4A6F);
    border: 2px solid #8FB4FF;
    box-shadow: 0 0 12px rgba(143, 180, 255, 0.3);
}

QLineEdit {
    color: #F2F4F7;
    background: rgba(45, 55, 72, 0.8);
    border: 1px solid #4A5568;
    border-radius: 10px;
    padding: 8px 12px;
    font-size: 13px;
    min-height: 32px;
}
QLineEdit:focus {
    border-color: #7FA7D9;
    box-shadow: 0 0 0 2px rgba(127, 167, 217, 0.2);
}
QLineEdit::placeholder {
    color: #6B7280;
}

QComboBox {
    color: #F2F4F7;
    background: rgba(45, 55, 72, 0.8);
    border: 1px solid #4A5568;
    border-radius: 10px;
    padding: 8px 12px;
    font-size: 13px;
    min-height: 32px;
}
QComboBox:hover {
    border-color: #6B788E;
}
QComboBox:focus {
    border-color: #7FA7D9;
}
QComboBox::drop-down {
    border: none;
    background: transparent;
}
QComboBox::down-arrow {
    image: url(:/icons/down_arrow.png);
    width: 16px;
    height: 16px;
}

QCheckBox {
    color: #DCE3EE;
    font-size: 13px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 6px;
    background: rgba(45, 55, 72, 0.8);
    border: 1px solid #4A5568;
}
QCheckBox::indicator:checked {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #7FA7D9, stop:1 #5A8BC7);
    border-color: #7FA7D9;
}
QCheckBox::indicator:checked::after {
    image: url(:/icons/check.png);
}

QListWidget {
    border: 1px solid #3E4552;
    border-radius: 12px;
    padding: 8px;
    background: rgba(28, 33, 40, 0.9);
}
QListWidget::item {
    background: rgba(44, 49, 56, 0.8);
    border: 1px solid #3A4250;
    border-radius: 10px;
    margin: 4px;
    padding: 8px;
}
QListWidget::item:hover {
    background: rgba(49, 56, 68, 0.9);
    border-color: #4E5E79;
}
QListWidget::item:selected {
    background: rgba(59, 74, 102, 0.9);
    border-color: #7597CC;
}

QLabel {
    color: #DCE3EE;
}
QLabel[guided="true"] {
    color: #FFE7A8;
}
QLabel#gameTitle {
    color: #F3F6FB;
    font-size: 15px;
    font-weight: 600;
}
QLabel#gameMeta {
    color: #93A1B6;
    font-size: 11px;
}
QLabel#gameMetaSource {
    color: #7FA7D9;
    font-size: 11px;
}

QFrame#gameCardSlot {
    background: rgba(44, 49, 56, 0.7);
    border: 1px solid #3A4250;
    border-radius: 14px;
    transition: all 0.2s ease;
}
QFrame#gameCardSlot:hover {
    border: 2px solid #7FA7D9;
    background: rgba(59, 74, 102, 0.8);
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(127, 167, 217, 0.2);
}
QFrame#gameCardSlot[selected="true"] {
    background: rgba(59, 74, 102, 0.9);
    border: 2px solid #7597CC;
    box-shadow: 0 0 20px rgba(117, 151, 204, 0.3);
}

QLabel#gridPageLabel {
    color: #93A1B6;
    font-size: 12px;
}

QWidget#gameTextBlock {
    background: rgba(40, 47, 57, 0.9);
    border-radius: 10px;
    padding: 8px;
}

QLabel#gameCover {
    background: transparent;
    border: none;
    border-radius: 8px;
}

QScrollArea {
    border: none;
    background: transparent;
}
QScrollArea QWidget {
    background: transparent;
}

QScrollBar:vertical {
    width: 8px;
    background: rgba(35, 40, 49, 0.5);
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: rgba(94, 106, 127, 0.8);
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background: rgba(116, 134, 163, 0.9);
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QProgressBar {
    color: #F2F4F7;
    background: rgba(45, 55, 72, 0.6);
    border: 1px solid #4A5568;
    border-radius: 8px;
    padding: 2px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7FA7D9, stop:1 #5A8BC7);
    border-radius: 6px;
}

QStatusBar {
    color: #93A1B6;
    background: rgba(31, 36, 44, 0.8);
    border-top: 1px solid #343B48;
    font-size: 12px;
}

QMenu {
    color: #F2F4F7;
    background: rgba(37, 43, 52, 0.98);
    border: 1px solid #4A5568;
    border-radius: 10px;
    padding: 4px;
}
QMenu::item {
    padding: 8px 24px;
    border-radius: 6px;
}
QMenu::item:hover {
    background: rgba(127, 167, 217, 0.2);
}
QMenu::item:selected {
    background: rgba(127, 167, 217, 0.3);
}
"""
