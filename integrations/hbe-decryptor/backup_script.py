"""
备份脚本：将关键文件复制到备份目录（默认 ./backup，可用环境变量覆盖）。
"""

import os
import shutil
import sys
from datetime import datetime
from typing import List, Tuple

from paths import ROOT, backup_enabled, backup_target_dir

BACKUP_FILES: List[str] = [
    "password_dict.txt",
    "decry-chunyang.py",
    "candidates.txt",
    "batch_decrypt_known.py",
    "hbe.js",
    "paths.py",
]


def backup_file(src_path: str, dest_dir: str) -> Tuple[bool, str]:
    try:
        if not os.path.isfile(src_path):
            return False, f"源文件不存在: {src_path}"

        filename = os.path.basename(src_path)
        dest_path = os.path.join(dest_dir, filename)
        shutil.copy2(src_path, dest_path)

        file_size = os.path.getsize(src_path)
        size_str = f"{file_size} bytes" if file_size < 1024 else f"{file_size/1024:.2f} KB"
        return True, f"{filename} ({size_str})"

    except PermissionError:
        return False, f"权限错误: 无法访问 {src_path}"
    except shutil.SameFileError:
        return False, f"源文件和目标文件相同: {src_path}"
    except Exception as e:
        return False, f"备份失败: {str(e)}"


def perform_backup() -> dict:
    stats = {
        "total": 0,
        "success": 0,
        "failed": 0,
        "skipped": 0,
        "details": [],
        "disabled": False,
    }

    target = backup_target_dir()
    if target is None:
        print("[备份] 已跳过（设置 HBE_BACKUP=0 可禁用）")
        stats["disabled"] = True
        return stats

    backup_dir = str(target)
    os.makedirs(backup_dir, exist_ok=True)

    print("=" * 50)
    print("开始执行文件备份...")
    print("=" * 50)
    print(f"[备份] 备份时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[备份] 源目录: {ROOT}")
    print(f"[备份] 目标目录: {backup_dir}")
    print("-" * 50)

    script_dir = str(ROOT)
    optional_files = {"candidates.txt"}

    for filename in BACKUP_FILES:
        src_path = os.path.join(script_dir, filename)
        stats["total"] += 1

        if not os.path.exists(src_path):
            if filename in optional_files:
                print(f"[跳过] {filename} (可选文件，不存在)")
                stats["skipped"] += 1
                continue
            print(f"[失败] {filename} - 文件不存在")
            stats["failed"] += 1
            continue

        success, message = backup_file(src_path, backup_dir)
        if success:
            print(f"[成功] {message}")
            stats["success"] += 1
        else:
            print(f"[失败] {filename} - {message}")
            stats["failed"] += 1

    print("-" * 50)
    print("备份摘要:")
    print(f"  总计: {stats['total']} 个文件")
    print(f"  成功: {stats['success']} 个")
    print(f"  失败: {stats['failed']} 个")
    print(f"  跳过: {stats['skipped']} 个")
    print("=" * 50)
    return stats


def main():
    if not backup_enabled():
        print("[备份] 已禁用 (HBE_BACKUP=0)")
        sys.exit(0)
    try:
        result = perform_backup()
        if result.get("disabled"):
            sys.exit(0)
        if result["failed"] == 0:
            sys.exit(0)
        if result["success"] > 0:
            sys.exit(1)
        sys.exit(2)
    except Exception as e:
        print(f"[错误] 备份过程发生异常: {e}")
        sys.exit(3)


if __name__ == "__main__":
    main()
