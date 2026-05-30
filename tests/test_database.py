from __future__ import annotations

from pathlib import Path

import pytest

from app.data.database import Database, GameRecord, VndbImportRow
from app.services.path_utils import normalize_game_dir


class TestDatabaseInit:
    def test_creates_db_file(self, tmp_path: Path) -> None:
        db = Database(tmp_path / "sub")
        assert (tmp_path / "sub" / "manager.sqlite3").exists()

    def test_ensure_default_user(self, db: Database) -> None:
        uid = db.ensure_default_user()
        assert uid > 0
        uid2 = db.ensure_default_user()
        assert uid2 == uid

    def test_list_users(self, db: Database) -> None:
        db.ensure_default_user()
        users = db.list_users()
        assert len(users) >= 1
        assert users[0][1] == "default"


class TestScanRoots:
    def test_add_and_list(self, db: Database) -> None:
        db.add_scan_root("C:/Games")
        db.add_scan_root("D:/Galgame")
        roots = db.list_scan_roots()
        assert len(roots) == 2
        assert "C:/Games" in roots
        assert "D:/Galgame" in roots

    def test_add_duplicate_ignored(self, db: Database) -> None:
        db.add_scan_root("C:/Games")
        db.add_scan_root("C:/Games")
        assert len(db.list_scan_roots()) == 1

    def test_remove(self, db: Database) -> None:
        db.add_scan_root("C:/Games")
        db.remove_scan_root("C:/Games")
        assert len(db.list_scan_roots()) == 0

    def test_remove_nonexistent_no_error(self, db: Database) -> None:
        db.remove_scan_root("nonexistent")


