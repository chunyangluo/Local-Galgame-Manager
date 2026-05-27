from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urljoin

from bs4 import BeautifulSoup


@dataclass(frozen=True)
class ListItem:
    download_id: int
    url: str
    title: str


@dataclass(frozen=True)
class DetailPage:
    download_id: int
    url: str
    title: str | None
    subject_url: str | None
    intro_text: str | None
    body_text: str


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def parse_total_pages(html: str) -> int | None:
    """Parse total page count from download list page HTML."""
    soup = BeautifulSoup(html, "html.parser")
    
    # Special handling for 2dfan "尾页" link - find the link containing "尾页" text
    for a in soup.select('a[href*="/downloads/page/"]'):
        if '尾页' in a.get_text():
            href = a.get("href", "")
            m = re.search(r'/downloads/page/(\d+)', href)
            if m:
                return int(m.group(1))
    
    # Try multiple patterns for pagination
    patterns = [
        # pattern: "共 123 页" or "共123页"
        re.compile(r'共\s*(\d+)\s*页'),
        # pattern: "123 pages" or "123Pages"
        re.compile(r'(\d+)\s*[Pp]ages?'),
        # data attributes
        re.compile(r'data-total=["\'](\d+)["\']'),
        re.compile(r'total\s*=\s*["\'](\d+)["\']', re.I),
    ]
    
    for pat in patterns:
        m = pat.search(html)
        if m:
            return int(m.group(1))
    
    # Try to find pagination UI element
    pagination = soup.select('.pagination, .pager, .page-nav, [class*="pagination"]')
    for p in pagination:
        text = p.get_text()
        for pat in patterns:
            m = pat.search(text)
            if m:
                return int(m.group(1))
    
    return None


def parse_download_list(html: str, base_url: str = "https://2dfan.com") -> list[ListItem]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[ListItem] = []
    
    # Try multiple selector patterns
    selectors = [
        'a[href^="/downloads/"]',
        'a[href*="/downloads/"]',
        'article a',
        '.download-item a',
        '.list-item a',
    ]
    
    found_links = set()
    
    for selector in selectors:
        for a in soup.select(selector):
            href = a.get("href") or ""
            m = re.match(r"^/downloads/(\d+)$", href)
            if not m:
                # Also check for full URL
                m = re.match(r"https?://2dfan\.com/downloads/(\d+)$", href)
            
            if not m:
                continue
            
            did = int(m.group(1))
            if did in found_links:
                continue
            
            title = _norm_ws(a.get_text(" ", strip=True))
            if not title:
                # Try to get title from parent element
                parent = a.find_parent(["article", "div", "li"])
                if parent:
                    title_elem = parent.find(["h3", "h2", ".title", ".name"])
                    if title_elem:
                        title = _norm_ws(title_elem.get_text(" ", strip=True))
            
            if not title:
                title = f"Download {did}"
            
            found_links.add(did)
            out.append(ListItem(did, urljoin(base_url, href), title))
    
    return out


def _first_text(soup: BeautifulSoup, selectors: Iterable[str]) -> str | None:
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            t = _norm_ws(el.get_text("\n", strip=True))
            if t:
                return t
    return None


def parse_download_detail(html: str, download_id: int, page_url: str) -> DetailPage:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    title = _first_text(
        soup,
        (
            "h1",
            "title",
            ".topic-title",
            "[itemprop=name]",
        ),
    )
    subject_url = None
    for a in soup.select('a[href^="/subjects/"]'):
        href = a.get("href") or ""
        if re.match(r"^/subjects/\d+", href):
            subject_url = urljoin("https://2dfan.com", href.split("#")[0])
            break

    intro = _first_text(soup, (".intro", ".summary", "meta[name=description]", ".download-intro"))

    body_el = soup.select_one("main") or soup.select_one("article") or soup.body
    body_text = _norm_ws(body_el.get_text("\n", strip=True)) if body_el else ""

    return DetailPage(
        download_id=download_id,
        url=page_url,
        title=title,
        subject_url=subject_url,
        intro_text=intro,
        body_text=body_text,
    )


_LINE_HINT_PATTERNS: list[tuple[re.Pattern[str], str, float]] = [
    (re.compile(r"存档位置\s*[:：]\s*(.+)", re.I), "save_location_colon", 0.95),
    (re.compile(r"セーブ(?:データ)?\s*[:：]\s*(.+)", re.I), "save_location_colon_ja", 0.9),
    (re.compile(r"(?:解压|解压缩|放置|覆盖)到\s*(.+)", re.I), "unpack_to", 0.75),
    (re.compile(r"(?:游戏|程式)?(?:根目录|安装目录|目录下)(?:的)?\s*([^\n。]{2,120})", re.I), "game_root_hint", 0.55),
]

_PATH_KEYWORDS = re.compile(
    r"(?:AppData|APPDATA|LOCALAPPDATA|LocalLow|Roaming|Local|"
    r"Documents|我的文档|文档\\\\|Saved Games|savedata|SaveData|SAVE|"
    r"セーブ|userdata|User Data|\.sav|save\.dat)",
    re.I,
)

_WIN_PATH = re.compile(r"(?:[A-Za-z]:\\|\\\\)[^\s\n\"'<>]{3,200}")


def extract_save_hints(full_text: str) -> list[tuple[str, str, float, str | None]]:
    """
    Returns list of (hint_text, hint_kind, confidence, source_line).
    """
    lines = [ln.strip() for ln in full_text.splitlines() if ln.strip()]
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str, float, str | None]] = []

    def add(text: str, kind: str, conf: float, line: str | None) -> None:
        text = _norm_ws(text)
        if len(text) < 4:
            return
        key = (text[:500], kind)
        if key in seen:
            return
        seen.add(key)
        out.append((text[:2000], kind, conf, line))

    for raw in lines:
        for pat, kind, conf in _LINE_HINT_PATTERNS:
            m = pat.search(raw)
            if m:
                add(m.group(1).strip(), kind, conf, raw[:500])
                break

    for raw in lines:
        if _PATH_KEYWORDS.search(raw):
            add(raw, "path_keyword_line", 0.65, raw[:500])

    for m in _WIN_PATH.finditer(full_text):
        span = m.group(0).strip().rstrip(".,;，。；")
        if len(span) > 5:
            add(span, "windows_path", 0.7, None)

    out.sort(key=lambda x: -x[2])
    return out[:50]
