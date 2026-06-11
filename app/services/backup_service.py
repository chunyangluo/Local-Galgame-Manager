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
        
        covers_dir = self.data_dir / "covers"
        if covers_dir.exists():
            shutil.copytree(covers_dir, bundle_dir / "covers")
        
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
        covers_temp = self.data_dir / "_covers_restore_temp"
        db_backup = temp_dir / f"{db_file.name}.current"
        covers_backup = temp_dir / "covers.current"
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        if covers_temp.exists():
            shutil.rmtree(covers_temp, ignore_errors=True)
        temp_dir.mkdir(parents=True, exist_ok=True)
        dest_covers = self.data_dir / "covers"
        try:
            shutil.unpack_archive(str(archive_path), str(temp_dir), "zip")
            source_db = temp_dir / db_file.name
            if not source_db.exists():
                raise FileNotFoundError("Backup does not include database file.")

            if db_file.exists():
                shutil.copy2(db_file, db_backup)
            if dest_covers.exists():
                shutil.copytree(dest_covers, covers_backup)

            source_covers = temp_dir / "covers"
            if source_covers.exists() and source_covers.is_dir():
                shutil.copytree(source_covers, covers_temp)

            shutil.copy2(source_db, db_file)
            if covers_temp.exists():
                if dest_covers.exists():
                    shutil.rmtree(dest_covers)
                covers_temp.replace(dest_covers)
        except Exception:
            if db_backup.exists():
                shutil.copy2(db_backup, db_file)
            if covers_backup.exists():
                if dest_covers.exists():
                    shutil.rmtree(dest_covers, ignore_errors=True)
                shutil.copytree(covers_backup, dest_covers)
            raise
        finally:
            shutil.rmtree(covers_temp, ignore_errors=True)
            shutil.rmtree(temp_dir, ignore_errors=True)
