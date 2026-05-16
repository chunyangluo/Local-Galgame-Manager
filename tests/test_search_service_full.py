from __future__ import annotations

import pytest

from app.data.database import GameRecord
from app.services.search_service import SearchService


def _game(
    gid: int = 1,
    name: str = "Game",
    favorite: bool = False,
    categories: str = "",
) -> GameRecord:
    return GameRecord(
        id=gid,
        name=name,
        root_dir=f"/games/{name}",
        launch_exe=f"/games/{name}/game.exe",
        cover_path=None,
        favorite=favorite,
        categories=categories,
        last_played_at=None,
        play_count=0,
        total_play_seconds=0,
    )


class TestFilterByQuery:
    def test_empty_query_returns_all(self) -> None:
        svc = SearchService()
        games = [_game(1, "Alpha"), _game(2, "Beta")]
        assert len(svc.filter_games(games)) == 2

    def test_case_insensitive(self) -> None:
        svc = SearchService()
        games = [_game(1, "RIDDLE JOKER")]
        result = svc.filter_games(games, query="riddle")
        assert len(result) == 1

    def test_partial_match(self) -> None:
        svc = SearchService()
        games = [_game(1, "Making Lovers"), _game(2, "Lovers Again")]
        result = svc.filter_games(games, query="lover")
        assert len(result) == 2

    def test_no_match(self) -> None:
        svc = SearchService()
        games = [_game(1, "Alpha")]
        result = svc.filter_games(games, query="zzz")
        assert len(result) == 0

    def test_whitespace_query(self) -> None:
        svc = SearchService()
        games = [_game(1, "Alpha")]
        result = svc.filter_games(games, query="  ")
        assert len(result) == 1


class TestFilterByFavorite:
    def test_only_favorite(self) -> None:
        svc = SearchService()
        games = [_game(1, "Fav", favorite=True), _game(2, "NotFav", favorite=False)]
        result = svc.filter_games(games, only_favorite=True)
        assert len(result) == 1
        assert result[0].name == "Fav"

    def test_no_favorites(self) -> None:
        svc = SearchService()
        games = [_game(1, "A", favorite=False), _game(2, "B", favorite=False)]
        result = svc.filter_games(games, only_favorite=True)
        assert len(result) == 0


class TestFilterByCategory:
    def test_category_match(self) -> None:
        svc = SearchService()
        games = [_game(1, "Game1", categories="RPG,ADV"), _game(2, "Game2", categories="ADV")]
        result = svc.filter_games(games, category="RPG")
        assert len(result) == 1
        assert result[0].name == "Game1"

    def test_category_case_insensitive(self) -> None:
        svc = SearchService()
        games = [_game(1, "Game1", categories="RPG")]
        result = svc.filter_games(games, category="rpg")
        assert len(result) == 1

    def test_category_no_match(self) -> None:
        svc = SearchService()
        games = [_game(1, "Game1", categories="RPG")]
        result = svc.filter_games(games, category="FPS")
        assert len(result) == 0

    def test_empty_category_returns_all(self) -> None:
        svc = SearchService()
        games = [_game(1, "A", categories="RPG"), _game(2, "B")]
        result = svc.filter_games(games, category="")
        assert len(result) == 2


class TestCombinedFilters:
    def test_query_and_favorite(self) -> None:
        svc = SearchService()
        games = [
            _game(1, "RIDDLE JOKER", favorite=True),
            _game(2, "Making Lovers", favorite=False),
            _game(3, "RIDDLE FIELD", favorite=False),
        ]
        result = svc.filter_games(games, query="riddle", only_favorite=True)
        assert len(result) == 1
        assert result[0].name == "RIDDLE JOKER"

    def test_query_and_category(self) -> None:
        svc = SearchService()
        games = [
            _game(1, "Alpha", categories="RPG"),
            _game(2, "Alpha Beta", categories="ADV"),
        ]
        result = svc.filter_games(games, query="alpha", category="RPG")
        assert len(result) == 1
        assert result[0].name == "Alpha"

    def test_all_filters(self) -> None:
        svc = SearchService()
        games = [
            _game(1, "Alpha", favorite=True, categories="RPG"),
            _game(2, "Alpha Beta", favorite=False, categories="RPG"),
            _game(3, "Alpha Gamma", favorite=True, categories="ADV"),
        ]
        result = svc.filter_games(games, query="alpha", only_favorite=True, category="RPG")
        assert len(result) == 1
        assert result[0].name == "Alpha"
