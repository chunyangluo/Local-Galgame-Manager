from __future__ import annotations

import struct
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from app.core.cover_manager import (
    CoverManager,
    read_image_size_fast,
    _read_jpeg_size,
    _read_png_size,
    _read_webp_size,
    PRIORITY_DIR_WHITELIST,
    DIR_BLACKLIST,
)


def _make_jpeg(path: Path, width: int = 800, height: int = 600) -> Path:
    img = Image.new("RGB", (width, height), (100, 150, 200))
    img.save(path, "JPEG", quality=90)
    return path


def _make_png(path: Path, width: int = 800, height: int = 600) -> Path:
    img = Image.new("RGB", (width, height), (100, 150, 200))
    img.save(path, "PNG")
    return path


def _make_webp(path: Path, width: int = 800, height: int = 600) -> Path:
    img = Image.new("RGB", (width, height), (100, 150, 200))
    img.save(path, "WEBP", quality=90)
    return path


class TestReadImageSizeFast:
    def test_jpeg(self, tmp_path: Path) -> None:
        p = _make_jpeg(tmp_path / "test.jpg", 640, 480)
        result = read_image_size_fast(p)
        assert result is not None
        assert result[0] == 640
        assert result[1] == 480

    def test_png(self, tmp_path: Path) -> None:
        p = _make_png(tmp_path / "test.png", 1024, 768)
        result = read_image_size_fast(p)
        assert result is not None
        assert result[0] == 1024
        assert result[1] == 768

    def test_webp(self, tmp_path: Path) -> None:
        p = _make_webp(tmp_path / "test.webp", 500, 400)
        result = read_image_size_fast(p)
        assert result is not None
        assert result[0] == 500
        assert result[1] == 400

    def test_non_image_returns_none(self, tmp_path: Path) -> None:
        p = tmp_path / "test.txt"
        p.write_text("hello", encoding="utf-8")
        assert read_image_size_fast(p) is None

    def test_small_file_returns_none(self, tmp_path: Path) -> None:
        p = tmp_path / "tiny.jpg"
        p.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 10)
        result = _read_jpeg_size(p.read_bytes())
        assert result is None


class TestCoverManagerInit:
    def test_creates_cache_dirs(self, tmp_path: Path) -> None:
        mgr = CoverManager(tmp_path / "covers")
        assert (tmp_path / "covers").is_dir()
        assert (tmp_path / "covers" / "online").is_dir()


class TestFindCoverLocal:
    def test_finds_cover_in_root(self, tmp_path: Path) -> None:
        game_dir = tmp_path / "game"
        game_dir.mkdir()
        _make_jpeg(game_dir / "cover.jpg", 600, 800)
        mgr = CoverManager(tmp_path / "cache")
        path, score = mgr.find_cover_local(str(game_dir), "game")
        assert path is not None
        assert "cover" in Path(path).name.lower()

    def test_finds_cover_in_cover_subdir(self, tmp_path: Path) -> None:
        game_dir = tmp_path / "game"
        cover_dir = game_dir / "cover"
        cover_dir.mkdir(parents=True)
        _make_jpeg(cover_dir / "title.jpg", 600, 800)
        mgr = CoverManager(tmp_path / "cache")
        path, score = mgr.find_cover_local(str(game_dir), "game")
        assert path is not None

    def test_no_images_returns_none(self, tmp_path: Path) -> None:
        game_dir = tmp_path / "game"
        game_dir.mkdir()
        (game_dir / "readme.txt").write_text("info", encoding="utf-8")
        mgr = CoverManager(tmp_path / "cache")
        path, score = mgr.find_cover_local(str(game_dir), "game")
        assert path is None
        assert score < 0

    def test_nonexistent_dir_returns_none(self, tmp_path: Path) -> None:
        mgr = CoverManager(tmp_path / "cache")
        path, score = mgr.find_cover_local("/nonexistent_dir_xyz", "game")
        assert path is None

    def test_prefers_game_keyword_in_name(self, tmp_path: Path) -> None:
        game_dir = tmp_path / "MyGalgame"
        game_dir.mkdir()
        _make_jpeg(game_dir / "MyGalgame.jpg", 600, 800)
        _make_jpeg(game_dir / "random.jpg", 600, 800)
        mgr = CoverManager(tmp_path / "cache")
        path, score = mgr.find_cover_local(str(game_dir), "MyGalgame")
        assert path is not None
        assert "mygalgame" in Path(path).name.lower()

    def test_blacklist_dir_excluded(self, tmp_path: Path) -> None:
        game_dir = tmp_path / "game"
        save_dir = game_dir / "save"
        save_dir.mkdir(parents=True)
        _make_jpeg(save_dir / "image.jpg", 600, 800)
        game_dir_img = game_dir / "title.jpg"
        _make_jpeg(game_dir_img, 600, 800)
        mgr = CoverManager(tmp_path / "cache")
        path, score = mgr.find_cover_local(str(game_dir), "game")
        assert path is not None
        assert Path(path).parent.name != "save"

    def test_tiny_image_low_score(self, tmp_path: Path) -> None:
        game_dir = tmp_path / "game"
        game_dir.mkdir()
        img = Image.new("RGB", (50, 50), (128, 128, 128))
        img.save(game_dir / "cover.jpg", "JPEG")
        mgr = CoverManager(tmp_path / "cache")
        path, score = mgr.find_cover_local(str(game_dir), "game")
        assert score <= -500


