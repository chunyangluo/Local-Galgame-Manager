from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.services.path_utils import is_path_under_root, normalize_game_dir


def test_normalize_game_dir_stable_for_same_path(tmp_path: Path) -> None:
    game = tmp_path / "MyGame"
    game.mkdir()
    a = normalize_game_dir(game)
    b = normalize_game_dir(str(game).replace("\\", "/") if os.sep == "\\" else game)
    assert a == b


def test_is_path_under_root_rejects_sibling_prefix(tmp_path: Path) -> None:
    root = tmp_path / "Game"
    sibling = tmp_path / "Games" / "Title"
    root.mkdir()
    sibling.mkdir(parents=True)
    assert is_path_under_root(sibling, root) is False
    assert is_path_under_root(root / "sub", root) is True


def test_delete_games_not_in_scan_no_false_positive_on_similar_prefix(
    db_with_user: tuple, tmp_path: Path
) -> None:
    from app.data.database import Database

    db, uid = db_with_user
    short_root = tmp_path / "Game"
    long_game = tmp_path / "Games" / "Title"
    short_root.mkdir()
    long_game.mkdir(parents=True)
    db.upsert_game("Wrong", str(long_game), str(long_game / "g.exe"))
    deleted = db.delete_games_not_in_scan([str(short_root)], {str(short_root / "other")})
    assert deleted == 0
    assert len(db.list_games(uid)) == 1
