from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from app.services.backup_service import BackupService


def test_import_backup_rolls_back_db_and_covers_on_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_file = data_dir / "manager.sqlite3"
    db_file.write_text("old-db", encoding="utf-8")
    covers = data_dir / "covers"
    covers.mkdir()
    (covers / "old.jpg").write_text("old-cover", encoding="utf-8")

    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "manager.sqlite3").write_text("new-db", encoding="utf-8")
    bundle_covers = bundle / "covers"
    bundle_covers.mkdir()
    (bundle_covers / "new.jpg").write_text("new-cover", encoding="utf-8")
    archive = tmp_path / "backup.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(bundle / "manager.sqlite3", "manager.sqlite3")
        zf.write(bundle_covers / "new.jpg", "covers/new.jpg")

    original_replace = Path.replace

    def fail_covers_replace(self: Path, target: Path):
        if self.name == "_covers_restore_temp":
            raise OSError("replace failed")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_covers_replace)
    service = BackupService(data_dir)

    with pytest.raises(OSError, match="replace failed"):
        service.import_backup(archive, db_file)

    assert db_file.read_text(encoding="utf-8") == "old-db"
    assert (covers / "old.jpg").read_text(encoding="utf-8") == "old-cover"
    assert not (covers / "new.jpg").exists()
