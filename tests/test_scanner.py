from __future__ import annotations

from pathlib import Path

import pytest

from app.core.scanner import GameScanner
from app.services.path_utils import normalize_game_dir


def _make_game_dir(parent: Path, name: str, exe_name: str = "Game.exe", exe_size: int = 64 * 1024) -> Path:
    d = parent / name
    d.mkdir(parents=True, exist_ok=True)
    exe = d / exe_name
    exe.write_bytes(b"\x00" * exe_size)
    return d


class TestBasicScan:
    def test_scan_empty_root(self, tmp_path: Path) -> None:
        root = tmp_path / "gamedata"
        root.mkdir()
        scanner = GameScanner()
        assert scanner.scan_root(str(root)) == []

    def test_scan_single_game(self, tmp_path: Path) -> None:
        root = tmp_path / "gamedata"
        root.mkdir()
        _make_game_dir(root, "MyGame")
        scanner = GameScanner()
        results = scanner.scan_root(str(root))
        assert len(results) == 1
        assert results[0].game_name == "MyGame"
        assert "Game.exe" in results[0].launch_exe
        assert results[0].content_type == "game"

    def test_scan_top_level_video_file(self, tmp_path: Path) -> None:
        root = tmp_path / "gamedata"
        root.mkdir()
        video = root / "Opening.mp4"
        video.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 4096)
        scanner = GameScanner()

        results = scanner.scan_root(str(root))

        assert len(results) == 1
        assert results[0].game_name == "Opening"
        assert results[0].content_type == "video"
        assert results[0].launch_exe == str(video)

    def test_scan_video_directory(self, tmp_path: Path) -> None:
        root = tmp_path / "gamedata"
        root.mkdir()
        video_dir = root / "Bonus Movie"
        video_dir.mkdir()
        video = video_dir / "movie.mkv"
        video.write_bytes(b"\x1a\x45\xdf\xa3" + b"\x00" * 4096)
        scanner = GameScanner()

        results = scanner.scan_root(str(root))

        assert len(results) == 1
        assert results[0].content_type == "video"
        assert results[0].game_dir == normalize_game_dir(video_dir)
        assert results[0].launch_exe == str(video)

    def test_scan_video_suffix_disguised_archive_is_not_video(self, tmp_path: Path) -> None:
        root = tmp_path / "gamedata"
        root.mkdir()
        disguised = root / "Movie.mp4"
        disguised.write_bytes(b"prefix" + b"\x00" * 2048 + b"PK\x03\x04payload" + b"PK\x05\x06")
        scanner = GameScanner()

        assert scanner.scan_root(str(root)) == []

    def test_scan_multiple_games(self, tmp_path: Path) -> None:
        root = tmp_path / "gamedata"
        root.mkdir()
        _make_game_dir(root, "Game1")
        _make_game_dir(root, "Game2")
        _make_game_dir(root, "Game3")
        scanner = GameScanner()
        results = scanner.scan_root(str(root))
        names = {r.game_name for r in results}
        assert names == {"Game1", "Game2", "Game3"}

    def test_scan_nonexistent_root(self) -> None:
        scanner = GameScanner()
        assert scanner.scan_root("C:/nonexistent_path_xyz") == []


class TestExeSelection:
    def test_prefers_exe_matching_dir_name(self, tmp_path: Path) -> None:
        d = tmp_path / "MyGame"
        d.mkdir()
        (d / "MyGame.exe").write_bytes(b"\x00" * (64 * 1024))
        (d / "launcher.exe").write_bytes(b"\x00" * (64 * 1024))
        (d / "config.exe").write_bytes(b"\x00" * (64 * 1024))
        scanner = GameScanner()
        result = scanner._pick_main_exe(d)
        assert result is not None
        assert result.name == "MyGame.exe"

    def test_excludes_uninstall_setup(self, tmp_path: Path) -> None:
        d = tmp_path / "MyGame"
        d.mkdir()
        (d / "uninstall.exe").write_bytes(b"\x00" * (64 * 1024))
        (d / "setup.exe").write_bytes(b"\x00" * (64 * 1024))
        (d / "Game.exe").write_bytes(b"\x00" * (64 * 1024))
        scanner = GameScanner()
        result = scanner._pick_main_exe(d)
        assert result is not None
        assert result.name.lower() == "game.exe"

    def test_excludes_patch_update(self, tmp_path: Path) -> None:
        d = tmp_path / "MyGame"
        d.mkdir()
        (d / "patch.exe").write_bytes(b"\x00" * (64 * 1024))
        (d / "update.exe").write_bytes(b"\x00" * (64 * 1024))
        (d / "Game.exe").write_bytes(b"\x00" * (64 * 1024))
        scanner = GameScanner()
        result = scanner._pick_main_exe(d)
        assert result is not None
        assert result.name.lower() == "game.exe"

    def test_no_exe_returns_none(self, tmp_path: Path) -> None:
        d = tmp_path / "NoExe"
        d.mkdir()
        (d / "readme.txt").write_text("info", encoding="utf-8")
        scanner = GameScanner()
        assert scanner._pick_main_exe(d) is None

    def test_prefers_larger_exe(self, tmp_path: Path) -> None:
        d = tmp_path / "MyGame"
        d.mkdir()
        (d / "small_tool.exe").write_bytes(b"\x00" * (4 * 1024))
        (d / "big_game.exe").write_bytes(b"\x00" * (256 * 1024))
        scanner = GameScanner()
        result = scanner._pick_main_exe(d)
        assert result is not None
        assert result.name == "big_game.exe"

    def test_all_excluded_returns_none(self, tmp_path: Path) -> None:
        d = tmp_path / "MyGame"
        d.mkdir()
        (d / "uninstall.exe").write_bytes(b"\x00" * (64 * 1024))
        (d / "setup.exe").write_bytes(b"\x00" * (64 * 1024))
        (d / "patch.exe").write_bytes(b"\x00" * (64 * 1024))
        scanner = GameScanner()
        assert scanner._pick_main_exe(d) is None


