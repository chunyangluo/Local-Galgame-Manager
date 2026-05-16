from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.data.database import Database


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return Database(tmp_path / "test_db")


@pytest.fixture
def db_with_user(db: Database) -> tuple[Database, int]:
    user_id = db.ensure_default_user()
    return db, user_id


@pytest.fixture
def game_dir(tmp_path: Path) -> Path:
    d = tmp_path / "MyGame"
    d.mkdir()
    exe = d / "Game.exe"
    exe.write_bytes(b"\x00" * 1024)
    return d


@pytest.fixture
def scanner_root(tmp_path: Path) -> Path:
    root = tmp_path / "gamedata"
    root.mkdir()
    return root
