from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path


class BackupService:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.backup_dir = data_dir / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def export_backup(self, db_file: Path, extra: dict | None = None) -> Path:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        bundle_dir = self.backup_dir / f"backup_{timestamp}"
        bundle_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(db_file, bundle_dir / db_file.name)
        payload = {"created_at": datetime.utcnow().isoformat(), "extra": extra or {}}
        (bundle_dir / "meta.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        archive = shutil.make_archive(str(bundle_dir), "zip", str(bundle_dir))
        shutil.rmtree(bundle_dir, ignore_errors=True)
        return Path(archive)

    def import_backup(self, archive_path: Path, db_file: Path) -> None:
        temp_dir = self.backup_dir / "_restore_temp"
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        temp_dir.mkdir(parents=True, exist_ok=True)
        shutil.unpack_archive(str(archive_path), str(temp_dir), "zip")
        source_db = temp_dir / db_file.name
        if not source_db.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise FileNotFoundError("Backup does not include database file.")
        shutil.copy2(source_db, db_file)
        shutil.rmtree(temp_dir, ignore_errors=True)
