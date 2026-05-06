from __future__ import annotations

import json
import os
import subprocess
import sys
import winreg
from pathlib import Path


class SystemService:
    RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
    RUN_VALUE_NAME = "LocalGalgameManager"

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.config_path = self.base_dir / "system_config.json"

    def set_startup(self, enabled: bool) -> None:
        if enabled:
            self._write_startup_registry()
        else:
            self._remove_startup_registry()
        state = self._read_config()
        state["run_on_startup"] = enabled
        self._write_config(state)

    def is_startup_enabled(self) -> bool:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
                value, _ = winreg.QueryValueEx(key, self.RUN_VALUE_NAME)
            return bool(value)
        except FileNotFoundError:
            return False

    def set_minimize_to_tray(self, enabled: bool) -> None:
        state = self._read_config()
        state["minimize_to_tray"] = enabled
        self._write_config(state)

    def create_desktop_shortcut(self, name: str, target_path: str) -> Path:
        target = Path(target_path)
        if not target.exists():
            raise FileNotFoundError(f"Launch target not found: {target_path}")
        desktop = Path(os.path.expanduser("~")) / "Desktop"
        desktop.mkdir(parents=True, exist_ok=True)
        safe_name = self._sanitize_filename(name)
        shortcut = desktop / f"{safe_name}.lnk"
        try:
            self._create_windows_lnk(shortcut, target)
            return shortcut
        except Exception:
            # Fallback for restricted environments where COM shortcut creation
            # may fail. URL shortcuts still allow launching target files.
            fallback = desktop / f"{safe_name}.url"
            normalized = str(target).replace("\\", "/")
            fallback.write_text(
                f"[InternetShortcut]\nURL=file:///{normalized}\n",
                encoding="utf-8",
            )
            return fallback

    def _create_windows_lnk(self, shortcut_path: Path, target: Path) -> None:
        working_dir = target.parent
        script = f"""
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut('{str(shortcut_path)}')
$s.TargetPath = '{str(target)}'
$s.WorkingDirectory = '{str(working_dir)}'
$s.IconLocation = '{str(target)},0'
$s.Save()
"""
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            check=True,
            capture_output=True,
            text=True,
        )

    def _sanitize_filename(self, value: str) -> str:
        invalid = '<>:"/\\|?*'
        result = "".join("_" if ch in invalid else ch for ch in value).strip()
        return result or "GameShortcut"

    def _read_config(self) -> dict:
        if not self.config_path.exists():
            return {}
        return json.loads(self.config_path.read_text(encoding="utf-8"))

    def _write_config(self, data: dict) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _build_startup_command(self) -> str:
        if getattr(sys, "frozen", False):
            return f"\"{sys.executable}\""
        return f"\"{sys.executable}\" -m app.main"

    def _write_startup_registry(self) -> None:
        command = self._build_startup_command()
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.RUN_KEY_PATH) as key:
            winreg.SetValueEx(key, self.RUN_VALUE_NAME, 0, winreg.REG_SZ, command)

    def _remove_startup_registry(self) -> None:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.RUN_KEY_PATH,
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.DeleteValue(key, self.RUN_VALUE_NAME)
        except FileNotFoundError:
            return
