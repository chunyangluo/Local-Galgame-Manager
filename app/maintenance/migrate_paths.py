"""CLI: normalize game root_dir values and merge duplicate library entries."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from app.data.database import Database
from app.services.app_data_dir import get_app_data_dir
from app.services.game_path_migration import (
    apply_migration_plan,
    build_migration_plan,
    format_plan_report,
)
from app.services.logging_setup import setup_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "一次性迁移：规范化游戏库中的安装路径 (root_dir)，"
            "合并因路径写法不同产生的重复记录。"
        ),
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="数据目录（默认：当前用户的应用数据目录）",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="执行迁移（默认仅预览计划，不写库）",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 输出计划/结果",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="执行前自动导出数据库 zip 备份（仅与 --apply 一起使用）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    data_dir = args.data_dir or get_app_data_dir()
    setup_logging(data_dir=data_dir)
    log = logging.getLogger(__name__)

    db = Database(data_dir)
    plan = build_migration_plan(db)

    if args.json:
        payload: dict = {"data_dir": str(data_dir), "dry_run": not args.apply, "plan": plan.to_dict()}
    else:
        print(format_plan_report(plan))
        print(f"\n数据目录: {data_dir}")

    if plan.total_changes == 0:
        if args.json:
            payload["message"] = "无需迁移"
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("\n无需迁移，库中路径已一致。")
        return 0

    if not args.apply:
        if args.json:
            payload["message"] = "dry-run; pass --apply to execute"
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("\n以上为预览。添加 --apply 执行迁移，建议同时加 --backup。")
        return 0

    if args.backup:
        from app.services.backup_service import BackupService

        archive = BackupService(data_dir).export_backup(db.db_path)
        log.info("pre-migration backup: %s", archive)
        if not args.json:
            print(f"\n已备份: {archive}")

    stats = apply_migration_plan(db, plan)
    if args.json:
        payload["result"] = stats
        payload["message"] = "migration applied"
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("\n迁移完成:")
        print(f"  合并重复: {stats['merges']}")
        print(f"  规范化路径: {stats['normalized']}")
        print(f"  扫描路径更新: {stats['scan_roots_updated']}")
        print(f"  扫描路径删除: {stats['scan_roots_removed']}")
        if stats.get("save_backup_files_moved"):
            print(f"  存档备份文件移动: {stats['save_backup_files_moved']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
