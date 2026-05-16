from __future__ import annotations

import importlib.util
import logging
import traceback
from enum import Enum
from pathlib import Path
from types import ModuleType
from typing import Any

from app.plugins.base import LocalGameManagerPlugin, PluginContext

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
        error: str | None = None,
    ) -> None:
        self.name = name
        self.status = status
        self.source = source
        self.error = error


class PluginManager:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.context = PluginContext(data_dir=str(data_dir))
        self.plugins: list[LocalGameManagerPlugin] = []
        self.available_plugin_names: list[str] = []
        self.load_info: list[PluginLoadInfo] = []

    def load_all(self, *, disabled_plugins: set[str] | None = None) -> None:
        self.plugins.clear()
        self.available_plugin_names.clear()
        self.load_info.clear()
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
            plugin = self._load_plugin_from_file(file, source="builtin")
            if plugin is not None:
                self._append_plugin(plugin, disabled_plugins, source="builtin")

    def _load_external_plugins(self, disabled_plugins: set[str]) -> None:
        plugin_dir = self.data_dir / "plugins"
        plugin_dir.mkdir(parents=True, exist_ok=True)
        for file in sorted(plugin_dir.glob("*.py")):
            if file.name.startswith("_"):
                continue
            logger.warning(
                "正在加载第三方插件: %s (来源: %s) — 第三方插件可执行任意代码，请确认来源可信",
                file.name,
                file,
            )
            plugin = self._load_plugin_from_file(file, source="external")
            if plugin is not None:
                self._append_plugin(plugin, disabled_plugins, source="external")

    def _load_plugin_from_file(
        self, file_path: Path, source: str
    ) -> LocalGameManagerPlugin | None:
        module_name = f"lgm_plugin_{file_path.stem}_{abs(hash(str(file_path)))}"
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            logger.error(
                "插件加载失败 [%s]: 无法创建模块规格 — file=%s",
                file_path.stem,
                file_path,
            )
            self.load_info.append(
                PluginLoadInfo(
                    name=file_path.stem,
                    status=PluginLoadStatus.FAILED,
                    source=source,
                    error="无法创建模块规格",
                )
            )
            return None
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception:
            tb = traceback.format_exc()
            logger.error(
                "插件加载失败 [%s]: 模块执行异常\n%s",
                file_path.stem,
                tb,
            )
            self.load_info.append(
                PluginLoadInfo(
                    name=file_path.stem,
                    status=PluginLoadStatus.FAILED,
                    source=source,
                    error=tb.strip().splitlines()[-1] if tb.strip() else "模块执行异常",
                )
            )
            return None
        return self._extract_plugin_instance(module, file_path, source)

    def _extract_plugin_instance(
        self, module: ModuleType, file_path: Path, source: str
    ) -> LocalGameManagerPlugin | None:
        register = getattr(module, "register", None)
        if register is None or not callable(register):
            logger.error(
                "插件加载失败 [%s]: 模块缺少 register() 函数 — file=%s",
                file_path.stem,
                file_path,
            )
            self.load_info.append(
                PluginLoadInfo(
                    name=file_path.stem,
                    status=PluginLoadStatus.FAILED,
                    source=source,
                    error="模块缺少 register() 函数",
                )
            )
            return None
        try:
            plugin = register()
        except Exception:
            tb = traceback.format_exc()
            logger.error(
                "插件加载失败 [%s]: register() 调用异常\n%s",
                file_path.stem,
                tb,
            )
            self.load_info.append(
                PluginLoadInfo(
                    name=file_path.stem,
                    status=PluginLoadStatus.FAILED,
                    source=source,
                    error=tb.strip().splitlines()[-1] if tb.strip() else "register() 调用异常",
                )
            )
            return None
        if not isinstance(plugin, LocalGameManagerPlugin):
            logger.error(
                "插件加载失败 [%s]: register() 返回对象未实现 LocalGameManagerPlugin 协议 — type=%s",
                file_path.stem,
                type(plugin).__name__,
            )
            self.load_info.append(
                PluginLoadInfo(
                    name=file_path.stem,
                    status=PluginLoadStatus.FAILED,
                    source=source,
                    error="register() 返回对象未实现 LocalGameManagerPlugin 协议",
                )
            )
            return None
        return plugin

    def _append_plugin(
        self, plugin: LocalGameManagerPlugin, disabled_plugins: set[str], source: str
    ) -> None:
        if plugin.name not in self.available_plugin_names:
            self.available_plugin_names.append(plugin.name)
        if plugin.name in disabled_plugins:
            self.load_info.append(
                PluginLoadInfo(
                    name=plugin.name,
                    status=PluginLoadStatus.DISABLED,
                    source=source,
                )
            )
            return
        self.plugins.append(plugin)
        self.load_info.append(
            PluginLoadInfo(
                name=plugin.name,
                status=PluginLoadStatus.LOADED,
                source=source,
            )
        )
        logger.info("插件已加载: %s (来源: %s)", plugin.name, source)
