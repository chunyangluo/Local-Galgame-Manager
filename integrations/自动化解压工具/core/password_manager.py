from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional

from loguru import logger

from core.config import get_settings

PINNED_PASSWORDS = ["6868", "9"]


class PasswordManager:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._lock = threading.Lock()
        self._passwords: list[str] = []
        self._success_map: dict[str, str] = {}
        self._success_counts: dict[str, int] = {}
        self._load()

    def _get_file_path(self) -> Path:
        return Path(self._settings.passwords.file)

    def _load(self) -> None:
        fp = self._get_file_path()
        if not fp.exists():
            self._passwords = []
            self._success_map = {}
            self._success_counts = {}
            return
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._passwords = data.get("passwords", [])
                self._success_map = data.get("success_map", {})
                self._success_counts = data.get("success_counts", {})
            elif isinstance(data, list):
                self._passwords = data
                self._success_map = {}
                self._success_counts = {}
            else:
                self._passwords = []
                self._success_map = {}
                self._success_counts = {}
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"密码本加载失败: {e}")
            self._passwords = []
            self._success_map = {}
            self._success_counts = {}

    def _save(self) -> None:
        fp = self._get_file_path()
        fp.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "passwords": self._passwords,
            "success_map": self._success_map,
            "success_counts": self._success_counts,
        }
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_passwords(self) -> list[str]:
        with self._lock:
            pinned = []
            rest = []
            for p in self._passwords:
                if p in PINNED_PASSWORDS:
                    pinned.append(p)
                else:
                    rest.append(p)

            pinned_sorted = sorted(pinned, key=lambda p: PINNED_PASSWORDS.index(p))
            rest_sorted = sorted(rest, key=lambda p: -self._success_counts.get(p, 0))

            return pinned_sorted + rest_sorted

    def add_password(self, password: str) -> tuple[bool, str]:
        with self._lock:
            if password in self._passwords:
                return False, "密码已存在"
            self._passwords.append(password)
            self._save()
            logger.info(f"新增密码: {password[0]}***{password[-1] if len(password) > 1 else ''}")
            return True, "添加成功"

    def record_success(self, file_path: str, password: str) -> None:
        with self._lock:
            self._success_map[file_path] = password
            self._success_counts[password] = self._success_counts.get(password, 0) + 1
            self._save()

    def get_success_password(self, file_path: str) -> Optional[str]:
        with self._lock:
            return self._success_map.get(file_path)

    def get_success_map(self) -> dict[str, str]:
        with self._lock:
            return dict(self._success_map)
