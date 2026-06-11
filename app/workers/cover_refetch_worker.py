from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal

from app.services.cover_manager import CoverManager


class CoverRefetchSignals(QObject):
    finished = Signal(int, str, bool)


class CoverRefetchTask(QRunnable):
    def __init__(
        self,
        game_id: int,
        vndb_id: str | None,
        image_url: str,
        game_name: str,
        cover_manager: CoverManager,
    ) -> None:
        super().__init__()
        self.signals = CoverRefetchSignals()
        self._game_id = game_id
        self._vndb_id = vndb_id
        self._image_url = image_url
        self._game_name = game_name
        self._cover_manager = cover_manager

    def run(self) -> None:  # type: ignore[override]
        cache_key = self._vndb_id or f"game_{self._game_id}"
        try:
            cached = self._cover_manager.cache_cover_with_fallback(
                image_url=self._image_url,
                cache_key=cache_key,
                game_name=self._game_name,
            )
            ok = bool(cached and Path(cached).exists())
            self.signals.finished.emit(self._game_id, cached or "", ok)
        except Exception:
            self.signals.finished.emit(self._game_id, "", False)
