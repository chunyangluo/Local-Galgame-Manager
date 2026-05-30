from __future__ import annotations

import pytest

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
