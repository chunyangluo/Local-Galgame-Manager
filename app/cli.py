from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path

from app.core.cover_manager import CoverManager
from app.core.scanner import GameScanner
from app.data.database import Database, VndbImportRow
from app.plugins.manager import PluginManager
from app.services.vndb_service import VndbOutcome, VndbService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scan local games without UI.")
    parser.add_argument(
        "--root",
        action="append",
        required=True,
        help="Game root directory. Can be provided multiple times.",
    )
    parser.add_argument(
        "--import-db",
        action="store_true",
        help="Import scan results into local database.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON.",
    )
    parser.add_argument(
        "--output",
        help="Write output to file path (UTF-8).",
    )
    parser.add_argument(
        "--vndb-import",
        action="store_true",
        help="Use VNDB-only metadata import mode for scanned games.",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=6,
        help="Thread count for VNDB import mode (default: 6).",
    )
    return parser


def run() -> int:
    parser = build_parser()
    args = parser.parse_args()

    data_dir = Path.cwd() / "data"
    scanner = GameScanner()
    db = Database(data_dir)
    db.ensure_default_user()
    cover_manager = CoverManager(data_dir / "covers")
    vndb_service = VndbService()
    plugin_manager = PluginManager(data_dir)
    plugin_manager.load_all()

    all_results: list[dict[str, str]] = []
    discovered: list[tuple[str, str, str]] = []
    for root in args.root:
        results = scanner.scan_root(root)
        results = plugin_manager.transform_scan_results(root=root, results=results)
        for item in results:
            discovered.append((item.game_name, item.game_dir, item.launch_exe))
            cover = ""
            if not args.vndb_import:
                cover = cover_manager.find_cover(item.game_dir, item.game_name) or ""
            row = {
                "game_name": item.game_name,
                "game_dir": item.game_dir,
                "launch_exe": item.launch_exe,
                "cover_path": cover,
            }
            all_results.append(row)
            if args.import_db and not args.vndb_import:
                db.upsert_game(item.game_name, item.game_dir, item.launch_exe, cover)

    summary: dict[str, object] | None = None
    if args.vndb_import:
        rows, outcomes = _run_vndb_import(
            discovered=discovered,
            vndb_service=vndb_service,
            cover_manager=cover_manager,
            threads=max(1, int(args.threads)),
        )
        if args.import_db and rows:
            db.upsert_games_batch(rows)
        failed = [
            {
                "query": outcome.query,
                "reason": outcome.error_kind,
                "detail": outcome.error_detail,
            }
            for outcome in outcomes
            if not outcome.success
        ]
        summary = {
            "total": len(discovered),
            "success": len(rows),
            "failed": len(failed),
            "failures": failed,
        }

    output_text = ""
    if args.json:
        payload: dict[str, object] = {"results": all_results}
        if summary is not None:
            payload["vndb_summary"] = summary
        output_text = json.dumps(payload, ensure_ascii=False, indent=2)
    else:
        lines: list[str] = []
        if not all_results:
            lines.append("No games detected.")
        for row in all_results:
            lines.append(f"{row['game_name']} | {row['launch_exe']}")
        output_text = "\n".join(lines)

    if args.output:
        Path(args.output).write_text(output_text + "\n", encoding="utf-8")
        print(f"Saved output to: {args.output}")
    else:
        print(output_text)

    if args.import_db:
        if summary is not None:
            print(
                f"VNDB import summary: total={summary['total']}, success={summary['success']}, failed={summary['failed']}"
            )
        else:
            print(f"Imported {len(all_results)} records into database.")

    return 0


def _run_vndb_import(
    discovered: list[tuple[str, str, str]],
    vndb_service: VndbService,
    cover_manager: CoverManager,
    threads: int,
) -> tuple[list[VndbImportRow], list[VndbOutcome]]:
    def _lookup(item: tuple[str, str, str]) -> tuple[VndbImportRow | None, VndbOutcome]:
        name, root_dir, launch_exe = item
        outcome = vndb_service.search_title(name, limit=1)
        if not outcome.success or outcome.record is None:
            return None, outcome
        rec = outcome.record
        cover_path = (
            cover_manager.cache_vndb_image(rec.image_url, rec.vndb_id) if rec.image_url else None
        )
        row = VndbImportRow(
            # Keep local display name stable; VNDB titles go to metadata columns.
            name=name,
            root_dir=root_dir,
            launch_exe=launch_exe,
            vndb_id=rec.vndb_id,
            title_original=rec.title_original,
            title_localized=rec.title_localized,
            description=rec.description,
            rating=rec.rating,
            platforms=rec.platforms_to_str(),
            languages=rec.languages_to_str(),
            image_url=rec.image_url,
            screenshots_json=rec.screenshots_to_json(),
            cover_path=cover_path,
        )
        return row, outcome

    rows: list[VndbImportRow] = []
    outcomes: list[VndbOutcome] = []
    with ThreadPoolExecutor(max_workers=max(1, threads)) as pool:
        futures = [pool.submit(_lookup, item) for item in discovered]
        for future in as_completed(futures):
            row, outcome = future.result()
            outcomes.append(outcome)
            if row is not None:
                rows.append(row)
    return rows, outcomes


if __name__ == "__main__":
    raise SystemExit(run())
