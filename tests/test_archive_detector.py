from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_TOOL = _ROOT / "integrations" / "自动化解压工具"
if str(_TOOL) not in sys.path:
    sys.path.insert(0, str(_TOOL))

from core.archive_detector import (  # type: ignore[import-not-found]
    classify_content_file,
    detect_archive_type,
    detect_disguised_archive,
    is_real_video_file,
)
from core.extractor import Extractor  # type: ignore[import-not-found]


def test_real_video_is_not_treated_as_archive(tmp_path: Path) -> None:
    video = tmp_path / "movie.mp4"
    video.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 2048)

    assert detect_archive_type(video) is None
    assert detect_disguised_archive(video) is None
    assert is_real_video_file(video) is True
    assert classify_content_file(video) == "video"


def test_video_suffix_with_zip_signature_is_archive(tmp_path: Path) -> None:
    disguised = tmp_path / "movie.mp4"
    prefix = b"fake-video-prefix" + (b"\x00" * 2048)
    disguised.write_bytes(prefix + b"PK\x03\x04payload" + b"PK\x05\x06")

    assert detect_archive_type(disguised) == "zip"
    assert detect_disguised_archive(disguised) == "zip"
    assert is_real_video_file(disguised) is False
    assert classify_content_file(disguised) == "archive"
    assert Extractor._find_disguised_archive_start(str(disguised), "zip") == len(prefix)


def test_video_suffix_with_7z_signature_is_archive(tmp_path: Path) -> None:
    disguised = tmp_path / "movie.mkv"
    prefix = b"matroska-prefix" + (b"\x00" * 2048)
    disguised.write_bytes(prefix + b"7z\xbc\xaf\x27\x1c" + b"payload")

    assert detect_archive_type(disguised) == "7z"
    assert detect_disguised_archive(disguised) == "7z"
    assert is_real_video_file(disguised) is False
    assert Extractor._find_disguised_archive_start(str(disguised), "7z") == len(prefix)