class TestExtractGameKeywords:
    def test_basic(self, tmp_path: Path) -> None:
        mgr = CoverManager(tmp_path / "cache")
        keywords = mgr._extract_game_keywords("RIDDLE JOKER")
        assert "riddle" in keywords
        assert "joker" in keywords

    def test_strips_brackets(self, tmp_path: Path) -> None:
        mgr = CoverManager(tmp_path / "cache")
        keywords = mgr._extract_game_keywords("[汉化组] Game Title [v1.02]")
        assert "汉化组" not in keywords
        assert "game" in keywords
        assert "title" in keywords

    def test_strips_version_tags(self, tmp_path: Path) -> None:
        mgr = CoverManager(tmp_path / "cache")
        keywords = mgr._extract_game_keywords("MyGame v2.1.0")
        assert "v2" not in keywords
        assert "mygame" in keywords


class TestCleanGameNameForSearch:
    def test_basic(self, tmp_path: Path) -> None:
        mgr = CoverManager(tmp_path / "cache")
        result = mgr._clean_game_name_for_search("[Group] Game Title (v1.0)")
        assert "[" not in result
        assert "]" not in result
        assert "Game" in result
        assert "Title" in result

    def test_empty(self, tmp_path: Path) -> None:
        mgr = CoverManager(tmp_path / "cache")
        result = mgr._clean_game_name_for_search("")
        assert result == ""


class TestScaleAndCenterCrop:
    def test_output_size(self, tmp_path: Path) -> None:
        mgr = CoverManager(tmp_path / "cache")
        img = Image.new("RGB", (1000, 600), (128, 128, 128))
        result = mgr._scale_and_center_crop(img, 300, 420)
        assert result.size == (300, 420)

    def test_already_correct_size(self, tmp_path: Path) -> None:
        mgr = CoverManager(tmp_path / "cache")
        img = Image.new("RGB", (300, 420), (128, 128, 128))
        result = mgr._scale_and_center_crop(img, 300, 420)
        assert result.size == (300, 420)


class TestImportCustomCover:
    def test_import_and_resize(self, tmp_path: Path) -> None:
        mgr = CoverManager(tmp_path / "cache")
        src = tmp_path / "source.jpg"
        _make_jpeg(src, 1000, 800)
        result = mgr.import_custom_cover(42, str(src))
        assert Path(result).exists()
        with Image.open(result) as img:
            assert img.size == (300, 420)


class TestCropCover:
    def test_crop(self, tmp_path: Path) -> None:
        mgr = CoverManager(tmp_path / "cache")
        src = tmp_path / "source.jpg"
        _make_jpeg(src, 1000, 800)
        result = mgr.crop_cover(str(src), 100, 100, 500, 600)
        assert Path(result).exists()
        with Image.open(result) as img:
            assert img.size == (300, 420)


class TestDeleteCover:
    def test_delete_existing(self, tmp_path: Path) -> None:
        mgr = CoverManager(tmp_path / "cache")
        src = tmp_path / "del.jpg"
        _make_jpeg(src, 100, 100)
        mgr.delete_cover(str(src))
        assert not src.exists()

    def test_delete_nonexistent_no_error(self, tmp_path: Path) -> None:
        mgr = CoverManager(tmp_path / "cache")
        mgr.delete_cover(str(tmp_path / "nonexistent.jpg"))
