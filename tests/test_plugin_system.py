from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from app.core.scanner import ScanResult
from app.data.database import Database
from app.plugins.base import BasePlugin, LaunchDecision, PluginContext
from app.plugins.loader import discover_plugin_sources, import_plugin_module
from app.plugins.manager import PluginManager


class _FilterPlugin(BasePlugin):
    name = "test_filter"
    version = "1.0.0"

    def should_include_scan_result(self, *, root, item, context) -> bool:
        return "skip" not in item.game_dir.lower()


class _LaunchPlugin(BasePlugin):
    name = "test_launch"
    version = "1.0.0"

    def modify_launch(self, **kwargs):
        return LaunchDecision(
            launch_exe=kwargs["launch_exe"],
            locale_emulator=kwargs["locale_emulator"],
            as_admin=True,
        )


def test_discover_package_plugin(tmp_path: Path) -> None:
    pkg = tmp_path / "plugins" / "hello"
    pkg.mkdir(parents=True)
    (pkg / "plugin.json").write_text(
        '{"name":"hello","entry":"plugin.py","min_api_version":1}',
        encoding="utf-8",
    )
    (pkg / "plugin.py").write_text(
        "from app.plugins.base import BasePlugin\n"
        "from app.core.scanner import ScanResult\n"
        "class HelloPlugin(BasePlugin):\n"
        "    name='hello'\n"
        "    def transform_scan_results(self,*,root,results,context):\n"
        "        return results\n"
        "def register():\n"
        "    return HelloPlugin()\n",
        encoding="utf-8",
    )
    sources = discover_plugin_sources(tmp_path / "builtin", tmp_path / "plugins")
    assert any(s.package and s.path.name == "plugin.py" for s in sources)
    result = import_plugin_module(sources[-1])
    assert result.plugin is not None
    assert result.plugin.name == "hello"


def test_manager_scan_filter_and_launch(tmp_path: Path) -> None:
    mgr = PluginManager(tmp_path)
    mgr.plugins = [_FilterPlugin(), _LaunchPlugin()]
    mgr.context = PluginContext(data_dir=str(tmp_path))

    rows = [
        ScanResult("A", r"C:\games\ok", r"C:\games\ok\a.exe"),
        ScanResult("B", r"C:\games\skip_me", r"C:\games\skip_me\b.exe"),
    ]
    out = mgr.transform_scan_results(root=r"C:\games", results=rows)
    assert len(out) == 1
    assert "ok" in out[0].game_dir

    decision = mgr.modify_launch(
        game_id=1,
        game_name="A",
        launch_exe=r"C:\games\ok\a.exe",
        locale_emulator=False,
        as_admin=False,
    )
    assert decision.as_admin is True


def test_plugin_configs_in_db(db: Database) -> None:
    db.set_plugin_config("prefix_name", {"prefix": "[TEST]"})
    assert db.get_plugin_config("prefix_name") == {"prefix": "[TEST]"}


def test_ensure_examples_installed(tmp_path: Path) -> None:
    mgr = PluginManager(tmp_path)
    installed = mgr.ensure_examples_installed()
    assert installed or (mgr.examples_dir.is_dir() and any(mgr.plugin_dir.iterdir()))
