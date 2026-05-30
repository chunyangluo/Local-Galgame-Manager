from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThreadPool, Qt

from app.ui.game_card_widget import GameCardWidget
from app.workers import CoverRefetchTask


class CoverMixin:
    _cover_retry_pool: QThreadPool
    _cover_retry_pending: set[int]
    _cover_retry_failed: set[int]
    _cover_retry_startup_running: bool
    _cover_retry_startup_total: int
    _cover_retry_startup_done: int
    _cover_retry_startup_success: int
    db: object
    cover_manager: object
    games_cache: list
    status: object
    cover_fetch_mode: str
    btn_online_cover: object

    COVER_FETCH_MODE_ORDER = ("local_only", "local_prefer", "online_prefer")
    COVER_FETCH_MODE_LABELS = {
        "local_only": "封面策略: 仅本地",
        "local_prefer": "封面策略: 本地优先",
        "online_prefer": "封面策略: 网图优先",
    }

    def _startup_auto_fix_covers(self) -> None:
        if self._scan_running:
            return
        if not self.games_cache:
            self.refresh_games()
        targets = [
            game
            for game in self.games_cache
            if game.image_url
            and game.image_url.startswith(("http://", "https://"))
            and (not game.cover_path or not Path(game.cover_path).exists())
        ]
        if not targets:
            return
        self._cover_retry_startup_running = True
        self._cover_retry_startup_total = len(targets)
        self._cover_retry_startup_done = 0
        self._cover_retry_startup_success = 0
        self.status.setText(f"启动自动修复封面：0/{len(targets)}")
        for game in targets:
            self._request_cover_refetch(game.id, user_triggered=False)

    def _request_cover_refetch(self, game_id: int, user_triggered: bool = True) -> None:
        if game_id in self._cover_retry_pending:
            return
        game = next((g for g in self.games_cache if g.id == game_id), None)
        if game is None:
            game = self.db.get_game_by_id(self.current_user_id, game_id)
        if game is None or not game.image_url:
            return
        if not game.image_url.startswith(("http://", "https://")):
            return
        self._cover_retry_pending.add(game_id)
        self._set_card_cover_loading(game_id, True)
        task = CoverRefetchTask(
            game_id=game.id,
            vndb_id=game.vndb_id,
            image_url=game.image_url,
            game_name=game.name,
            cover_manager=self.cover_manager,
        )
        task.signals.finished.connect(
            lambda gid, path, ok: self._on_cover_refetch_finished(gid, path, ok, user_triggered),
            Qt.QueuedConnection,
        )
        self._cover_retry_pool.start(task)

    def _on_cover_refetch_finished(
        self, game_id: int, cover_path: str, success: bool, user_triggered: bool
    ) -> None:
        self._cover_retry_pending.discard(game_id)
        self._set_card_cover_loading(game_id, False)
        game = next((g for g in self.games_cache if g.id == game_id), None)
        if game is None:
            game = self.db.get_game_by_id(self.current_user_id, game_id)
        if success:
            self._cover_retry_failed.discard(game_id)
            self.db.update_game_cover_path(game_id, cover_path)
        else:
            local_cover = None
            if game is not None:
                local_cover, _ = self.cover_manager.find_cover_local(game.root_dir, game.name)
            if local_cover:
                self._cover_retry_failed.discard(game_id)
                self.db.update_game_cover_path(game_id, local_cover)
                success = True
                cover_path = local_cover
            else:
                self._cover_retry_failed.add(game_id)

        if self._cover_retry_startup_running:
            self._cover_retry_startup_done += 1
            if success:
                self._cover_retry_startup_success += 1
            if self._cover_retry_startup_done < self._cover_retry_startup_total:
                self.status.setText(
                    f"启动自动修复封面：{self._cover_retry_startup_done}/{self._cover_retry_startup_total}"
                )
            else:
                self._cover_retry_startup_running = False
                self.refresh_games()
                self.status.setText(
                    f"启动自动修复封面完成：成功 {self._cover_retry_startup_success}/{self._cover_retry_startup_total}"
                )
                self._cover_toast(
                    f"封面修复完成：{self._cover_retry_startup_success}/{self._cover_retry_startup_total}",
                    "success" if self._cover_retry_startup_success else "info",
                )
                return

        if user_triggered:
            if success:
                self.refresh_games()
                self.status.setText("封面已重新获取")
                self._cover_toast("封面修复成功", "success")
            else:
                self.refresh_games()
                self.status.setText("重新获取封面失败，已标记为暂无封面")
                self._cover_toast("封面修复失败，可右键手动添加封面", "warning")

    def _toggle_online_cover(self) -> None:
        current_index = self.COVER_FETCH_MODE_ORDER.index(self.cover_fetch_mode)
        next_mode = self.COVER_FETCH_MODE_ORDER[(current_index + 1) % len(self.COVER_FETCH_MODE_ORDER)]
        self.cover_fetch_mode = next_mode
        self.cover_manager.cover_fetch_mode = next_mode
        self.db.set_cover_fetch_mode(next_mode)
        self._apply_cover_fetch_mode_ui()
        if next_mode == "local_only":
            self.status.setText("封面策略已切换：仅本地")
        elif next_mode == "local_prefer":
            self.status.setText("封面策略已切换：本地优先（低置信度时联网）")
        else:
            self.status.setText("封面策略已切换：网图优先")

    def _apply_cover_fetch_mode_ui(self) -> None:
        label = self.COVER_FETCH_MODE_LABELS.get(self.cover_fetch_mode, "封面策略: 本地优先")
        self.btn_online_cover.setText(label)

    def set_custom_cover_for_game_id(self, game_id: int) -> bool:
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        game = self.db.get_game_by_id(self.current_user_id, game_id)
        if game is None:
            return False
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择封面", "", "Images (*.png *.jpg *.jpeg *.webp)"
        )
        if not file_path:
            return False
        try:
            cover = self.cover_manager.import_custom_cover(game_id, file_path)
            self.db.update_game_custom_cover(game_id, cover)
            self.refresh_games()
            self.status.setText("封面已更新")
        except Exception as exc:
            QMessageBox.critical(self, "封面更新失败", str(exc))
            return False
        return True

    def _cover_toast(self, message: str, level: str = "info") -> None:
        fn = getattr(self, "show_toast", None)
        if callable(fn):
            fn(message, level)

    def _set_card_cover_loading(self, game_id: int, loading: bool) -> None:
        if getattr(self, "_is_grid_view", False) and hasattr(self, "_game_paged_grid"):
            card = self._game_paged_grid.card_for_game_id(game_id)
            if card is not None:
                card.set_cover_loading(loading)
                return
        games_list = getattr(self, "games_list", None)
        if games_list is None:
            return
        for i in range(games_list.count()):
            item = games_list.item(i)
            if item is None or item.data(Qt.UserRole) != game_id:
                continue
            widget = games_list.itemWidget(item)
            if isinstance(widget, GameCardWidget):
                widget.set_cover_loading(loading)
            break

    def retry_cover_for_game_id(self, game_id: int) -> bool:
        game = self.db.get_game_by_id(self.current_user_id, game_id)
        if game is None:
            return False
        if not game.image_url or not game.image_url.startswith(("http://", "https://")):
            self.status.setText("当前游戏没有可重试的在线封面来源")
            return False
        self._cover_retry_failed.discard(game_id)
        self._request_cover_refetch(game_id, user_triggered=True)
        return True
