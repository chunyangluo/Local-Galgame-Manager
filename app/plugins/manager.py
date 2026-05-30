from __future__ import annotations

import logging
import shutil
from enum import Enum
from pathlib import Path
from typing import Any

from app.core.scanner import ScanResult
from app.plugins.base import (
    BasePlugin,
    LaunchDecision,
    LocalGameManagerPlugin,
    PluginContext,
    PluginMetadata,
)
from app.plugins.hooks import HOOK_LAUNCH_MODIFY, HOOK_SCAN_FILTER, HOOK_SCAN_TRANSFORM
from app.plugins.loader import (
    ImportResult,
    discover_plugin_sources,
    import_plugin_module,
    read_manifest_for_source,
)

logger = logging.getLogger(__name__)


class PluginLoadStatus(str, Enum):
    LOADED = "loaded"
    DISABLED = "disabled"
    FAILED = "failed"


class PluginLoadInfo:
    def __init__(
        self,
        name: str,
        status: PluginLoadStatus,
        source: str,
        *,
        error: str | None = None,
        version: str = "",
        description: str = "",
        author: str = "",
        hooks: list[str] | None = None,
        path: str = "",
        package: bool = False,
    ) -> None:
        self.name = name
        self.status = status
        self.source = source
        self.error = error
        self.version = version
        self.description = description
        self.author = author
        self.hooks = hooks or []
        self.path = path
        self.package = package


def _metadata_for(plugin: LocalGameManagerPlugin, manifest: dict[str, Any] | None) -> PluginMetadata:
    if hasattr(plugin, "metadata") and callable(plugin.metadata):
        meta = plugin.metadata()
        if isinstance(meta, PluginMetadata):
            if manifest:
                if manifest.get("description") and not meta.description:
                    meta = PluginMetadata(
                        name=meta.name,
                        version=meta.version,
                        description=str(manifest["description"]),
                        author=meta.author or str(manifest.get("author") or ""),
                        api_version=meta.api_version,
                        hooks=meta.hooks,
                    )
            return meta
    hooks: list[str] = []
    if callable(getattr(plugin, "transform_scan_results", None)):
        hooks.append(HOOK_SCAN_TRANSFORM)
    if callable(getattr(plugin, "should_include_scan_result", None)):
        hooks.append(HOOK_SCAN_FILTER)
    if callable(getattr(plugin, "modify_launch", None)):
        hooks.append(HOOK_LAUNCH_MODIFY)
    version = str(getattr(plugin, "version", "") or "")
    description = str(getattr(plugin, "description", "") or "")
    author = str(getattr(plugin, "author", "") or "")
    if manifest:
        version = version or str(manifest.get("version") or "")
        description = description or str(manifest.get("description") or "")
        author = author or str(manifest.get("author") or "")
    return PluginMetadata(
        name=str(getattr(plugin, "name", "unnamed")),
        version=version or "0.0.0",
        description=description,
        author=author,
        hooks=hooks,
    )


