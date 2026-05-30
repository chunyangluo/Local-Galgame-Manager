"""Example: filter scan results by folder name."""

from __future__ import annotations

from app.core.scanner import ScanResult
from app.plugins.base import BasePlugin, PluginContext


class SkipDemoFoldersPlugin(BasePlugin):
    name = "skip_demo_folders"
    version = "1.0.0"
    description = "跳过 demo/sample 目录下的扫描候选"
    author = "LGM Examples"

    def should_include_scan_result(
        self, *, root: str, item: ScanResult, context: PluginContext
    ) -> bool:
        blocked = context.config_for(self.name).get("blocked_tokens") or [
            "demo",
            "sample",
            "trial",
        ]
        path_lower = item.game_dir.replace("\\", "/").lower()
        for token in blocked:
            if token and str(token).lower() in path_lower:
                return False
        return True


def register() -> SkipDemoFoldersPlugin:
    return SkipDemoFoldersPlugin()
