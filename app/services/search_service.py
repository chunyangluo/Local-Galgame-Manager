from __future__ import annotations

from app.data.database import GameRecord


class SearchService:
    def filter_games(
        self,
        games: list[GameRecord],
        query: str = "",
        only_favorite: bool = False,
        category: str = "",
        play_state: str = "",
        sort_by: str = "",
        exclude_hidden: bool = True,
    ) -> list[GameRecord]:
        normalized_query = query.strip().lower()
        normalized_category = category.strip().lower()
        normalized_state = play_state.strip().lower()
        filtered: list[GameRecord] = []
        for game in games:
            if exclude_hidden and getattr(game, "hidden", False):
                continue
            if only_favorite and not game.favorite:
                continue
            if normalized_state == "played" and int(game.play_count or 0) <= 0:
                continue
            if normalized_state == "unplayed" and int(game.play_count or 0) > 0:
                continue
            if normalized_state == "favorite" and not game.favorite:
                continue
            if normalized_query:
                # 搜索所有可能的标题字段
                search_targets = [
                    game.name.lower(),
                    (game.title_localized or "").lower(),
                    (game.title_original or "").lower(),
                ]
                # 如果有窗口标题也加入搜索
                if hasattr(game, "window_title") and game.window_title:
                    search_targets.append(game.window_title.lower())
                # 检查是否有任何目标匹配
                found = False
                for target in search_targets:
                    if normalized_query in target:
                        found = True
                        break
                if not found:
                    continue
            if normalized_category:
                categories = [c.strip().lower() for c in game.categories.split(",") if c.strip()]
                if normalized_category not in categories:
                    continue
            filtered.append(game)
        return self._sort_games(filtered, sort_by.strip().lower())

    def _sort_games(self, games: list[GameRecord], sort_by: str) -> list[GameRecord]:
        if not sort_by or sort_by == "default":
            return games
        if sort_by == "added_desc":
            return sorted(games, key=lambda g: int(g.id), reverse=True)
        if sort_by == "added_asc":
            return sorted(games, key=lambda g: int(g.id))
        if sort_by == "name":
            return sorted(games, key=lambda g: g.name.lower())
        if sort_by == "play_count":
            return sorted(games, key=lambda g: int(g.play_count or 0), reverse=True)
        if sort_by == "last_played":
            return sorted(
                games,
                key=lambda g: (g.last_played_at or ""),
                reverse=True,
            )
        return games
