from __future__ import annotations

from core.extractor import Extractor
from core.file_manager import FileManager
from core.password_manager import PasswordManager
from core.watcher import WatcherService

_extractor: Extractor | None = None
_file_manager: FileManager | None = None
_password_manager: PasswordManager | None = None
_watcher_service: WatcherService | None = None


def init_services(
    extractor: Extractor,
    file_manager: FileManager,
    password_manager: PasswordManager,
    watcher_service: WatcherService,
) -> None:
    global _extractor, _file_manager, _password_manager, _watcher_service
    _extractor = extractor
    _file_manager = file_manager
    _password_manager = password_manager
    _watcher_service = watcher_service


def get_extractor() -> Extractor:
    if _extractor is None:
        raise RuntimeError("Extractor not initialized")
    return _extractor


def get_file_manager() -> FileManager:
    if _file_manager is None:
        raise RuntimeError("FileManager not initialized")
    return _file_manager


def get_password_manager() -> PasswordManager:
    if _password_manager is None:
        raise RuntimeError("PasswordManager not initialized")
    return _password_manager


def get_watcher_service() -> WatcherService:
    if _watcher_service is None:
        raise RuntimeError("WatcherService not initialized")
    return _watcher_service
