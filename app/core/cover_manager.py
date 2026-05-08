from __future__ import annotations
import re
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
    "title",
    "bg",
    "art",
    "splash",
)
DIR_BLACKLIST = (
    "save",
    "save_data",
    "backup",
    "patch",
    "update",
    "manual",
    "doc",
    "movie",
    "voice",
)

PRIMARY_NAME_KEYWORDS = (
    "cover",
    "title",
    "logo",
    "bg",
    "splash",
    "icon",
)
SECONDARY_NAME_KEYWORDS = (
    "game",
    "start",
    "main",
    "menu",
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
)
COVER_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


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
        game_keywords = self._extract_game_keywords(game_name or path.name)
        candidates = self._collect_image_candidates(path, whitelist_only=True, max_depth=1)
        if not candidates:
            # Fallback: widen candidate source but still honor blacklist and depth.
            candidates = self._collect_image_candidates(path, whitelist_only=False, max_depth=2)
            if not candidates:
                return None

        best_file: Path | None = None
        best_score = -10_000
        for file in candidates:
            score = self._score_cover_candidate(file, base_dir=path, game_keywords=game_keywords)
            if score > best_score:
                best_score = score
                best_file = file
        if best_file is not None:
            # If local match confidence is low, prefer online fallback when enabled.
            if self.cover_fetch_mode in {"local_prefer", "online_prefer"} and best_score < self.online_min_local_score:
                online = self._fetch_cover_online(game_name or path.name)
                if online:
                    return online
            return str(best_file)
        if self.cover_fetch_mode == "local_only":
            return None
        return self._fetch_cover_online(game_name or path.name)

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

    def _score_cover_candidate(self, file: Path, base_dir: Path, game_keywords: list[str]) -> int:
        name = file.stem.lower()
        score = 0

        if any(k in name for k in PRIMARY_NAME_KEYWORDS):
            score += 10
        if any(k in name for k in SECONDARY_NAME_KEYWORDS):
            score += 8
        if any(k in name for k in NEGATIVE_NAME_KEYWORDS):
            score -= 5
        if any(keyword and keyword in name for keyword in game_keywords):
            score += 15

        # Prefer files close to game root, cover assets are usually nearby.
        rel_depth = max(0, len(file.parent.parts) - len(base_dir.parts))
        score -= rel_depth * 3

        try:
            with Image.open(file) as img:
                width, height = img.size
                gray = img.convert("L")
                brightness = float(ImageStat.Stat(gray).mean[0])
        except Exception:
            return -9999

        # Basic quality filter for tiny assets.
        short_edge = min(width, height)
        if short_edge < 260:
            return -500

        ratio = width / max(1, height)

        # Prefer common title art ratios: 16:9 / 4:3 / 16:10 and portrait covers.
        ratio_targets = (16 / 9, 4 / 3, 16 / 10, 3 / 4, 9 / 16, 2 / 3)
        closest_delta = min(abs(ratio - target) for target in ratio_targets)
        if closest_delta <= 0.08:
            score += 14
        elif closest_delta <= 0.2:
            score += 6
        else:
            score -= 6

        # Reject extreme strip-like images.
        if ratio < 0.45 or ratio > 3.2:
            score -= 15

        pixel_area = width * height
        if pixel_area >= 900_000:
            score += 10

        # Avoid almost pure black/white resources.
        if brightness < 18 or brightness > 240:
            score -= 8

        return score

    def _is_in_whitelist_dir(self, file: Path, base_dir: Path) -> bool:
        rel_parts = file.relative_to(base_dir).parts[:-1]
        if not rel_parts:
            # Root-level files are strong candidates in many game folders.
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
        # Keep top few stable keywords to avoid over-penalizing filenames.
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
                # Fallback to newer API path when legacy path is unavailable/limited.
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
            # Ignore network failures to keep UI stable.
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
            # Keep card framing consistent: scale + center crop.
            processed = self._scale_and_center_crop(img.convert("RGB"), 300, 420)
            processed.save(destination)
        return str(destination)

    @property
    def vndb_cache_dir(self) -> Path:
        path = self.cover_cache_dir / "vndb"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def cache_vndb_image(self, image_url: str, vndb_id: str) -> str | None:
        """Download a VNDB CDN image once and return the cached local path.

        Returns ``None`` on any network/parse error so callers can fall back
        to URL-based or local lookups.
        """

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
        try:
            response = requests.get(image_url, headers=self._http_headers, timeout=(3, 8))
            response.raise_for_status()
        except Exception:
            return None
        try:
            from io import BytesIO

            img = Image.open(BytesIO(response.content)).convert("RGB")
            img.save(cache_file, "JPEG", quality=92)
            return str(cache_file)
        except Exception:
            if cache_file.exists():
                cache_file.unlink(missing_ok=True)
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
