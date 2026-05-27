from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generator, Iterable


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS crawl_pages (
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

CREATE TABLE IF NOT EXISTS save_hints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    download_id INTEGER NOT NULL REFERENCES crawl_pages(download_id) ON DELETE CASCADE,
    hint_text TEXT NOT NULL,
    hint_kind TEXT NOT NULL,
    confidence REAL NOT NULL,
    source_line TEXT,
    UNIQUE(download_id, hint_text, hint_kind)
);

CREATE TABLE IF NOT EXISTS crawl_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_save_hints_download ON save_hints(download_id);
CREATE INDEX IF NOT EXISTS idx_save_hints_kind ON save_hints(hint_kind);
CREATE INDEX IF NOT EXISTS idx_crawl_pages_title ON crawl_pages(title);
"""


@contextmanager
def connect(db_path: str | Path) -> Generator[sqlite3.Connection, None, None]:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: str | Path) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)


@dataclass
class PageRow:
    download_id: int
    url: str
    title: str | None
    subject_url: str | None
    intro_text: str | None
    body_text: str | None
    fetched_at: str
    http_status: int | None
    error: str | None


def upsert_page(conn: sqlite3.Connection, row: PageRow) -> None:
    conn.execute(
        """
        INSERT INTO crawl_pages (
            download_id, url, title, subject_url, intro_text, body_text,
            fetched_at, http_status, error
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(download_id) DO UPDATE SET
            url = excluded.url,
            title = excluded.title,
            subject_url = excluded.subject_url,
            intro_text = excluded.intro_text,
            body_text = excluded.body_text,
            fetched_at = excluded.fetched_at,
            http_status = excluded.http_status,
            error = excluded.error
        """,
        (
            row.download_id,
            row.url,
            row.title,
            row.subject_url,
            row.intro_text,
            row.body_text,
            row.fetched_at,
            row.http_status,
            row.error,
        ),
    )


def replace_hints(conn: sqlite3.Connection, download_id: int, hints: Iterable[tuple[str, str, float, str | None]]) -> None:
    conn.execute("DELETE FROM save_hints WHERE download_id = ?", (download_id,))
    conn.executemany(
        """
        INSERT OR IGNORE INTO save_hints (download_id, hint_text, hint_kind, confidence, source_line)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (download_id, text, kind, conf, line)
            for text, kind, conf, line in hints
        ],
    )


def iter_export_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT p.download_id, p.url, p.title, p.subject_url, p.intro_text,
               h.hint_text, h.hint_kind, h.confidence, h.source_line, p.fetched_at
        FROM crawl_pages p
        LEFT JOIN save_hints h ON h.download_id = p.download_id
        ORDER BY p.download_id, h.confidence DESC
        """
    )
    return [dict(r) for r in cur.fetchall()]


def get_state(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    cur = conn.execute("SELECT value FROM crawl_state WHERE key = ?", (key,))
    row = cur.fetchone()
    return row["value"] if row else default


def set_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO crawl_state (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


def get_last_page(conn: sqlite3.Connection) -> int:
    val = get_state(conn, "last_page", "0")
    return int(val) if val else 0


def set_last_page(conn: sqlite3.Connection, page: int) -> None:
    set_state(conn, "last_page", str(page))


def page_exists(conn: sqlite3.Connection, download_id: int) -> bool:
    cur = conn.execute("SELECT 1 FROM crawl_pages WHERE download_id = ?", (download_id,))
    return cur.fetchone() is not None
