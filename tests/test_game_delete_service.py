from __future__ import annotations

from pathlib import Path

import pytest

from app.data.database import Database
from app.services.game_delete_service import (
    delete_game_from_library,
    delete_game_install_folder,
    get_skip_delete_game_confirm,
    set_skip_delete_game_confirm,
)


def test_skip_delete_confirm_preference(db: Database) -> None:
    assert get_skip_delete_game_confirm(db) is False
    set_skip_delete_game_confirm(db, True)
    assert get_skip_delete_game_confirm(db) is True
    set_skip_delete_game_confirm(db, False)
    assert get_skip_delete_game_confirm(db) is False


def test_install_delete_failure_happens_after_db_row_removed(
    db_with_user: tuple[Database, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import game_delete_service as gds

    db, uid = db_with_user
    install = Path(db.base_dir) / "games" / "stay"
    install.mkdir(parents=True)
    exe = install / "g.exe"
    exe.write_bytes(b"")
    db.upsert_game("Stay", str(install), str(exe))
    gid = db.list_games(uid)[0].id

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(gds, "delete_game_install_folder", boom)
    with pytest.raises(OSError):
        delete_game_from_library(db, gid, delete_install_folder=True)
    assert db.list_games(uid) == []


def test_db_delete_failure_keeps_install_folder(
    db_with_user: tuple[Database, int], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, uid = db_with_user
    install = tmp_path / "games" / "stay"
    install.mkdir(parents=True)
    exe = install / "g.exe"
    exe.write_bytes(b"")
    db.upsert_game("Stay", str(install), str(exe))
    gid = db.list_games(uid)[0].id

    monkeypatch.setattr(db, "delete_game", lambda _gid: False)
    with pytest.raises(ValueError, match="删除失败"):
        delete_game_from_library(db, gid, delete_install_folder=True)
    assert install.exists()
    assert len(db.list_games(uid)) == 1


def test_delete_uses_custom_launch_exe_for_safety(
    db_with_user: tuple[Database, int], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import game_delete_service as gds

    db, uid = db_with_user
    install = tmp_path / "gal" / "MyGame"
    install.mkdir(parents=True)
    exe = install / "game.exe"
    exe.write_bytes(b"")
    db.upsert_game("G", str(install), str(exe))
    gid = db.list_games(uid)[0].id
    db.conn.execute(
        "UPDATE games SET custom_launch_exe = ? WHERE id = ?",
        (str(exe), gid),
    )
    db.conn.commit()
    seen: list[str] = []

    def record(_root: str, launch: str) -> None:
        seen.append(launch)

    monkeypatch.setattr(gds, "delete_game_install_folder", record)
    delete_game_from_library(db, gid, delete_install_folder=True)
    assert seen == [str(exe)]


def test_delete_game_from_library_removes_row(db_with_user: tuple[Database, int]) -> None:
    db, uid = db_with_user
    db.upsert_game("Gone", "/games/gone", "/games/gone/g.exe")
    gid = db.list_games(uid)[0].id
    name = delete_game_from_library(db, gid)
    assert name == "Gone"
    assert db.list_games(uid) == []


def test_delete_game_install_folder(tmp_path: Path) -> None:
    install = tmp_path / "gal" / "MyGame"
    install.mkdir(parents=True)
    exe = install / "game.exe"
    exe.write_bytes(b"")
    delete_game_install_folder(str(install), str(exe))
    assert not install.exists()


def test_delete_game_from_library_with_install_folder(
    db_with_user: tuple[Database, int], tmp_path: Path
) -> None:
    db, uid = db_with_user
    install = tmp_path / "games" / "gone"
    install.mkdir(parents=True)
    exe = install / "g.exe"
    exe.write_bytes(b"")
    db.upsert_game("Gone", str(install), str(exe))
    gid = db.list_games(uid)[0].id
    delete_game_from_library(db, gid, delete_install_folder=True)
    assert db.list_games(uid) == []
    assert not install.exists()


def test_delete_game_install_folder_rejects_shallow_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import game_delete_service as gds

    monkeypatch.setattr(gds, "_MIN_INSTALL_PATH_PARTS", 20)
    install = tmp_path / "a" / "b"
    install.mkdir(parents=True)
    with pytest.raises(ValueError, match="过短"):
        delete_game_install_folder(str(install), "")


def test_delete_game_from_library_cleans_backup_zip(
    db_with_user: tuple[Database, int], tmp_path: Path
) -> None:
    db, uid = db_with_user
    db.upsert_game("G", "/g", "/g/g.exe")
    gid = db.list_games(uid)[0].id
    zip_path = db.base_dir / "save-backups" / str(uid) / str(gid) / "bak.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    zip_path.write_bytes(b"zip")
    db.insert_save_backup(uid, gid, "test", str(zip_path), zip_path.stat().st_size)
    delete_game_from_library(db, gid)
    assert not zip_path.exists()
