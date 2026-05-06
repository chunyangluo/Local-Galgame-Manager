from __future__ import annotations

from app.data.database import GameRecord


class SearchService:
    def filter_games(
        self,
        games: list[GameRecord],
        query: str = "",
        only_favorite: bool = False,
        category: str = "",
    ) -> list[GameRecord]:
        normalized_query = query.strip().lower()
        normalized_category = category.strip().lower()
        filtered: list[GameRecord] = []
        for game in games:
            if only_favorite and not game.favorite:
                continue
            if normalized_query and normalized_query not in game.name.lower():
                continue
            if normalized_category:
                categories = [c.strip().lower() for c in game.categories.split(",") if c.strip()]
                if normalized_category not in categories:
                    continue
            filtered.append(game)
        return filtered
