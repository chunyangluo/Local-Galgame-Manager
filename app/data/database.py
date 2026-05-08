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
        # Index on vndb_id for quick idempotent lookups.
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_games_vndb_id ON games(vndb_id)"
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
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            """
            INSERT INTO games (name, root_dir, launch_exe, cover_path, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(root_dir) DO UPDATE SET
                name = excluded.name,
                launch_exe = excluded.launch_exe,
                cover_path = COALESCE(excluded.cover_path, games.cover_path),
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
        now = datetime.utcnow().isoformat()
        payload = [
            (
                row.name,
                row.root_dir,
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
                    name = excluded.name,
                    launch_exe = excluded.launch_exe,
                    cover_path = COALESCE(excluded.cover_path, games.cover_path),
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
        row = self.conn.execute(
            """
            SELECT
                g.id,
                COALESCE(NULLIF(g.custom_name, ''), g.name) AS name,
                g.root_dir,
                COALESCE(NULLIF(g.custom_launch_exe, ''), g.launch_exe) AS launch_exe,
                g.cover_path,
                g.vndb_id,
                g.title_original,
                g.title_localized,
                g.description,
                g.rating,
                g.platforms,
                g.languages,
                g.image_url,
                g.screenshots_json,
                g.source
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

    def list_games(self, user_id: int) -> list[GameRecord]:
        rows = self.conn.execute(
            """
            SELECT
                g.id,
                COALESCE(NULLIF(g.custom_name, ''), g.name) AS name,
                g.root_dir,
                COALESCE(NULLIF(g.custom_launch_exe, ''), g.launch_exe) AS launch_exe,
                g.cover_path,
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
            )
            for r in rows
        ]

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

    def delete_games_not_in_scan(self, roots: list[str], valid_game_dirs: set[str]) -> int:
        if not roots:
            return 0
        where_clause = " OR ".join(["root_dir LIKE ?"] * len(roots))
        params: list[str] = [f"{root}%" for root in roots]
        rows = self.conn.execute(
            f"SELECT id, root_dir FROM games WHERE {where_clause}",
            params,
        ).fetchall()
        to_delete_ids = [int(r["id"]) for r in rows if str(r["root_dir"]) not in valid_game_dirs]
        if not to_delete_ids:
            return 0
        placeholders = ",".join(["?"] * len(to_delete_ids))
        self.conn.execute(f"DELETE FROM games WHERE id IN ({placeholders})", to_delete_ids)
        self.conn.commit()
        return len(to_delete_ids)

    def clear_all_games(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS cnt FROM games").fetchone()
        count = int(row["cnt"]) if row else 0
        self.conn.execute("DELETE FROM games")
        self.conn.commit()
        return count
