from __future__ import annotations

from pathlib import Path

from app.services.loose_install_consolidator import (
    consolidate_loose_install,
    detect_loose_install_at_root,
    is_existing_game_folder,
    is_game_launcher_exe,
    suggest_install_folder_name,
)


def test_is_game_launcher_exe() -> None:
    assert is_game_launcher_exe("momoero.exe") is True
    assert is_game_launcher_exe("setup.exe") is False
    assert is_game_launcher_exe("UINSTampMOMOERO.exe") is False


def test_suggest_folder_from_iso() -> None:
    name = suggest_install_folder_name(iso_names=("MOMOERO.ISO",))
    assert name == "MOMOERO"


def test_detect_loose_install(tmp_path: Path) -> None:
    (tmp_path / "momoero.exe").write_bytes(b"MZ" + b"\0" * 100)
    (tmp_path / "instfile.lst").write_text("x")
    (tmp_path / "DLL").mkdir()
    (tmp_path / "DLL" / "a.dll").write_bytes(b"\0" * 10)
    (tmp_path / "exe").mkdir()
    (tmp_path / "RealGame").mkdir()
    (tmp_path / "RealGame" / "game.exe").write_bytes(b"MZ" + b"\0" * 2000)
    for _ in range(40):
        (tmp_path / "RealGame" / f"f{_}.dat").write_bytes(b"\0" * 100_000)

    cluster = detect_loose_install_at_root(tmp_path)
    assert cluster is not None
    assert cluster.launcher_exe.name == "momoero.exe"
    names = {p.name for p in cluster.items}
    assert "DLL" in names
    assert "RealGame" not in names


def test_consolidate_moves_to_subfolder(tmp_path: Path) -> None:
    (tmp_path / "game.exe").write_bytes(b"MZ")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "x.txt").write_text("1")

    result = consolidate_loose_install(tmp_path, folder_name="MyGame")
    assert result.success
    assert (tmp_path / "MyGame" / "game.exe").is_file()
    assert not (tmp_path / "game.exe").exists()


def test_is_existing_game_folder(tmp_path: Path) -> None:
    g = tmp_path / "BigGame"
    g.mkdir()
    (g / "play.exe").write_bytes(b"MZ" + b"\0" * 5000)
    for i in range(35):
        (g / f"chunk{i}.dat").write_bytes(b"\0" * 100_000)
    assert is_existing_game_folder(g) is True
    assert is_existing_game_folder(tmp_path / "dll") is False
