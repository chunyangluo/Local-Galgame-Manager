"""Read-only lookup in the standalone 2DFan crawler SQLite for save-path hints."""

from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

from app.data.database import GameRecord

_WIN_PATH = re.compile(r"(?:[A-Za-z]:\\|\\\\)[^\s\n\"'<>]{3,240}")


@dataclass(frozen=True)
class TwodfanPathHit:
    path: Path
    hint_confidence: float
    download_id: int
    page_url: str
    page_title: str
    hint_kind: str
    hint_text: str


def _sqlite_readonly_uri(path: Path) -> str:
    return path.expanduser().resolve().as_uri() + "?mode=ro"


def _normalize_title(s: str) -> str:
    s = s.lower()
    s = re.sub(r"\s+", "", s)
    for noise in ("全cg存档", "存档", "补丁", "翻譯", "翻译", "gemini", "deepseek", "claude"):
        s = s.replace(noise, "")
    return s


def _title_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, _normalize_title(a), _normalize_title(b)).ratio()


def _search_terms(game: GameRecord) -> list[str]:
    raw: list[str] = []
    for s in (game.name, game.title_original or "", game.title_localized or ""):
        s = (s or "").strip()
        if s:
            raw.append(s)
            for w in re.split(r"[\s\-_/\\・]+", s):
                t = w.strip()
                if len(t) >= 2:
                    raw.append(t)
    out: list[str] = []
    seen: set[str] = set()
    for t in raw:
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
        if len(out) >= 16:
            break
    return out


def _open_twodfan(path: Path) -> sqlite3.Connection | None:
    try:
        p = path.expanduser().resolve()
        if not p.is_file():
            return None
        conn = sqlite3.connect(_sqlite_readonly_uri(p), uri=True)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='crawl_pages'"
        ).fetchone()
        if row is None:
            conn.close()
            return None
        return conn
    except sqlite3.Error:
        return None


def twodfan_db_stats(db_path: str | Path) -> tuple[int, int] | None:
    """Return ``(crawl_pages_rows, save_hints_rows)`` if the file is a readable 2DFan crawler DB."""
    conn = _open_twodfan(Path(str(db_path).strip()))
    if conn is None:
        return None
    try:
        n_pages = int(conn.execute("SELECT COUNT(*) AS c FROM crawl_pages").fetchone()["c"])
        n_hints = 0
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='save_hints'"
        ).fetchone()
        if row:
            n_hints = int(conn.execute("SELECT COUNT(*) AS c FROM save_hints").fetchone()["c"])
        return (n_pages, n_hints)
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def _pick_matching_pages(conn: sqlite3.Connection, game: GameRecord, *, page_limit: int) -> list[sqlite3.Row]:
    terms = _search_terms(game)
    if not terms:
        return []
    seen: set[int] = set()
    rows: list[sqlite3.Row] = []
    for term in terms:
        if len(term) < 2:
            continue
        pat = f"%{term.replace('%', '\\%').replace('_', '\\_')}%"
        try:
            cur = conn.execute(
                """
                SELECT download_id, title, url, intro_text, body_text
                FROM crawl_pages
                WHERE title LIKE ? ESCAPE '\\'
                LIMIT 40
                """,
                (pat,),
            )
        except sqlite3.Error:
            continue
        for r in cur.fetchall():
            did = int(r["download_id"])
            if did in seen:
                continue
            seen.add(did)
            rows.append(r)
            if len(rows) >= page_limit * 3:
                break
        if len(rows) >= page_limit * 3:
            break

    names = [x for x in (game.name, game.title_original or "", game.title_localized or "") if x.strip()]
    scored: list[tuple[float, sqlite3.Row]] = []
    for r in rows:
        title = str(r["title"] or "")
        score = max((_title_similarity(n, title) for n in names), default=0.0)
        if score < 0.22 and not any(
            t.lower() in title.lower() for t in terms if len(t) >= 3
        ):
            continue
        scored.append((score, r))
    scored.sort(key=lambda x: -x[0])
    return [r for _, r in scored[:page_limit]]


def _expand_hint_text(hint: str) -> list[Path]:
    raw = os.path.expandvars((hint or "").strip().strip('"'))
    out: list[Path] = []
    if raw and (raw.startswith("/") or (len(raw) > 2 and raw[1] == ":")):
        try:
            pr = Path(raw)
            if pr.is_dir():
                out.append(pr)
        except OSError:
            pass

    for m in _WIN_PATH.finditer(raw):
        p = Path(m.group(0).rstrip("\\/.,;，。；"))
        out.append(p)

    norm = raw.replace("/", "\\")
    for mk in ("文档\\", "我的文档\\", "documents\\"):
        idx = norm.lower().find(mk.lower())
        if idx < 0:
            continue
        tail = norm[idx + len(mk) :].lstrip("\\")
        if not tail:
            continue
        parts = [Path(part) for part in tail.split("\\") if part and part not in (".", "..")]
        if parts:
            out.append(Path.home() / "Documents" / Path(*parts))

    low = norm.lower()
    if "appdata" in low or "local" in low or "roaming" in low:
        p = Path(raw)
        if len(str(p)) > 4:
            out.append(p)

    uniq: list[Path] = []
    seen: set[str] = set()
    for p in out:
        key = str(p).lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    return uniq


def _kind_weight(kind: str) -> float:
    k = (kind or "").lower()
    if "save_location" in k:
        return 1.0
    if k == "windows_path":
        return 0.92
    if k == "unpack_to":
        return 0.85
    if k == "path_keyword_line":
        return 0.78
    return 0.7


def iter_twodfan_existing_paths(
    db_path: str | Path,
    game: GameRecord,
    *,
    page_limit: int = 6,
    hints_per_page: int = 12,
) -> Iterable[TwodfanPathHit]:
    path = Path(str(db_path).strip())
    if not str(path):
        return
    conn = _open_twodfan(path)
    if conn is None:
        return
    try:
        pages = _pick_matching_pages(conn, game, page_limit=page_limit)
        for page in pages:
            did = int(page["download_id"])
            title = str(page["title"] or "")
            url = str(page["url"] or "")
            cur = conn.execute(
                """
                SELECT hint_text, hint_kind, confidence
                FROM save_hints
                WHERE download_id = ?
                ORDER BY confidence DESC
                LIMIT ?
                """,
                (did, hints_per_page),
            )
            for h in cur.fetchall():
                hint_text = str(h["hint_text"] or "")
                kind = str(h["hint_kind"] or "")
                try:
                    hconf = float(h["confidence"] or 0.5)
                except (TypeError, ValueError):
                    hconf = 0.5
                eff = min(1.0, hconf * _kind_weight(kind))
                for p in _expand_hint_text(hint_text):
                    try:
                        rp = p.expanduser().resolve()
                    except OSError:
                        continue
                    if rp.is_dir():
                        yield TwodfanPathHit(
                            path=rp,
                            hint_confidence=eff,
                            download_id=did,
                            page_url=url,
                            page_title=title,
                            hint_kind=kind,
                            hint_text=hint_text[:500],
                        )
    finally:
        conn.close()
