"""Example: rename games at scan time."""

from __future__ import annotations

from dataclasses import replace

from app.core.scanner import ScanResult
from app.plugins.base import BasePlugin, PluginContext


class PrefixNamePlugin(BasePlugin):
    name = "prefix_name"
    version = "1.0.0"
    description = "为扫描到的游戏名添加 [本地] 前缀"
    author = "LGM Examples"

    def transform_scan_results(
        self, *, root: str, results: list[ScanResult], context: PluginContext
    ) -> list[ScanResult]:
        prefix = str(context.config_for(self.name).get("prefix") or "[本地]")
        out: list[ScanResult] = []
        for item in results:
            name = item.game_name
            if not name.startswith(prefix):
                name = f"{prefix} {name}"
            out.append(replace(item, game_name=name))
        return out


def register() -> PrefixNamePlugin:
    return PrefixNamePlugin()
