#!/usr/bin/env python3
"""Create a new plugin package under the user data/plugins directory."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from app.services.app_data_dir import get_app_data_dir

_TEMPLATE_PY = '''"""{description}"""

from __future__ import annotations

from app.plugins.base import BasePlugin, PluginContext
from app.core.scanner import ScanResult


class {class_name}(BasePlugin):
    name = "{name}"
    version = "0.1.0"
    description = "{description}"
    author = ""

    def transform_scan_results(
        self, *, root: str, results: list[ScanResult], context: PluginContext
    ) -> list[ScanResult]:
        return list(results)


def register() -> {class_name}:
    return {class_name}()
'''


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", name.strip()).strip("_").lower()
    if not slug:
        raise ValueError("插件名无效")
    if slug[0].isdigit():
        slug = f"plugin_{slug}"
    return slug


def _class_name(slug: str) -> str:
    return "".join(part.capitalize() for part in slug.split("_")) + "Plugin"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="创建插件包骨架")
    parser.add_argument("name", help="插件目录名，如 my_filter")
    parser.add_argument("--description", default="自定义插件", help="插件说明")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="数据目录（默认 LocalAppData）",
    )
    args = parser.parse_args(argv)

    slug = _slug(args.name)
    data_dir = args.data_dir or get_app_data_dir()
    dest = data_dir / "plugins" / slug
    if dest.exists():
        print(f"已存在: {dest}", file=sys.stderr)
        return 1

    dest.mkdir(parents=True)
    manifest = {
        "name": slug,
        "version": "0.1.0",
        "description": args.description,
        "entry": "plugin.py",
        "min_api_version": 1,
    }
    (dest / "plugin.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    class_name = _class_name(slug)
    (dest / "plugin.py").write_text(
        _TEMPLATE_PY.format(
            name=slug,
            class_name=class_name,
            description=args.description.replace('"', "'"),
        ),
        encoding="utf-8",
    )
    print(f"已创建插件包: {dest}")
    print("下一步: 编辑 plugin.py，在主程序「插件管理」中启用。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
