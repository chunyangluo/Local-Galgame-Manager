from __future__ import annotations

import sys
from pathlib import Path


def test_get_all_with_stats_reuses_password_ordering(tmp_path: Path) -> None:
    tool_root = Path(__file__).resolve().parents[1] / "integrations" / "自动化解压工具"
    sys.path.insert(0, str(tool_root))
    previous_settings = None
    try:
        from core import config as tool_config
        from core.password_manager import PasswordManager

        previous_settings = tool_config._settings
        config_path = tmp_path / "config" / "config.yaml"
        config_path.parent.mkdir(parents=True)
        passwords_path = tmp_path / "passwords.json"
        config_path.write_text(
            "passwords:\n"
            f"  file: {passwords_path.as_posix()!r}\n",
            encoding="utf-8",
        )

        tool_config.init_settings(config_path)
        manager = PasswordManager()
        manager.add_password("alpha")
        manager.add_password("beta")
        manager.record_success("one.zip", "beta")
        manager.record_success("two.zip", "beta")

        items = manager.get_all_with_stats()

        assert [item["password"] for item in items] == ["beta", "alpha"]
        assert items[0]["success_count"] == 2
    finally:
        if "core.config" in sys.modules:
            sys.modules["core.config"]._settings = previous_settings
        try:
            sys.path.remove(str(tool_root))
        except ValueError:
            pass
