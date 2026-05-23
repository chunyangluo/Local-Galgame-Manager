from __future__ import annotations
import re
import struct
import time
from pathlib import Path
from urllib.parse import quote

from PIL import Image, ImageStat
import requests


PRIORITY_DIR_WHITELIST = (
    "cover",
    "covers",
    "img",
    "image",
    "images",
    "title",
    "bg",
    "art",
    "splash",
    "illust",
    "picture",
    "pic",
    "graphic",
    "resource",
    "resources",
    "data",
    "media",
)
DIR_BLACKLIST = (
    "save",
    "save_data",
    "backup",
    "patch",
    "update",
    "manual",
    "doc",
    "docs",
    "movie",
    "voice",
    "sound",
    "music",
    "audio",
    "system",
    "temp",
    "cache",
    "log",
    "logs",
)

PRIMARY_NAME_KEYWORDS = (
    "cover",
    "title",
    "logo",
    "bg",
    "splash",
    "icon",
    "art",
    "illust",
    "poster",
    "main",
    "start",
    "menu",
    "游戏封面",
    "封面",
    "标题",
    "开始",
    "菜单",
)
SECONDARY_NAME_KEYWORDS = (
    "game",
    "visual",
    "novel",
    "opening",
    "intro",
    "cg",
    "scene",
    "story",
    "character",
    "chara",
    "profile",
    "face",
    "portrait",
    "立绘",
    "CG",
    "角色",
    "人物",
)
NEGATIVE_NAME_KEYWORDS = (
    "back",
    "cg",
    "scene",
    "bgm",
    "ev",
    "screenshot",
    "thumb",
    "thumbnail",
    "sample",
    "icon",
    "small",
    "mini",
    "preview",
    "temp",
    "cache",
    "backup",
    "old",
    "_bak",
    "_old",
    "_backup",
)
COVER_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")

_FINE_SCORE_TOP_N = 3


def _read_jpeg_size(data: bytes) -> tuple[int, int] | None:
    i = 2
    length = len(data)
    while i < length - 9:
        if data[i] != 0xFF:
            return None
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2):
            h = struct.unpack_from(">H", data, i + 5)[0]
            w = struct.unpack_from(">H", data, i + 7)[0]
            return w, h
        if marker in (0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9):
            i += 2
        else:
            seg_len = struct.unpack_from(">H", data, i + 2)[0]
            i += 2 + seg_len
    return None


def _read_png_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    w = struct.unpack_from(">I", data, 16)[0]
    h = struct.unpack_from(">I", data, 20)[0]
    return w, h


def _read_webp_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 30:
        return None
    riff = data[:4]
    webp = data[8:12]
    if riff != b"RIFF" or webp != b"WEBP":
        return None
    chunk = data[12:16]
    if chunk == b"VP8 " and len(data) >= 30:
        w = struct.unpack_from("<H", data, 26)[0] & 0x3FFF
        h = struct.unpack_from("<H", data, 28)[0] & 0x3FFF
        return w, h
    if chunk == b"VP8L" and len(data) >= 25:
        bits = struct.unpack_from("<I", data, 21)[0]
        w = (bits & 0x3FFF) + 1
        h = ((bits >> 14) & 0x3FFF) + 1
        return w, h
    return None


def read_image_size_fast(path: Path) -> tuple[int, int] | None:
    with open(path, "rb") as f:
        header = f.read(64)
    if header[:2] == b"\xff\xd8":
        with open(path, "rb") as f:
            data = f.read(min(path.stat().st_size, 65536))
        return _read_jpeg_size(data)
    if header[:8] == b"\x89PNG\r\n\x1a\n":
        return _read_png_size(header)
    if header[:4] == b"RIFF":
        return _read_webp_size(header)
    return None


