"""One-shot: point Local-Galgame-Manager settings at this repo's 2dfan SQLite."""

from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
CRAWL_DB = (REPO / "tools" / "2dfan-save-crawler" / "data" / "2dfan_saves.sqlite3").resolve()


def main() -> int:
    mgr = Path(os.environ.get("LOCALAPPDATA", "")) / "LocalGalgameManager" / "data" / "manager.sqlite3"
    if not mgr.is_file():
        print("manager.sqlite3 not found:", mgr, file=sys.stderr)
        print("Start the GUI once to create data, then re-run this script.", file=sys.stderr)
        return 1
    if not CRAWL_DB.is_file():
        print("Crawler DB missing; run: python -m dfan_save_crawler init --db data/2dfan_saves.sqlite3", file=sys.stderr)
        return 1
    conn = sqlite3.connect(mgr)
    cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(settings)").fetchall()}
    if "twodfan_hints_db_path" not in cols:
        conn.execute("ALTER TABLE settings ADD COLUMN twodfan_hints_db_path TEXT DEFAULT ''")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    conn.execute(
        "UPDATE settings SET twodfan_hints_db_path = ?, updated_at = ? WHERE id = 1",
        (str(CRAWL_DB), now),
    )
    conn.commit()
    conn.close()
    print("Set twodfan_hints_db_path ->", CRAWL_DB)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