class TestDirectoryFiltering:
    def test_should_skip_redist(self) -> None:
        scanner = GameScanner()
        assert scanner._should_skip_directory(Path("C:/Games/_commonredist")) is True

    def test_should_skip_support(self) -> None:
        scanner = GameScanner()
        assert scanner._should_skip_directory(Path("C:/Games/support")) is True

    def test_should_skip_runtime(self) -> None:
        scanner = GameScanner()
        assert scanner._should_skip_directory(Path("C:/Games/runtime")) is True

    def test_should_not_skip_normal(self) -> None:
        scanner = GameScanner()
        assert scanner._should_skip_directory(Path("C:/Games/RealGame")) is False

    def test_no_false_positive_from_parent_path(self) -> None:
        scanner = GameScanner()
        assert scanner._should_skip_directory(Path("C:/test_redist_dir/RealGame")) is False

    def test_is_non_game_dir_patch(self) -> None:
        scanner = GameScanner()
        assert scanner._is_non_game_dir_name("汉化补丁") is True

    def test_is_non_game_dir_crack(self) -> None:
        scanner = GameScanner()
        assert scanner._is_non_game_dir_name("crack") is True

    def test_is_not_non_game_dir(self) -> None:
        scanner = GameScanner()
        assert scanner._is_non_game_dir_name("RIDDLE JOKER") is False

    def test_is_dev_project(self, tmp_path: Path) -> None:
        scanner = GameScanner()
        d = tmp_path / "project"
        d.mkdir()
        (d / ".git").mkdir()
        assert scanner._is_dev_project_directory(d) is True

    def test_is_not_dev_project(self, tmp_path: Path) -> None:
        scanner = GameScanner()
        d = tmp_path / "game"
        d.mkdir()
        assert scanner._is_dev_project_directory(d) is False

    def test_scan_skips_redist_keeps_normal(self, tmp_path: Path) -> None:
        root = tmp_path / "gamedata"
        root.mkdir()
        _make_game_dir(root, "_commonredist")
        _make_game_dir(root, "RealGame")
        scanner = GameScanner()
        results = scanner.scan_root(str(root))
        names = {r.game_name for r in results}
        assert "_commonredist" not in names
        assert "RealGame" in names

    def test_scan_skips_support_runtime(self, tmp_path: Path) -> None:
        root = tmp_path / "gamedata"
        root.mkdir()
        _make_game_dir(root, "support")
        _make_game_dir(root, "runtime")
        _make_game_dir(root, "ActualGame")
        scanner = GameScanner()
        results = scanner.scan_root(str(root))
        names = {r.game_name for r in results}
        assert "support" not in names
        assert "runtime" not in names
        assert "ActualGame" in names


class TestGroupedFolders:
    def test_extract_group_count(self) -> None:
        scanner = GameScanner()
        assert scanner._extract_group_count("合集(2)") == 2
        assert scanner._extract_group_count("合集(10)") == 10
        assert scanner._extract_group_count("普通文件夹") == 0
        assert scanner._extract_group_count("合集2") == 0


class TestBridgeDir:
    def test_is_bridge_dir(self) -> None:
        scanner = GameScanner()
        assert scanner._is_bridge_dir_name("pc") is True
        assert scanner._is_bridge_dir_name("game") is True
        assert scanner._is_bridge_dir_name("x64") is True
        assert scanner._is_bridge_dir_name("MyGame") is False


class TestGameNameResolution:
    def test_resolve_normal_name(self, tmp_path: Path) -> None:
        d = tmp_path / "RIDDLE JOKER"
        d.mkdir()
        scanner = GameScanner()
        assert scanner._resolve_game_name(d) == "RIDDLE JOKER"

    def test_resolve_bridge_dir_name(self, tmp_path: Path) -> None:
        parent = tmp_path / "MyTitle"
        parent.mkdir()
        pc = parent / "PC"
        pc.mkdir()
        scanner = GameScanner()
        name = scanner._resolve_game_name(pc)
        assert name == "MyTitle"
