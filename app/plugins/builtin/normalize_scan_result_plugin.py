from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.plugins.base import PluginContext


class NormalizeScanResultPlugin:
    name = "normalize_scan_result"

    def transform_scan_results(
        self, *, root: str, results: list[Any], context: PluginContext
    ) -> list[Any]:
        normalized: list[Any] = []
        seen: set[tuple[str, str]] = set()
        for item in results:
            game_name = str(getattr(item, "game_name", "")).strip()
            game_dir = str(getattr(item, "game_dir", "")).strip()
            launch_exe = str(getattr(item, "launch_exe", "")).strip()
            if not game_name or not game_dir or not launch_exe:
                continue
            key = (game_dir.lower(), launch_exe.lower())
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

