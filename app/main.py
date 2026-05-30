from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QMessageBox

from app.services.app_branding import APP_DISPLAY_NAME, setup_app_branding
from app.services.logging_setup import log_file_path, setup_logging
from app.plugins.manager import PluginManager
from app.services.app_data_dir import get_app_data_dir
from app.ui.main_window import MainWindow


def main() -> int:
    data_dir = get_app_data_dir()
    setup_logging(data_dir=data_dir)
    log = logging.getLogger(__name__)
    app = QApplication(sys.argv)
    setup_app_branding(app)

    try:
        plugin_manager = PluginManager(data_dir)
        window = MainWindow(data_dir, plugin_manager=plugin_manager)
        window.showMaximized()
        log.info("Application UI started (data_dir=%s)", data_dir)
        return app.exec()
    except Exception:  # pragma: no cover
        log.exception("Startup crash")
        QMessageBox.critical(
            None,
            f"{APP_DISPLAY_NAME} 启动失败",
            f"程序启动异常，详情见日志：\n{log_file_path(data_dir)}",
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
