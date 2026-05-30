"""One-shot migration: normalize ``games.root_dir`` and merge duplicate library rows."""

from __future__ import annotations

import json
import logging
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.data.database import Database
from app.services.path_utils import normalize_game_dir

logger = logging.getLogger(__name__)

_MERGE_TEXT_COLUMNS = (
    "custom_name",
    "custom_launch_exe",
    "custom_cover_path",
    "cover_path",
    "vndb_id",
    "title_original",
    "title_localized",
    "description",
    "platforms",
    "languages",
    "image_url",
    "screenshots_json",
    "source",
    "custom_save_root",
    "window_title",
)


@dataclass
class PathNormalizeAction:
    game_id: int
    old_root_dir: str
    new_root_dir: str


@dataclass
class GameMergeAction:
    keeper_id: int
    duplicate_id: int
    keeper_root_before: str
    duplicate_root_dir: str
    canonical_root_dir: str


@dataclass
class ScanRootNormalizeAction:
    old_path: str
    new_path: str


@dataclass
class MigrationPlan:
    normalize_only: list[PathNormalizeAction] = field(default_factory=list)
    merges: list[GameMergeAction] = field(default_factory=list)
    scan_root_updates: list[ScanRootNormalizeAction] = field(default_factory=list)
    scan_root_removals: list[str] = field(default_factory=list)

    @property
    def total_changes(self) -> int:
        return (
            len(self.normalize_only)
            + len(self.merges)
            + len(self.scan_root_updates)
            + len(self.scan_root_removals)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "normalize_only": [a.__dict__ for a in self.normalize_only],
            "merges": [a.__dict__ for a in self.merges],
            "scan_root_updates": [a.__dict__ for a in self.scan_root_updates],
            "scan_root_removals": list(self.scan_root_removals),
            "total_changes": self.total_changes,
        }


def _row_text(row: dict[str, Any], key: str) -> str:
    val = row.get(key)
    if val is None:
        return ""
    return str(val).strip()


def _keeper_rank(
    row: dict[str, Any],
    play_counts: dict[int, int],
    favorite_game_ids: set[int],
) -> tuple:
    gid = int(row["id"])
    return (
        1 if _row_text(row, "custom_name") else 0,
        1 if _row_text(row, "custom_launch_exe") else 0,
        1 if _row_text(row, "custom_cover_path") else 0,
        play_counts.get(gid, 0),
        1 if gid in favorite_game_ids else 0,
        1 if _row_text(row, "vndb_id") else 0,
        float(row["rating"]) if row.get("rating") is not None else 0.0,
        -gid,
    )


def _fetch_games(conn) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM games ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def _play_counts(conn) -> dict[int, int]:
    return {
        int(r["game_id"]): int(r["cnt"])
        for r in conn.execute(
            "SELECT game_id, COUNT(*) AS cnt FROM play_records GROUP BY game_id"
        ).fetchall()
    }


def _favorite_game_ids(conn) -> set[int]:
    return {int(r["game_id"]) for r in conn.execute("SELECT game_id FROM favorites").fetchall()}


