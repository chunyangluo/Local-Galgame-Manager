from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.cover_manager import CoverManager
from app.core.scanner import GameScanner
from app.data.database import Database


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
    return parser


def run() -> int:
    parser = build_parser()
    args = parser.parse_args()

    data_dir = Path.cwd() / "data"
    scanner = GameScanner()
    db = Database(data_dir)
    db.ensure_default_user()
    cover_manager = CoverManager(data_dir / "covers")

    all_results: list[dict[str, str]] = []
    for root in args.root:
        results = scanner.scan_root(root)
        for item in results:
            cover = cover_manager.find_cover(item.game_dir)
            row = {
                "game_name": item.game_name,
                "game_dir": item.game_dir,
                "launch_exe": item.launch_exe,
                "cover_path": cover or "",
            }
            all_results.append(row)
            if args.import_db:
                db.upsert_game(item.game_name, item.game_dir, item.launch_exe, cover)

    output_text = ""
    if args.json:
        output_text = json.dumps(all_results, ensure_ascii=False, indent=2)
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
        print(f"Imported {len(all_results)} records into database.")

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
