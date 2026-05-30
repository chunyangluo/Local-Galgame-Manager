from __future__ import annotations

import logging
import time
from datetime import datetime
from enum import Enum
from typing import Callable


class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    SUCCESS = "SUCCESS"


class LogService:
    _instance = None
    
    def __init__(self):
        self._callbacks: list[Callable[[LogLevel, str, float], None]] = []
        self._logger = logging.getLogger("app")
        self._logger.setLevel(logging.DEBUG)
        
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s | %(levelname)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            handler.setFormatter(formatter)
            self._logger.addHandler(handler)
    
    @classmethod
    def get_instance(cls) -> "LogService":
        if cls._instance is None:
            cls._instance = LogService()
        return cls._instance
    
    def add_callback(self, callback: Callable[[LogLevel, str, float], None]) -> None:
        if callback not in self._callbacks:
            self._callbacks.append(callback)
    
    def remove_callback(self, callback: Callable[[LogLevel, str, float], None]) -> None:
        if callback in self._callbacks:
            self._callbacks.remove(callback)
    
    def _notify(self, level: LogLevel, message: str, timestamp: float) -> None:
        for callback in self._callbacks:
            try:
                callback(level, message, timestamp)
            except Exception:
                pass
    
    def log(self, message: str, level: LogLevel = LogLevel.INFO) -> None:
        timestamp = time.time()
        time_str = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
        
        self._logger.log(
            {
                LogLevel.DEBUG: logging.DEBUG,
                LogLevel.INFO: logging.INFO,
                LogLevel.WARNING: logging.WARNING,
                LogLevel.ERROR: logging.ERROR,
            }.get(level, logging.INFO),
            message
        )
        
        self._notify(level, message, timestamp)
    
    def info(self, message: str) -> None:
        self.log(message, LogLevel.INFO)
    
    def debug(self, message: str) -> None:
        self.log(message, LogLevel.DEBUG)
    
    def warning(self, message: str) -> None:
        self.log(message, LogLevel.WARNING)
    
    def error(self, message: str) -> None:
        self.log(message, LogLevel.ERROR)
    
    def success(self, message: str) -> None:
        self.log(message, LogLevel.SUCCESS)
    
    def progress(self, operation: str, current: int, total: int) -> None:
        percent = int((current / max(total, 1)) * 100)
        message = f"{operation} - 进度: {current}/{total} ({percent}%)"
        self.log(message, LogLevel.INFO)