class TestGameCRUD:
    def test_upsert_and_list(self, db_with_user: tuple[Database, int]) -> None:
        db, uid = db_with_user
        db.upsert_game("TestGame", "/games/test", "/games/test/game.exe", "/cover.jpg")
        games = db.list_games(uid)
        assert len(games) == 1
        assert games[0].name == "TestGame"
        assert games[0].root_dir == normalize_game_dir("/games/test")
        assert games[0].cover_path == "/cover.jpg"

    def test_upsert_update(self, db_with_user: tuple[Database, int]) -> None:
        db, uid = db_with_user
        db.upsert_game("OldName", "/games/test", "/games/test/old.exe")
        db.upsert_game("NewName", "/games/test", "/games/test/new.exe")
        games = db.list_games(uid)
        assert len(games) == 1
        assert games[0].name == "NewName"
        assert games[0].launch_exe == "/games/test/new.exe"

    def test_upsert_preserves_cover_on_conflict(self, db_with_user: tuple[Database, int]) -> None:
        db, uid = db_with_user
        db.upsert_game("Game", "/games/g", "/games/g/g.exe", "/cover1.jpg")
        db.upsert_game("Game", "/games/g", "/games/g/g.exe", None)
        games = db.list_games(uid)
        assert len(games) == 1
        assert games[0].cover_path == "/cover1.jpg"


    def test_upsert_preserves_custom_name_on_conflict(self, db_with_user: tuple[Database, int]) -> None:
        db, uid = db_with_user
        db.upsert_game("AutoName", "/games/g", "/games/g/g.exe")
        games = db.list_games(uid)
        assert games[0].name == "AutoName"
        db.update_game_identity(games[0].id, "MyCustomName", "/games/g/g.exe")
        games = db.list_games(uid)
        assert games[0].name == "MyCustomName"
        db.upsert_game("NewAutoName", "/games/g", "/games/g/g.exe")
        games = db.list_games(uid)
        assert len(games) == 1
        assert games[0].name == "MyCustomName"

    def test_find_game_by_root(self, db_with_user: tuple[Database, int]) -> None:
        db, uid = db_with_user
        db.upsert_game("MyGame", "/games/my", "/games/my/g.exe")
        found = db.find_game_by_root("/games/my")
        assert found is not None
        assert found.name == "MyGame"

    def test_find_game_by_root_not_found(self, db: Database) -> None:
        assert db.find_game_by_root("/nonexistent") is None

    def test_get_game_by_id(self, db_with_user: tuple[Database, int]) -> None:
        db, uid = db_with_user
        db.upsert_game("Game1", "/g1", "/g1/g.exe")
        games = db.list_games(uid)
        gid = games[0].id
        found = db.get_game_by_id(uid, gid)
        assert found is not None
        assert found.name == "Game1"

    def test_get_game_by_id_invalid(self, db_with_user: tuple[Database, int]) -> None:
        db, uid = db_with_user
        assert db.get_game_by_id(uid, -1) is None
        assert db.get_game_by_id(uid, "abc") is None

    def test_delete_game(self, db_with_user: tuple[Database, int]) -> None:
        db, uid = db_with_user
        db.upsert_game("ToDelete", "/games/del", "/games/del/game.exe")
        gid = db.list_games(uid)[0].id
        assert db.delete_game(gid) is True
        assert db.list_games(uid) == []
        assert db.get_game_by_id(uid, gid) is None
        assert db.delete_game(gid) is False
        assert db.delete_game(99999) is False

    def test_list_all_game_dirs(self, db_with_user: tuple[Database, int]) -> None:
        db, uid = db_with_user
        assert db.list_all_game_dirs() == set()
        db.upsert_game("Game1", "/g1", "/g1/g.exe")
        db.upsert_game("Game2", "/g2", "/g2/g.exe")
        dirs = db.list_all_game_dirs()
        assert dirs == {normalize_game_dir("/g1"), normalize_game_dir("/g2")}
    def test_update_game_custom_cover(self, db_with_user: tuple[Database, int]) -> None:
        db, uid = db_with_user
        db.upsert_game("Game", "/g", "/g/g.exe", "/old_cover.jpg")
        games = db.list_games(uid)
        gid = games[0].id
        db.update_game_custom_cover(gid, "/custom_cover.jpg")
        updated = db.get_game_by_id(uid, gid)
        assert updated is not None
        assert updated.cover_path == "/custom_cover.jpg"

    def test_update_game_cover_path_preserves_custom(self, db_with_user: tuple[Database, int]) -> None:
        db, uid = db_with_user
        db.upsert_game("Game", "/g", "/g/g.exe", "/scan_cover.jpg")
        games = db.list_games(uid)
        gid = games[0].id
        db.update_game_custom_cover(gid, "/custom.jpg")
        db.update_game_cover_path(gid, "/new_scan.jpg")
        updated = db.get_game_by_id(uid, gid)
        assert updated is not None
        assert updated.cover_path == "/custom.jpg"

    def test_delete_games_not_in_scan(self, db_with_user: tuple[Database, int]) -> None:
        db, uid = db_with_user
        db.upsert_game("Keep", "/games/keep", "/games/keep/g.exe")
        db.upsert_game("Remove", "/games/remove", "/games/remove/g.exe")
        deleted = db.delete_games_not_in_scan(["/games"], {"/games/keep"})
        assert deleted == 1
        games = db.list_games(uid)
        assert len(games) == 1
        assert games[0].name == "Keep"

    def test_delete_games_not_in_scan_preserves_custom_name(self, db_with_user: tuple[Database, int]) -> None:
        db, uid = db_with_user
        db.upsert_game("AutoName1", "/games/keep", "/games/keep/g.exe")
        db.upsert_game("AutoName2", "/games/remove", "/games/remove/g.exe")
        games = db.list_games(uid)
        assert len(games) == 2
        # 找到 "/games/keep" 并设置 custom_name
        for game in games:
            if normalize_game_dir(game.root_dir) == normalize_game_dir("/games/keep"):
                db.update_game_identity(game.id, "MyCustomName", "/games/keep/g.exe")
                break
        # 现在 delete_games_not_in_scan 应该只删除没有 custom_name 的那个
        deleted = db.delete_games_not_in_scan(["/games"], {"/games/keep"})
        # 因为 "/games/remove" 不在 valid_game_dirs 中，且没有 custom_name，应该被删除
        assert deleted == 1
        games = db.list_games(uid)
        assert len(games) == 1
        assert games[0].name == "MyCustomName"

    def test_clear_all_games(self, db_with_user: tuple[Database, int]) -> None:
        db, uid = db_with_user
        db.upsert_game("A", "/a", "/a/a.exe")
        db.upsert_game("B", "/b", "/b/b.exe")
        count = db.clear_all_games()
        assert count == 2
        assert len(db.list_games(uid)) == 0

    def test_clear_all_games_preserves_custom_name(self, db_with_user: tuple[Database, int]) -> None:
        db, uid = db_with_user
        db.upsert_game("AutoName1", "/a", "/a/a.exe")
        db.upsert_game("AutoName2", "/b", "/b/b.exe")
        games = db.list_games(uid)
        assert len(games) == 2
        # 给其中一个设置 custom_name
        gid = games[0].id
        db.update_game_identity(gid, "MyCustomName", "/a/a.exe")
        # clear_all_games 应该只删除没有 custom_name 的那个
        count = db.clear_all_games()
        assert count == 1
        games = db.list_games(uid)
        assert len(games) == 1
        assert games[0].name == "MyCustomName"