class PluginManager:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.plugin_dir = data_dir / "plugins"
        self.builtin_dir = Path(__file__).resolve().parent / "builtin"
        self.examples_dir = Path(__file__).resolve().parent / "examples"
        self._plugin_configs: dict[str, dict[str, Any]] = {}
        self.context = PluginContext(data_dir=str(data_dir))
        self.plugins: list[LocalGameManagerPlugin] = []
        self.available_plugin_names: list[str] = []
        self.load_info: list[PluginLoadInfo] = []
        self._instances: dict[str, LocalGameManagerPlugin] = {}

    def set_plugin_configs(self, configs: dict[str, dict[str, Any]]) -> None:
        self._plugin_configs = {
            str(k): dict(v) for k, v in configs.items() if isinstance(v, dict)
        }
        self.context = PluginContext(
            data_dir=str(self.data_dir),
            plugin_configs=self._plugin_configs,
        )

    def ensure_examples_installed(self) -> list[Path]:
        """Copy bundled example plugins into user plugin dir (once per example name)."""
        installed: list[Path] = []
        if not self.examples_dir.is_dir():
            return installed
        self.plugin_dir.mkdir(parents=True, exist_ok=True)
        for example in sorted(self.examples_dir.iterdir()):
            if not example.is_dir() or example.name.startswith("_"):
                continue
            dest = self.plugin_dir / example.name
            if dest.exists():
                continue
            shutil.copytree(example, dest)
            installed.append(dest)
            logger.info("installed example plugin: %s", dest)
        return installed

    def load_all(self, *, disabled_plugins: set[str] | None = None) -> None:
        for plugin in self.plugins:
            self._call_unload(plugin)
        self.plugins.clear()
        self._instances.clear()
        self.available_plugin_names.clear()
        self.load_info.clear()
        disabled = disabled_plugins or set()

        self.ensure_examples_installed()
        self._ensure_readme()

        sources = discover_plugin_sources(self.builtin_dir, self.plugin_dir)
        for src in sources:
            if src.source == "external":
                logger.info("loading external plugin: %s", src.path)
            result = import_plugin_module(src)
            self._register_import_result(result, src, disabled)

    def reload(self, *, disabled_plugins: set[str] | None = None) -> None:
        self.load_all(disabled_plugins=disabled_plugins)

    def transform_scan_results(self, *, root: str, results: list[Any]) -> list[Any]:
        transformed: list[Any] = list(results)
        for plugin in self.plugins:
            transformed = plugin.transform_scan_results(
                root=root,
                results=transformed,
                context=self.context,
            )
        filtered: list[Any] = []
        for item in transformed:
            keep = True
            for plugin in self.plugins:
                fn = getattr(plugin, "should_include_scan_result", None)
                if callable(fn) and not fn(root=root, item=item, context=self.context):
                    keep = False
                    break
            if keep:
                filtered.append(item)
        return filtered

    def modify_launch(
        self,
        *,
        game_id: int,
        game_name: str,
        launch_exe: str,
        locale_emulator: bool,
        as_admin: bool,
    ) -> LaunchDecision:
        decision = LaunchDecision(
            launch_exe=launch_exe,
            locale_emulator=locale_emulator,
            as_admin=as_admin,
        )
        for plugin in self.plugins:
            fn = getattr(plugin, "modify_launch", None)
            if not callable(fn):
                continue
            out = fn(
                game_id=game_id,
                game_name=game_name,
                launch_exe=decision.launch_exe,
                locale_emulator=decision.locale_emulator,
                as_admin=decision.as_admin,
                context=self.context,
            )
            if isinstance(out, LaunchDecision):
                decision = out
            if decision.cancel:
                break
        return decision

    def plugin_metadata_list(self) -> list[PluginMetadata]:
        return [_metadata_for(p, None) for p in self.plugins]

    def _register_import_result(
        self, result: ImportResult, src, disabled_plugins: set[str]
    ) -> None:
        from app.plugins.loader import PluginSource

        assert isinstance(src, PluginSource)
        manifest = result.manifest or read_manifest_for_source(src)
        fallback_name = src.path.parent.name if src.package else src.path.stem

        if result.plugin is None:
            self.load_info.append(
                PluginLoadInfo(
                    name=str(manifest.get("name") if manifest else fallback_name),
                    status=PluginLoadStatus.FAILED,
                    source=src.source,
                    error=result.error,
                    path=str(src.path),
                    package=src.package,
                )
            )
            return

        plugin = result.plugin
        meta = _metadata_for(plugin, manifest)
        if meta.name not in self.available_plugin_names:
            self.available_plugin_names.append(meta.name)

        if meta.name in disabled_plugins:
            self.load_info.append(
                PluginLoadInfo(
                    name=meta.name,
                    status=PluginLoadStatus.DISABLED,
                    source=src.source,
                    version=meta.version,
                    description=meta.description,
                    author=meta.author,
                    hooks=meta.hooks,
                    path=str(src.path),
                    package=src.package,
                )
            )
            return

        self.plugins.append(plugin)
        self._instances[meta.name] = plugin
        self._call_on_load(plugin)
        self.load_info.append(
            PluginLoadInfo(
                name=meta.name,
                status=PluginLoadStatus.LOADED,
                source=src.source,
                version=meta.version,
                description=meta.description,
                author=meta.author,
                hooks=meta.hooks,
                path=str(src.path),
                package=src.package,
            )
        )
        logger.info(
            "plugin loaded: %s v%s hooks=%s (%s)",
            meta.name,
            meta.version,
            ",".join(meta.hooks) or "-",
            src.source,
        )

    def _call_on_load(self, plugin: LocalGameManagerPlugin) -> None:
        fn = getattr(plugin, "on_load", None)
        if callable(fn):
            try:
                fn(self.context)
            except Exception:
                logger.exception("on_load failed for plugin %s", getattr(plugin, "name", "?"))

    def _call_unload(self, plugin: LocalGameManagerPlugin) -> None:
        fn = getattr(plugin, "on_unload", None)
        if callable(fn):
            try:
                fn(self.context)
            except Exception:
                logger.exception("on_unload failed for plugin %s", getattr(plugin, "name", "?"))

    def _ensure_readme(self) -> None:
        readme = self.plugin_dir / "README.md"
        if readme.exists():
            return
        template = self.examples_dir.parent / "templates" / "plugins_README.md"
        if template.is_file():
            readme.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            readme.write_text(
                "# 外部插件目录\n\n将插件包文件夹或 `.py` 文件放在此目录。"
                "详见仓库 `docs/PLUGIN_GUIDE.md`。\n",
                encoding="utf-8",
            )
