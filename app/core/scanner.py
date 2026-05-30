from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from collections import deque


HARD_EXCLUDED_EXE_KEYWORDS = (
    "uninstall",
    "setup",
    "patch",
    "update",
    "config",
    "crash",
    "errorreport",
    "tool",
    "repair",
    "dxsetup",
    "vcredist",
    "redist",
    "benchmark",
    "editor",
    "register",
    "activation",
    "steam",
)

SOFT_PENALTY_KEYWORDS = (
    "launcher",
    "config",
    "setting",
    "updater",
    "mod",
    "tool",
    "diagnostic",
)

SKIP_DIRECTORY_KEYWORDS = (
    "_commonredist",
    "redist",
    "runtime",
    "support",
    "update",
    "sdk",
)
SKIP_DIRECTORY_NAMES = {
    "build",
    "dist",
    ".git",
    ".idea",
    ".vscode",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    "venv",
    ".venv",
}

NON_GAME_DIR_NAME_KEYWORDS = (
    "汉化补丁",
    "汉化修正",
    "补丁",
    "修正",
    "升级档",
    "存档",
    "攻略",
    "说明",
    "工具",
    "运行库",
    "必备组件",
    "破解",
    "crack",
    "patch",
    "fix",
    "update",
    "mod",
    "trainer",
)

BRIDGE_DIR_NAMES = {
    "pc", "game", "games", "bin", "x64", "x86", "win64", "win32", "release",
    "data", "files", "lib", "logs", "assets",
}

# 垃圾后缀列表：语言标识、附加标签，解析目录名时自动剔除
_DIR_SUFFIX_BLACKLIST = (
    "_chs", "_cn", "_jp", "_en", "_kr",
    "_汉化", "_全cg", "_存档", "_绿色版", "_免安装",
    "_简体", "_繁体", "_中文", "_日文", "_英文",
)

# 全角→半角映射表
_FULLWIDTH_MAP = str.maketrans(
    "　０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ！？～－",
    " 0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz!?~-",
)

@dataclass
class ScanResult:
    game_name: str
    game_dir: str
    launch_exe: str