class TestUniqueness:
    def test_root_dir_unique_constraint(self, db_with_user: tuple[Database, int]) -> None:
        db, uid = db_with_user
        db.upsert_game("Game1", "/same/root", "/same/root/g1.exe")
        db.upsert_game("Game2", "/same/root", "/same/root/g2.exe")
        games = db.list_games(uid)
        assert len(games) == 1
        assert games[0].name == "Game2"

    def test_batch_upsert_dedup_by_root(self, db_with_user: tuple[Database, int]) -> None:
        db, uid = db_with_user
        rows = [
            VndbImportRow("A", "/root/a", "/root/a/a.exe", None, None, None, None, None, None, None, None, None, None),
            VndbImportRow("A2", "/root/a", "/root/a/a2.exe", None, None, None, None, None, None, None, None, None, None),
        ]
        db.upsert_games_batch(rows)
        games = db.list_games(uid)
        assert len(games) == 1
        assert games[0].name == "A2"


class TestBatchUpsert:
    def test_upsert_games_batch(self, db_with_user: tuple[Database, int]) -> None:
        db, uid = db_with_user
        rows = [
            VndbImportRow("Game1", "/g1", "/g1/g.exe", "v1", "Title1", None, None, 8.5, "win", "ja", "http://img/1.jpg", None, None),
            VndbImportRow("Game2", "/g2", "/g2/g.exe", "v2", "Title2", None, None, 7.0, "win", "en", "http://img/2.jpg", None, None),
        ]
        count = db.upsert_games_batch(rows)
        assert count == 2
        games = db.list_games(uid)
        assert len(games) == 2
        by_root = {normalize_game_dir(g.root_dir): g for g in games}
        assert by_root[normalize_game_dir("/g1")].vndb_id == "v1"
        assert by_root[normalize_game_dir("/g2")].rating == 7.0

    def test_upsert_games_batch_empty(self, db: Database) -> None:
        assert db.upsert_games_batch([]) == 0


class TestFavorites:
    def test_set_and_unset_favorite(self, db_with_user: tuple[Database, int]) -> None:
        db, uid = db_with_user
        db.upsert_game("Game", "/g", "/g/g.exe")
        games = db.list_games(uid)
        gid = games[0].id
        db.set_favorite(uid, gid, True)
        assert db.get_game_by_id(uid, gid).favorite is True
        db.set_favorite(uid, gid, False)
        assert db.get_game_by_id(uid, gid).favorite is False


class TestPlayRecords:
    def test_record_and_list(self, db_with_user: tuple[Database, int]) -> None:
        db, uid = db_with_user
        db.upsert_game("Game", "/g", "/g/g.exe")
        gid = db.list_games(uid)[0].id
        db.record_play(uid, gid, 3600)
        records = db.list_play_records(uid, gid)
        assert len(records) == 1
        assert records[0].duration_seconds == 3600

    def test_delete_play_records_by_ids(self, db_with_user: tuple[Database, int]) -> None:
        db, uid = db_with_user
        db.upsert_game("Game", "/g", "/g/g.exe")
        gid = db.list_games(uid)[0].id
        db.record_play(uid, gid, 100)
        db.record_play(uid, gid, 200)
        records = db.list_play_records(uid, gid)
        ids = [r.id for r in records]
        deleted = db.delete_play_records_by_ids(uid, ids)
        assert deleted == 2
        assert len(db.list_play_records(uid, gid)) == 0

    def test_delete_all_play_records(self, db_with_user: tuple[Database, int]) -> None:
        db, uid = db_with_user
        db.upsert_game("Game", "/g", "/g/g.exe")
        gid = db.list_games(uid)[0].id
        db.record_play(uid, gid, 100)
        db.record_play(uid, gid, 200)
        count = db.delete_all_play_records(uid)
        assert count == 2


