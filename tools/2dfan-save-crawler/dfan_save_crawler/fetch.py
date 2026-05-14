from __future__ import annotations

import time
from typing import Any

import httpx

from dfan_save_crawler import __version__


BASE = "https://2dfan.com"
CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
DEFAULT_UA = (
    f"dfan-save-crawler/{__version__} (+local research; respectful crawl; "
    "contact via project maintainer)"
)

# 贴近真实 Chrome 导航，部分 CDN 会校验这些头
_CHROME_CLIENT_HINTS: dict[str, str] = {
    "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
}


class RateLimitedClient:
    """
    HTTP GET with fixed delay between requests.
    Use ``curl_cffi=True`` when the site returns 403 (Cloudflare); optional ``cookie_header``
    is the raw ``Cookie`` request line copied from the browser (preferred over parsing).
    Call ``warm_up()`` once before hitting ``/downloads`` — many WAFs expect a normal HTML hit first.
    """

    def __init__(
        self,
        delay_sec: float = 1.2,
        timeout: float = 30.0,
        *,
        curl_cffi: bool = False,
        cookie_header: str | None = None,
    ) -> None:
        self._delay = delay_sec
        self._last = 0.0
        self._timeout = timeout
        self._curl_cffi = curl_cffi
        self._cookie_header = (cookie_header or "").strip() or None
        self._client: httpx.Client | None = None
        self._cr_session: Any = None

        base_headers = {
            "User-Agent": CHROME_UA,
            "X-DFan-Save-Crawler": DEFAULT_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,ja;q=0.8,en-US;q=0.7,en;q=0.6",
            "Accept-Encoding": "gzip, deflate, br",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
        }
        base_headers.update(_CHROME_CLIENT_HINTS)
        if self._cookie_header:
            base_headers["Cookie"] = self._cookie_header

        if curl_cffi:
            try:
                from curl_cffi import requests as cr  # type: ignore[import-untyped]
            except ImportError as e:
                raise SystemExit(
                    "curl_cffi is not installed. Run: pip install curl_cffi\n"
                    "Then retry with --curl-cffi (helps with some Cloudflare 403 responses)."
                ) from e
            self._cr_session = cr.Session()
            self._cffi_default_headers = dict(base_headers)
        else:
            self._cffi_default_headers = {}
            self._client = httpx.Client(
                headers=base_headers,
                follow_redirects=True,
                timeout=timeout,
                trust_env=True,
            )

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
        if self._cr_session is not None:
            closer = getattr(self._cr_session, "close", None)
            if callable(closer):
                closer()

    def _sleep_if_needed(self) -> None:
        now = time.monotonic()
        wait = self._delay - (now - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()

    def get_text(self, url: str, *, extra_headers: dict[str, str] | None = None) -> tuple[int, str]:
        self._sleep_if_needed()
        merge = dict(extra_headers or {})
        if self._cr_session is not None:
            kw: dict[str, Any] = {"impersonate": "chrome131", "timeout": self._timeout}
            hdrs = dict(self._cffi_default_headers)
            hdrs.update(merge)
            kw["headers"] = hdrs
            r = self._cr_session.get(url, **kw)
            return int(r.status_code), r.text
        assert self._client is not None
        r = self._client.get(url, headers=merge or None)
        return r.status_code, r.text

    def warm_up(self) -> tuple[int, str]:
        """GET 站点首页，便于后续 /downloads 带上 same-origin 导航特征。"""
        return self.get_text(
            f"{BASE}/",
            extra_headers={
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
            },
        )


def fetch_robots_summary(client: RateLimitedClient) -> tuple[int, str]:
    status, body = client.get_text(
        f"{BASE}/robots.txt",
        extra_headers={
            "Referer": f"{BASE}/",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
        },
    )
    snippet = body.replace("\r\n", "\n")[:800] if body else ""
    return status, snippet
