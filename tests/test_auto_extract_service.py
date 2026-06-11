from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from app.services import auto_extract_service as aes
from app.services.paths import auto_extract_tool_dir


def test_auto_extract_integration_present() -> None:
    assert auto_extract_tool_dir() is not None


def test_read_directory_config_has_keys() -> None:
    if auto_extract_tool_dir() is None:
        pytest.skip("auto extract tool not in tree")
    cfg = aes.read_directory_config()
    assert "watch" in cfg
    assert "game_save" in cfg


def test_is_auto_extract_available() -> None:
    if not auto_extract_tool_dir():
        pytest.skip("auto extract tool not in tree")
    reason = aes.auto_extract_missing_reason()
    if reason:
        pytest.skip(reason)
    assert aes.is_auto_extract_available() is True


def test_runtime_config_is_created_in_user_data(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    if auto_extract_tool_dir() is None:
        pytest.skip("auto extract tool not in tree")

    monkeypatch.setattr(aes, "get_app_data_dir", lambda: tmp_path)

    cfg_path = aes.config_yaml_path()
    assert cfg_path == tmp_path / "auto_extract" / "config" / "config.yaml"
    assert cfg_path.is_file()

    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    directory_text = "\n".join(str(v) for v in data["directories"].values())
    assert "D:\\" not in directory_text
    assert "E:\\" not in directory_text
    assert data["passwords"]["file"] == str(
        tmp_path / "auto_extract" / "config" / "passwords.json"
    )
    assert Path(data["seven_zip"]["path"]).name == "7za.exe"

    password_data = json.loads(
        (tmp_path / "auto_extract" / "config" / "passwords.json").read_text(
            encoding="utf-8"
        )
    )
    assert password_data == {"passwords": [], "success_map": {}, "success_counts": {}}
