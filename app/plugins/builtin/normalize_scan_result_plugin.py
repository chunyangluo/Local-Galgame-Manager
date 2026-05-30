from __future__ import annotations

from dataclasses import replace

from app.core.scanner import ScanResult
from app.plugins.base import BasePlugin, PluginContext
from app.services.path_utils import normalize_game_dir


class NormalizeScanResultPlugin(BasePlugin):
    name = "normalize_scan_result"
    version = "1.0.0"
    description = "去重并规范化扫描结果中的路径与名称字段"

    def transform_scan_results(
        self, *, root: str, results: list[ScanResult], context: PluginContext
    ) -> list[ScanResult]:
        normalized: list[ScanResult] = []
        seen: set[tuple[str, str]] = set()
        for item in results:
            game_name = str(getattr(item, "game_name", "")).strip()
            game_dir = normalize_game_dir(str(getattr(item, "game_dir", "")).strip())
            launch_exe = str(getattr(item, "launch_exe", "")).strip()
            if not game_name or not game_dir or not launch_exe:
                continue
            key = (game_dir, launch_exe.lower())
            if key in seen:
                continue
            seen.add(key)
            normalized.append(
                replace(
                    item,
                    game_name=game_name,
                    game_dir=game_dir,
                    launch_exe=launch_exe,
                )
            )
        return normalized


def register() -> NormalizeScanResultPlugin:
    return NormalizeScanResultPlugin()
