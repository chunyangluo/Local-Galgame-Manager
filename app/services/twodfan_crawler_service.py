"""2DFan integrated crawler service — runs the crawler from within the main application."""

from __future__ import annotations

import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from app.services.paths import default_twodfan_sqlite_path


class TwodfanCrawlerService(QObject):
    """Runs the 2DFan crawler in a background thread using Playwright and emits progress signals."""

    progress = Signal(int, int, str)   # processed, total, current_title
    finished = Signal(bool, str)        # success, message
    page_done = Signal(int, str, int)   # download_id, title, hints_count
    log = Signal(str)                   # log message

    def __init__(
        self,
        *,
        max_pages: int = 0,  # 0 means all pages
        save_only: bool = True,
        cookie_header: str | None = None,
        use_playwright: bool = True,
        resume: bool = True,  # Whether to resume from last position
        skip_existing: bool = False,  # Whether to skip existing pages
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._max_pages = max_pages
        self._save_only = save_only
        self._cookie_header = cookie_header
        self._use_playwright = use_playwright
        self._resume = resume
        self._skip_existing = skip_existing
        self._cancel = False
        db_path = default_twodfan_sqlite_path()
        self._db_path = str(db_path) if db_path is not None else None

    def request_cancel(self) -> None:
        self._cancel = True

    def _log(self, msg: str) -> None:
        print(f"[2DFan Crawler] {msg}", flush=True)
        self.log.emit(msg)

    def run(self) -> None:
        """Execute the crawl. Call from a QThread."""
        self._log("开始爬取...")
        if self._db_path is None:
            self.finished.emit(False, "2DFan 线索库路径不可用，无法启动爬取。")
            return
        if self._use_playwright:
            self._run_with_playwright()
        else:
            self._run_with_httpx()

    def _run_with_playwright(self) -> None:
        """Use Playwright (Chromium) to bypass Cloudflare."""
        self._log("使用 Playwright 模式（Chromium 浏览器）...")
        
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.finished.emit(False, "Playwright 未安装\n请运行: pip install playwright && playwright install chromium")
            return

        try:
            # Add crawler to path for DB operations
            crawler_dir = str(Path(__file__).resolve().parent.parent.parent / "tools" / "2dfan-save-crawler")
            if crawler_dir not in sys.path:
                sys.path.insert(0, crawler_dir)

            from dfan_save_crawler.db import PageRow, connect, init_db, replace_hints, upsert_page, get_last_page, set_last_page, page_exists
            from dfan_save_crawler.parse import extract_save_hints, parse_download_detail, parse_download_list, parse_total_pages

            # Ensure DB exists
            init_db(self._db_path)

            self._log("启动 Chromium 浏览器（非 headless 模式以通过 Cloudflare）...")
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=False,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                    ]
                )
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    viewport={'width': 1280, 'height': 720},
                )
                page = context.new_page()
                
                # Set extra HTTP headers
                page.set_extra_http_headers({
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                })

                # Navigate to warm up (handles Cloudflare challenge)
                self._log("访问 2dfan.com (等待 Cloudflare 验证，可能需要手动点击)...")
                try:
                    page.goto("https://2dfan.com", timeout=90000, wait_until="domcontentloaded")
                    self._log(f"页面加载完成: {page.title()}")
                    
                    # Wait for Cloudflare challenge to complete
                    self._log("等待 Cloudflare 验证完成...")
                    page.wait_for_timeout(8000)
                    
                    # Check if we're still on challenge page
                    html = page.content()
                    if "cloudflare" in html.lower() or len(html) < 10000:
                        self._log("检测到 Cloudflare 验证页面，等待更长时间...")
                        page.wait_for_timeout(15000)
                        
                    self._log(f"访问成功: {page.title()}")
                except Exception as e:
                    self._log(f"访问失败: {e}")
                    browser.close()
                    self.finished.emit(False, f"无法访问 2dfan.com: {e}\n可能是网络问题或 Cloudflare 验证失败")
                    return

                total_processed = 0
                crawl_all = self._max_pages <= 0
                actual_max_pages = self._max_pages if self._max_pages > 0 else 999999
                
                # Get last page for resume
                start_page = 1
                if self._resume:
                    with connect(self._db_path) as conn:
                        start_page = get_last_page(conn) + 1
                        self._log(f"上次爬取到第 {start_page - 1} 页，从第 {start_page} 页继续")
                
                # First page determines total pages if crawling all
                first_page_url = "https://2dfan.com/downloads?page=1"
                self._log(f"访问首页获取页面信息: {first_page_url}")
                
                try:
                    page.goto(first_page_url, timeout=30000, wait_until="domcontentloaded")
                    page.wait_for_timeout(3000)
                except Exception as e:
                    self._log(f"首页访问失败: {e}")
                    browser.close()
                    self.finished.emit(False, f"无法访问列表页: {e}")
                    return
                
                first_html = page.content()
                total_pages = parse_total_pages(first_html) if crawl_all else None
                
                if crawl_all and total_pages:
                    actual_max_pages = total_pages
                    self._log(f"检测到总页数: {total_pages}，将爬取全部页面")
                    estimated_total = total_pages * 15
                elif crawl_all:
                    self._log("未能检测到总页数，将持续爬取直到无内容")
                    estimated_total = 999999
                else:
                    self._log(f"将爬取前 {actual_max_pages} 页")
                    estimated_total = actual_max_pages * 15

                for page_num in range(start_page, actual_max_pages + 1):
                    if self._cancel:
                        self.finished.emit(True, f"已取消，共处理 {total_processed} 个页面")
                        browser.close()
                        return

                    list_url = f"https://2dfan.com/downloads?page={page_num}"
                    self._log(f"访问列表页 {page_num}: {list_url}")
                    
                    try:
                        page.goto(list_url, timeout=30000, wait_until="domcontentloaded")
                        page.wait_for_timeout(3000)  # Wait for JS to render
                        
                        # Wait for download items to appear
                        try:
                            page.wait_for_selector('a[href*="/downloads/"]', timeout=10000)
                            self._log(f"列表页 {page_num} 找到下载链接元素")
                        except:
                            self._log(f"列表页 {page_num} 未找到下载链接元素，继续尝试")
                            
                    except Exception as e:
                        self._log(f"列表页 {page_num} 访问失败: {e}")
                        continue

                    # Get page content
                    html = page.content()
                    self._log(f"列表页 {page_num} HTML长度: {len(html)} 字符")
                        
                    items = parse_download_list(html)
                    self._log(f"列表页 {page_num} 解析到 {len(items)} 个链接")

                    if not items:
                        continue

                    if self._save_only:
                        items = [x for x in items if "存档" in x.title]
                        self._log(f"筛选存档相关: {len(items)} 个")

                    for it in items:
                        if self._cancel:
                            self.finished.emit(True, f"已取消，共处理 {total_processed} 个页面")
                            browser.close()
                            return

                        # Skip existing pages if requested
                        if self._skip_existing:
                            with connect(self._db_path) as conn:
                                if page_exists(conn, it.download_id):
                                    self._log(f"跳过已存在页面: {it.title[:50]}")
                                    continue

                        total_processed += 1
                        self.progress.emit(total_processed, estimated_total, it.title[:50])

                        try:
                            detail_page = context.new_page()
                            detail_page.goto(it.url, timeout=30000, wait_until="domcontentloaded")
                            detail_page.wait_for_timeout(500)
                            dhtml = detail_page.content()
                            detail_page.close()
                        except Exception as e:
                            self._log(f"详情页访问失败: {it.url} - {e}")
                            now = datetime.now(timezone.utc).isoformat()
                            with connect(self._db_path) as conn:
                                upsert_page(conn, PageRow(
                                    download_id=it.download_id, url=it.url, title=it.title,
                                    subject_url=None, intro_text=None, body_text="",
                                    fetched_at=now, http_status=0, error=str(e)
                                ))
                            continue

                        now = datetime.now(timezone.utc).isoformat()
                        detail = parse_download_detail(dhtml, it.download_id, it.url)
                        combined = "\n".join(
                            x for x in (detail.title or "", detail.intro_text or "", detail.body_text or "") if x
                        )
                        hints = extract_save_hints(combined)
                        
                        with connect(self._db_path) as conn:
                            upsert_page(conn, PageRow(
                                download_id=detail.download_id, url=detail.url,
                                title=detail.title or it.title, subject_url=detail.subject_url,
                                intro_text=detail.intro_text, body_text=detail.body_text,
                                fetched_at=now, http_status=200, error=None
                            ))
                            replace_hints(conn, detail.download_id, hints)

                        self.page_done.emit(it.download_id, detail.title or it.title, len(hints))
                    
                    # Save progress after each list page
                    with connect(self._db_path) as conn:
                        set_last_page(conn, page_num)
                    self._log(f"已保存进度到第 {page_num} 页")

                browser.close()

            self.finished.emit(True, f"爬取完成，共处理 {total_processed} 个页面")

        except Exception as e:
            tb = traceback.format_exc()
            self._log(f"Exception: {e}\n{tb}")
            self.finished.emit(False, f"爬取出错: {e}\n\n{tb}")

    def _run_with_httpx(self) -> None:
        """Fallback: use httpx (may fail on Cloudflare)."""
        self._log("使用 httpx 模式...")
        
        try:
            crawler_dir = str(Path(__file__).resolve().parent.parent.parent / "tools" / "2dfan-save-crawler")
            if crawler_dir not in sys.path:
                sys.path.insert(0, crawler_dir)

            from dfan_save_crawler.db import PageRow, connect, init_db, replace_hints, upsert_page, get_last_page, set_last_page, page_exists
            from dfan_save_crawler.fetch import BASE, RateLimitedClient, fetch_robots_summary
            from dfan_save_crawler.parse import extract_save_hints, parse_download_detail, parse_download_list, parse_total_pages

            init_db(self._db_path)

            client = RateLimitedClient(
                delay_sec=1.2,
                curl_cffi=False,
                cookie_header=self._cookie_header,
            )

            try:
                wst, wbody = client.warm_up()
                if wst == 403:
                    self.finished.emit(False, "访问 2dfan.com 被拒绝 (HTTP 403)\n建议使用 Playwright 模式")
                    return

                total_processed = 0
                crawl_all = self._max_pages <= 0
                actual_max_pages = self._max_pages if self._max_pages > 0 else 999999
                
                # Get last page for resume
                start_page = 1
                if self._resume:
                    with connect(self._db_path) as conn:
                        start_page = get_last_page(conn) + 1
                        self._log(f"上次爬取到第 {start_page - 1} 页，从第 {start_page} 页继续")
                
                # First page determines total pages if crawling all
                first_url = f"{BASE}/downloads?page=1"
                nav_headers = {
                    "Referer": f"{BASE}/",
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "same-origin",
                    "Sec-Fetch-User": "?1",
                }
                first_code, first_html = client.get_text(first_url, extra_headers=nav_headers)
                
                if first_code != 200:
                    self.finished.emit(False, f"无法访问列表首页: HTTP {first_code}")
                    return
                
                total_pages = parse_total_pages(first_html) if crawl_all else None
                
                if crawl_all and total_pages:
                    actual_max_pages = total_pages
                    self._log(f"检测到总页数: {total_pages}，将爬取全部页面")
                    estimated_total = total_pages * 15
                elif crawl_all:
                    self._log("未能检测到总页数，将持续爬取直到无内容")
                    estimated_total = 999999
                else:
                    self._log(f"将爬取前 {actual_max_pages} 页")
                    estimated_total = actual_max_pages * 15

                for page_num in range(start_page, actual_max_pages + 1):
                    if self._cancel:
                        self.finished.emit(True, f"已取消，共处理 {total_processed} 个页面")
                        return

                    list_url = f"{BASE}/downloads?page={page_num}"
                    code, html = client.get_text(list_url, extra_headers=nav_headers)

                    if code != 200:
                        continue

                    items = parse_download_list(html)
                    if not items:
                        continue

                    if self._save_only:
                        items = [x for x in items if "存档" in x.title]

                    for it in items:
                        if self._cancel:
                            self.finished.emit(True, f"已取消，共处理 {total_processed} 个页面")
                            return

                        # Skip existing pages if requested
                        if self._skip_existing:
                            with connect(self._db_path) as conn:
                                if page_exists(conn, it.download_id):
                                    self._log(f"跳过已存在页面: {it.title[:50]}")
                                    continue

                        total_processed += 1
                        self.progress.emit(total_processed, estimated_total, it.title[:50])

                        detail_nav = {
                            "Referer": list_url,
                            "Sec-Fetch-Dest": "document",
                            "Sec-Fetch-Mode": "navigate",
                            "Sec-Fetch-Site": "same-origin",
                            "Sec-Fetch-User": "?1",
                        }
                        dcode, dhtml = client.get_text(it.url, extra_headers=detail_nav)
                        now = datetime.now(timezone.utc).isoformat()

                        if dcode != 200:
                            with connect(self._db_path) as conn:
                                upsert_page(conn, PageRow(
                                    download_id=it.download_id, url=it.url, title=it.title,
                                    subject_url=None, intro_text=None, body_text="",
                                    fetched_at=now, http_status=dcode, error=f"HTTP {dcode}"
                                ))
                            continue

                        detail = parse_download_detail(dhtml, it.download_id, it.url)
                        combined = "\n".join(
                            x for x in (detail.title or "", detail.intro_text or "", detail.body_text or "") if x
                        )
                        hints = extract_save_hints(combined)
                        
                        with connect(self._db_path) as conn:
                            upsert_page(conn, PageRow(
                                download_id=detail.download_id, url=detail.url,
                                title=detail.title or it.title, subject_url=detail.subject_url,
                                intro_text=detail.intro_text, body_text=detail.body_text,
                                fetched_at=now, http_status=dcode, error=None
                            ))
                            replace_hints(conn, detail.download_id, hints)

                        self.page_done.emit(it.download_id, detail.title or it.title, len(hints))
                    
                    # Save progress after each list page
                    with connect(self._db_path) as conn:
                        set_last_page(conn, page_num)
                    self._log(f"已保存进度到第 {page_num} 页")

                self.finished.emit(True, f"爬取完成，共处理 {total_processed} 个页面")

            finally:
                client.close()

        except ImportError as e:
            self.finished.emit(False, f"缺少依赖: {e}\n请安装: pip install httpx beautifulsoup4")
        except Exception as e:
            tb = traceback.format_exc()
            self._log(f"Exception: {e}\n{tb}")
            self.finished.emit(False, f"爬取出错: {e}\n\n{tb}")
