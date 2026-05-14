"""Offline tests for HTML parsing and hint extraction (no network)."""

from dfan_save_crawler.parse import extract_save_hints, parse_download_detail, parse_download_list


def test_parse_download_list_dedupes_and_ids() -> None:
    html = """
    <html><body>
      <a href="/downloads/43341">Re:レムプラス全CG存档</a>
      <a href="/downloads/43341">duplicate</a>
      <a href="/downloads/1">Another全CG存档</a>
    </body></html>
    """
    items = parse_download_list(html)
    ids = sorted(i.download_id for i in items)
    assert ids == [1, 43341]


def test_extract_save_location_colon() -> None:
    text = "简介存档位置：文档\\slavenir\\お願い\n第二行 AppData\\LocalLow\\Foo"
    hints = extract_save_hints(text)
    kinds = {h[1] for h in hints}
    assert "save_location_colon" in kinds
    assert any("AppData" in h[0] for h in hints)


def test_parse_detail_subject_link() -> None:
    html = """
    <html><head><title>Page</title></head><body>
      <main>
        <h1>某游戏全CG存档</h1>
        <p>解压到游戏根目录savedata</p>
        <a href="/subjects/24690">去游戏页</a>
      </main>
    </body></html>
    """
    d = parse_download_detail(html, 99, "https://2dfan.com/downloads/99")
    assert d.download_id == 99
    assert "全CG存档" in (d.title or "")
    assert d.subject_url and "subjects/24690" in d.subject_url