def build_migration_plan(db: Database) -> MigrationPlan:
    conn = db.conn
    games = _fetch_games(conn)
    play_counts = _play_counts(conn)
    favorite_ids = _favorite_game_ids(conn)
    plan = MigrationPlan()

    by_canonical: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in games:
        canonical = normalize_game_dir(str(row["root_dir"]))
        by_canonical[canonical].append(row)

    for canonical, members in sorted(by_canonical.items()):
        if len(members) == 1:
            row = members[0]
            old = str(row["root_dir"])
            if old != canonical:
                plan.normalize_only.append(
                    PathNormalizeAction(int(row["id"]), old, canonical)
                )
            continue

        keeper = max(
            members, key=lambda r: _keeper_rank(r, play_counts, favorite_ids)
        )
        keeper_id = int(keeper["id"])
        for row in members:
            gid = int(row["id"])
            old = str(row["root_dir"])
            if gid == keeper_id:
                if old != canonical:
                    plan.normalize_only.append(
                        PathNormalizeAction(gid, old, canonical)
                    )
            else:
                plan.merges.append(
                    GameMergeAction(
                        keeper_id=keeper_id,
                        duplicate_id=gid,
                        keeper_root_before=str(keeper["root_dir"]),
                        duplicate_root_dir=old,
                        canonical_root_dir=canonical,
                    )
                )

    scan_paths = [str(r["path"]) for r in conn.execute("SELECT path FROM scan_roots").fetchall()]
    seen_normalized: dict[str, str] = {}
    for path in scan_paths:
        norm = normalize_game_dir(path)
        if norm == path:
            seen_normalized.setdefault(norm, path)
            continue
        if norm in seen_normalized:
            plan.scan_root_removals.append(path)
        else:
            plan.scan_root_updates.append(ScanRootNormalizeAction(path, norm))
            seen_normalized[norm] = norm

    return plan


def _merge_metadata(conn, keeper_id: int, duplicate_id: int) -> list[str]:
    keeper = dict(
        conn.execute("SELECT * FROM games WHERE id = ?", (keeper_id,)).fetchone()
    )
    dup = dict(
        conn.execute("SELECT * FROM games WHERE id = ?", (duplicate_id,)).fetchone()
    )
    updates: dict[str, Any] = {}
    for col in _MERGE_TEXT_COLUMNS:
        if _row_text(keeper, col):
            continue
        dup_val = _row_text(dup, col)
        if dup_val:
            updates[col] = dup_val
    if dup.get("rating") is not None and keeper.get("rating") is None:
        updates["rating"] = dup["rating"]
    if not updates:
        return []
    sets = ", ".join(f"{k} = ?" for k in updates)
    conn.execute(
        f"UPDATE games SET {sets}, updated_at = ? WHERE id = ?",
        (*updates.values(), datetime.now(UTC).isoformat(), keeper_id),
    )
    return list(updates.keys())


def _repoint_game_children(conn, keeper_id: int, duplicate_id: int) -> None:
    conn.execute(
        "UPDATE play_records SET game_id = ? WHERE game_id = ?",
        (keeper_id, duplicate_id),
    )
    conn.execute(
        """
        DELETE FROM favorites
        WHERE game_id = ? AND user_id IN (
            SELECT user_id FROM favorites WHERE game_id = ?
        )
        """,
        (duplicate_id, keeper_id),
    )
    conn.execute(
        "UPDATE favorites SET game_id = ? WHERE game_id = ?",
        (keeper_id, duplicate_id),
    )
    conn.execute(
        """
        DELETE FROM game_categories
        WHERE game_id = ? AND category_id IN (
            SELECT category_id FROM game_categories WHERE game_id = ?
        )
        """,
        (duplicate_id, keeper_id),
    )
    conn.execute(
        "UPDATE game_categories SET game_id = ? WHERE game_id = ?",
        (keeper_id, duplicate_id),
    )
    conn.execute(
        "UPDATE save_backups SET game_id = ? WHERE game_id = ?",
        (keeper_id, duplicate_id),
    )


def _relocate_save_backup_dirs(base_dir: Path, keeper_id: int, duplicate_id: int) -> int:
    moved = 0
    backups_root = base_dir / "save-backups"
    if not backups_root.is_dir():
        return 0
    for user_dir in backups_root.iterdir():
        if not user_dir.is_dir():
            continue
        src = user_dir / str(duplicate_id)
        dst = user_dir / str(keeper_id)
        if not src.is_dir():
            continue
        dst.mkdir(parents=True, exist_ok=True)
        for item in src.iterdir():
            target = dst / item.name
            if target.exists():
                stem = item.stem
                suffix = item.suffix
                n = 1
                while target.exists():
                    target = dst / f"{stem}_merged{n}{suffix}"
                    n += 1
            shutil.move(str(item), str(target))
            moved += 1
        try:
            src.rmdir()
        except OSError:
            pass
    return moved


