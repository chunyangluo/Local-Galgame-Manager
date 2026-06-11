from __future__ import annotations

from pathlib import Path

from app.ui.dialogs.game_data_manager_dialog import _is_unsafe_clear_dir


def test_clear_directory_rejects_root_and_home(tmp_path: Path) -> None:
    assert _is_unsafe_clear_dir(Path(tmp_path.anchor))
    assert _is_unsafe_clear_dir(Path.home())
    assert not _is_unsafe_clear_dir(tmp_path / "archive")
