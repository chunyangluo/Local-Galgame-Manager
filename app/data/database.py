from __future__ import annotations

import sqlite3
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


@dataclass
class GameRecord:
    id: int
    name: str
    root_dir: str
    launch_exe: str
    cover_path: str | None
    favorite: bool
    categories: str
    last_played_at: str | None
    play_count: int
    total_play_seconds: int
    vndb_id: str | None = None
    title_original: str | None = None
    title_localized: str | None = None
    description: str | None = None
    rating: float | None = None
    platforms: str | None = None
    languages: str | None = None
    image_url: str | None = None
    screenshots_json: str | None = None
    source: str | None = None
    custom_save_root: str | None = None
    window_title: str | None = None


@dataclass
class SaveBackupRecord:
    """User-created or auto restore-guard save archive."""

    id: int
    user_id: int
    game_id: int
    label: str
    zip_path: str
    created_at: str
    size_bytes: int
    checksum_sha256: str | None = None


@dataclass
class PlayRecordEntry:
    """Single play session row for a user + game."""

    id: int
    started_at: str
    ended_at: str | None
    duration_seconds: int


@dataclass
class PlayHistoryRow:
    """One play session joined with display name and cover (for global history UI)."""

    record_id: int
    game_id: int
    game_name: str
    cover_path: str | None
    image_url: str | None
    started_at: str
    ended_at: str | None
    duration_seconds: int


@dataclass
class VndbImportRow:
    """Container for a single VNDB import write."""

    name: str
    root_dir: str
    launch_exe: str
    vndb_id: str | None
    title_original: str | None
    title_localized: str | None
    description: str | None
    rating: float | None
    platforms: str | None
    languages: str | None
    image_url: str | None
    screenshots_json: str | None
    cover_path: str | None
    source: str = "vndb"


