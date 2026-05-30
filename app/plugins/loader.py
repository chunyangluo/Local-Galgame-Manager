"""Discover and import plugin modules from builtin dir and user data/plugins."""

from __future__ import annotations

import importlib.util
import json
import logging
import traceback
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from app.plugins.base import PLUGIN_API_VERSION, LocalGameManagerPlugin

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PluginSource:
    path: Path
    source: str  # builtin | external
    package: bool


@dataclass
class ImportResult:
    plugin: LocalGameManagerPlugin | None
    module_name: str
    error: str | None = None
    manifest: dict[str, Any] | None = None


def discover_plugin_sources(builtin_dir: Path, external_dir: Path) -> list[PluginSource]:
    sources: list[PluginSource] = []

    if builtin_dir.is_dir():
        for file in sorted(builtin_dir.glob("*.py")):
            if file.name.startswith("_"):
                continue
            sources.append(PluginSource(path=file, source="builtin", package=False))

    external_dir.mkdir(parents=True, exist_ok=True)
    packaged_dirs: set[str] = set()

    for child in sorted(external_dir.iterdir()):
        if not child.is_dir() or child.name.startswith(("_", ".")):
            continue
        entry = _package_entry_file(child)
        if entry is not None:
            sources.append(PluginSource(path=entry, source="external", package=True))
            packaged_dirs.add(child.name)

    for file in sorted(external_dir.glob("*.py")):
        if file.name.startswith("_"):
            continue
        sources.append(PluginSource(path=file, source="external", package=False))

    return sources


def _package_entry_file(package_dir: Path) -> Path | None:
    manifest_path = package_dir / "plugin.json"
    if manifest_path.is_file():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            entry = str(data.get("entry") or "plugin.py").strip()
            candidate = package_dir / entry
            if candidate.is_file():
                return candidate
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("invalid plugin.json in %s: %s", package_dir, exc)
    for name in ("plugin.py", "__init__.py"):
        candidate = package_dir / name
        if candidate.is_file():
            return candidate
    return None


def read_manifest_for_source(src: PluginSource) -> dict[str, Any] | None:
    if not src.package:
        return None
    manifest_path = src.path.parent / "plugin.json"
    if not manifest_path.is_file():
        return None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def import_plugin_module(src: PluginSource) -> ImportResult:
    file_path = src.path
    module_name = f"lgm_plugin_{file_path.parent.name}_{file_path.stem}_{abs(hash(str(file_path)))}"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        return ImportResult(
            plugin=None,
            module_name=module_name,
            error="无法创建模块规格",
        )
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:
        tb = traceback.format_exc()
        return ImportResult(
            plugin=None,
            module_name=module_name,
            error=tb.strip().splitlines()[-1] if tb.strip() else "模块执行异常",
        )
    manifest = read_manifest_for_source(src)
    plugin = extract_plugin_instance(module, file_path)
    if plugin is None:
        return ImportResult(
            plugin=None,
            module_name=module_name,
            error="模块缺少 register() 或返回无效插件对象",
            manifest=manifest,
        )
    api_err = _check_api_version(plugin, manifest)
    if api_err:
        return ImportResult(
            plugin=None,
            module_name=module_name,
            error=api_err,
            manifest=manifest,
        )
    return ImportResult(plugin=plugin, module_name=module_name, manifest=manifest)


def extract_plugin_instance(
    module: ModuleType, file_path: Path
) -> LocalGameManagerPlugin | None:
    register = getattr(module, "register", None)
    if register is None or not callable(register):
        return None
    try:
        plugin = register()
    except Exception:
        logger.exception("register() failed for %s", file_path)
        return None
    name = getattr(plugin, "name", None)
    transform = getattr(plugin, "transform_scan_results", None)
    if not name or not callable(transform):
        return None
    return plugin  # type: ignore[return-value]


def _check_api_version(plugin: Any, manifest: dict[str, Any] | None) -> str | None:
    min_required = PLUGIN_API_VERSION
    if manifest and manifest.get("min_api_version") is not None:
        try:
            min_required = int(manifest["min_api_version"])
        except (TypeError, ValueError):
            pass
    plugin_api = int(getattr(plugin, "api_version", PLUGIN_API_VERSION) or PLUGIN_API_VERSION)
    if min_required > PLUGIN_API_VERSION:
        return f"插件需要 API v{min_required}，当前程序仅支持 v{PLUGIN_API_VERSION}"
    if plugin_api > PLUGIN_API_VERSION:
        return f"插件声明 api_version={plugin_api}，高于当前程序 v{PLUGIN_API_VERSION}"
    return None