class CoverManager:
    def __init__(self, cover_cache_dir: Path) -> None:
        self.cover_cache_dir = cover_cache_dir
        self.cover_cache_dir.mkdir(parents=True, exist_ok=True)
        self.online_cache_dir = self.cover_cache_dir / "online"
        self.online_cache_dir.mkdir(parents=True, exist_ok=True)
        self.cover_fetch_mode = "local_prefer"
        self.online_min_local_score = 20
        self._online_block_until_ts = 0.0
        self._online_failed_names: set[str] = set()
        self._http_headers = {
            "User-Agent": "LocalGalgameManager/2.0 (+https://github.com/)",
            "Accept": "application/json,image/*,*/*",
        }

    def find_cover(self, game_dir: str, game_name: str | None = None) -> str | None:
        path = Path(game_dir)
        if not path.exists():
            return None

        if self.cover_fetch_mode == "online_prefer":
            online = self._fetch_cover_online(game_name or path.name)
            if online:
                return online

        local_path, local_score = self.find_cover_local(game_dir, game_name)

        if local_path is not None:
            if self.cover_fetch_mode in {"local_prefer", "online_prefer"} and local_score < self.online_min_local_score:
                online = self._fetch_cover_online(game_name or path.name)
                if online:
                    return online
            return local_path

        if self.cover_fetch_mode == "local_only":
            return None
        return self._fetch_cover_online(game_name or path.name)

    def find_cover_local(self, game_dir: str, game_name: str | None = None) -> tuple[str | None, int]:
        path = Path(game_dir)
        if not path.exists():
            return None, -10_000

        game_keywords = self._extract_game_keywords(game_name or path.name)
        candidates = self._collect_image_candidates(path, whitelist_only=True, max_depth=1)
        if not candidates:
            candidates = self._collect_image_candidates(path, whitelist_only=False, max_depth=2)
            if not candidates:
                return None, -10_000

        scored: list[tuple[int, Path]] = []
        for file in candidates:
            score = self._quick_score_candidate(file, base_dir=path, game_keywords=game_keywords)
            scored.append((score, file))

        scored.sort(key=lambda x: x[0], reverse=True)

        best_file: Path | None = None
        best_score = -10_000
        for score, file in scored[:_FINE_SCORE_TOP_N]:
            fine_score = self._fine_score_candidate(file, score)
            if fine_score > best_score:
                best_score = fine_score
                best_file = file

        if best_file is None and scored:
            best_file = scored[0][1]
            best_score = scored[0][0]

        if best_file is not None:
            return str(best_file), best_score
        return None, -10_000

    def fetch_cover_online(self, game_name: str) -> str | None:
        return self._fetch_cover_online(game_name)

    def _collect_image_candidates(self, root: Path, whitelist_only: bool, max_depth: int) -> list[Path]:
        files: list[Path] = []
        root_depth = len(root.parts)
        for candidate in root.rglob("*"):
            if not candidate.is_file():
                continue
            if candidate.suffix.lower() not in COVER_EXTENSIONS:
                continue
            depth = len(candidate.parts) - root_depth
            if depth > max_depth:
                continue
            if self._is_in_blacklist_dir(candidate, root):
                continue
            if whitelist_only and not self._is_in_whitelist_dir(candidate, root):
                continue
            files.append(candidate)
        return files

    def _quick_score_candidate(self, file: Path, base_dir: Path, game_keywords: list[str]) -> int:
        name = file.stem.lower()
        score = 0

        primary_count = sum(1 for k in PRIMARY_NAME_KEYWORDS if k in name)
        if primary_count > 0:
            score += primary_count * 12

        secondary_count = sum(1 for k in SECONDARY_NAME_KEYWORDS if k in name)
        if secondary_count > 0:
            score += secondary_count * 6

        negative_count = sum(1 for k in NEGATIVE_NAME_KEYWORDS if k in name)
        if negative_count > 0:
            score -= negative_count * 8

        keyword_matches = sum(1 for kw in game_keywords if kw and kw in name)
        if keyword_matches > 0:
            score += keyword_matches * 20

        rel_depth = max(0, len(file.parent.parts) - len(base_dir.parts))
        if rel_depth == 0:
            score += 5
        elif rel_depth == 1:
            score += 0
        elif rel_depth == 2:
            score -= 5
        else:
            score -= 12

        try:
            file_size = file.stat().st_size
        except OSError:
            return -9999

        if file_size < 4_096:
            return -500
        elif file_size < 16_384:
            score -= 5
        elif file_size >= 256_000:
            score += 8
        elif file_size >= 128_000:
            score += 4

        dims = read_image_size_fast(file)
        if dims is None:
            try:
                with Image.open(file) as img:
                    dims = img.size
            except Exception:
                return -9999

        width, height = dims
        short_edge = min(width, height)
        long_edge = max(width, height)

        if short_edge < 200:
            return -500
        elif short_edge < 260:
            score -= 8
        elif short_edge >= 500:
            score += 10
        elif short_edge >= 350:
            score += 5

        ratio = width / max(1, height)

        cover_ratios = (
            (2/3, "2:3 竖版封面"),
            (3/4, "3:4 竖版"),
            (9/16, "9:16 手机竖版"),
            (16/10, "16:10 横版"),
            (4/3, "4:3 经典"),
            (16/9, "16:9 宽屏"),
            (1/1, "1:1 正方形"),
        )

        best_ratio_score = 0
        for target_ratio, _name in cover_ratios:
            delta = abs(ratio - target_ratio)
            if delta <= 0.05:
                ratio_score = 18
            elif delta <= 0.1:
                ratio_score = 12
            elif delta <= 0.15:
                ratio_score = 6
            elif delta <= 0.25:
                ratio_score = 2
            else:
                ratio_score = -8

            if ratio_score > best_ratio_score:
                best_ratio_score = ratio_score

        score += best_ratio_score

        if ratio < 0.35 or ratio > 4.0:
            score -= 20

        pixel_area = width * height
        if pixel_area >= 1_000_000:
            score += 8
        elif pixel_area >= 500_000:
            score += 4

        aspect_bonus = 0
        if 0.4 < ratio < 0.7:
            aspect_bonus = 6
        elif 1.3 < ratio < 2.0:
            aspect_bonus = 4
        score += aspect_bonus

        return score

    def _fine_score_candidate(self, file: Path, base_score: int) -> int:
        try:
            with Image.open(file) as img:
                img.load()
                gray = img.convert("L")
                brightness = float(ImageStat.Stat(gray).mean[0])
        except Exception:
            return base_score

        if brightness < 18 or brightness > 240:
            base_score -= 8

        return base_score

    def _is_in_whitelist_dir(self, file: Path, base_dir: Path) -> bool:
        rel_parts = file.relative_to(base_dir).parts[:-1]
        if not rel_parts:
            return True
        return any(part.lower() in PRIORITY_DIR_WHITELIST for part in rel_parts)

    def _is_in_blacklist_dir(self, file: Path, base_dir: Path) -> bool:
        rel_parts = file.relative_to(base_dir).parts[:-1]
        return any(part.lower() in DIR_BLACKLIST for part in rel_parts)

    def _extract_game_keywords(self, folder_name: str) -> list[str]:
        normalized = folder_name.lower()
        normalized = re.sub(r"\[.*?\]|\(.*?\)|\{.*?\}", " ", normalized)
        normalized = re.sub(r"v\d+(\.\d+)*", " ", normalized)
        normalized = re.sub(r"(krkr|riri|dx|win\d+|x64|x86|steam|chs|cht|汉化组)", " ", normalized)
        normalized = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", normalized)
        tokens = [token.strip() for token in normalized.split() if len(token.strip()) >= 2]
        return tokens[:4]

    def _fetch_cover_online(self, game_name: str) -> str | None:
        clean_name = self._clean_game_name_for_search(game_name)
        if not clean_name:
            return None
        if clean_name in self._online_failed_names:
            return None
        if time.time() < self._online_block_until_ts:
            return None

        cache_file = self.online_cache_dir / f"{clean_name}.jpg"
        if cache_file.exists():
            return str(cache_file)

        search_url = f"https://api.bgm.tv/search/subject/{quote(clean_name)}?type=4&max_results=1"
        try:
            response = requests.get(search_url, headers=self._http_headers, timeout=(2, 4))
            response.raise_for_status()
            data = response.json()
            subjects = data.get("list") or []
            if not subjects:
                fallback_url = "https://api.bgm.tv/v0/search/subjects"
                payload = {"keyword": clean_name, "filter": {"type": [4]}, "limit": 1}
                fallback_resp = requests.post(
                    fallback_url,
                    headers={**self._http_headers, "Content-Type": "application/json"},
                    json=payload,
                    timeout=(2, 4),
                )
                fallback_resp.raise_for_status()
                subjects = fallback_resp.json().get("data") or []
            if not subjects:
                self._online_failed_names.add(clean_name)
                return None
            images = subjects[0].get("images") or {}
            cover_url = images.get("large") or images.get("common") or images.get("small")
            if not cover_url:
                self._online_failed_names.add(clean_name)
                return None
            image_response = requests.get(cover_url, headers=self._http_headers, timeout=(2, 5))
            image_response.raise_for_status()
        except Exception:
            self._online_failed_names.add(clean_name)
            self._online_block_until_ts = time.time() + 120
            return None

        try:
            from io import BytesIO

            img = Image.open(BytesIO(image_response.content)).convert("RGB")
            img.save(cache_file, "JPEG", quality=92)
            return str(cache_file)
        except Exception:
            if cache_file.exists():
                cache_file.unlink(missing_ok=True)
            return None

    def _clean_game_name_for_search(self, name: str) -> str:
        cleaned = name
        cleaned = re.sub(r"\[.*?\]|\(.*?\)|\{.*?\}", " ", cleaned)
        cleaned = re.sub(r"v\d+(\.\d+)*|ver\.?|patch|final|krkr|riki", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]+", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()

    def import_custom_cover(self, game_id: int, source_path: str) -> str:
        source = Path(source_path)
        destination = self.cover_cache_dir / f"{game_id}{source.suffix.lower()}"
        with Image.open(source) as img:
            processed = self._scale_and_center_crop(img.convert("RGB"), 300, 420)
            processed.save(destination)
        return str(destination)

    @property
    def vndb_cache_dir(self) -> Path:
        path = self.cover_cache_dir / "vndb"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def cache_vndb_image(self, image_url: str, vndb_id: str) -> str | None:
        if not image_url or not vndb_id:
            return None
        ext = ".jpg"
        for candidate in (".jpg", ".jpeg", ".png", ".webp"):
            if image_url.lower().endswith(candidate):
                ext = candidate if candidate != ".jpeg" else ".jpg"
                break
        cache_file = self.vndb_cache_dir / f"{vndb_id}{ext}"
        if cache_file.exists() and cache_file.stat().st_size > 0:
            return str(cache_file)
        for attempt in range(3):
            try:
                response = requests.get(image_url, headers=self._http_headers, timeout=(3, 8))
                response.raise_for_status()
                from io import BytesIO

                img = Image.open(BytesIO(response.content)).convert("RGB")
                img.save(cache_file, "JPEG", quality=92)
                return str(cache_file)
            except Exception:
                if cache_file.exists():
                    cache_file.unlink(missing_ok=True)
                if attempt < 2:
                    time.sleep(min(0.8 * (2**attempt), 2.5))
        return None

    def cache_cover_with_fallback(
        self, image_url: str | None, cache_key: str, game_name: str | None = None
    ) -> str | None:
        if image_url:
            cached = self.cache_vndb_image(image_url, cache_key)
            if cached:
                return cached
        if game_name:
            return self._fetch_cover_online(game_name)
        return None

    def crop_cover(self, source_path: str, x: int, y: int, width: int, height: int) -> str:
        source = Path(source_path)
        destination = self.cover_cache_dir / f"crop_{source.name}"
        with Image.open(source) as img:
            cropped = img.crop((x, y, x + width, y + height)).convert("RGB")
            processed = self._scale_and_center_crop(cropped, 300, 420)
            processed.save(destination)
        return str(destination)

    def _scale_and_center_crop(self, image: Image.Image, target_w: int, target_h: int) -> Image.Image:
        src_w, src_h = image.size
        if src_w <= 0 or src_h <= 0:
            return image.resize((target_w, target_h))
        scale = max(target_w / src_w, target_h / src_h)
        scaled_w = max(1, int(src_w * scale))
        scaled_h = max(1, int(src_h * scale))
        resized = image.resize((scaled_w, scaled_h))
        left = max(0, (scaled_w - target_w) // 2)
        top = max(0, (scaled_h - target_h) // 2)
        return resized.crop((left, top, left + target_w, top + target_h))

    def delete_cover(self, cover_path: str) -> None:
        path = Path(cover_path)
        if path.exists() and path.is_file():
            path.unlink()
