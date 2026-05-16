from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.vndb_service import (
    VndbService,
    VndbRecord,
    VndbOutcome,
    clean_title_for_search,
    ERR_NO_MATCH,
    ERR_DEPENDENCY,
    ERR_PARSE,
    ERR_HTTP,
    ERR_NETWORK,
    ERR_TIMEOUT,
)


class TestCleanTitleForSearch:
    def test_basic(self) -> None:
        assert "RIDDLE" in clean_title_for_search("RIDDLE JOKER")

    def test_strips_brackets(self) -> None:
        result = clean_title_for_search("[汉化组] Game Title")
        assert "[" not in result
        assert "汉化组" not in result

    def test_strips_version_tags(self) -> None:
        result = clean_title_for_search("MyGame v1.02 patch")
        assert "v1.02" not in result
        assert "patch" not in result

    def test_empty(self) -> None:
        assert clean_title_for_search("") == ""

    def test_whitespace_only(self) -> None:
        assert clean_title_for_search("   ") == ""


class TestVndbRecord:
    def test_screenshots_to_json(self) -> None:
        rec = VndbRecord(vndb_id="v17", title="Test", screenshots=["url1", "url2"])
        assert rec.screenshots_to_json() == '["url1", "url2"]'

    def test_screenshots_to_json_empty(self) -> None:
        rec = VndbRecord(vndb_id="v17", title="Test")
        assert rec.screenshots_to_json() is None

    def test_platforms_to_str(self) -> None:
        rec = VndbRecord(vndb_id="v17", title="Test", platforms=["win", "linux"])
        assert rec.platforms_to_str() == "win,linux"

    def test_platforms_to_str_empty(self) -> None:
        rec = VndbRecord(vndb_id="v17", title="Test")
        assert rec.platforms_to_str() is None

    def test_languages_to_str(self) -> None:
        rec = VndbRecord(vndb_id="v17", title="Test", languages=["ja", "en"])
        assert rec.languages_to_str() == "ja,en"


class TestVndbServiceNormalizeResult:
    def test_basic_normalize(self) -> None:
        raw = {
            "id": "v17",
            "title": "Test Game",
            "alttitle": "テストゲーム",
            "description": "A test game.",
            "rating": 8.5,
            "released": "2020-01-01",
            "platforms": ["win"],
            "languages": ["ja"],
            "image": {"url": "https://example.com/cover.jpg"},
            "screenshots": [{"url": "https://example.com/ss1.jpg"}],
        }
        record = VndbService.normalize_result(raw)
        assert record is not None
        assert record.vndb_id == "v17"
        assert record.title == "Test Game"
        assert record.title_localized == "テストゲーム"
        assert record.rating == 8.5
        assert record.platforms == ["win"]
        assert record.image_url == "https://example.com/cover.jpg"
        assert len(record.screenshots) == 1

    def test_normalize_empty_id(self) -> None:
        assert VndbService.normalize_result({}) is None
        assert VndbService.normalize_result({"id": ""}) is None

    def test_normalize_not_dict(self) -> None:
        assert VndbService.normalize_result("not a dict") is None
        assert VndbService.normalize_result(None) is None

    def test_normalize_japanese_title(self) -> None:
        raw = {
            "id": "v100",
            "title": "English Title",
            "titles": [
                {"lang": "en", "title": "English Title", "main": True},
                {"lang": "ja", "title": "日本語タイトル"},
            ],
        }
        record = VndbService.normalize_result(raw)
        assert record is not None
        assert record.title_original == "日本語タイトル"

    def test_normalize_no_image(self) -> None:
        raw = {"id": "v1", "title": "NoImg"}
        record = VndbService.normalize_result(raw)
        assert record is not None
        assert record.image_url is None

    def test_normalize_invalid_rating(self) -> None:
        raw = {"id": "v1", "title": "Test", "rating": "not_a_number"}
        record = VndbService.normalize_result(raw)
        assert record is not None
        assert record.rating is None


class TestVndbServiceSearchTitle:
    def test_empty_query(self) -> None:
        svc = VndbService()
        result = svc.search_title("")
        assert result.success is False
        assert result.error_kind == ERR_NO_MATCH

    def test_missing_requests(self) -> None:
        with patch("app.services.vndb_service.requests", None):
            svc = VndbService()
            result = svc.search_title("test")
            assert result.success is False
            assert result.error_kind == ERR_DEPENDENCY


class TestVndbServiceFetchDetails:
    def test_empty_id(self) -> None:
        svc = VndbService()
        result = svc.fetch_details("")
        assert result.success is False
        assert result.error_kind == ERR_NO_MATCH

    def test_missing_requests(self) -> None:
        with patch("app.services.vndb_service.requests", None):
            svc = VndbService()
            result = svc.fetch_details("v17")
            assert result.success is False
            assert result.error_kind == ERR_DEPENDENCY


class TestVndbServiceNormalizeBangumi:
    def test_basic(self) -> None:
        raw = {
            "id": 12345,
            "name": "Japanese Title",
            "name_cn": "中文标题",
            "images": {"large": "https://example.com/cover.jpg"},
            "rating": {"score": 8.0},
        }
        record = VndbService._normalize_bangumi_subject(raw)
        assert record is not None
        assert record.vndb_id == "bgm:12345"
        assert record.title == "Japanese Title"
        assert record.title_localized == "中文标题"
        assert record.image_url == "https://example.com/cover.jpg"
        assert record.rating == 8.0

    def test_no_id(self) -> None:
        assert VndbService._normalize_bangumi_subject({}) is None

    def test_no_name(self) -> None:
        assert VndbService._normalize_bangumi_subject({"id": 1}) is None

    def test_not_dict(self) -> None:
        assert VndbService._normalize_bangumi_subject("not a dict") is None
        assert VndbService._normalize_bangumi_subject(None) is None
