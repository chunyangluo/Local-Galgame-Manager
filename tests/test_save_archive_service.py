from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from app.services.save_archive_service import restore_zip_to_directory


def test_restore_zip_to_directory_replaces_contents(tmp_path: Path) -> None:
    dest = tmp_path / "save"
    dest.mkdir()
    (dest / "old.dat").write_text("old", encoding="utf-8")
    archive = tmp_path / "save.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("new.dat", "new")

    restore_zip_to_directory(archive, dest)

    assert not (dest / "old.dat").exists()
    assert (dest / "new.dat").read_text(encoding="utf-8") == "new"


def test_restore_zip_to_directory_keeps_existing_on_invalid_zip(tmp_path: Path) -> None:
    dest = tmp_path / "save"
    dest.mkdir()
    old_file = dest / "old.dat"
    old_file.write_text("old", encoding="utf-8")
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../escape.dat", "bad")

    with pytest.raises(ValueError, match="非法路径"):
        restore_zip_to_directory(archive, dest)

    assert old_file.read_text(encoding="utf-8") == "old"