class TestCategories:
    def test_create_and_list(self, db_with_user: tuple[Database, int]) -> None:
        db, uid = db_with_user
        db.create_category(uid, "RPG")
        db.create_category(uid, "ADV")
        cats = db.list_categories(uid)
        assert len(cats) == 2
        names = [c[1] for c in cats]
        assert "RPG" in names
        assert "ADV" in names

    def test_duplicate_category_ignored(self, db_with_user: tuple[Database, int]) -> None:
        db, uid = db_with_user
        db.create_category(uid, "RPG")
        db.create_category(uid, "RPG")
        assert len(db.list_categories(uid)) == 1

    def test_assign_categories_to_game(self, db_with_user: tuple[Database, int]) -> None:
        db, uid = db_with_user
        db.upsert_game("Game", "/g", "/g/g.exe")
        gid = db.list_games(uid)[0].id
        c1 = db.create_category(uid, "RPG")
        c2 = db.create_category(uid, "ADV")
        db.assign_categories(gid, [c1, c2])
        game = db.get_game_by_id(uid, gid)
        cats = game.categories.split(",")
        assert "RPG" in cats
        assert "ADV" in cats


class TestSettings:
    def test_cover_fetch_mode(self, db: Database) -> None:
        assert db.get_cover_fetch_mode() == "local_prefer"
        db.set_cover_fetch_mode("online_prefer")
        assert db.get_cover_fetch_mode() == "online_prefer"
        db.set_cover_fetch_mode("invalid_mode")
        assert db.get_cover_fetch_mode() == "local_prefer"

    def test_disabled_plugins(self, db: Database) -> None:
        assert db.get_disabled_plugins() == []
        db.set_disabled_plugins(["plugin_a", "plugin_b"])
        result = db.get_disabled_plugins()
        assert set(result) == {"plugin_a", "plugin_b"}

    def test_plugin_configs(self, db: Database) -> None:
        assert db.get_plugin_configs() == {}
        db.set_plugin_config("demo", {"key": "value"})
        assert db.get_plugin_config("demo") == {"key": "value"}

    def test_auto_backup_before_launch(self, db: Database) -> None:
        assert db.get_auto_backup_before_launch() is False
        db.set_auto_backup_before_launch(True)
        assert db.get_auto_backup_before_launch() is True


class TestMigration:
    def test_new_columns_exist_after_init(self, db: Database) -> None:
        cols = {
            str(row["name"])
            for row in db.conn.execute("PRAGMA table_info(games)").fetchall()
        }
        for col in (
            "vndb_id", "title_original", "title_localized", "description",
            "rating", "platforms", "languages", "image_url", "screenshots_json",
            "source", "custom_name", "custom_launch_exe", "custom_cover_path",
            "custom_save_root",
        ):
            assert col in cols, f"missing column: {col}"

    def test_settings_columns_exist(self, db: Database) -> None:
        cols = {
            str(row["name"])
            for row in db.conn.execute("PRAGMA table_info(settings)").fetchall()
        }
        for col in (
            "plugin_disabled_names", "cover_fetch_mode",
            "locale_emulator_leproc_path", "auto_backup_before_launch",
            "twodfan_hints_db_path",
        ):
            assert col in cols, f"missing column: {col}"

    def test_save_backups_table_exists(self, db: Database) -> None:
        cols = {
            str(row["name"])
            for row in db.conn.execute("PRAGMA table_info(save_backups)").fetchall()
        }
        assert "checksum_sha256" in cols


class TestSaveBackups:
    def test_insert_and_list(self, db_with_user: tuple[Database, int]) -> None:
        db, uid = db_with_user
        db.upsert_game("Game", "/g", "/g/g.exe")
        gid = db.list_games(uid)[0].id
        bid = db.insert_save_backup(uid, gid, "测试备份", "/backups/test.zip", 1024, checksum_sha256="abc123")
        assert bid > 0
        backups = db.list_save_backups(uid, gid)
        assert len(backups) == 1
        assert backups[0].label == "测试备份"
        assert backups[0].checksum_sha256 == "abc123"

    def test_update_label(self, db_with_user: tuple[Database, int]) -> None:
        db, uid = db_with_user
        db.upsert_game("Game", "/g", "/g/g.exe")
        gid = db.list_games(uid)[0].id
        bid = db.insert_save_backup(uid, gid, "old", "/b.zip", 100)
        ok = db.update_save_backup_label(uid, bid, "new")
        assert ok is True
        backups = db.list_save_backups(uid, gid)
        assert backups[0].label == "new"

    def test_delete(self, db_with_user: tuple[Database, int]) -> None:
        db, uid = db_with_user
        db.upsert_game("Game", "/g", "/g/g.exe")
        gid = db.list_games(uid)[0].id
        bid = db.insert_save_backup(uid, gid, "del", "/del.zip", 50)
        zp = db.delete_save_backup_row(uid, bid)
        assert zp == "/del.zip"
        assert len(db.list_save_backups(uid, gid)) == 0
