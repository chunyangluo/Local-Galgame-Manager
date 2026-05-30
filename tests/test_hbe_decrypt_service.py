from __future__ import annotations

from pathlib import Path

import pytest

from app.services import hbe_decrypt_service as hbe
from app.services.paths import hbe_decryptor_dir


@pytest.fixture
def minimal_hbe_html(tmp_path: Path) -> Path:
    """Not a real HBE file — only for parse error / availability checks."""
    p = tmp_path / "fake.html"
    p.write_text("<html><body>not hbe</body></html>", encoding="utf-8")
    return p


def test_hbe_integration_present() -> None:
    assert hbe_decryptor_dir() is not None


def test_is_hbe_available() -> None:
    if not hbe_decryptor_dir():
        pytest.skip("hbe-decryptor not in tree")
    try:
        import cryptography  # noqa: F401
    except ImportError:
        pytest.skip("cryptography not installed")
    assert hbe.is_hbe_available() is True


def test_decrypt_single_known_fails_on_invalid_html(minimal_hbe_html: Path) -> None:
    if not hbe.is_hbe_available():
        pytest.skip(hbe.hbe_missing_reason())
    result = hbe.decrypt_single_known(minimal_hbe_html, "test123")
    assert result.success is False
