from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dfan_save_crawler.db import PageRow, connect, init_db, iter_export_rows, replace_hints, upsert_page
from dfan_save_crawler.fetch import BASE, RateLimitedClient, fetch_robots_summary
from dfan_save_crawler.parse import extract_save_hints, parse_download_detail, parse_download_list


def _html_nav_headers(referer: str, *, sec_fetch_site: str = "same-origin") -> dict[str, str]:
    return {
        "Referer": referer,
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": sec_fetch_site,
        "Sec-Fetch-User": "?1",
    }


def _print_list_403_hint(body: str) -> None:
    # Windows GBK consoles may fail on arbitrary HTML; use ascii() for a safe peek.
    print(f"  body_preview_ascii: {ascii(body[:300])}")
    raw = body.encode("utf-8", errors="replace").lower()
    if (
        b"cloudflare" in raw
        or b"cf-ray" in raw
        or b"just a moment" in raw
        or b"challenge-platform" in raw
    ):
        print(
            "  hint: Cloudflare/WAF page — use a **fresh** Cookie from the same browser session "
            "(--cookie-file), add --curl-cffi if TLS is blocked, and run from the **same IP** as the browser."
        )
def _resolve_cookie_header(args: argparse.Namespace) -> str | None:
    """Prefer --cookie-file over --cookie (full Cookie header line)."""
    cf = (getattr(args, "cookie_file", "") or "").strip()
    if cf:
        p = Path(cf)
        if not p.is_file():
            print(f"error: --cookie-file not found: {p}", file=sys.stderr)
            raise SystemExit(2)
        return p.read_text(encoding="utf-8").strip() or None
    c = (args.cookie or "").strip()
    return c or None


def cmd_init(args: argparse.Namespace) -> int:
    init_db(args.db)
    print(f"Initialized {args.db}")
    return 0


def cmd_crawl(args: argparse.Namespace) -> int:
    init_db(args.db)
    try:
        cookie_header = _resolve_cookie_header(args)
    except SystemExit as e:
        return int(e.code)
    client = RateLimitedClient(
        delay_sec=args.delay,
        curl_cffi=args.curl_cffi,
        cookie_header=cookie_header,
    )
    try:
        if not args.no_warm:
            wst, _ = client.warm_up()
            print(f"warm-up GET / HTTP {wst}")
        st, rob = fetch_robots_summary(client)
        print(f"robots.txt HTTP {st}, body_chars={len(rob)}")

        total_processed = 0
        for page_num in range(args.start_page, args.start_page + args.max_pages):
            list_url = f"{BASE}/downloads?page={page_num}"
            code, html = client.get_text(list_url, extra_headers=_html_nav_headers(f"{BASE}/"))
            if code != 200:
                print(f"List page {page_num}: HTTP {code}, skip")
                if code == 403 and html:
                    _print_list_403_hint(html)
                continue
            items = parse_download_list(html)
            if not items:
                print(f"List page {page_num}: no links parsed (layout changed?)")
                continue

            if not args.all:
                items = [x for x in items if "存档" in x.title]
            if args.max_downloads:
                remain = args.max_downloads - total_processed
                if remain <= 0:
                    break
                items = items[:remain]

            for it in items:
                if args.max_downloads and total_processed >= args.max_downloads:
                    break
                detail_url = it.url
                dcode, dhtml = client.get_text(detail_url, extra_headers=_html_nav_headers(list_url))
                now = datetime.now(timezone.utc).isoformat()
                if dcode != 200:
                    with connect(args.db) as conn:
                        upsert_page(
                            conn,
                            PageRow(
                                download_id=it.download_id,
                                url=detail_url,
                                title=it.title,
                                subject_url=None,
                                intro_text=None,
                                body_text="",
                                fetched_at=now,
                                http_status=dcode,
                                error=f"HTTP {dcode}",
                            ),
                        )
                    print(f"[{it.download_id}] HTTP {dcode}")
                    total_processed += 1
                    continue

                detail = parse_download_detail(dhtml, it.download_id, detail_url)
                combined = "\n".join(
                    x
                    for x in (
                        detail.title or "",
                        detail.intro_text or "",
                        detail.body_text or "",
                    )
                    if x
                )
                hints = extract_save_hints(combined)
                with connect(args.db) as conn:
                    upsert_page(
                        conn,
                        PageRow(
                            download_id=detail.download_id,
                            url=detail.url,
                            title=detail.title or it.title,
                            subject_url=detail.subject_url,
                            intro_text=detail.intro_text,
                            body_text=detail.body_text,
                            fetched_at=now,
                            http_status=dcode,
                            error=None,
                        ),
                    )
                    replace_hints(conn, detail.download_id, hints)

                print(f"[{it.download_id}] hints={len(hints)} title={(detail.title or it.title)[:60]!r}")
                total_processed += 1
    finally:
        client.close()
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(args.db) as conn:
        rows = iter_export_rows(conn)
    with out_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Wrote {len(rows)} rows to {out_path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="2DFan save-location hint crawler")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("init", help="Create SQLite schema")
    pi.add_argument("--db", default="data/2dfan_saves.sqlite3")
    pi.set_defaults(func=cmd_init)

    pc = sub.add_parser("crawl", help="Crawl /downloads list pages and detail")
    pc.add_argument("--db", default="data/2dfan_saves.sqlite3")
    pc.add_argument("--start-page", type=int, default=1)
    pc.add_argument("--max-pages", type=int, default=1)
    pc.add_argument("--delay", type=float, default=1.2)
    pc.add_argument("--all", action="store_true", help="Include non-存档 titles")
    pc.add_argument("--max-downloads", type=int, default=0, help="Cap detail fetches (0 = no cap)")
    pc.add_argument(
        "--curl-cffi",
        action="store_true",
        help="Use curl_cffi TLS impersonation (pip install curl_cffi); often fixes HTTP 403",
    )
    pc.add_argument(
        "--cookie",
        default="",
        metavar="STRING",
        help="Raw Cookie header line from browser (use --cookie-file if quoting is painful)",
    )
    pc.add_argument(
        "--cookie-file",
        default="",
        metavar="PATH",
        help="UTF-8 file whose entire contents are sent as the Cookie header (not committed to git: use data/cookies.txt)",
    )
    pc.add_argument(
        "--no-warm",
        action="store_true",
        help="Skip GET / warm-up (not recommended; for debugging only)",
    )
    pc.set_defaults(func=cmd_crawl)

    pe = sub.add_parser("export", help="Export pages+hints as JSONL")
    pe.add_argument("--db", default="data/2dfan_saves.sqlite3")
    pe.add_argument("--out", default="export/hints.jsonl")
    pe.set_defaults(func=cmd_export)

    args = p.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
