"""Integration: 2DFan SQLite hints merged into save path resolver."""

import sqlite3
from pathlib import Path

from app.data.database import GameRecord
from app.services.save_path_resolver import resolve_save_path_candidates

_MIN_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE crawl_pages (
    download_id INTEGER PRIMARY KEY,
    url TEXT NOT NULL,
    title TEXT,
    subject_url TEXT,
    intro_text TEXT,
    body_text TEXT,
    fetched_at TEXT NOT NULL,
    http_status INTEGER,
    error TEXT
);
CREATE TABLE save_hints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    download_id INTEGER NOT NULL REFERENCES crawl_pages(download_id) ON DELETE CASCADE,
    hint_text TEXT NOT NULL,
    hint_kind TEXT NOT NULL,
    confidence REAL NOT NULL,
    source_line TEXT,
    UNIQUE(download_id, hint_text, hint_kind)
);
"""


def test_resolve_merges_twodfan_when_path_exists(tmp_path: Path) -> None:
    save_dir = tmp_path / "my_save_root"
    save_dir.mkdir()
    game_root = tmp_path / "game"
    game_root.mkdir()
    exe = game_root / "game.exe"
    exe.write_text("x", encoding="utf-8")

    dbf = tmp_path / "2dfan.sqlite3"
    conn = sqlite3.connect(dbf)
    conn.executescript(_MIN_SCHEMA)
    now = "2026-01-01T00:00:00"
    conn.execute(
        """
        INSERT INTO crawl_pages (
            download_id, url, title, subject_url, intro_text, body_text,
            fetched_at, http_status, error
        ) VALUES (?, ?, ?, '', '', '', ?, 200, NULL)
        """,
        (
            1001,
            "https://2dfan.com/downloads/1001",
            "お願い测试游戏 全CG存档",
            now,
        ),
    )
    conn.execute(
        """
        INSERT INTO save_hints (download_id, hint_text, hint_kind, confidence, source_line)
        VALUES (?, ?, 'windows_path', 0.9, NULL)
        """,
        (1001, str(save_dir)),
    )
    conn.commit()
    conn.close()

    game = GameRecord(
        1,
        "お願い测试游戏",
        str(game_root),
        str(exe),
        None,
        False,
        "",
        None,
        0,
        0,
        title_original="お願い测试游戏",
    )
    rows = resolve_save_path_candidates(
        game,
        max_results=12,
        twodfan_hints_db_path=str(dbf),
    )
    tw = [c for c in rows if c.source == "2dfan"]
    assert tw, "expected at least one 2dfan candidate"
    assert any(c.path.resolve() == save_dir.resolve() for c in tw)


def test_twodfan_ignored_when_db_missing(tmp_path: Path) -> None:
    game_root = tmp_path / "g"
    game_root.mkdir()
    exe = game_root / "a.exe"
    exe.write_text("", encoding="utf-8")
    game = GameRecord(1, "X", str(game_root), str(exe), None, False, "", None, 0, 0)
    rows = resolve_save_path_candidates(
        game,
        twodfan_hints_db_path=str(tmp_path / "nope.sqlite3"),
    )
    assert all(c.source != "2dfan" for c in rows)


def test_twodfan_db_stats_counts(tmp_path: Path) -> None:
    from app.services.twodfan_hints import twodfan_db_stats

    dbf = tmp_path / "s.sqlite3"
    conn = sqlite3.connect(dbf)
    conn.executescript(
        """
        CREATE TABLE crawl_pages (download_id INTEGER PRIMARY KEY, url TEXT, title TEXT,
            fetched_at TEXT);
        CREATE TABLE save_hints (id INTEGER PRIMARY KEY, download_id INTEGER, hint_text TEXT,
            hint_kind TEXT, confidence REAL);
        INSERT INTO crawl_pages VALUES (1,'u','t','now');
        INSERT INTO save_hints VALUES (1,1,'x','k',1.0);
        """
    )
    conn.close()
    assert twodfan_db_stats(dbf) == (1, 1)
    assert twodfan_db_stats(tmp_path / "missing.sqlite3") is None
