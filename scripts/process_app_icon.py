"""Convert a square-ish PNG into app/assets app_icon.png + app_icon.ico."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRC = Path.home() / "Downloads" / "galgame管理器图标.png"
OUT_DIR = ROOT / "app" / "assets"
ICO_SIZES = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)]

# Pixels with any channel below this are always kept (line art, skin, hair).
INK_LUM = 240
# Near-white background threshold for exterior flood seeds.
BG_WHITE = 250


def _center_square(img: Image.Image) -> Image.Image:
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    return img.crop((left, top, left + side, top + side))


def _clamp_byte(value: float) -> int:
    return max(0, min(255, int(round(value))))


def _dilate_mask(mask: list[list[bool]], radius: int) -> list[list[bool]]:
    if radius <= 0:
        return mask
    h, w = len(mask), len(mask[0])
    for _ in range(radius):
        expanded = [row[:] for row in mask]
        for y in range(h):
            for x in range(w):
                if not mask[y][x]:
                    continue
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < h and 0 <= nx < w:
                            expanded[ny][nx] = True
        mask = expanded
    return mask


def _fill_row_holes(mask: list[list[bool]]) -> list[list[bool]]:
    h, w = len(mask), len(mask[0])
    out = [row[:] for row in mask]
    for y in range(h):
        xs = [x for x in range(w) if mask[y][x]]
        if len(xs) >= 2:
            for x in range(xs[0], xs[-1] + 1):
                out[y][x] = True
    return out


def _fill_col_holes(mask: list[list[bool]]) -> list[list[bool]]:
    h, w = len(mask), len(mask[0])
    out = [row[:] for row in mask]
    for x in range(w):
        ys = [y for y in range(h) if mask[y][x]]
        if len(ys) >= 2:
            for y in range(ys[0], ys[-1] + 1):
                out[y][x] = True
    return out


def _edge_alpha_from_white(r: int, g: int, b: int) -> int:
    """Map near-white fringe pixels to soft alpha (removes sticker white ring)."""
    return _clamp_byte((min(r, g, b) - 220) * 255 / 40)


def _decontaminate_white_bg(r: int, g: int, b: int, *, alpha_cap: int | None = None) -> tuple[int, int, int, int]:
    """Unblend a pixel that was composited on white; yields soft edge alpha."""
    alpha = min(r, g, b)
    if alpha_cap is not None:
        alpha = min(alpha, alpha_cap)
    if alpha <= 10:
        return (0, 0, 0, 0)
    a = alpha / 255.0
    fr = _clamp_byte((r - 255.0 * (1.0 - a)) / a)
    fg = _clamp_byte((g - 255.0 * (1.0 - a)) / a)
    fb = _clamp_byte((b - 255.0 * (1.0 - a)) / a)
    return (fr, fg, fb, alpha)


def _build_character_mask(px, w: int, h: int, *, dilate_r: int) -> list[list[bool]]:
    """Silhouette mask: character + interior whites (shirt), not outer background."""
    fg = [[False] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if min(r, g, b) < INK_LUM or max(r, g, b) - min(r, g, b) > 12:
                fg[y][x] = True

    mask = _fill_col_holes(_fill_row_holes(_dilate_mask(fg, dilate_r)))

    for y in range(h):
        for x in range(w):
            if min(px[x, y]) < INK_LUM:
                mask[y][x] = True
    return mask


def _matte_character_cutout(img_rgb: Image.Image, *, size: int) -> Image.Image:
    """Keep only the character; outside is transparent with soft anti-aliased edges."""
    w, h = img_rgb.size
    px = img_rgb.load()
    dilate_r = max(4, round(size * 14 / 1024))
    mask = _build_character_mask(px, w, h, dilate_r=dilate_r)

    out = Image.new("RGBA", (w, h))
    dst = out.load()
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if not mask[y][x]:
                if min(r, g, b) >= BG_WHITE:
                    dst[x, y] = (255, 255, 255, 0)
                elif min(r, g, b) < INK_LUM:
                    dst[x, y] = (r, g, b, 255)
                else:
                    dst[x, y] = _decontaminate_white_bg(r, g, b)
                continue

            touches_clear = False
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                ny, nx = y + dy, x + dx
                if ny < 0 or ny >= h or nx < 0 or nx >= w or not mask[ny][nx]:
                    touches_clear = True
                    break

            if min(r, g, b) < INK_LUM:
                dst[x, y] = (r, g, b, 255)
            elif touches_clear:
                cap = (
                    _edge_alpha_from_white(r, g, b)
                    if min(r, g, b) >= 230
                    else None
                )
                dst[x, y] = _decontaminate_white_bg(r, g, b, alpha_cap=cap)
            else:
                dst[x, y] = (r, g, b, 255)

    return out


def _render_icon(source: Path, size: int) -> Image.Image:
    base = _center_square(Image.open(source).convert("RGB"))
    inner = int(size * 0.88)
    scaled = base.resize((inner, inner), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (size, size), (255, 255, 255))
    offset = (size - inner) // 2
    canvas.paste(scaled, (offset, offset))
    return _matte_character_cutout(canvas, size=size)


def process_icon(source: Path, out_dir: Path = OUT_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    png = _render_icon(source, 1024)
    png_path = out_dir / "app_icon.png"
    png.save(png_path, optimize=True)

    icons = [_render_icon(source, s[0]) for s in ICO_SIZES]
    ico_path = out_dir / "app_icon.ico"
    icons[0].save(
        ico_path,
        format="ICO",
        sizes=[(i.width, i.height) for i in icons],
        append_images=icons[1:],
    )
    print(f"Wrote {png_path} ({png_path.stat().st_size} bytes)")
    print(f"Wrote {ico_path} ({ico_path.stat().st_size} bytes)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SRC)
    args = parser.parse_args()
    if not args.source.is_file():
        raise SystemExit(f"Source not found: {args.source}")
    process_icon(args.source)


if __name__ == "__main__":
    main()
