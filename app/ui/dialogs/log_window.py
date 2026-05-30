from __future__ import annotations

import time
from datetime import datetime
from enum import Enum

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QTextCursor, QColor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    SUCCESS = "SUCCESS"


class LogEntry:
    def __init__(self, level: LogLevel, message: str, timestamp: float | None = None):
        self.level = level
        self.message = message
        self.timestamp = timestamp or time.time()

    def to_html(self) -> str:
        time_str = datetime.fromtimestamp(self.timestamp).strftime("%H:%M:%S.%f")[:-3]
        
        color_map = {
            LogLevel.DEBUG: "#6B7280",
            LogLevel.INFO: "#3B82F6",
            LogLevel.WARNING: "#F59E0B",
            LogLevel.ERROR: "#EF4444",
            LogLevel.SUCCESS: "#10B981",
        }
        color = color_map.get(self.level, "#FFFFFF")
        
        level_str = f'<span style="color:{color};font-weight:bold;">[{self.level.value}]</span>'
        return f"<span style=\"color:#9CA3AF;\">{time_str}</span> {level_str} {self.message}"


class LogWindow(QDialog):
    new_log = Signal(LogEntry)
    
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("系统日志")
        self.setMinimumSize(800, 500)
        self.resize(900, 600)
        
        self._log_buffer: list[LogEntry] = []
        self._max_buffer_size = 10000
        self._auto_scroll = True
        
        self._init_ui()
        self._setup_log_listener()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(10)
        
        self._status_label = QLabel("运行中")
        self._status_label.setStyleSheet("color: #10B981; font-weight: bold;")
        header.addWidget(self._status_label)
        
        header.addStretch(1)
        
        self._auto_scroll_check = QPushButton("自动滚动")
        self._auto_scroll_check.setCheckable(True)
        self._auto_scroll_check.setChecked(True)
        self._auto_scroll_check.clicked.connect(self._toggle_auto_scroll)
        header.addWidget(self._auto_scroll_check)
        
        self._clear_btn = QPushButton("清空日志")
        self._clear_btn.clicked.connect(self._clear_log)
        header.addWidget(self._clear_btn)
        
        self._filter_btn = QPushButton("筛选")
        self._filter_btn.clicked.connect(self._show_filter_menu)
        header.addWidget(self._filter_btn)
        
        layout.addLayout(header)

        self._log_display = QPlainTextEdit()
        self._log_display.setReadOnly(True)
        self._log_display.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1C2230;
                color: #E5E7EB;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 12px;
                border: 1px solid #374151;
                border-radius: 8px;
                padding: 8px;
            }
        """)
        layout.addWidget(self._log_display, 1)

        footer = QHBoxLayout()
        footer.setSpacing(10)
        
        self._entry_count = QLabel("0 条日志")
        footer.addWidget(self._entry_count)
        
        footer.addStretch(1)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        footer.addWidget(buttons)
        
        layout.addLayout(footer)

    def _setup_log_listener(self) -> None:
        self.new_log.connect(self._add_log_entry)
        
        from app.services.log_service import LogService, LogLevel
        
        def on_log(level: LogLevel, message: str, timestamp: float) -> None:
            entry = LogEntry(level, message, timestamp)
            self.new_log.emit(entry)
        
        self._log_callback = on_log
        LogService.get_instance().add_callback(on_log)

    def _toggle_auto_scroll(self) -> None:
        self._auto_scroll = self._auto_scroll_check.isChecked()

    def _clear_log(self) -> None:
        self._log_buffer.clear()
        self._log_display.clear()
        self._entry_count.setText("0 条日志")

    def _show_filter_menu(self) -> None:
        pass

    def _add_log_entry(self, entry: LogEntry) -> None:
        self._log_buffer.append(entry)
        
        if len(self._log_buffer) > self._max_buffer_size:
            self._log_buffer = self._log_buffer[-self._max_buffer_size:]
        
        html = entry.to_html()
        cursor = self._log_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        
        if self._log_buffer:
            cursor.insertHtml("<br>")
        
        cursor.insertHtml(html)
        self._log_display.setTextCursor(cursor)
        
        if self._auto_scroll:
            self._log_display.verticalScrollBar().setValue(
                self._log_display.verticalScrollBar().maximum()
            )
        
        self._entry_count.setText(f"{len(self._log_buffer)} 条日志")

    def log(self, message: str, level: LogLevel = LogLevel.INFO) -> None:
        entry = LogEntry(level, message)
        self.new_log.emit(entry)

    def log_progress(self, operation: str, current: int, total: int) -> None:
        percent = int((current / max(total, 1)) * 100)
        message = f"{operation} - 进度: {current}/{total} ({percent}%)"
        self.log(message, LogLevel.INFO)

    def log_success(self, message: str) -> None:
        self.log(message, LogLevel.SUCCESS)

    def log_warning(self, message: str) -> None:
        self.log(message, LogLevel.WARNING)

    def log_error(self, message: str) -> None:
        self.log(message, LogLevel.ERROR)

    def log_debug(self, message: str) -> None:
        self.log(message, LogLevel.DEBUG)

    @staticmethod
    def get_instance(parent: QWidget | None = None) -> "LogWindow":
        if not hasattr(LogWindow, "_instance") or LogWindow._instance is None:
            LogWindow._instance = LogWindow(parent)
        return LogWindow._instance