def _rewrite_backup_zip_paths(conn, keeper_id: int, duplicate_id: int) -> None:
    rows = conn.execute(
        "SELECT id, zip_path FROM save_backups WHERE game_id = ?",
        (keeper_id,),
    ).fetchall()
    dup_token = f"/{duplicate_id}/"
    keep_token = f"/{keeper_id}/"
    for row in rows:
        zp = str(row["zip_path"])
        if dup_token not in zp.replace("\\", "/"):
            continue
        new_zp = zp.replace(f"\\{duplicate_id}\\", f"\\{keeper_id}\\").replace(
            dup_token, keep_token
        )
        conn.execute(
            "UPDATE save_backups SET zip_path = ? WHERE id = ?",
            (new_zp, int(row["id"])),
        )


def apply_migration_plan(db: Database, plan: MigrationPlan) -> dict[str, Any]:
    if plan.total_changes == 0:
        return {"applied": 0, "merges": 0, "normalized": 0}

    stats = {
        "applied": plan.total_changes,
        "merges": len(plan.merges),
        "normalized": len(plan.normalize_only),
        "scan_roots_updated": len(plan.scan_root_updates),
        "scan_roots_removed": len(plan.scan_root_removals),
        "metadata_fields_merged": [],
        "save_backup_files_moved": 0,
    }
    conn = db.conn

    with conn:
        for merge in plan.merges:
            merged_fields = _merge_metadata(conn, merge.keeper_id, merge.duplicate_id)
            if merged_fields:
                stats["metadata_fields_merged"].append(
                    {"keeper_id": merge.keeper_id, "fields": merged_fields}
                )
            _repoint_game_children(conn, merge.keeper_id, merge.duplicate_id)
            stats["save_backup_files_moved"] += _relocate_save_backup_dirs(
                db.base_dir, merge.keeper_id, merge.duplicate_id
            )
            _rewrite_backup_zip_paths(conn, merge.keeper_id, merge.duplicate_id)
            conn.execute("DELETE FROM games WHERE id = ?", (merge.duplicate_id,))

        for action in plan.normalize_only:
            conn.execute(
                "UPDATE games SET root_dir = ?, updated_at = ? WHERE id = ?",
                (action.new_root_dir, datetime.now(UTC).isoformat(), action.game_id),
            )

        for action in plan.scan_root_updates:
            conn.execute(
                "UPDATE scan_roots SET path = ? WHERE path = ?",
                (action.new_path, action.old_path),
            )
        for path in plan.scan_root_removals:
            conn.execute("DELETE FROM scan_roots WHERE path = ?", (path,))

    return stats


def format_plan_report(plan: MigrationPlan) -> str:
    lines = [
        f"路径迁移计划：共 {plan.total_changes} 项变更",
        f"  - 仅规范化 root_dir：{len(plan.normalize_only)}",
        f"  - 合并重复游戏：{len(plan.merges)}",
        f"  - 扫描路径更新：{len(plan.scan_root_updates)}",
        f"  - 扫描路径删除（重复）：{len(plan.scan_root_removals)}",
        "",
    ]
    for m in plan.merges:
        lines.append(
            f"合并 game_id {m.duplicate_id} → {m.keeper_id} "
            f"({m.duplicate_root_dir!r} → {m.canonical_root_dir!r})"
        )
    for n in plan.normalize_only:
        lines.append(f"规范化 game_id {n.game_id}: {n.old_root_dir!r} → {n.new_root_dir!r}")
    for s in plan.scan_root_updates:
        lines.append(f"扫描路径: {s.old_path!r} → {s.new_path!r}")
    for s in plan.scan_root_removals:
        lines.append(f"删除重复扫描路径: {s!r}")
    return "\n".join(lines)
