from __future__ import annotations

import argparse
import json
import tempfile
import traceback
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from PIL import Image

from app.services.cover_manager import CoverManager
from app.core.scanner import GameScanner
from app.data.database import Database
from app.services.logging_setup import setup_logging
from app.plugins.manager import PluginManager
from app.services.app_data_dir import get_app_data_dir
from app.services.search_service import SearchService
from app.services.vndb_service import VndbService, clean_title_for_search


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


def _run_check(name: str, fn: Callable[[], str]) -> CheckResult:
    try:
        detail = fn()
        return CheckResult(name=name, passed=True, detail=detail)
    except Exception as exc:  # pragma: no cover
        return CheckResult(
            name=name,
            passed=False,
            detail=f"{exc}\n{traceback.format_exc(limit=2)}".strip(),
        )


class FeatureSelfTester:
    def __init__(self, with_network: bool, with_ui: bool, keep_temp: bool) -> None:
        self.with_network = with_network
        self.with_ui = with_ui
        self.keep_temp = keep_temp
        self._tmp = tempfile.TemporaryDirectory(prefix="lgm-selftest-")
        self.base = Path(self._tmp.name)
        self.data_dir = self.base / "data"
        self.scan_root = self.base / "scan_root"
        self.scan_root.mkdir(parents=True, exist_ok=True)

    def run(self) -> list[CheckResult]:
        checks: list[CheckResult] = [
            _run_check("database_basic", self._check_database_basic),
            _run_check("scanner_detect_game", self._check_scanner),
            _run_check("search_filter", self._check_search_filter),
            _run_check("plugin_pipeline", self._check_plugin_pipeline),
            _run_check("cover_manager_custom_cover", self._check_cover_manager),
            _run_check("vndb_normalization", self._check_vndb_normalization),
            _run_check("path_utils", self._check_path_utils),
            _run_check("auto_extract_integration", self._check_auto_extract),
            _run_check("iso_handler_basics", self._check_iso_handler),
            _run_check("disc_install_guide", self._check_disc_install_guide),
            _run_check("archive_detector", self._check_archive_detector),
        ]
        if self.with_network:
            checks.append(_run_check("vndb_network_search", self._check_vndb_network))
        if self.with_ui:
            checks.append(_run_check("ui_smoke_init", self._check_ui_smoke))
        return checks

    def cleanup(self) -> None:
        if self.keep_temp:
            return
        self._tmp.cleanup()

    # ── original checks ──

    def _check_database_basic(self) -> str:
        db = Database(self.data_dir)
        user_id = db.ensure_default_user()
        db.upsert_game(
            name="测试游戏A",
            root_dir=str(self.scan_root / "GameA"),
            launch_exe=str(self.scan_root / "GameA" / "game.exe"),
            cover_path=None,
        )
        games = db.list_games(user_id)
        if not games:
            raise RuntimeError("Database list_games returned empty after upsert_game")
        return f"default_user_id={user_id}, games={len(games)}"

    def _check_scanner(self) -> str:
        game_dir = self.scan_root / "MyGame"
        game_dir.mkdir(parents=True, exist_ok=True)
        exe = game_dir / "MyGame.exe"
        exe.write_bytes(b"\x00" * (2 * 1024 * 1024))
        scanner = GameScanner()
        results = scanner.scan_root(str(self.scan_root))
        if not results:
            raise RuntimeError("Scanner found no games in synthetic root")
        names = [r.game_name for r in results]
        return f"detected={len(results)}, sample={names[0]}"

    def _check_search_filter(self) -> str:
        db = Database(self.data_dir)
        user_id = db.ensure_default_user()
        games = db.list_games(user_id)
        service = SearchService()
        filtered = service.filter_games(games, query="测试", only_favorite=False)
        if not filtered:
            raise RuntimeError("SearchService failed to match existing test game")
        return f"matched={len(filtered)}"

    def _check_plugin_pipeline(self) -> str:
        pm = PluginManager(self.data_dir)
        pm.load_all()
        out = pm.transform_scan_results(root=str(self.scan_root), results=[])
        if out != []:
            raise RuntimeError("Plugin pipeline changed empty scan result unexpectedly")
        return f"plugins_loaded={len(pm.plugins)}"

    def _check_cover_manager(self) -> str:
        cm = CoverManager(self.data_dir / "covers")
        src = self.base / "cover_src.jpg"
        Image.new("RGB", (800, 600), color=(100, 120, 140)).save(src)
        out = cm.import_custom_cover(game_id=1, source_path=str(src))
        out_path = Path(out)
        if not out_path.exists():
            raise RuntimeError("CoverManager import_custom_cover did not output file")
        with Image.open(out_path) as img:
            if img.size != (300, 420):
                raise RuntimeError(f"Unexpected cover size: {img.size}")
        return f"cover_saved={out_path.name}"

    def _check_vndb_normalization(self) -> str:
        raw = {
            "id": "v17",
            "title": "Kana Sample",
            "alttitle": "样例",
            "titles": [{"lang": "ja", "title": "かな", "main": True}],
            "rating": 7.8,
            "platforms": ["win"],
            "languages": ["ja", "zh-Hans"],
            "image": {"url": "https://example.org/image.jpg"},
            "screenshots": [{"url": "https://example.org/shot1.jpg"}],
        }
        rec = VndbService.normalize_result(raw)
        if rec is None:
            raise RuntimeError("normalize_result returned None")
        cleaned = clean_title_for_search("[汉化组] 白色相簿2 final")
        if not cleaned:
            raise RuntimeError("clean_title_for_search returned empty string")
        return f"id={rec.vndb_id}, cleaned_query={cleaned}"

    def _check_vndb_network(self) -> str:
        service = VndbService(timeout=(4, 8), max_retries=1, requests_per_second=1.0)
        outcome = service.search_title("白色相簿2", limit=1)
        if not outcome.success:
            raise RuntimeError(
                f"VNDB network check failed: {outcome.error_kind} {outcome.error_detail}"
            )
        assert outcome.record is not None
        return f"matched={outcome.record.vndb_id} {outcome.record.title}"

    def _check_ui_smoke(self) -> str:
        from PySide6.QtWidgets import QApplication

        from app.ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        win = MainWindow(self.data_dir)
        win.close()
        # Avoid quitting existing app instance if user already has one.
        if QApplication.instance() is app:
            app.processEvents()
        return "main_window_init_ok"

    # ── new checks ──

    def _check_path_utils(self) -> str:
        from app.services.path_utils import normalize_game_dir, is_path_under_root

        norm = normalize_game_dir("C:/Games/My  Game")
        if not norm:
            raise RuntimeError("normalize_game_dir returned empty")
        under = is_path_under_root("C:/Games/MyGame", "C:/Games")
        if not under:
            raise RuntimeError("is_path_under_root failed for valid sub-path")
        not_under = is_path_under_root("D:/Other", "C:/Games")
        if not_under:
            raise RuntimeError("is_path_under_root true for different drive")
        return f"normalize_ok=True, under_root_ok=True"

    def _check_auto_extract(self) -> str:
        from app.services.auto_extract_service import (
            is_auto_extract_available,
            read_directory_config,
        )

        available = is_auto_extract_available()
        if not available:
            raise RuntimeError("AutoExtract integration not available")
        config = read_directory_config()
        keys = list(config.keys())
        if not keys:
            raise RuntimeError("read_directory_config returned empty dict")
        return f"available=True, config_keys={keys[:5]}"

    def _check_iso_handler(self) -> str:
        import sys
        from app.services.paths import auto_extract_tool_dir

        tool_dir = auto_extract_tool_dir()
        if tool_dir is None:
            raise RuntimeError("auto_extract_tool_dir returned None")
        tool_str = str(tool_dir)
        if tool_str not in sys.path:
            sys.path.insert(0, tool_str)

        from core.iso_handler import (
            find_iso_files,
            find_installer_exe,
            is_disc_sidecar,
            INSTALLER_NAMES,
        )

        # Verify INSTALLER_NAMES does not contain common game launchers
        bad = {"launcher.exe", "start.exe"}
        overlap = INSTALLER_NAMES & bad
        if overlap:
            raise RuntimeError(
                f"INSTALLER_NAMES contains game launchers (should be removed): {overlap}"
            )

        # find_iso_files on empty dir should return []
        empty = self.base / "iso_test_empty"
        empty.mkdir(exist_ok=True)
        found = find_iso_files(empty)
        if found:
            raise RuntimeError("find_iso_files found ISOs in empty directory")

        # find_installer_exe on dir without installer should return None
        no_inst = self.base / "no_installer"
        no_inst.mkdir(exist_ok=True)
        (no_inst / "game.exe").write_bytes(b"\x00")
        inst = find_installer_exe(no_inst)
        if inst is not None:
            raise RuntimeError(
                f"find_installer_exe incorrectly found installer: {inst}"
            )

        # find_installer_exe on dir with setup.exe should find it
        with_inst = self.base / "with_setup"
        with_inst.mkdir(exist_ok=True)
        (with_inst / "setup.exe").write_bytes(b"\x00")
        inst2 = find_installer_exe(with_inst)
        if inst2 is None:
            raise RuntimeError("find_installer_exe missed setup.exe")

        # is_disc_sidecar (single-arg: checks suffix)
        assert is_disc_sidecar(Path("game.mds"))
        assert is_disc_sidecar(Path("game.cue"))  # .cue is a disc sidecar
        assert not is_disc_sidecar(Path("game.txt"))
        return f"installer_names={INSTALLER_NAMES}, sidecar_ok=True"

    def _check_disc_install_guide(self) -> str:
        from app.services.disc_install_guide import guide_from_post_process

        # Non-ISO archive should NOT trigger guide even with installer_exe
        guide1 = guide_from_post_process(
            {"expanded": [], "installer_exe": "D:/game/setup.exe"}
        )
        if guide1 is not None:
            raise RuntimeError(
                f"guide_from_post_process should return None for non-ISO, got: {guide1}"
            )

        # ISO expanded with installer should trigger guide
        guide2 = guide_from_post_process(
            {"iso_expanded": ["game.iso"], "installer_exe": "D:/game/setup.exe"}
        )
        if guide2 is None:
            raise RuntimeError(
                "guide_from_post_process should return guide for ISO+installer"
            )

        # ISO expanded without installer still triggers guide (user needs to
        # know this is a disc image and may need manual install)
        guide3 = guide_from_post_process({"iso_expanded": ["game.iso"]})
        if guide3 is None:
            raise RuntimeError(
                "guide_from_post_process should return guide for ISO-only"
            )

        # Neither ISO nor installer should return None
        guide4 = guide_from_post_process({"expanded": []})
        if guide4 is not None:
            raise RuntimeError(
                "guide_from_post_process should return None when no ISO and no installer"
            )
        return "iso_plus_installer=guide, iso_only=guide, no_iso_no_guide=True"

    def _check_archive_detector(self) -> str:
        import sys
        from app.services.paths import auto_extract_tool_dir

        tool_dir = auto_extract_tool_dir()
        if tool_dir is None:
            raise RuntimeError("auto_extract_tool_dir returned None")
        tool_str = str(tool_dir)
        if tool_str not in sys.path:
            sys.path.insert(0, tool_str)

        from core.archive_detector import detect_by_extension

        # Test extension-based detection (doesn't need real files)
        cases = {
            "game.7z": "7z",
            "game.rar": "rar",
            "game.zip": "zip",
            "game.iso": "iso",
        }
        for filename, expected in cases.items():
            result = detect_by_extension(Path(filename))
            if result != expected:
                raise RuntimeError(f"Expected {expected} for {filename}, got {result}")

        # .exe and .txt should not be detected by extension alone
        r_exe = detect_by_extension(Path("game.exe"))
        if r_exe is not None:
            raise RuntimeError(f"Expected None for .exe extension, got {r_exe}")

        return "7z/rar/zip/iso=all_correct"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Local Galgame Manager feature self-tests."
    )
    parser.add_argument(
        "--with-network",
        action="store_true",
        help="Include live VNDB network check (may fail on poor network/rate limit).",
    )
    parser.add_argument(
        "--with-ui",
        action="store_true",
        help="Include MainWindow initialization smoke test.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON output.",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep generated temporary workspace for debugging.",
    )
    return parser


def run() -> int:
    args = build_parser().parse_args()
    setup_logging(data_dir=get_app_data_dir())
    tester = FeatureSelfTester(
        with_network=args.with_network,
        with_ui=args.with_ui,
        keep_temp=args.keep_temp,
    )
    try:
        results = tester.run()
    finally:
        tester.cleanup()

    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed
    if args.json:
        payload = {
            "passed": passed,
            "failed": failed,
            "results": [asdict(r) for r in results],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("Feature Self-Test Report")
        print("=" * 26)
        for r in results:
            mark = "PASS" if r.passed else "FAIL"
            print(f"[{mark}] {r.name}: {r.detail}")
        print("-" * 26)
        print(f"Summary: passed={passed}, failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(run())
