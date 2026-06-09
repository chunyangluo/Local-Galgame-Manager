from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_TOOL = _ROOT / "integrations" / "自动化解压工具"
if str(_TOOL) not in sys.path:
    sys.path.insert(0, str(_TOOL))

from core.iso_handler import (  # type: ignore[import-not-found]
    find_installer_exe,
    find_iso_files,
    is_disc_image_staging_dir,
    is_disc_sidecar,
)


@pytest.mark.parametrize(
    "name,expected",
    [
        ("game.mds", True),
        ("game.MDS", True),
        ("game.cue", True),
        ("game.iso", False),
        ("setup.exe", False),
    ],
)
def test_is_disc_sidecar(name: str, expected: bool) -> None:
    assert is_disc_sidecar(Path(name)) is expected


def test_find_iso_files(tmp_path: Path) -> None:
    (tmp_path / "a.iso").write_bytes(b"x")
    (tmp_path / "b.txt").write_text("n")
    (tmp_path / "c.ISO").write_bytes(b"y")
    names = [p.name for p in find_iso_files(tmp_path)]
    assert sorted(names) == ["a.iso", "c.ISO"]


def test_is_disc_image_staging_dir_iso_only(tmp_path: Path) -> None:
    (tmp_path / "MOMOERO.iso").write_bytes(b"\x00" * 100)
    (tmp_path / "MOMOERO.mds").write_bytes(b"\x00" * 10)
    assert is_disc_image_staging_dir(tmp_path) is True


def test_is_disc_image_staging_dir_with_setup(tmp_path: Path) -> None:
    (tmp_path / "MOMOERO.iso").write_bytes(b"\x00" * 100)
    (tmp_path / "setup.exe").write_bytes(b"MZ")
    assert is_disc_image_staging_dir(tmp_path) is False


def test_find_installer_exe(tmp_path: Path) -> None:
    sub = tmp_path / "disc"
    sub.mkdir()
    (sub / "readme.txt").write_text("x")
    installer = sub / "setup.exe"
    installer.write_bytes(b"MZ")
    found = find_installer_exe(tmp_path)
    assert found == installer
