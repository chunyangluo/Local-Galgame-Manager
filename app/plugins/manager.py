from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

from app.plugins.base import LocalGameManagerPlugin, PluginContext


class PluginManager:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.context = PluginContext(data_dir=str(data_dir))
        self.plugins: list[LocalGameManagerPlugin] = []
        self.available_plugin_names: list[str] = []

    def load_all(self, *, disabled_plugins: set[str] | None = None) -> None:
        self.plugins.clear()
        self.available_plugin_names.clear()
        disabled = disabled_plugins or set()
        self._load_builtin_plugins(disabled)
        self._load_external_plugins(disabled)

    def transform_scan_results(self, *, root: str, results: list[Any]) -> list[Any]:
        transformed = list(results)
        for plugin in self.plugins:
            transformed = plugin.transform_scan_results(
                root=root,
                results=transformed,
                context=self.context,
            )
        return transformed

    def _load_builtin_plugins(self, disabled_plugins: set[str]) -> None:
        builtin_dir = Path(__file__).resolve().parent / "builtin"
        if not builtin_dir.exists():
            return
        for file in sorted(builtin_dir.glob("*.py")):
            if file.name.startswith("_"):
                continue
            plugin = self._load_plugin_from_file(file)
            if plugin is not None:
                self._append_plugin(plugin, disabled_plugins)

    def _load_external_plugins(self, disabled_plugins: set[str]) -> None:
        plugin_dir = self.data_dir / "plugins"
        plugin_dir.mkdir(parents=True, exist_ok=True)
        for file in sorted(plugin_dir.glob("*.py")):
            if file.name.startswith("_"):
                continue
            plugin = self._load_plugin_from_file(file)
            if plugin is not None:
                self._append_plugin(plugin, disabled_plugins)

    def _load_plugin_from_file(self, file_path: Path) -> LocalGameManagerPlugin | None:
        module_name = f"lgm_plugin_{file_path.stem}_{abs(hash(str(file_path)))}"
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception:
            return None
        return self._extract_plugin_instance(module)

    def _extract_plugin_instance(self, module: ModuleType) -> LocalGameManagerPlugin | None:
        register = getattr(module, "register", None)
        if register is None or not callable(register):
            return None
        try:
            plugin = register()
        except Exception:
            return None
        if not isinstance(plugin, LocalGameManagerPlugin):
            return None
        return plugin

    def _append_plugin(
        self, plugin: LocalGameManagerPlugin, disabled_plugins: set[str]
    ) -> None:
        if plugin.name not in self.available_plugin_names:
            self.available_plugin_names.append(plugin.name)
        if plugin.name in disabled_plugins:
            return
        self.plugins.append(plugin)

