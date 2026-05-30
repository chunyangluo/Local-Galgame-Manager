"""Plugin API v1 — extend ``BasePlugin`` or implement the protocol duck-typed hooks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from app.core.scanner import ScanResult

PLUGIN_API_VERSION = 1


@dataclass
class PluginMetadata:
    name: str
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    api_version: int = PLUGIN_API_VERSION
    hooks: list[str] = field(default_factory=list)


@dataclass
class PluginContext:
    """Runtime context passed to every hook."""

    data_dir: str
    plugin_configs: dict[str, dict[str, Any]] = field(default_factory=dict)

    def config_for(self, plugin_name: str) -> dict[str, Any]:
        raw = self.plugin_configs.get(plugin_name)
        return dict(raw) if isinstance(raw, dict) else {}


@dataclass
class LaunchDecision:
    """Result of ``modify_launch`` — plugins may adjust or cancel a launch."""

    launch_exe: str
    locale_emulator: bool = False
    as_admin: bool = False
    cancel: bool = False
    cancel_reason: str = ""


@runtime_checkable
class LocalGameManagerPlugin(Protocol):
    """Minimum contract (legacy plugins only need ``name`` + ``transform_scan_results``)."""

    name: str

    def transform_scan_results(
        self, *, root: str, results: list[ScanResult], context: PluginContext
    ) -> list[ScanResult]:
        ...


class BasePlugin:
    """
    Recommended base class. Override only the hooks you need.

    Hook summary:
    - ``transform_scan_results`` — mutate scan result list per root
    - ``should_include_scan_result`` — return False to drop a single candidate
    - ``modify_launch`` — adjust launch executable / flags or cancel
    - ``on_load`` / ``on_unload`` — lifecycle when manager loads plugins
  """

    name: str = "unnamed_plugin"
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    api_version: int = PLUGIN_API_VERSION

    def metadata(self) -> PluginMetadata:
        from app.plugins.hooks import (
            HOOK_LAUNCH_MODIFY,
            HOOK_ON_LOAD,
            HOOK_ON_UNLOAD,
            HOOK_SCAN_FILTER,
            HOOK_SCAN_TRANSFORM,
        )

        hooks: list[str] = []
        if type(self).transform_scan_results is not BasePlugin.transform_scan_results:
            hooks.append(HOOK_SCAN_TRANSFORM)
        if type(self).should_include_scan_result is not BasePlugin.should_include_scan_result:
            hooks.append(HOOK_SCAN_FILTER)
        if type(self).modify_launch is not BasePlugin.modify_launch:
            hooks.append(HOOK_LAUNCH_MODIFY)
        if type(self).on_load is not BasePlugin.on_load:
            hooks.append(HOOK_ON_LOAD)
        if type(self).on_unload is not BasePlugin.on_unload:
            hooks.append(HOOK_ON_UNLOAD)
        return PluginMetadata(
            name=self.name,
            version=self.version,
            description=self.description,
            author=self.author,
            api_version=self.api_version,
            hooks=hooks,
        )

    def on_load(self, context: PluginContext) -> None:
        """Called once after the plugin is enabled and loaded."""

    def on_unload(self, context: PluginContext) -> None:
        """Called when the manager reloads plugins (previous instance discarded)."""

    def transform_scan_results(
        self, *, root: str, results: list[ScanResult], context: PluginContext
    ) -> list[ScanResult]:
        return list(results)

    def should_include_scan_result(
        self, *, root: str, item: ScanResult, context: PluginContext
    ) -> bool:
        return True

    def modify_launch(
        self,
        *,
        game_id: int,
        game_name: str,
        launch_exe: str,
        locale_emulator: bool,
        as_admin: bool,
        context: PluginContext,
    ) -> LaunchDecision:
        return LaunchDecision(
            launch_exe=launch_exe,
            locale_emulator=locale_emulator,
            as_admin=as_admin,
        )

    def get_config_schema(self) -> dict[str, Any]:
        """Optional JSON-schema-like hint for future settings UI."""
        return {}
