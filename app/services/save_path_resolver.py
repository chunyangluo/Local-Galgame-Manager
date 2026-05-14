"""Resolve candidate save directories using rules + heuristics."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from app.data.database import GameRecord
from app.services.twodfan_hints import iter_twodfan_existing_paths

COMMON_SAVE_DIR_NAMES = {
    "save",
    "saves",
    "savedata",
    "save_data",
    "savefile",
    "セーブデータ",
    "の保存",
    "data",
    "dat",
    "system",
    "persist",
    "renpy data",
    "ren'py data",
    "kirikiri",
    "reallive",
}
SAVE_FILE_EXTS = {".sav", ".dat", ".bin", ".rvdata2", ".rxdata", ".lsd", ".save", ".json"}
COMPANY_HINTS = {"nitro+", "cube", "yuzu-soft", "leaf", "戏画", "f&c"}


@dataclass
class SavePathCandidate:
    path: Path
    source: str  # rule | heuristic
    confidence: int
    reason: str


def resolve_save_path_candidates(
    game: GameRecord,
    *,
    max_results: int = 8,
    twodfan_hints_db_path: str | None = None,
) -> list[SavePathCandidate]:
    """Return candidates sorted by confidence desc, then shorter path."""
    seen: dict[str, SavePathCandidate] = {}

    def add(path: Path, source: str, confidence: int, reason: str) -> None:
        p = path.expanduser().resolve()
        if not p.exists() or not p.is_dir():
            return
        key = str(p).lower()
        cur = seen.get(key)
        cand = SavePathCandidate(path=p, source=source, confidence=confidence, reason=reason)
        if cur is None or cand.confidence > cur.confidence:
            seen[key] = cand

    root = Path(game.root_dir).expanduser()
    game_name = game.name.strip()

    # Rule group 1: near game root (common folders)
    for rel, score in [
        ("save", 95),
        ("saves", 94),
        ("savedata", 92),
        ("SaveData", 92),
        ("savefile", 90),
        ("セーブデータ", 90),
        ("の保存", 88),
        ("data", 70),
        ("dat", 68),
        ("system/save", 90),
        ("data/save", 88),
        ("www/save", 88),
        ("game/saves", 85),
        ("Ren'Py Data", 96),
        ("renpy data", 96),
        ("KiriKiri", 84),
        ("RealLive", 84),
        ("persist", 82),
    ]:
        add(root / rel, "rule", score, f"常见相对目录：{rel}")

    # Rule group 1.5: save-like files beside exe / root
    exe_dir = Path(game.launch_exe).expanduser().parent
    for d, score in ((exe_dir, 93), (root, 86)):
        if _contains_specific_save_files(d, cap=120):
            add(d, "rule", score, "目录下存在 *.sav/*.dat/*.bin 等存档文件")

    # Rule group 2: user profile locations
    home = Path.home()
    local_app = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local")))
    local_low = local_app.parent / "LocalLow"
    user_roots = [
        local_app,
        local_low,
        Path(os.environ.get("APPDATA", str(home / "AppData" / "Roaming"))),
        home / "Documents",
        home / "Saved Games",
    ]
    name_tokens = [t for t in _name_tokens(game_name) if len(t) >= 3][:4]
    for ur in user_roots:
        if not ur.exists():
            continue
        for token in name_tokens:
            for child in _glob_prefix_dirs(ur, token):
                add(child, "rule", 76, f"用户目录名匹配：{token}")
                for sub in ("save", "savedata", "SaveData", "persist"):
                    add(child / sub, "rule", 80, f"用户目录 + 常见子目录：{token}/{sub}")
        # company/brand names (Nitro+, CUBE, Yuzu-Soft, ...)
        for company in COMPANY_HINTS:
            for child in _glob_prefix_dirs(ur, company, cap=6):
                add(child, "rule", 74, f"厂牌目录匹配：{company}")
                for sub in ("save", "savedata", "SaveData", "persist"):
                    add(child / sub, "rule", 78, f"厂牌目录 + 常见子目录：{company}/{sub}")

    # Rule group 3: documents engine folders
    docs = home / "Documents"
    for rel in ("KiriKiri", "RealLive", "krkr", "kirikiri2"):
        add(docs / rel, "rule", 84, f"文档中的引擎目录：{rel}")

    # Rule group 3.5: 2DFan crawler SQLite (optional; paths must exist locally)
    raw_twodfan = (twodfan_hints_db_path or "").strip()
    if raw_twodfan:
        for hit in iter_twodfan_existing_paths(raw_twodfan, game):
            score = int(82 + min(12, hit.hint_confidence * 12))
            snippet = hit.hint_text.replace("\n", " ")[:100]
            add(
                hit.path,
                "2dfan",
                score,
                f"2DFan 下载页 #{hit.download_id} ({hit.hint_kind}): {snippet}",
            )

    # Rule group 4: registry-based path hints (legacy engines; windows only)
    for p in _probe_registry_save_paths(name_tokens, COMPANY_HINTS):
        add(p, "rule", 72, "注册表中发现可用路径")

    # Heuristic scan in game root (depth limited)
    for p in _walk_dirs_limited(root, max_depth=4):
        name = p.name.lower()
        if name in COMMON_SAVE_DIR_NAMES:
            add(p, "heuristic", 72, f"目录名匹配：{p.name}")
            continue
        if any(k in name for k in ("save", "savedata", "saves")):
            add(p, "heuristic", 68, f"目录名包含 save：{p.name}")
            continue
        if _contains_save_files(p, cap=80):
            add(p, "heuristic", 64, "目录内含常见存档文件")

    rows = list(seen.values())
    rows.sort(key=lambda c: (-c.confidence, len(str(c.path))))
    return rows[:max_results]


def _name_tokens(name: str) -> list[str]:
    buf = name.replace("_", " ").replace("-", " ").replace(".", " ")
    return [x.strip().lower() for x in buf.split() if x.strip()]


def _glob_prefix_dirs(root: Path, token: str, cap: int = 8) -> list[Path]:
    token_l = token.lower()
    out: list[Path] = []
    try:
        for p in root.iterdir():
            if len(out) >= cap:
                break
            if not p.is_dir():
                continue
            if p.name.lower().startswith(token_l):
                out.append(p)
    except OSError:
        return out
    return out


def _walk_dirs_limited(root: Path, *, max_depth: int) -> list[Path]:
    out: list[Path] = []
    if not root.exists() or not root.is_dir():
        return out
    stack: list[tuple[Path, int]] = [(root, 0)]
    while stack:
        cur, depth = stack.pop()
        if depth > max_depth:
            continue
        out.append(cur)
        if depth == max_depth:
            continue
        try:
            for child in cur.iterdir():
                if child.is_dir():
                    stack.append((child, depth + 1))
        except OSError:
            continue
    return out


def _contains_save_files(folder: Path, *, cap: int) -> bool:
    exts = SAVE_FILE_EXTS
    checked = 0
    try:
        for p in folder.iterdir():
            if checked >= cap:
                break
            checked += 1
            if p.is_file() and p.suffix.lower() in exts:
                return True
    except OSError:
        return False
    return False


def _contains_specific_save_files(folder: Path, *, cap: int) -> bool:
    if not folder.exists() or not folder.is_dir():
        return False
    checked = 0
    try:
        for p in folder.iterdir():
            if checked >= cap:
                break
            checked += 1
            if not p.is_file():
                continue
            if p.suffix.lower() in {".sav", ".dat", ".bin"}:
                return True
            if p.name.lower() in {"save.dat", "savedata.dat"}:
                return True
    except OSError:
        return False
    return False


def _probe_registry_save_paths(name_tokens: list[str], companies: set[str]) -> list[Path]:
    if sys.platform != "win32":
        return []
    try:
        import winreg
    except Exception:
        return []

    roots: list[Path] = []
    tokens = {t.lower() for t in name_tokens if len(t) >= 3} | {c.lower() for c in companies}
    if not tokens:
        return roots

    key_names = ["Software", r"Software\WOW6432Node"]
    value_name_hints = {"savepath", "savedir", "save_dir", "path", "userdata", "datapath"}

    for base in key_names:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, base) as hbase:
                sub_count, _, _ = winreg.QueryInfoKey(hbase)
                for i in range(min(sub_count, 200)):
                    sub_name = winreg.EnumKey(hbase, i)
                    if not any(t in sub_name.lower() for t in tokens):
                        continue
                    _collect_registry_paths(hbase, sub_name, roots, value_name_hints)
        except OSError:
            continue
    return roots


def _collect_registry_paths(hbase, sub_name: str, out: list[Path], hints: set[str]) -> None:
    import winreg

    def collect_from_key(hk) -> None:
        _, val_count, _ = winreg.QueryInfoKey(hk)
        for j in range(min(val_count, 40)):
            vname, vdata, vtype = winreg.EnumValue(hk, j)
            if vtype not in (winreg.REG_SZ, winreg.REG_EXPAND_SZ):
                continue
            name_l = str(vname).lower()
            if hints and name_l and not any(h in name_l for h in hints):
                continue
            raw = os.path.expandvars(str(vdata)).strip().strip('"')
            p = Path(raw)
            if p.exists() and p.is_dir():
                out.append(p)

    try:
        with winreg.OpenKey(hbase, sub_name) as hk:
            collect_from_key(hk)
            sub_count, _, _ = winreg.QueryInfoKey(hk)
            for i in range(min(sub_count, 30)):
                child = winreg.EnumKey(hk, i)
                with winreg.OpenKey(hk, child) as h2:
                    collect_from_key(h2)
    except OSError:
        return