class Database:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.base_dir / "manager.sqlite3"
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def close(self) -> None:
        """Close the SQLite connection (e.g. before replacing the DB file on disk)."""
        if self.conn is not None:
            self.conn.close()
            self.conn = None  # type: ignore[assignment]

    def reopen(self) -> None:
        """Re-open the database after the file on disk was replaced."""
        if self.conn is not None:
            return
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def _create_tables(self) -> None:
        self.conn.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                last_login_at TEXT
            );

            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                current_user_id INTEGER,
                auto_scan_on_startup INTEGER DEFAULT 1,
                minimize_to_tray INTEGER DEFAULT 1,
                run_on_startup INTEGER DEFAULT 0,
                startup_scan_roots TEXT DEFAULT '[]',
                ui_preferences TEXT DEFAULT '{}',
                updated_at TEXT NOT NULL,
                FOREIGN KEY(current_user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                root_dir TEXT NOT NULL,
                launch_exe TEXT NOT NULL,
                custom_name TEXT,
                custom_launch_exe TEXT,
                custom_cover_path TEXT,
                cover_path TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(root_dir)
            );

            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, name),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS game_categories (
                game_id INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                PRIMARY KEY(game_id, category_id),
                FOREIGN KEY(game_id) REFERENCES games(id) ON DELETE CASCADE,
                FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS favorites (
                user_id INTEGER NOT NULL,
                game_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(user_id, game_id),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(game_id) REFERENCES games(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS play_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                game_id INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                duration_seconds INTEGER DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(game_id) REFERENCES games(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS scan_roots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            "INSERT OR IGNORE INTO settings (id, updated_at) VALUES (1, ?)", (now,)
        )
        self._ensure_games_columns()
        self._ensure_settings_columns()
        self._ensure_save_backup_schema()
        self.conn.commit()

    def _ensure_games_columns(self) -> None:
        cols = {
            str(row["name"])
            for row in self.conn.execute("PRAGMA table_info(games)").fetchall()
        }
        if "custom_name" not in cols:
            self.conn.execute("ALTER TABLE games ADD COLUMN custom_name TEXT")
        if "custom_launch_exe" not in cols:
            self.conn.execute("ALTER TABLE games ADD COLUMN custom_launch_exe TEXT")
        if "custom_cover_path" not in cols:
            self.conn.execute("ALTER TABLE games ADD COLUMN custom_cover_path TEXT")
        vndb_columns = {
            "vndb_id": "TEXT",
            "title_original": "TEXT",
            "title_localized": "TEXT",
            "description": "TEXT",
            "rating": "REAL",
            "platforms": "TEXT",
            "languages": "TEXT",
            "image_url": "TEXT",
            "screenshots_json": "TEXT",
            "source": "TEXT",
        }
        for col_name, col_type in vndb_columns.items():
            if col_name not in cols:
                self.conn.execute(
                    f"ALTER TABLE games ADD COLUMN {col_name} {col_type}"
                )
        self._promote_legacy_custom_covers()
        # Index on vndb_id for quick idempotent lookups.
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_games_vndb_id ON games(vndb_id)"
        )
        if "custom_save_root" not in cols:
            self.conn.execute("ALTER TABLE games ADD COLUMN custom_save_root TEXT")
        if "window_title" not in cols:
            self.conn.execute("ALTER TABLE games ADD COLUMN window_title TEXT")

    def _ensure_save_backup_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS save_backups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                game_id INTEGER NOT NULL,
                label TEXT NOT NULL,
                zip_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                size_bytes INTEGER NOT NULL DEFAULT 0,
                checksum_sha256 TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(game_id) REFERENCES games(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_save_backups_user_game
            ON save_backups(user_id, game_id);
            """
        )
        cols = {
            str(row["name"])
            for row in self.conn.execute("PRAGMA table_info(save_backups)").fetchall()
        }
        if "checksum_sha256" not in cols:
            self.conn.execute("ALTER TABLE save_backups ADD COLUMN checksum_sha256 TEXT")

    def _promote_legacy_custom_covers(self) -> None:
        """Promote old user-imported covers to custom override field.

        Older versions stored manually imported covers directly in `cover_path`
        (usually as `<covers>/<game_id>.<ext>`), which could be overwritten by
        scan/VNDB updates. Promote those rows once so manual covers keep highest
        priority permanently.
        """
        rows = self.conn.execute(
            """
            SELECT id, cover_path
            FROM games
            WHERE (custom_cover_path IS NULL OR custom_cover_path = '')
              AND cover_path IS NOT NULL
              AND cover_path != ''
            """
        ).fetchall()
        updates: list[tuple[str, int]] = []
        for row in rows:
            game_id = int(row["id"])
            cover_path = str(row["cover_path"])
            normalized = cover_path.replace("\\", "/").lower()
            if f"/covers/{game_id}." in normalized:
                updates.append((cover_path, game_id))
        if updates:
            self.conn.executemany(
                "UPDATE games SET custom_cover_path = ? WHERE id = ?",
                updates,
            )

    def _ensure_settings_columns(self) -> None:
        cols = {
            str(row["name"])
            for row in self.conn.execute("PRAGMA table_info(settings)").fetchall()
        }
        if "plugin_disabled_names" not in cols:
            self.conn.execute(
                "ALTER TABLE settings ADD COLUMN plugin_disabled_names TEXT DEFAULT '[]'"
            )
        if "cover_fetch_mode" not in cols:
            self.conn.execute(
                "ALTER TABLE settings ADD COLUMN cover_fetch_mode TEXT DEFAULT 'local_prefer'"
            )
        if "locale_emulator_leproc_path" not in cols:
            self.conn.execute(
                "ALTER TABLE settings ADD COLUMN locale_emulator_leproc_path TEXT DEFAULT ''"
            )
        if "auto_backup_before_launch" not in cols:
            self.conn.execute(
                "ALTER TABLE settings ADD COLUMN auto_backup_before_launch INTEGER DEFAULT 0"
            )
        if "ui_preferences" not in cols:
            self.conn.execute(
                "ALTER TABLE settings ADD COLUMN ui_preferences TEXT DEFAULT '{}'"
            )
        if "twodfan_hints_db_path" not in cols:
            self.conn.execute(
                "ALTER TABLE settings ADD COLUMN twodfan_hints_db_path TEXT DEFAULT ''"
            )
        if "double_click_action" not in cols:
            self.conn.execute(
                "ALTER TABLE settings ADD COLUMN double_click_action TEXT DEFAULT 'normal'"
            )
        if "last_launch_mode" not in cols:
            self.conn.execute(
                "ALTER TABLE settings ADD COLUMN last_launch_mode TEXT DEFAULT ''"
            )
        if "plugin_configs" not in cols:
            self.conn.execute(
                "ALTER TABLE settings ADD COLUMN plugin_configs TEXT DEFAULT '{}'"
            )
        if "search_history" not in cols:
            self.conn.execute(
                "ALTER TABLE settings ADD COLUMN search_history TEXT DEFAULT '[]'"
            )

    def get_plugin_configs(self) -> dict[str, dict]:
        row = self.conn.execute(
            "SELECT plugin_configs FROM settings WHERE id = 1"
        ).fetchone()
        if row is None or row["plugin_configs"] is None:
            return {}
        try:
            value = json.loads(str(row["plugin_configs"]))
        except json.JSONDecodeError:
            return {}
        if not isinstance(value, dict):
            return {}
        out: dict[str, dict] = {}
        for key, val in value.items():
            if isinstance(val, dict):
                out[str(key)] = dict(val)
        return out

    def set_plugin_configs(self, configs: dict[str, dict]) -> None:
        payload = json.dumps(configs, ensure_ascii=False)
        self.conn.execute(
            "UPDATE settings SET plugin_configs = ?, updated_at = ? WHERE id = 1",
            (payload, datetime.utcnow().isoformat()),
        )
        self.conn.commit()

    def get_plugin_config(self, plugin_name: str) -> dict:
        return dict(self.get_plugin_configs().get(plugin_name) or {})

    def set_plugin_config(self, plugin_name: str, config: dict) -> None:
        all_cfg = self.get_plugin_configs()
        all_cfg[plugin_name] = dict(config)
        self.set_plugin_configs(all_cfg)

    def ensure_default_user(self) -> int:
        row = self.conn.execute("SELECT current_user_id FROM settings WHERE id = 1").fetchone()
        if row and row["current_user_id"]:
            return int(row["current_user_id"])
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            "INSERT OR IGNORE INTO users (username, created_at, last_login_at) VALUES (?, ?, ?)",
            ("default", now, now),
        )
        user = self.conn.execute("SELECT id FROM users WHERE username = ?", ("default",)).fetchone()
        user_id = int(user["id"])
        self.conn.execute(
            "UPDATE settings SET current_user_id = ?, updated_at = ? WHERE id = 1",
            (user_id, now),
        )
        self.conn.commit()
        return user_id

    def list_users(self) -> list[tuple[int, str]]:
        rows = self.conn.execute("SELECT id, username FROM users ORDER BY created_at").fetchall()
        return [(int(r["id"]), str(r["username"])) for r in rows]

    def create_user(self, username: str) -> int:
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            "INSERT INTO users (username, created_at, last_login_at) VALUES (?, ?, ?)",
            (username, now, now),
        )
        self.conn.commit()
        row = self.conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        return int(row["id"])

    def switch_user(self, user_id: int) -> None:
        now = datetime.utcnow().isoformat()
        self.conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now, user_id))
        self.conn.execute(
            "UPDATE settings SET current_user_id = ?, updated_at = ? WHERE id = 1",
            (user_id, now),
        )
        self.conn.commit()

    def get_disabled_plugins(self) -> list[str]:
        row = self.conn.execute(
            "SELECT plugin_disabled_names FROM settings WHERE id = 1"
        ).fetchone()
        if row is None:
            return []
        raw = row["plugin_disabled_names"]
        if raw is None:
            return []
        try:
            value = json.loads(str(raw))
        except json.JSONDecodeError:
            return []
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if str(item).strip()]

    def set_disabled_plugins(self, names: list[str]) -> None:
        normalized = sorted({name.strip() for name in names if name.strip()})
        self.conn.execute(
            "UPDATE settings SET plugin_disabled_names = ?, updated_at = ? WHERE id = 1",
            (json.dumps(normalized, ensure_ascii=False), datetime.utcnow().isoformat()),
        )
        self.conn.commit()

    def get_cover_fetch_mode(self) -> str:
        row = self.conn.execute(
            "SELECT cover_fetch_mode FROM settings WHERE id = 1"
        ).fetchone()
        if row is None:
            return "local_prefer"
        mode = str(row["cover_fetch_mode"] or "local_prefer").strip().lower()
        if mode not in {"local_only", "local_prefer", "online_prefer"}:
            return "local_prefer"
        return mode

    def set_cover_fetch_mode(self, mode: str) -> None:
        normalized = mode.strip().lower()
        if normalized not in {"local_only", "local_prefer", "online_prefer"}:
            normalized = "local_prefer"
        self.conn.execute(
            "UPDATE settings SET cover_fetch_mode = ?, updated_at = ? WHERE id = 1",
            (normalized, datetime.utcnow().isoformat()),
        )
        self.conn.commit()

    def get_locale_emulator_leproc_path(self) -> str:
        row = self.conn.execute(
            "SELECT locale_emulator_leproc_path FROM settings WHERE id = 1"
        ).fetchone()
        if row is None or row["locale_emulator_leproc_path"] is None:
            return ""
        return str(row["locale_emulator_leproc_path"]).strip()

    def set_locale_emulator_leproc_path(self, path: str) -> None:
        normalized = path.strip()
        self.conn.execute(
            "UPDATE settings SET locale_emulator_leproc_path = ?, updated_at = ? WHERE id = 1",
            (normalized, datetime.utcnow().isoformat()),
        )
        self.conn.commit()

    def get_auto_backup_before_launch(self) -> bool:
        row = self.conn.execute(
            "SELECT auto_backup_before_launch FROM settings WHERE id = 1"
        ).fetchone()
        if row is None:
            return False
        try:
            return bool(int(row["auto_backup_before_launch"] or 0))
        except (TypeError, ValueError):
            return False

    def set_auto_backup_before_launch(self, enabled: bool) -> None:
        self.conn.execute(
            "UPDATE settings SET auto_backup_before_launch = ?, updated_at = ? WHERE id = 1",
            (1 if enabled else 0, datetime.utcnow().isoformat()),
        )
        self.conn.commit()

    def get_twodfan_hints_db_path(self) -> str:
        row = self.conn.execute(
            "SELECT twodfan_hints_db_path FROM settings WHERE id = 1"
        ).fetchone()
        if row is None or row["twodfan_hints_db_path"] is None:
            return ""
        return str(row["twodfan_hints_db_path"]).strip()

    def set_twodfan_hints_db_path(self, path: str) -> None:
        normalized = path.strip()
        self.conn.execute(
            "UPDATE settings SET twodfan_hints_db_path = ?, updated_at = ? WHERE id = 1",
            (normalized, datetime.utcnow().isoformat()),
        )
        self.conn.commit()

    def get_double_click_action(self) -> str:
        """获取双击打开游戏的方式: normal/force_le/smart"""
        row = self.conn.execute(
            "SELECT double_click_action FROM settings WHERE id = 1"
        ).fetchone()
        if row is None or row["double_click_action"] is None:
            return "normal"
        return str(row["double_click_action"]).strip().lower()

    def set_double_click_action(self, action: str) -> None:
        """设置双击打开游戏的方式: normal/force_le/smart"""
        valid_actions = ("normal", "force_le", "smart")
        if action not in valid_actions:
            action = "normal"
        self.conn.execute(
            "UPDATE settings SET double_click_action = ?, updated_at = ? WHERE id = 1",
            (action, datetime.utcnow().isoformat()),
        )
        self.conn.commit()

    def get_last_launch_mode(self) -> str:
        """获取上一次启动游戏的方式: normal/le"""
        row = self.conn.execute(
            "SELECT last_launch_mode FROM settings WHERE id = 1"
        ).fetchone()
        if row is None or row["last_launch_mode"] is None:
            return "normal"
        return str(row["last_launch_mode"]).strip().lower()

    def set_last_launch_mode(self, mode: str) -> None:
        """设置上一次启动游戏的方式: normal/le"""
        valid_modes = ("normal", "le")
        if mode not in valid_modes:
            mode = "normal"
        self.conn.execute(
            "UPDATE settings SET last_launch_mode = ?, updated_at = ? WHERE id = 1",
            (mode, datetime.utcnow().isoformat()),
        )
        self.conn.commit()

    def get_ui_preferences(self) -> dict:
        row = self.conn.execute(
            "SELECT ui_preferences FROM settings WHERE id = 1"
        ).fetchone()
        if row is None or row["ui_preferences"] is None:
            return {}
        try:
            import json
            return json.loads(str(row["ui_preferences"]))
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_ui_preferences(self, preferences: dict) -> None:
        import json
        preferences_json = json.dumps(preferences)
        self.conn.execute(
            "UPDATE settings SET ui_preferences = ?, updated_at = ? WHERE id = 1",
            (preferences_json, datetime.utcnow().isoformat()),
        )
        self.conn.commit()

    def get_search_history(self) -> list[str]:
        row = self.conn.execute(
            "SELECT search_history FROM settings WHERE id = 1"
        ).fetchone()
        if row is None or row["search_history"] is None:
            return []
        try:
            value = json.loads(str(row["search_history"]))
        except (json.JSONDecodeError, TypeError):
            return []
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if str(item).strip()]

    def add_search_history(self, term: str, *, limit: int = 15) -> list[str]:
        normalized = term.strip()
        if not normalized:
            return self.get_search_history()
        history = [h for h in self.get_search_history() if h.lower() != normalized.lower()]
        history.insert(0, normalized)
        history = history[:limit]
        self.conn.execute(
            "UPDATE settings SET search_history = ?, updated_at = ? WHERE id = 1",
            (json.dumps(history, ensure_ascii=False), datetime.utcnow().isoformat()),
        )
        self.conn.commit()
        return history

    def clear_search_history(self) -> None:
        self.conn.execute(
            "UPDATE settings SET search_history = '[]', updated_at = ? WHERE id = 1",
            (datetime.utcnow().isoformat(),),
        )
        self.conn.commit()

    def add_scan_root(self, path: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO scan_roots (path, created_at) VALUES (?, ?)",
            (path, datetime.utcnow().isoformat()),
        )
        self.conn.commit()

    def remove_scan_root(self, path: str) -> None:
        self.conn.execute("DELETE FROM scan_roots WHERE path = ?", (path,))
        self.conn.commit()

    def list_scan_roots(self) -> list[str]:
        rows = self.conn.execute("SELECT path FROM scan_roots ORDER BY created_at DESC").fetchall()
        return [str(r["path"]) for r in rows]

    def upsert_game(self, name: str, root_dir: str, launch_exe: str, cover_path: str | None = None) -> None:
        from app.services.path_utils import normalize_game_dir

        root_dir = normalize_game_dir(root_dir)
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            """
            INSERT INTO games (name, root_dir, launch_exe, cover_path, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(root_dir) DO UPDATE SET
                name = COALESCE(NULLIF(games.custom_name, ''), excluded.name),
                launch_exe = COALESCE(NULLIF(games.custom_launch_exe, ''), excluded.launch_exe),
                cover_path = COALESCE(NULLIF(games.custom_cover_path, ''), COALESCE(excluded.cover_path, games.cover_path)),
                updated_at = excluded.updated_at
            """,
            (name, root_dir, launch_exe, cover_path, now, now),
        )
        self.conn.commit()

    def upsert_games_batch(self, rows: list["VndbImportRow"]) -> int:
        """Bulk-write VNDB-enriched rows in a single transaction.

        Returns the number of records written.
        """
        if not rows:
            return 0
        from app.services.path_utils import normalize_game_dir

        now = datetime.utcnow().isoformat()
        payload = [
            (
                row.name,
                normalize_game_dir(row.root_dir),
                row.launch_exe,
                row.cover_path,
                row.vndb_id,
                row.title_original,
                row.title_localized,
                row.description,
                row.rating,
                row.platforms,
                row.languages,
                row.image_url,
                row.screenshots_json,
                row.source or "vndb",
                now,
                now,
            )
            for row in rows
        ]
        with self.conn:
            self.conn.executemany(
                """
                INSERT INTO games (
                    name, root_dir, launch_exe, cover_path,
                    vndb_id, title_original, title_localized, description,
                    rating, platforms, languages, image_url, screenshots_json,
                    source, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(root_dir) DO UPDATE SET
                    name = COALESCE(NULLIF(games.custom_name, ''), excluded.name),
                    launch_exe = COALESCE(NULLIF(games.custom_launch_exe, ''), excluded.launch_exe),
                    cover_path = COALESCE(NULLIF(games.custom_cover_path, ''), COALESCE(excluded.cover_path, games.cover_path)),
                    vndb_id = COALESCE(excluded.vndb_id, games.vndb_id),
                    title_original = COALESCE(excluded.title_original, games.title_original),
                    title_localized = COALESCE(excluded.title_localized, games.title_localized),
                    description = COALESCE(excluded.description, games.description),
                    rating = COALESCE(excluded.rating, games.rating),
                    platforms = COALESCE(excluded.platforms, games.platforms),
                    languages = COALESCE(excluded.languages, games.languages),
                    image_url = COALESCE(excluded.image_url, games.image_url),
                    screenshots_json = COALESCE(excluded.screenshots_json, games.screenshots_json),
                    source = excluded.source,
                    updated_at = excluded.updated_at
                """,
                payload,
            )
        return len(payload)

    def find_game_by_root(self, root_dir: str) -> GameRecord | None:
        from app.services.path_utils import normalize_game_dir

        root_dir = normalize_game_dir(root_dir)
        row = self.conn.execute(
            """
            SELECT
                g.id,
                COALESCE(
                    NULLIF(g.custom_name, ''),
                    NULLIF(g.window_title, ''),
                    NULLIF(g.title_localized, ''),
                    NULLIF(g.title_original, ''),
                    g.name
                ) AS name,
                g.root_dir,
                COALESCE(NULLIF(g.custom_launch_exe, ''), g.launch_exe) AS launch_exe,
                COALESCE(NULLIF(g.custom_cover_path, ''), g.cover_path) AS cover_path,
                g.vndb_id,
                g.title_original,
                g.title_localized,
                g.description,
                g.rating,
                g.platforms,
                g.languages,
                g.image_url,
                g.screenshots_json,
                g.source,
                NULLIF(TRIM(g.custom_save_root), '') AS custom_save_root,
                g.window_title
            FROM games g
            WHERE g.root_dir = ?
            """,
            (root_dir,),
        ).fetchone()
        if row is None:
            return None
        return GameRecord(
            id=int(row["id"]),
            name=str(row["name"]),
            root_dir=str(row["root_dir"]),
            launch_exe=str(row["launch_exe"]),
            cover_path=row["cover_path"],
            favorite=False,
            categories="",
            last_played_at=None,
            play_count=0,
            total_play_seconds=0,
            vndb_id=row["vndb_id"],
            title_original=row["title_original"],
            title_localized=row["title_localized"],
            description=row["description"],
            rating=float(row["rating"]) if row["rating"] is not None else None,
            platforms=row["platforms"],
            languages=row["languages"],
            image_url=row["image_url"],
            screenshots_json=row["screenshots_json"],
            source=row["source"],
            custom_save_root=row["custom_save_root"],
            window_title=row["window_title"],
        )

    def update_game_identity(self, game_id: int, name: str, launch_exe: str) -> None:
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            """
            UPDATE games
            SET custom_name = ?, custom_launch_exe = ?, updated_at = ?
            WHERE id = ?
            """,
            (name, launch_exe, now, game_id),
        )
        self.conn.commit()

    def update_game_custom_cover(self, game_id: int, cover_path: str) -> None:
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            """
            UPDATE games
            SET custom_cover_path = ?, updated_at = ?
            WHERE id = ?
            """,
            (cover_path, now, game_id),
        )
        self.conn.commit()

    def update_game_cover_path(self, game_id: int, cover_path: str) -> None:
        """Update non-custom cover cache path.

        This never touches custom_cover_path, so user overrides remain highest
        priority across scans and VNDB refreshes.
        """
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            """
            UPDATE games
            SET cover_path = ?, updated_at = ?
            WHERE id = ?
            """,
            (cover_path, now, game_id),
        )
        self.conn.commit()

    def list_games(self, user_id: int) -> list[GameRecord]:
        rows = self.conn.execute(
            """
            SELECT
                g.id,
                COALESCE(
                    NULLIF(g.custom_name, ''),
                    NULLIF(g.window_title, ''),
                    NULLIF(g.title_localized, ''),
                    NULLIF(g.title_original, ''),
                    g.name
                ) AS name,
                g.root_dir,
                COALESCE(NULLIF(g.custom_launch_exe, ''), g.launch_exe) AS launch_exe,
                COALESCE(NULLIF(g.custom_cover_path, ''), g.cover_path) AS cover_path,
                g.vndb_id,
                g.title_original,
                g.title_localized,
                g.description,
                g.rating,
                g.platforms,
                g.languages,
                g.image_url,
                g.screenshots_json,
                g.source,
                NULLIF(TRIM(g.custom_save_root), '') AS custom_save_root,
                g.window_title,
                CASE WHEN f.game_id IS NULL THEN 0 ELSE 1 END AS favorite,
                COALESCE(GROUP_CONCAT(c.name, ','), '') AS categories,
                MAX(p.started_at) AS last_played_at,
                COALESCE(COUNT(p.id), 0) AS play_count,
                COALESCE(SUM(p.duration_seconds), 0) AS total_play_seconds
            FROM games g
            LEFT JOIN favorites f ON f.game_id = g.id AND f.user_id = ?
            LEFT JOIN game_categories gc ON gc.game_id = g.id
            LEFT JOIN categories c ON c.id = gc.category_id AND c.user_id = ?
            LEFT JOIN play_records p ON p.game_id = g.id AND p.user_id = ?
            GROUP BY g.id
            ORDER BY g.updated_at DESC
            """,
            (user_id, user_id, user_id),
        ).fetchall()
        return [
            GameRecord(
                id=int(r["id"]),
                name=str(r["name"]),
                root_dir=str(r["root_dir"]),
                launch_exe=str(r["launch_exe"]),
                cover_path=r["cover_path"],
                favorite=bool(r["favorite"]),
                categories=str(r["categories"]),
                last_played_at=r["last_played_at"],
                play_count=int(r["play_count"]),
                total_play_seconds=int(r["total_play_seconds"]),
                vndb_id=r["vndb_id"],
                title_original=r["title_original"],
                title_localized=r["title_localized"],
                description=r["description"],
                rating=float(r["rating"]) if r["rating"] is not None else None,
                platforms=r["platforms"],
                languages=r["languages"],
                image_url=r["image_url"],
                screenshots_json=r["screenshots_json"],
                source=r["source"],
                custom_save_root=r["custom_save_root"],
                window_title=r["window_title"],
            )
            for r in rows
        ]

    def list_all_game_dirs(self) -> set[str]:
        """Return all game root directories in the database.

        Used for incremental scan to skip already-imported games.
        Paths are normalized so ``E:\\foo`` and ``E:/foo`` compare equal.
        """
        from app.services.path_utils import normalize_game_dir

        rows = self.conn.execute("SELECT root_dir FROM games").fetchall()
        return {normalize_game_dir(str(r["root_dir"])) for r in rows}

    def get_game_by_id(self, user_id: int, game_id: int) -> GameRecord | None:
        """Return one game with the same fields as list_games.

        Implemented as a scan of ``list_games(user_id)`` so the result matches the library list
        exactly (avoids SQL drift for single-row fetch).
        """
        try:
            gid = int(game_id)
        except (TypeError, ValueError):
            return None
        for g in self.list_games(user_id):
            if int(g.id) == gid:
                return g
        return None

    def list_play_records(self, user_id: int, game_id: int, *, limit: int = 500) -> list[PlayRecordEntry]:
        rows = self.conn.execute(
            """
            SELECT id, started_at, ended_at, duration_seconds
            FROM play_records
            WHERE user_id = ? AND game_id = ?
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (user_id, game_id, limit),
        ).fetchall()
        return [
            PlayRecordEntry(
                id=int(r["id"]),
                started_at=str(r["started_at"]),
                ended_at=str(r["ended_at"]) if r["ended_at"] else None,
                duration_seconds=int(r["duration_seconds"] or 0),
            )
            for r in rows
        ]

    def list_all_play_records(
        self,
        user_id: int,
        *,
        game_id: int | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        min_duration_seconds: int | None = None,
        max_duration_seconds: int | None = None,
        limit: int = 20000,
    ) -> list[PlayHistoryRow]:
        """All play rows for user, newest first. Optional filters (dates as YYYY-MM-DD)."""
        where = ["pr.user_id = ?"]
        params: list[object] = [user_id]
        if game_id is not None:
            where.append("pr.game_id = ?")
            params.append(game_id)
        if date_from:
            where.append("date(pr.started_at) >= date(?)")
            params.append(date_from)
        if date_to:
            where.append("date(pr.started_at) <= date(?)")
            params.append(date_to)
        if min_duration_seconds is not None:
            where.append("pr.duration_seconds >= ?")
            params.append(min_duration_seconds)
        if max_duration_seconds is not None:
            where.append("pr.duration_seconds <= ?")
            params.append(max_duration_seconds)
        sql = f"""
            SELECT
                pr.id AS record_id,
                pr.game_id,
                pr.started_at,
                pr.ended_at,
                pr.duration_seconds,
                COALESCE(NULLIF(g.custom_name, ''), NULLIF(g.window_title, ''), g.name) AS game_name,
                COALESCE(NULLIF(g.custom_cover_path, ''), g.cover_path) AS cover_path,
                g.image_url
            FROM play_records pr
            JOIN games g ON g.id = pr.game_id
            WHERE {' AND '.join(where)}
            ORDER BY pr.started_at DESC
            LIMIT ?
        """
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [
            PlayHistoryRow(
                record_id=int(r["record_id"]),
                game_id=int(r["game_id"]),
                game_name=str(r["game_name"]),
                cover_path=r["cover_path"],
                image_url=r["image_url"],
                started_at=str(r["started_at"]),
                ended_at=str(r["ended_at"]) if r["ended_at"] else None,
                duration_seconds=int(r["duration_seconds"] or 0),
            )
            for r in rows
        ]

    def delete_play_records_by_ids(self, user_id: int, record_ids: list[int]) -> int:
        if not record_ids:
            return 0
        placeholders = ",".join("?" * len(record_ids))
        cur = self.conn.execute(
            f"DELETE FROM play_records WHERE user_id = ? AND id IN ({placeholders})",
            (user_id, *record_ids),
        )
        self.conn.commit()
        return int(cur.rowcount or 0)

    def delete_all_play_records(self, user_id: int) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS c FROM play_records WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        n = int(row["c"]) if row else 0
        self.conn.execute("DELETE FROM play_records WHERE user_id = ?", (user_id,))
        self.conn.commit()
        return n

    def get_game_storage_debug(self, game_id: int) -> dict[str, str | None] | None:
        """Raw DB columns for troubleshooting (stored vs custom fields)."""
        row = self.conn.execute(
            """
            SELECT
                name, launch_exe, custom_name, custom_launch_exe,
                cover_path, custom_cover_path, root_dir, vndb_id,
                image_url, source, created_at, updated_at,
                custom_save_root
            FROM games
            WHERE id = ?
            """,
            (game_id,),
        ).fetchone()
        if row is None:
            return None
        return {str(k): (str(row[k]) if row[k] is not None else None) for k in row.keys()}

    def record_play(self, user_id: int, game_id: int, duration_seconds: int) -> None:
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            """
            INSERT INTO play_records (user_id, game_id, started_at, ended_at, duration_seconds)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, game_id, now, now, duration_seconds),
        )
        self.conn.commit()

    def set_favorite(self, user_id: int, game_id: int, value: bool) -> None:
        if value:
            self.conn.execute(
                "INSERT OR IGNORE INTO favorites (user_id, game_id, created_at) VALUES (?, ?, ?)",
                (user_id, game_id, datetime.utcnow().isoformat()),
            )
        else:
            self.conn.execute(
                "DELETE FROM favorites WHERE user_id = ? AND game_id = ?",
                (user_id, game_id),
            )
        self.conn.commit()

    def create_category(self, user_id: int, name: str) -> int:
        self.conn.execute(
            "INSERT OR IGNORE INTO categories (user_id, name, created_at) VALUES (?, ?, ?)",
            (user_id, name, datetime.utcnow().isoformat()),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT id FROM categories WHERE user_id = ? AND name = ?",
            (user_id, name),
        ).fetchone()
        return int(row["id"])

    def assign_categories(self, game_id: int, category_ids: Iterable[int]) -> None:
        self.conn.execute("DELETE FROM game_categories WHERE game_id = ?", (game_id,))
        self.conn.executemany(
            "INSERT OR IGNORE INTO game_categories (game_id, category_id) VALUES (?, ?)",
            [(game_id, cid) for cid in category_ids],
        )
        self.conn.commit()

    def list_categories(self, user_id: int) -> list[tuple[int, str]]:
        rows = self.conn.execute(
            "SELECT id, name FROM categories WHERE user_id = ? ORDER BY name",
            (user_id,),
        ).fetchall()
        return [(int(r["id"]), str(r["name"])) for r in rows]

    def ensure_category_ids(self, user_id: int, names: list[str]) -> list[int]:
        ids: list[int] = []
        for raw_name in names:
            name = raw_name.strip()
            if not name:
                continue
            ids.append(self.create_category(user_id, name))
        return ids

    def delete_game(self, game_id: int) -> bool:
        """Remove one game row; related rows cascade via foreign keys."""
        row = self.conn.execute("SELECT id FROM games WHERE id = ?", (game_id,)).fetchone()
        if row is None:
            return False
        self.conn.execute("DELETE FROM games WHERE id = ?", (game_id,))
        self.conn.commit()
        return True

    def delete_games_not_in_scan(self, roots: list[str], valid_game_dirs: set[str]) -> int:
        if not roots:
            return 0
        from app.services.path_utils import is_path_under_root, normalize_game_dir

        norm_valid = {normalize_game_dir(d) for d in valid_game_dirs}
        rows = self.conn.execute(
            "SELECT id, root_dir, custom_name, custom_launch_exe, custom_cover_path FROM games"
        ).fetchall()
        to_delete_ids = []
        for r in rows:
            root_dir = str(r["root_dir"])
            if not any(is_path_under_root(root_dir, root) for root in roots):
                continue
            if normalize_game_dir(root_dir) in norm_valid:
                continue
            custom_name = str(r["custom_name"]).strip() if r["custom_name"] is not None else ""
            custom_launch_exe = (
                str(r["custom_launch_exe"]).strip() if r["custom_launch_exe"] is not None else ""
            )
            custom_cover_path = (
                str(r["custom_cover_path"]).strip() if r["custom_cover_path"] is not None else ""
            )
            has_custom = custom_name or custom_launch_exe or custom_cover_path
            if not has_custom:
                to_delete_ids.append(int(r["id"]))
        if not to_delete_ids:
            return 0
        placeholders = ",".join(["?"] * len(to_delete_ids))
        self.conn.execute(f"DELETE FROM games WHERE id IN ({placeholders})", to_delete_ids)
        self.conn.commit()
        return len(to_delete_ids)

    def clear_all_games(self) -> int:
        rows = self.conn.execute("SELECT id, custom_name, custom_launch_exe, custom_cover_path FROM games").fetchall()
        to_delete_ids = []
        for r in rows:
            custom_name = str(r["custom_name"]).strip() if r["custom_name"] is not None else ""
            custom_launch_exe = str(r["custom_launch_exe"]).strip() if r["custom_launch_exe"] is not None else ""
            custom_cover_path = str(r["custom_cover_path"]).strip() if r["custom_cover_path"] is not None else ""
            has_custom = custom_name or custom_launch_exe or custom_cover_path
            if not has_custom:
                to_delete_ids.append(int(r["id"]))
        if not to_delete_ids:
            return 0
        placeholders = ",".join(["?"] * len(to_delete_ids))
        self.conn.execute(f"DELETE FROM games WHERE id IN ({placeholders})", to_delete_ids)
        self.conn.commit()
        return len(to_delete_ids)

    def set_game_custom_save_root(self, game_id: int, path: str | None) -> None:
        now = datetime.utcnow().isoformat()
        normalized = (path or "").strip() or None
        self.conn.execute(
            "UPDATE games SET custom_save_root = ?, updated_at = ? WHERE id = ?",
            (normalized, now, game_id),
        )
        self.conn.commit()

    def update_game_window_title(self, game_id: int, window_title: str | None) -> None:
        """缓存游戏窗口标题，只写入一次（已有值不覆盖）。"""
        if not window_title or not window_title.strip():
            return
        existing = self.conn.execute(
            "SELECT window_title FROM games WHERE id = ?", (game_id,)
        ).fetchone()
        if existing and existing["window_title"]:
            return  # 已缓存，不覆盖
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            "UPDATE games SET window_title = ?, updated_at = ? WHERE id = ?",
            (window_title.strip(), now, game_id),
        )
        self.conn.commit()

    def get_game_window_title(self, game_id: int) -> str | None:
        row = self.conn.execute(
            "SELECT window_title FROM games WHERE id = ?", (game_id,)
        ).fetchone()
        if row is None or row["window_title"] is None:
            return None
        return str(row["window_title"]).strip() or None

    def get_window_titles_by_root_dirs(self, root_dirs: list[str]) -> dict[str, str]:
        """批量获取多个目录对应的窗口标题（优化性能）"""
        if not root_dirs:
            return {}
        placeholders = ",".join("?" * len(root_dirs))
        rows = self.conn.execute(
            f"SELECT root_dir, window_title FROM games WHERE root_dir IN ({placeholders})",
            root_dirs,
        ).fetchall()
        result: dict[str, str] = {}
        for row in rows:
            wt = row["window_title"]
            if wt:
                wt = str(wt).strip()
                if wt:
                    result[str(row["root_dir"])] = wt
        return result

    def list_save_backups(self, user_id: int, game_id: int) -> list[SaveBackupRecord]:
        rows = self.conn.execute(
            """
            SELECT id, user_id, game_id, label, zip_path, created_at, size_bytes, checksum_sha256
            FROM save_backups
            WHERE user_id = ? AND game_id = ?
            ORDER BY datetime(created_at) DESC, id DESC
            """,
            (user_id, game_id),
        ).fetchall()
        return [
            SaveBackupRecord(
                id=int(r["id"]),
                user_id=int(r["user_id"]),
                game_id=int(r["game_id"]),
                label=str(r["label"]),
                zip_path=str(r["zip_path"]),
                created_at=str(r["created_at"]),
                size_bytes=int(r["size_bytes"] or 0),
                checksum_sha256=(str(r["checksum_sha256"]) if r["checksum_sha256"] else None),
            )
            for r in rows
        ]

    def insert_save_backup(
        self,
        user_id: int,
        game_id: int,
        label: str,
        zip_path: str,
        size_bytes: int,
        *,
        checksum_sha256: str | None = None,
    ) -> int:
        now = datetime.utcnow().isoformat()
        cur = self.conn.execute(
            """
            INSERT INTO save_backups (
                user_id, game_id, label, zip_path, created_at, size_bytes, checksum_sha256
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                game_id,
                label.strip() or "备份",
                zip_path,
                now,
                size_bytes,
                (checksum_sha256.strip().lower() if checksum_sha256 else None),
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def update_save_backup_label(self, user_id: int, backup_id: int, label: str) -> bool:
        cur = self.conn.execute(
            "UPDATE save_backups SET label = ? WHERE id = ? AND user_id = ?",
            (label.strip() or "备份", backup_id, user_id),
        )
        self.conn.commit()
        return (cur.rowcount or 0) > 0

    def delete_save_backup_row(self, user_id: int, backup_id: int) -> str | None:
        row = self.conn.execute(
            "SELECT zip_path FROM save_backups WHERE id = ? AND user_id = ?",
            (backup_id, user_id),
        ).fetchone()
        if row is None:
            return None
        zp = str(row["zip_path"])
        self.conn.execute(
            "DELETE FROM save_backups WHERE id = ? AND user_id = ?",
            (backup_id, user_id),
        )
        self.conn.commit()
        return zp

    def get_save_backup(self, user_id: int, backup_id: int) -> SaveBackupRecord | None:
        row = self.conn.execute(
            """
            SELECT id, user_id, game_id, label, zip_path, created_at, size_bytes, checksum_sha256
            FROM save_backups WHERE id = ? AND user_id = ?
            """,
            (backup_id, user_id),
        ).fetchone()
        if row is None:
            return None
        return SaveBackupRecord(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            game_id=int(row["game_id"]),
            label=str(row["label"]),
            zip_path=str(row["zip_path"]),
            created_at=str(row["created_at"]),
            size_bytes=int(row["size_bytes"] or 0),
            checksum_sha256=(str(row["checksum_sha256"]) if row["checksum_sha256"] else None),
        )
