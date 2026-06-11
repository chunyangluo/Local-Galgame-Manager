from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal

from app.core.scanner import GameScanner
from app.plugins.manager import PluginManager


class ScanWorker(QObject):
    progress = Signal(int, int, int, str)
    finished = Signal(object, object, int, str)

    def __init__(
        self,
        roots: list[str],
        scanner: GameScanner,
        plugin_manager: PluginManager,
    ) -> None:
        super().__init__()
        self.roots = roots
        self.scanner = scanner
        self.plugin_manager = plugin_manager
        self._cancel_requested = False

    def run(self) -> None:
        try:
            imported = 0
            rows: list[tuple[str, str, str, str]] = []
            total_roots = len(self.roots)
            for idx, root in enumerate(self.roots, start=1):
                if self._cancel_requested:
                    self.finished.emit(self.roots, rows, imported, "__CANCELLED__")
                    return
                results = self.scanner.scan_root(root)
                results = self.plugin_manager.transform_scan_results(root=root, results=results)
                for result in results:
                    if self._cancel_requested:
                        self.finished.emit(self.roots, rows, imported, "__CANCELLED__")
                        return
                    rows.append((result.game_name, result.game_dir, result.launch_exe, result.content_type))
                    imported += 1
                self.progress.emit(idx, total_roots, imported, root)
            self.finished.emit(self.roots, rows, imported, "")
        except Exception as exc:  # pragma: no cover
            self.finished.emit(self.roots, [], 0, str(exc))

    def request_cancel(self) -> None:
        self._cancel_requested = True