class GameScanner:
    def __init__(self) -> None:
        pass

    def scan_root(self, root: str) -> list[ScanResult]:
        root_path = Path(root)
        if not root_path.exists():
            print(f"[Scanner] Root path does not exist: {root}")
            return []
        
        results: list[ScanResult] = []
        skipped_dirs: list[tuple[str, str]] = []  # (dir_name, reason)
        no_exe_dirs: list[str] = []
        
        try:
            game_dirs = self._iter_game_directories(root_path)
            print(f"[Scanner] Found {len(game_dirs)} potential game directories in {root}")
        except Exception as e:
            print(f"[Scanner] Error iterating game directories in {root}: {e}")
            return []
        
        for directory in game_dirs:
            try:
                candidate = self._pick_main_exe(directory)
                if candidate is None:
                    no_exe_dirs.append(str(directory))
                    continue
                from app.services.path_utils import normalize_game_dir

                results.append(
                    ScanResult(
                        game_name=self._resolve_game_name(directory),
                        game_dir=normalize_game_dir(directory),
                        launch_exe=str(candidate),
                    )
                )
            except Exception as e:
                skipped_dirs.append((str(directory), str(e)))
                continue
        
        # 去重
        dedup: dict[str, ScanResult] = {}
        for item in results:
            dedup[item.game_dir] = item
        
        # 输出扫描总结
        print(f"\n[Scanner] === 扫描完成 ===")
        print(f"[Scanner] 总目录数: {len(game_dirs)}")
        print(f"[Scanner] 识别到游戏: {len(dedup.values())}")
        print(f"[Scanner] 无有效可执行文件: {len(no_exe_dirs)}")
        print(f"[Scanner] 处理异常跳过: {len(skipped_dirs)}")
        
        if no_exe_dirs:
            print(f"[Scanner] 无有效可执行文件的目录:")
            for d in no_exe_dirs:
                print(f"  - {d}")
        
        if skipped_dirs:
            print(f"[Scanner] 跳过的目录:")
            for d, reason in skipped_dirs:
                print(f"  - {d}: {reason}")
        
        return list(dedup.values())

    def _iter_game_directories(self, root_path: Path) -> list[Path]:
        game_dirs: list[Path] = []
        try:
            first_level_dirs = sorted([p for p in root_path.iterdir() if p.is_dir()])
        except PermissionError as e:
            print(f"[Scanner] Permission denied accessing {root_path}: {e}")
            return []
        except OSError as e:
            print(f"[Scanner] OS error accessing {root_path}: {e}")
            return []
        
        for first_dir in first_level_dirs:
            try:
                if self._should_skip_directory(first_dir):
                    continue
                if self._is_dev_project_directory(first_dir):
                    continue
                if self._is_non_game_dir_name(first_dir.name) and not self._is_bridge_dir_name(first_dir.name):
                    continue
                grouped_count = self._extract_group_count(first_dir.name)
                if grouped_count > 0:
                    sub_games = sorted([p for p in first_dir.iterdir() if p.is_dir()])
                    if grouped_count <= len(sub_games):
                        sub_games = sub_games[:grouped_count]
                    for sub in sub_games:
                        if self._should_skip_directory(sub):
                            continue
                        if self._is_dev_project_directory(sub):
                            continue
                        if self._is_non_game_dir_name(sub.name) and not self._is_bridge_dir_name(sub.name):
                            continue
                        game_dirs.append(sub)
                    continue
                auto_sub_games = self._auto_detect_bundle_subgames(first_dir)
                if auto_sub_games:
                    game_dirs.extend(auto_sub_games)
                    continue
                nested_games = self._discover_nested_game_dirs(first_dir, max_depth=4)
                if nested_games:
                    game_dirs.extend(nested_games)
                    continue
                game_dirs.append(first_dir)
            except PermissionError:
                continue
            except OSError:
                continue
        return game_dirs

    def _auto_detect_bundle_subgames(self, first_dir: Path) -> list[Path]:
        """
        Auto-expand folder as a multi-game bundle when:
        1) parent folder has no valid launcher candidate
        2) contains multiple child folders that each look launchable
        """
        parent_candidate = self._pick_main_exe(first_dir)
        if parent_candidate is not None:
            return []
        children = sorted(
            [
                p
                for p in first_dir.iterdir()
                if p.is_dir()
                and not self._should_skip_directory(p)
                and not self._is_dev_project_directory(p)
                and not self._is_non_game_dir_name(p.name)
            ]
        )
        if len(children) < 2:
            return []
        launchable_children = [child for child in children if self._pick_main_exe(child) is not None]
        # Require at least 2 launchable subfolders and most subfolders launchable.
        if len(launchable_children) < 2:
            return []
        if len(launchable_children) / len(children) < 0.6:
            return []
        return launchable_children

    def _pick_main_exe(self, directory: Path) -> Path | None:
        try:
            exes = sorted(directory.glob("*.exe"))
        except PermissionError:
            return None
        except OSError:
            return None
        
        if not exes:
            return None
        
        scored: list[tuple[int, Path]] = []
        dir_key = self._normalize_name(directory.name)
        
        for exe in exes:
            try:
                lower = exe.name.lower()
                if any(k in lower for k in HARD_EXCLUDED_EXE_KEYWORDS):
                    continue
                
                score = 0
                exe_stem_key = self._normalize_name(exe.stem)
                
                if dir_key and exe_stem_key == dir_key:
                    score += 8
                elif dir_key and dir_key in exe_stem_key:
                    score += 5
                
                if "game" in lower or "start" in lower:
                    score += 2
                if "x64" in lower or "64" in lower:
                    score += 1
                # 中文版优先级：包含中文标识的exe优先选择
                if any(k in lower for k in ("_zh", "_cn", "_chs", "_chinese", "_中文")):
                    score += 3
                if any(k in lower for k in SOFT_PENALTY_KEYWORDS):
                    score -= 3
                
                size_mb = exe.stat().st_size / (1024 * 1024)
                if size_mb >= 5:
                    score += 2
                elif size_mb < 1:
                    score -= 2
                
                scored.append((score, exe))
            except (PermissionError, OSError):
                continue
        
        if not scored:
            return None
        
        scored.sort(key=lambda x: (x[0], x[1].stat().st_size), reverse=True)
        
        if scored[0][0] < -2:
            return None
        
        return scored[0][1]

    def _should_skip_directory(self, directory: Path) -> bool:
        lower_name = directory.name.strip().lower()
        if lower_name in SKIP_DIRECTORY_NAMES:
            return True
        return any(token in lower_name for token in SKIP_DIRECTORY_KEYWORDS)

    def _normalize_name(self, value: str) -> str:
        return re.sub(r"[^a-z0-9\u4e00-\u9fff\u3040-\u30ff]+", "", value.lower())

    def _extract_group_count(self, directory_name: str) -> int:
        match = re.search(r"\((\d+)\)\s*$", directory_name)
        if not match:
            return 0
        return int(match.group(1))

    def _is_non_game_dir_name(self, directory_name: str) -> bool:
        normalized = directory_name.strip().lower()
        compact = self._normalize_name(directory_name)
        if normalized in {"pc", "patch", "update", "tool", "tools"}:
            return True
        return any(token in normalized or token in compact for token in NON_GAME_DIR_NAME_KEYWORDS)

    def _is_bridge_dir_name(self, directory_name: str) -> bool:
        return directory_name.strip().lower() in BRIDGE_DIR_NAMES

    def _discover_nested_game_dirs(self, base_dir: Path, max_depth: int) -> list[Path]:
        """
        Fallback for nested layouts like:
        root/Title/PC/xxxx/game-folder-with-exe
        """
        found: list[Path] = []
        queue: deque[tuple[Path, int]] = deque([(base_dir, 0)])
        seen: set[Path] = set()

        while queue:
            current, depth = queue.popleft()
            if current in seen:
                continue
            seen.add(current)
            if depth > max_depth:
                continue
            if current != base_dir and self._should_skip_directory(current):
                continue
            if self._is_dev_project_directory(current):
                continue

            candidate = self._pick_main_exe(current)
            if candidate is not None and not self._is_non_game_dir_name(current.name):
                found.append(current)
                # If a directory is already launchable, do not keep descending
                # under it to avoid importing duplicated internals.
                continue

            if depth == max_depth:
                continue
            try:
                children = [p for p in current.iterdir() if p.is_dir()]
            except OSError:
                continue
            for child in children:
                queue.append((child, depth + 1))

        # Keep stable order and de-duplicate.
        unique: list[Path] = []
        seen_paths: set[str] = set()
        for path in sorted(found):
            key = str(path)
            if key in seen_paths:
                continue
            seen_paths.add(key)
            unique.append(path)
        return unique

    def _resolve_game_name(self, directory: Path) -> str:
        raw_name = directory.name
        # 全角→半角统一
        normalized = raw_name.translate(_FULLWIDTH_MAP)
        # 后缀过滤
        normalized = self._strip_dir_suffix(normalized)

        if not self._is_bridge_dir_name(raw_name) and not self._is_code_like_dir_name(raw_name):
            return normalized
        # Bridge folders like "PC" are often wrappers; try extracting a better
        # display name from the single-child chain.
        best_name = self._find_best_ancestor_name(directory)
        # 对 best_name 也做后缀过滤和全角统一
        best_name = best_name.translate(_FULLWIDTH_MAP)
        best_name = self._strip_dir_suffix(best_name)

        # 优化递归：若连续多层都是桥接目录，直接向上回溯取顶层有效文件夹名
        current = directory
        consecutive_bridge = 0
        for _ in range(4):
            try:
                children = [p for p in current.iterdir() if p.is_dir() and not self._should_skip_directory(p)]
            except OSError:
                break
            if len(children) != 1:
                break
            child = children[0]
            if self._is_bridge_dir_name(child.name) or self._is_code_like_dir_name(child.name):
                consecutive_bridge += 1
                if consecutive_bridge >= 2:
                    # 连续多层桥接目录，直接使用 best_name（向上回溯的结果）
                    break
            else:
                consecutive_bridge = 0
                child_name = child.name.translate(_FULLWIDTH_MAP)
                child_name = self._strip_dir_suffix(child_name)
                if not self._is_non_game_dir_name(child.name):
                    best_name = child_name
            current = child
        return best_name

    @staticmethod
    def _strip_dir_suffix(name: str) -> str:
        """剔除目录名末尾的垃圾后缀（语言标识、附加标签等）。"""
        lower = name.lower()
        for suffix in _DIR_SUFFIX_BLACKLIST:
            if lower.endswith(suffix):
                name = name[: len(name) - len(suffix)]
                break
        return name.strip()

    def _is_code_like_dir_name(self, directory_name: str) -> bool:
        """
        Detect packaging/code folders like:
        2816-PC, v1.02, game_x64, etc.
        """
        lower = directory_name.strip().lower()
        if not lower:
            return False
        if re.fullmatch(r"v\d+(\.\d+)*", lower):
            return True
        if re.fullmatch(r"\d{3,6}([._\-]?(pc|x64|x86|win\d*|ver\d+(\.\d+)*))?", lower):
            return True
        if re.fullmatch(r"\d{3,6}[a-z]{0,4}", lower):
            return True
        if re.fullmatch(r"[a-z0-9._\- ]+", lower) is None:
            return False
        has_digit = any(ch.isdigit() for ch in lower)
        has_platform_token = any(token in lower for token in ("pc", "x64", "x86", "win", "ver"))
        # Require both platform-ish token and digit to avoid classifying normal
        # English game titles as code-like folders.
        return has_digit and has_platform_token and len(lower) <= 18

    def _find_best_ancestor_name(self, directory: Path) -> str:
        cursor = directory
        for _ in range(5):
            parent = cursor.parent
            if parent == cursor or parent is None:
                break
            name = parent.name
            if (
                name
                and not self._is_bridge_dir_name(name)
                and not self._is_non_game_dir_name(name)
                and not self._is_code_like_dir_name(name)
            ):
                return name
            cursor = parent
        return directory.parent.name if directory.parent else directory.name

    def _is_dev_project_directory(self, directory: Path) -> bool:
        """
        Skip local source/build folders to avoid importing this manager itself
        (or other software projects) as a game.
        """
        try:
            has_git = (directory / ".git").exists()
            has_python_project = (directory / "requirements.txt").exists() and (directory / "app").is_dir()
            has_entry = (directory / "app" / "main.py").exists()
            has_build_outputs = (directory / "dist").is_dir() and (directory / "build").is_dir()
            return has_git or (has_python_project and has_entry) or (has_python_project and has_build_outputs)
        except OSError:
            return False
