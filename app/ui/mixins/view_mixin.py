from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QListWidget, QListWidgetItem

from app.data.database import GameRecord
from app.ui.game_card_widget import GameCardWidget


class ViewMixin:
    _is_grid_view: bool
    _render_timer: QTimer
    _render_batch_size: int
    _render_index: int
    _render_total: int
    _highlight_timer: QTimer
    _highlight_phase: bool
    _cover_retry_failed: set[int]
    games_cache: list[GameRecord]
    filtered_games: list[GameRecord]
    search_input: object
    favorite_only: object
    search_service: object
    status: object
    empty_hint: object
    btn_add_root: object
    btn_toggle_view: object
    games_list: QListWidget
    _game_paged_grid: object
    _library_stack: object

    def _apply_filters(self) -> None:
        self.filtered_games = self.search_service.filter_games(
            self.games_cache,
            query=self.search_input.text(),
            only_favorite=self.favorite_only.isChecked(),
        )
        self._refresh_library_view()
        self._update_empty_state()
        self._update_action_state()

    def _refresh_library_view(self) -> None:
        if self._is_grid_view:
            if self._render_timer.isActive():
                self._render_timer.stop()
            self.games_list.clear()
            self._library_stack.setCurrentWidget(self._game_paged_grid)
            self._game_paged_grid.set_games(
                self.filtered_games,
                cover_retry_failed=self._cover_retry_failed,
                on_retry_cover=lambda gid: self._request_cover_refetch(gid, user_triggered=False),
            )
            n = len(self.filtered_games)
            self.status.setText(f"共 {n} / {len(self.games_cache)} 个游戏")
        else:
            self._library_stack.setCurrentWidget(self.games_list)
            self._start_incremental_render()

    def _start_incremental_render(self) -> None:
        if self._render_timer.isActive():
            self._render_timer.stop()
        self.games_list.clear()
        self._render_index = 0
        self._render_total = len(self.filtered_games)
        if self._render_total == 0:
            self.status.setText(f"共 0 / {len(self.games_cache)} 个游戏")
            return
        self.status.setText(f"正在渲染 0/{self._render_total} ...")
        self._render_next_batch()

    def _render_next_batch(self) -> None:
        if self._render_index >= self._render_total:
            self.status.setText(f"共 {self._render_total} / {len(self.games_cache)} 个游戏")
            return
        end = min(self._render_index + self._render_batch_size, self._render_total)
        for idx in range(self._render_index, end):
            game = self.filtered_games[idx]
            item = QListWidgetItem()
            item.setSizeHint(QSize(300, 320))
            item.setData(Qt.UserRole, game.id)
            self.games_list.addItem(item)
            card = GameCardWidget(game)
            if game.id in self._cover_retry_failed:
                card.force_no_cover_placeholder()
            card.retry_cover_requested.connect(
                lambda gid, self=self: self._request_cover_refetch(gid, user_triggered=False)
            )
            self.games_list.setItemWidget(item, card)
        self._render_index = end
        if self._render_index < self._render_total:
            self.status.setText(f"正在渲染 {self._render_index}/{self._render_total} ...")
            self._render_timer.start(0)
        else:
            self.status.setText(f"共 {self._render_total} / {len(self.games_cache)} 个游戏")

    def _selected_game(self) -> GameRecord | None:
        if self._is_grid_view:
            gid = self._game_paged_grid.selected_game_id()
            if gid is None:
                return None
            for g in self.filtered_games:
                if g.id == gid:
                    return g
            return None
        index = self.games_list.currentRow()
        if index < 0:
            return None
        if index >= len(self.filtered_games):
            return None
        return self.filtered_games[index]

    def _show_selected(self) -> None:
        game = self._selected_game()
        if game is None:
            self._update_action_state()
            return
        self.status.setText(
            f"{game.name} | 最近游玩: {game.last_played_at or '无'} | 分类: {game.categories or '无'}"
        )
        self._update_action_state()

    def _message_box_parent(self, explicit):
        if explicit is not None:
            return explicit
        app = QApplication.instance()
        if app is not None:
            active = app.activeWindow()
            if active is not None:
                return active
        return self

    def _toggle_view_mode(self) -> None:
        self._is_grid_view = not self._is_grid_view
        self.btn_toggle_view.setChecked(self._is_grid_view)
        self.btn_toggle_view.setProperty("active", self._is_grid_view)
        self.btn_toggle_view.style().unpolish(self.btn_toggle_view)
        self.btn_toggle_view.style().polish(self.btn_toggle_view)
        if self._is_grid_view:
            self.btn_toggle_view.setText("网格视图")
        else:
            self.games_list.setViewMode(QListWidget.ListMode)
            self.games_list.setGridSize(QSize())
            self.games_list.setWordWrap(False)
            self.games_list.setSpacing(10)
            self.btn_toggle_view.setText("列表视图")
        self._apply_filters()

    def _update_empty_state(self) -> None:
        has_games = len(self.filtered_games) > 0
        self.empty_hint.setVisible(not has_games)
        if has_games:
            self._highlight_timer.stop()
            self.btn_add_root.setProperty("highlighted", False)
            self.btn_add_root.style().unpolish(self.btn_add_root)
            self.btn_add_root.style().polish(self.btn_add_root)
        elif not self._highlight_timer.isActive():
            self._highlight_timer.start()

    def _pulse_add_root_button(self) -> None:
        if len(self.filtered_games) > 0:
            return
        self._highlight_phase = not self._highlight_phase
        self.btn_add_root.setProperty("highlighted", self._highlight_phase)
        self.btn_add_root.style().unpolish(self.btn_add_root)
        self.btn_add_root.style().polish(self.btn_add_root)
        self.empty_hint.setProperty("guided", self._highlight_phase)
        self.empty_hint.style().unpolish(self.empty_hint)
        self.empty_hint.style().polish(self.empty_hint)
        if self._highlight_phase:
            self.empty_hint.setText(
                "还没有游戏？在第一行「库」分组中点击【添加目录】导入游戏文件夹\n"
                ">> 点击【添加目录】开始导入 <<"
            )
        else:
            self.empty_hint.setText(
                "还没有游戏？在第一行「库」分组中点击【添加目录】导入游戏文件夹\n"
                "   点击【添加目录】开始导入   "
            )

    def _update_action_state(self) -> None:
        has_selection = self._selected_game() is not None
        self.btn_refresh.setEnabled(True)
        if has_selection:
            if self._is_grid_view:
                self._game_paged_grid.set_focus_chain()
            else:
                self.games_list.setFocus()

    def _show_game_context_menu(self, pos) -> None:
        item = self.games_list.itemAt(pos)
        if item is None:
            item = self.games_list.itemAt(self.games_list.viewport().mapFromGlobal(QCursor.pos()))
        if item is None:
            item = self.games_list.currentItem()
        if item is None:
            return
        self.games_list.setCurrentItem(item)
        raw = item.data(Qt.ItemDataRole.UserRole)
        if raw is None:
            raw = item.data(Qt.UserRole)
        if raw is None:
            return
        try:
            game_id = int(raw)
        except (TypeError, ValueError):
            return
        self._exec_game_context_menu_for_id(game_id, QCursor.pos())

    def _open_game_context_menu_by_id(self, game_id: int, global_pos) -> None:
        self._exec_game_context_menu_for_id(game_id, global_pos)
