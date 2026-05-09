from __future__ import annotations

import argparse
import json
import tempfile
import traceback
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from PIL import Image

from app.core.cover_manager import CoverManager
from app.core.scanner import GameScanner
from app.data.database import Database
from app.logging_setup import setup_logging
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
