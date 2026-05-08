from __future__ import annotations

import sys
import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QMessageBox

from app.plugins.manager import PluginManager
from app.services.app_data_dir import get_app_data_dir
from app.ui.main_window import MainWindow


def _write_startup_log(data_dir: Path, title: str, detail: str) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    log_path = data_dir / "startup.log"
    payload = (
        f"[{datetime.now().isoformat(timespec='seconds')}] {title}\n"
        f"{detail}\n"
        f"{'-' * 72}\n"
    )
    with log_path.open("a", encoding="utf-8") as fp:
        fp.write(payload)


def main() -> int:
    data_dir = get_app_data_dir()
    app = QApplication(sys.argv)

    try:
        plugin_manager = PluginManager(data_dir)
        window = MainWindow(data_dir, plugin_manager=plugin_manager)
        window.showMaximized()
        return app.exec()
    except Exception as exc:  # pragma: no cover
        detail = "".join(traceback.format_exception(exc))
        _write_startup_log(data_dir, "Startup crash", detail)
        QMessageBox.critical(
            None,
            "Local Galgame Manager 启动失败",
            f"程序启动异常，已写入日志：{data_dir / 'startup.log'}",
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
