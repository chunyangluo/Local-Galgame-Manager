from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.core.launcher import GameLauncher


class TestLaunchValidation:
    def test_launch_nonexistent_file_raises(self) -> None:
        launcher = GameLauncher()
        with pytest.raises(FileNotFoundError, match="Launch target not found"):
            launcher.launch("C:/nonexistent_game_xyz/game.exe")

    def test_launch_via_locale_emulator_nonexistent_leproc(self, tmp_path: Path) -> None:
        if sys.platform != "win32":
            pytest.skip("Locale Emulator only on Windows")
        launcher = GameLauncher()
        target = tmp_path / "game.exe"
        target.write_bytes(b"\x00" * 1024)
        with pytest.raises(FileNotFoundError, match="LEProc not found"):
            launcher.launch_via_locale_emulator(str(tmp_path / "LEProc.exe"), str(target))

    def test_launch_via_locale_emulator_nonexistent_target(self, tmp_path: Path) -> None:
        if sys.platform != "win32":
            pytest.skip("Locale Emulator only on Windows")
        launcher = GameLauncher()
        leproc = tmp_path / "LEProc.exe"
        leproc.write_bytes(b"\x00" * 1024)
        with pytest.raises(FileNotFoundError, match="Launch target not found"):
            launcher.launch_via_locale_emulator(str(leproc), "C:/no_game.exe")

    def test_launch_via_locale_emulator_wrong_leproc_name(self, tmp_path: Path) -> None:
        if sys.platform != "win32":
            pytest.skip("Locale Emulator only on Windows")
        launcher = GameLauncher()
        not_leproc = tmp_path / "something.exe"
        not_leproc.write_bytes(b"\x00" * 1024)
        target = tmp_path / "game.exe"
        target.write_bytes(b"\x00" * 1024)
        with pytest.raises(ValueError, match="LEProc.exe"):
            launcher.launch_via_locale_emulator(str(not_leproc), str(target))

    def test_launch_via_locale_emulator_non_windows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "platform", "linux")
        launcher = GameLauncher()
        with pytest.raises(RuntimeError, match="only supported on Windows"):
            launcher.launch_via_locale_emulator("LEProc.exe", "game.exe")


class TestLaunchQuickProcess:
    def test_launch_short_lived_process(self, tmp_path: Path) -> None:
        if sys.platform != "win32":
            pytest.skip("Process launch tests only on Windows")
        script = tmp_path / "quick_exit.bat"
        script.write_text("@echo off\nexit /b 0\n", encoding="utf-8")
        launcher = GameLauncher()
        duration = launcher.launch(str(script))
        assert duration >= 0
