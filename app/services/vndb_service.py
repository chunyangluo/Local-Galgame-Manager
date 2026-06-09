"""VNDB API client service (no-auth public access).

Implements the public, unauthenticated portion of the VNDB Kana API
(https://api.vndb.org/kana). Provides title search and a normalized
result model with structured failure reasons so the UI can show
actionable summaries to the user.

Notes on rate limits / fairness:
- The unauthenticated tier permits ~200 requests / 5 minutes per IP.
- This service applies a small per-process throttle (token bucket) and
  bounded retries with backoff for transient failures.
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

try:  # ``requests`` is part of project requirements; defensive fallback.
    import requests
except Exception:  # pragma: no cover - requests should be present
    requests = None  # type: ignore[assignment]


VNDB_BASE_URL = "https://api.vndb.org/kana"
VNDB_VN_ENDPOINT = f"{VNDB_BASE_URL}/vn"
BANGUMI_SEARCH_ENDPOINT = "https://api.bgm.tv/search/subject/{keyword}?type=4&max_results={limit}"
BANGUMI_V0_SEARCH_ENDPOINT = "https://api.bgm.tv/v0/search/subjects"

# Fields requested in a single search call. Keep this minimal but enough
# for UI rendering and persistence.
_VN_FIELDS = ",".join(
    [
        "id",
        "title",
        "alttitle",
        "titles{lang,title,latin,official,main}",
        "description",
        "rating",
        "released",
        "platforms",
        "languages",
        "image.url",
        "image.sexual",
        "image.violence",
        "screenshots.url",
        "screenshots.thumbnail",
    ]
)


# Failure kind constants used by the UI/CLI summary dialog.
ERR_TIMEOUT = "timeout"
ERR_NO_MATCH = "no_match"
ERR_HTTP = "http_error"
ERR_PARSE = "parse_error"
ERR_RATE_LIMIT = "rate_limit"
ERR_NETWORK = "network_error"
ERR_DEPENDENCY = "missing_requests"


@dataclass
class VndbRecord:
    """Normalized VNDB record persisted by the importer."""

    vndb_id: str
    title: str
    title_original: str | None = None
    title_localized: str | None = None
    description: str | None = None
    rating: float | None = None
    released: str | None = None
    platforms: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    image_url: str | None = None
    screenshots: list[str] = field(default_factory=list)

    def screenshots_to_json(self) -> str | None:
        if not self.screenshots:
            return None
        return json.dumps(self.screenshots, ensure_ascii=False)

    def platforms_to_str(self) -> str | None:
        if not self.platforms:
            return None
        return ",".join(self.platforms)

    def languages_to_str(self) -> str | None:
        if not self.languages:
            return None
        return ",".join(self.languages)


@dataclass
class VndbOutcome:
    """Result of a single VNDB lookup."""

    query: str
    success: bool
    record: VndbRecord | None = None
    error_kind: str | None = None
    error_detail: str | None = None
    candidates: list[VndbRecord] | None = None  # 多个候选结果供选择


_VERSION_TAG_RE = re.compile(
    r"\b(v\d+(?:\.\d+)*|ver\.?|patch|final|repack|update|trial|demo|krkr|riki|youkoso)\b",
    re.IGNORECASE,
)
_BRACKET_RE = re.compile(r"[\[\(\【\(].*?[\]\)\】\)]")
# VNDB 检索用：移除几乎所有非文字符号
_SYMBOL_RE = re.compile(r"[^\w\u4e00-\u9fff\u3040-\u30ff\u3400-\u4dbf]+", re.UNICODE)
# 本地展示用：保留游戏常用符号（- ~ ! ? ☆ ♡ 等）
_DISPLAY_SYMBOL_RE = re.compile(
    r"[^\w\u4e00-\u9fff\u3040-\u30ff\u3400-\u4dbf\-\~\!\?☆♡★♥♦♠♣♪●○◎◇◆□■△▽▽△]+",
    re.UNICODE,
)
# 平台/语言标识
_PLATFORM_TAG_RE = re.compile(
    r"\b(chs|cht|cn|jp|en|kr|jpn|eng|kor|中文|简体|繁体|日文|英文|汉化|全cg|存档|绿色版|免安装)\b",
    re.IGNORECASE,
)


def clean_title_for_search(name: str) -> str:
    """Normalize a noisy folder name into a clean VNDB search query.

    Aggressive cleaning: strips brackets, version tags, platform tags,
    and most symbols. Designed for maximum API match rate.
    """
    if not name:
        return ""
    text = _BRACKET_RE.sub(" ", name)
    text = _VERSION_TAG_RE.sub(" ", text)
    text = _PLATFORM_TAG_RE.sub(" ", text)
    text = _SYMBOL_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def clean_title_for_display(name: str) -> str:
    """Light cleaning for local display: preserves game-common symbols.

    Only strips brackets, version tags, and platform/language tags,
    but keeps characters like - ~ ! ? ☆ ♡ that are part of the title.
    """
    if not name:
        return ""
    text = _BRACKET_RE.sub(" ", name)
    text = _VERSION_TAG_RE.sub(" ", text)
    text = _PLATFORM_TAG_RE.sub(" ", text)
    text = _DISPLAY_SYMBOL_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


class _RateLimiter:
    """Simple thread-safe token bucket for outbound VNDB requests."""

    def __init__(self, requests_per_second: float = 1.5) -> None:
        self._interval = 1.0 / max(requests_per_second, 0.1)
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                wait = self._next_allowed - now
                if wait <= 0:
                    self._next_allowed = now + self._interval
                    return
            time.sleep(wait)


class VndbService:
    """No-auth VNDB client with retry/timeout and a normalized output model."""

    def __init__(
        self,
        *,
        timeout: tuple[float, float] = (4.0, 8.0),
        max_retries: int = 2,
        requests_per_second: float = 1.5,
        user_agent: str = "LocalGalgameManager/2.0 (+vndb-only-import)",
    ) -> None:
        self._timeout = timeout
        self._max_retries = max(0, int(max_retries))
        self._limiter = _RateLimiter(requests_per_second=requests_per_second)
        self._headers = {
            "User-Agent": user_agent,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        self._session = requests.Session() if requests is not None else None

    # ---------------------------------------------------------------- public

    def search_title(self, query: str, limit: int = 1, *, extra_queries: list[str] | None = None) -> VndbOutcome:
        """Search by title and return the best match (or a structured error).

        ``limit`` controls how many candidates the API should consider
        before we pick the top result. We always normalize and return
        a single :class:`VndbOutcome`.

        ``extra_queries`` allows providing additional search terms
        (e.g. window title) for multi-keyword parallel search.
        """
        cleaned = clean_title_for_search(query)
        if not cleaned and not extra_queries:
            return VndbOutcome(query=query, success=False, error_kind=ERR_NO_MATCH,
                               error_detail="empty query")
        if requests is None or self._session is None:
            return VndbOutcome(query=query, success=False, error_kind=ERR_DEPENDENCY,
                               error_detail="requests package not installed")

        # 收集所有检索词（去重、去空）
        all_queries: list[str] = []
        if cleaned:
            all_queries.append(cleaned)
        if extra_queries:
            for eq in extra_queries:
                eq_cleaned = clean_title_for_search(eq)
                if eq_cleaned and eq_cleaned not in all_queries:
                    all_queries.append(eq_cleaned)

        # 依次用每个检索词查询，取第一个成功结果
        best_outcome: VndbOutcome | None = None
        candidate_records: list[VndbRecord] = []
        
        for q in all_queries:
            body = {
                "filters": ["search", "=", q],
                "fields": _VN_FIELDS,
                "results": max(5, min(limit, 25)),  # 获取更多候选结果
                "sort": "searchrank",
            }
            outcome = self._post_json(VNDB_VN_ENDPOINT, body, query)
            if outcome.success and outcome.record is not None:
                best_outcome = outcome
                # 收集所有候选记录
                if hasattr(outcome, 'candidates') and outcome.candidates:
                    candidate_records.extend(outcome.candidates)
                candidate_records.append(outcome.record)
                break
            # 记录第一个有意义的错误
            if best_outcome is None:
                best_outcome = outcome

        if best_outcome is None:
            best_outcome = VndbOutcome(query=query, success=False, error_kind=ERR_NO_MATCH,
                                       error_detail="no candidates from any query")

        if not best_outcome.success:
            # Fallback: use Bangumi as secondary metadata source.
            for q in all_queries:
                bgm_outcome = self._search_bangumi(q, original_query=query, limit=limit)
                if bgm_outcome.success:
                    return bgm_outcome
            return best_outcome

        # 设置候选列表（去重）
        seen_ids = set()
        unique_candidates = []
        for rec in candidate_records:
            if rec.vndb_id not in seen_ids:
                seen_ids.add(rec.vndb_id)
                unique_candidates.append(rec)
        best_outcome.candidates = unique_candidates[:10]  # 最多保留10个候选

        # VNDB hit but sometimes lacks usable cover; enrich with Bangumi image.
        if best_outcome.record is not None and not best_outcome.record.image_url:
            for q in all_queries:
                bgm_outcome = self._search_bangumi(q, original_query=query, limit=limit)
                if bgm_outcome.success and bgm_outcome.record is not None:
                    bgm = bgm_outcome.record
                    if bgm.image_url:
                        best_outcome.record.image_url = bgm.image_url
                    if not best_outcome.record.title_localized and bgm.title_localized:
                        best_outcome.record.title_localized = bgm.title_localized
                    if not best_outcome.record.title_original and bgm.title_original:
                        best_outcome.record.title_original = bgm.title_original
                    break
        return best_outcome

    def fetch_details(self, vndb_id: str) -> VndbOutcome:
        """Fetch full record for a known VNDB id."""

        if not vndb_id:
            return VndbOutcome(query=vndb_id, success=False, error_kind=ERR_NO_MATCH,
                               error_detail="empty vndb_id")
        if requests is None or self._session is None:
            return VndbOutcome(query=vndb_id, success=False, error_kind=ERR_DEPENDENCY,
                               error_detail="requests package not installed")
        body = {
            "filters": ["id", "=", vndb_id],
            "fields": _VN_FIELDS,
            "results": 1,
        }
        return self._post_json(VNDB_VN_ENDPOINT, body, vndb_id)

    @staticmethod
    def normalize_result(raw: dict[str, Any]) -> VndbRecord | None:
        """Convert a VNDB ``vn`` API record into our normalized model."""

        if not isinstance(raw, dict):
            return None
        vn_id = str(raw.get("id") or "").strip()
        if not vn_id:
            return None
        title = str(raw.get("title") or "").strip()
        alttitle = raw.get("alttitle")
        title_localized = str(alttitle).strip() if alttitle else None

        title_original: str | None = None
        titles = raw.get("titles")
        if isinstance(titles, list):
            for entry in titles:
                if not isinstance(entry, dict):
                    continue
                if entry.get("main") and entry.get("title"):
                    title_original = str(entry["title"]).strip() or title_original
                if entry.get("lang") == "ja" and entry.get("title"):
                    title_original = str(entry["title"]).strip()
                    break

        description = raw.get("description")
        description = str(description).strip() if description else None
        rating_raw = raw.get("rating")
        rating: float | None
        try:
            rating = float(rating_raw) if rating_raw is not None else None
        except (TypeError, ValueError):
            rating = None
        released = raw.get("released")
        released = str(released).strip() if released else None

        platforms_raw = raw.get("platforms") or []
        platforms = [str(p).strip() for p in platforms_raw if str(p).strip()]
        languages_raw = raw.get("languages") or []
        languages = [str(l).strip() for l in languages_raw if str(l).strip()]

        image = raw.get("image")
        image_url: str | None = None
        if isinstance(image, dict):
            url = image.get("url")
            if isinstance(url, str) and url.strip():
                image_url = url.strip()

        screenshots_raw = raw.get("screenshots") or []
        screenshots: list[str] = []
        if isinstance(screenshots_raw, list):
            for shot in screenshots_raw:
                if isinstance(shot, dict):
                    shot_url = shot.get("url") or shot.get("thumbnail")
                    if isinstance(shot_url, str) and shot_url.strip():
                        screenshots.append(shot_url.strip())

        if not title:
            title = title_original or title_localized or vn_id

        return VndbRecord(
            vndb_id=vn_id,
            title=title,
            title_original=title_original,
            title_localized=title_localized,
            description=description,
            rating=rating,
            released=released,
            platforms=platforms,
            languages=languages,
            image_url=image_url,
            screenshots=screenshots,
        )

    # ----------------------------------------------------------- internals

    def _post_json(self, url: str, body: dict[str, Any], original_query: str) -> VndbOutcome:
        assert self._session is not None  # narrowed by callers
        last_error: tuple[str, str] | None = None
        for attempt in range(self._max_retries + 1):
            self._limiter.acquire()
            try:
                response = self._session.post(
                    url,
                    headers=self._headers,
                    data=json.dumps(body),
                    timeout=self._timeout,
                )
            except requests.exceptions.Timeout as exc:  # type: ignore[union-attr]
                last_error = (ERR_TIMEOUT, f"timeout after {self._timeout}s ({exc})")
                self._sleep_backoff(attempt)
                continue
            except requests.exceptions.RequestException as exc:  # type: ignore[union-attr]
                last_error = (ERR_NETWORK, str(exc))
                self._sleep_backoff(attempt)
                continue

            status = response.status_code
            if status == 429:
                last_error = (ERR_RATE_LIMIT, "rate limited (429)")
                self._sleep_backoff(attempt, base=2.0)
                continue
            if 500 <= status < 600:
                last_error = (ERR_HTTP, f"server error {status}")
                self._sleep_backoff(attempt)
                continue
            if status >= 400:
                detail = response.text[:200] if response.text else ""
                return VndbOutcome(
                    query=original_query,
                    success=False,
                    error_kind=ERR_HTTP,
                    error_detail=f"{status}: {detail}",
                )

            try:
                payload = response.json()
            except ValueError as exc:
                return VndbOutcome(
                    query=original_query,
                    success=False,
                    error_kind=ERR_PARSE,
                    error_detail=str(exc),
                )

            if not isinstance(payload, dict):
                return VndbOutcome(
                    query=original_query,
                    success=False,
                    error_kind=ERR_PARSE,
                    error_detail="response is not an object",
                )

            results = payload.get("results")
            if not isinstance(results, list) or not results:
                return VndbOutcome(
                    query=original_query,
                    success=False,
                    error_kind=ERR_NO_MATCH,
                    error_detail="no candidates",
                )

            record = self.normalize_result(results[0])
            if record is None:
                return VndbOutcome(
                    query=original_query,
                    success=False,
                    error_kind=ERR_PARSE,
                    error_detail="record missing id/title",
                )
            return VndbOutcome(query=original_query, success=True, record=record)

        kind, detail = last_error or (ERR_NETWORK, "exhausted retries")
        return VndbOutcome(query=original_query, success=False, error_kind=kind, error_detail=detail)

    def _search_bangumi(self, cleaned_query: str, original_query: str, limit: int = 1) -> VndbOutcome:
        assert self._session is not None  # narrowed by callers
        safe_limit = max(1, min(limit, 10))
        try:
            self._limiter.acquire()
            resp = self._session.get(
                BANGUMI_SEARCH_ENDPOINT.format(keyword=cleaned_query, limit=safe_limit),
                headers=self._headers,
                timeout=self._timeout,
            )
            if resp.status_code < 400:
                payload = resp.json()
                subjects = payload.get("list") if isinstance(payload, dict) else None
                record = self._normalize_bangumi_subject((subjects or [None])[0])
                if record is not None:
                    return VndbOutcome(query=original_query, success=True, record=record)
        except Exception:
            pass

        try:
            self._limiter.acquire()
            payload = {"keyword": cleaned_query, "filter": {"type": [4]}, "limit": safe_limit}
            resp = self._session.post(
                BANGUMI_V0_SEARCH_ENDPOINT,
                headers=self._headers,
                data=json.dumps(payload),
                timeout=self._timeout,
            )
            if resp.status_code >= 400:
                return VndbOutcome(
                    query=original_query,
                    success=False,
                    error_kind=ERR_HTTP,
                    error_detail=f"bangumi {resp.status_code}",
                )
            data = resp.json()
            subjects = data.get("data") if isinstance(data, dict) else None
            record = self._normalize_bangumi_subject((subjects or [None])[0])
            if record is None:
                return VndbOutcome(
                    query=original_query,
                    success=False,
                    error_kind=ERR_NO_MATCH,
                    error_detail="bangumi no candidates",
                )
            return VndbOutcome(query=original_query, success=True, record=record)
        except Exception as exc:
            return VndbOutcome(
                query=original_query,
                success=False,
                error_kind=ERR_NETWORK,
                error_detail=f"bangumi fallback failed: {exc}",
            )

    @staticmethod
    def _normalize_bangumi_subject(raw: Any) -> VndbRecord | None:
        if not isinstance(raw, dict):
            return None
        sid = raw.get("id")
        if sid is None:
            return None
        title = str(raw.get("name") or raw.get("name_cn") or "").strip()
        if not title:
            return None
        images = raw.get("images") if isinstance(raw.get("images"), dict) else {}
        image_url = (
            images.get("large")
            or images.get("common")
            or images.get("medium")
            or images.get("small")
        )
        rating = None
        rating_info = raw.get("rating")
        if isinstance(rating_info, dict):
            score = rating_info.get("score")
            try:
                rating = float(score) if score is not None else None
            except (TypeError, ValueError):
                rating = None
        return VndbRecord(
            vndb_id=f"bgm:{sid}",
            title=title,
            title_original=str(raw.get("name") or "").strip() or None,
            title_localized=str(raw.get("name_cn") or "").strip() or None,
            description=None,
            rating=rating,
            released=None,
            platforms=[],
            languages=[],
            image_url=str(image_url).strip() if image_url else None,
            screenshots=[],
        )

    @staticmethod
    def _sleep_backoff(attempt: int, base: float = 0.6) -> None:
        delay = base * (2 ** attempt)
        time.sleep(min(delay, 5.0))
