from app.data.database import GameRecord
from app.services.search_service import SearchService


def test_filter_favorite_and_query() -> None:
    service = SearchService()
    games = [
        GameRecord(1, "RIDDLE JOKER", "a", "a.exe", None, True, "校园", None, 1, 100),
        GameRecord(2, "Making Lovers", "b", "b.exe", None, False, "恋爱", None, 1, 100),
    ]
    result = service.filter_games(games, query="riddle", only_favorite=True)
    assert len(result) == 1
    assert result[0].name == "RIDDLE JOKER"
