from __future__ import annotations

from pathlib import Path

from app.data.database import Database
from app.services.game_path_migration import apply_migration_plan, build_migration_plan
from app.services.path_utils import normalize_game_dir


def test_merge_duplicate_root_dir_variants(db_with_user: tuple[Database, int], tmp_path: Path) -> None:
    db, uid = db_with_user
    game_dir = tmp_path / "Gal" / "Title"
    game_dir.mkdir(parents=True)
    exe = game_dir / "game.exe"
    exe.write_bytes(b"")

    resolved = normalize_game_dir(game_dir)
    alt = str(game_dir).replace("\\", "/") if "\\" in str(game_dir) else str(game_dir) + "/"
    if alt == resolved:
        alt = str(game_dir) + "\\"

    db.upsert_game("FromScan", resolved, str(exe))
    db.conn.execute(
        """
        INSERT INTO games (name, root_dir, launch_exe, custom_name, created_at, updated_at)
        VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))
        """,
        ("Custom", alt, str(exe), "My Title",),
    )
    db.conn.commit()

    assert len(db.list_games(uid)) == 2

    plan = build_migration_plan(db)
    assert len(plan.merges) == 1
    merge = plan.merges[0]
    assert merge.canonical_root_dir == resolved

    db.set_favorite(uid, merge.duplicate_id, True)
    apply_migration_plan(db, plan)

    games = db.list_games(uid)
    assert len(games) == 1
    assert games[0].name == "My Title"
    assert games[0].root_dir == resolved
    assert games[0].favorite is True


def test_normalize_only_no_duplicates(db_with_user: tuple[Database, int], tmp_path: Path) -> None:
    import os

    db, uid = db_with_user
    game_dir = tmp_path / "only"
    game_dir.mkdir()
    exe = game_dir / "g.exe"
    exe.write_bytes(b"")
    canonical = normalize_game_dir(game_dir)
    stored = game_dir.as_posix()
    if stored == canonical:
        pytest.skip("platform does not produce a separate stored path variant")
    db.conn.execute(
        """
        INSERT INTO games (name, root_dir, launch_exe, created_at, updated_at)
        VALUES (?, ?, ?, datetime('now'), datetime('now'))
        """,
        ("G", stored, str(exe)),
    )
    db.conn.commit()
    plan = build_migration_plan(db)
    assert len(plan.merges) == 0
    assert len(plan.normalize_only) == 1
    apply_migration_plan(db, plan)
    assert db.list_games(uid)[0].root_dir == canonical


def test_dry_run_leaves_db_unchanged(db_with_user: tuple[Database, int], tmp_path: Path) -> None:
    db, uid = db_with_user
    a = tmp_path / "dup"
    a.mkdir()
    exe = a / "g.exe"
    exe.write_bytes(b"")
    r1 = normalize_game_dir(a)
    db.upsert_game("A", r1, str(exe))
    db.conn.execute(
        """
        INSERT INTO games (name, root_dir, launch_exe, created_at, updated_at)
        VALUES ('B', ?, ?, datetime('now'), datetime('now'))
        """,
        (str(a).replace("\\", "/"), str(exe)),
    )
    db.conn.commit()
    before = len(db.list_games(uid))
    build_migration_plan(db)
    assert len(db.list_games(uid)) == before
