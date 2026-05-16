from __future__ import annotations

MAIN_WINDOW_STYLESHEET = """
QPushButton {
    color: #F2F4F7;
    background-color: #3A3F46;
    border: 1px solid #596273;
    border-radius: 8px;
    padding: 6px 12px;
}
QPushButton:hover {
    background-color: #454B55;
    border-color: #6B788E;
}
QPushButton:pressed {
    background-color: #2F343B;
    border-color: #4A5568;
}
QToolButton {
    color: #F2F4F7;
    background-color: #3A3F46;
    border: 1px solid #596273;
    border-radius: 8px;
    padding: 6px 12px;
}
QToolButton:hover {
    background-color: #454B55;
    border-color: #6B788E;
}
QToolButton:pressed {
    background-color: #2F343B;
    border-color: #4A5568;
}
QLabel#toolbarSectionLabel {
    color: #8B96AA;
    font-size: 11px;
    font-weight: 600;
    min-width: 3.2em;
}
QWidget[toolbarGroup="true"] {
    background-color: #232831;
    border: 1px solid #3B4250;
    border-radius: 10px;
}
QWidget[toolbarTier="primary"] {
    background-color: #252B34;
    border: 1px solid #4A5568;
}
QWidget[toolbarTier="secondary"] {
    background-color: #1F242C;
    border: 1px solid #343B48;
}
QPushButton:disabled {
    color: #8A93A5;
    background-color: #2E3238;
    border: 1px solid #444B57;
}
QPushButton[highlighted="true"] {
    border: 2px solid #FFD166;
    background-color: #5A4B2F;
}
QPushButton[active="true"] {
    color: #F2F4F7;
    background-color: #3A3F46;
    border: 2px solid #8FB4FF;
}
QListWidget {
    border: 1px solid #3E4552;
    border-radius: 10px;
    padding: 6px;
}
QListWidget::item {
    background: #2C3138;
    border: 1px solid #3A4250;
    border-radius: 10px;
    margin: 2px;
}
QListWidget::item:hover {
    background: #313844;
    border: 1px solid #4E5E79;
}
QListWidget::item:selected {
    background: #3B4A66;
    border: 1px solid #7597CC;
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
    font-size: 10px;
}
QLabel#gameMetaSource {
    color: #7FA7D9;
    font-size: 10px;
}
QFrame#gameCardSlot {
    background: #2C3138;
    border: 1px solid #3A4250;
    border-radius: 10px;
}
QFrame#gameCardSlot:hover {
    border: 2px solid #7FA7D9;
}
QFrame#gameCardSlot[selected="true"] {
    background: #3B4A66;
    border: 2px solid #7597CC;
}
QLabel#gridPageLabel {
    color: #93A1B6;
    font-size: 12px;
}
QWidget#gameTextBlock {
    background: #282F39;
    border-radius: 8px;
}
QLabel#gameCover {
    background: transparent;
    border: none;
    border-radius: 6px;
}
"""
