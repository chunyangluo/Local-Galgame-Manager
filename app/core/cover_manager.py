from __future__ import annotations
from pathlib import Path

from PIL import Image


COVER_KEYWORDS = ("cover", "封面", "title", "bg", "package")
COVER_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


class CoverManager:
    def __init__(self, cover_cache_dir: Path) -> None:
        self.cover_cache_dir = cover_cache_dir
        self.cover_cache_dir.mkdir(parents=True, exist_ok=True)

    def find_cover(self, game_dir: str) -> str | None:
        path = Path(game_dir)
        if not path.exists():
            return None
        for file in path.iterdir():
            if not file.is_file():
                continue
            if file.suffix.lower() not in COVER_EXTENSIONS:
                continue
            lower = file.name.lower()
            if any(k in lower for k in COVER_KEYWORDS):
                return str(file)
        for file in path.iterdir():
            if file.is_file() and file.suffix.lower() in COVER_EXTENSIONS:
                return str(file)
        return None

    def import_custom_cover(self, game_id: int, source_path: str) -> str:
        source = Path(source_path)
        destination = self.cover_cache_dir / f"{game_id}{source.suffix.lower()}"
        with Image.open(source) as img:
            # Keep a consistent portrait ratio for card rendering.
            resized = img.convert("RGB").resize((300, 420))
            resized.save(destination)
        return str(destination)

    def crop_cover(self, source_path: str, x: int, y: int, width: int, height: int) -> str:
        source = Path(source_path)
        destination = self.cover_cache_dir / f"crop_{source.name}"
        with Image.open(source) as img:
            cropped = img.crop((x, y, x + width, y + height)).resize((300, 420))
            cropped.save(destination)
        return str(destination)

    def delete_cover(self, cover_path: str) -> None:
        path = Path(cover_path)
        if path.exists() and path.is_file():
            path.unlink()
