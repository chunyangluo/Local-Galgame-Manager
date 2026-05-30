"""2DFan爬取进度对话框 - 支持断点续传和增量更新"""

from __future__ import annotations

from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QTextEdit,
    QVBoxLayout,
    QGroupBox,
    QCheckBox,
)

from app.services.twodfan_crawler_service import TwodfanCrawlerService
from app.services.twodfan_hints import twodfan_db_stats
from app.services.paths import default_twodfan_sqlite_path
import sys
from pathlib import Path


class TwodfanCrawlDialog(QDialog):
    """2DFan爬取进度对话框 - 支持断点续传和增量更新"""

    def __init__(
        self,
        *,
        max_pages: int = 0,  # 0 means all pages
        save_only: bool = True,
        cookie_header: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("2DFan爬取")
        self.resize(620, 700)
        self._finished = False
        self._saved_cookie = cookie_header or ""

        layout = QVBoxLayout(self)

        # 标题
        header = QLabel("从2DFan爬取存档位置线索")
        header.setObjectName("gameTitle")
        layout.addWidget(header)

        # 当前状态信息
        state_group = QGroupBox("爬取状态")
        state_layout = QVBoxLayout(state_group)
        self._state_label = QLabel("正在加载状态...")
        self._state_label.setObjectName("gameMeta")
        self._state_label.setWordWrap(True)
        state_layout.addWidget(self._state_label)
        layout.addWidget(state_group)

        # 爬取选项
        options_group = QGroupBox("爬取选项")
        options_layout = QVBoxLayout(options_group)
        
        self._resume_checkbox = QCheckBox("断点续传（从上次中断的位置继续）")
        self._resume_checkbox.setChecked(True)
        options_layout.addWidget(self._resume_checkbox)
        
        self._skip_existing_checkbox = QCheckBox("跳过已存在页面（加快速度）")
        self._skip_existing_checkbox.setChecked(False)
        options_layout.addWidget(self._skip_existing_checkbox)
        
        layout.addWidget(options_group)

        # 访问方式
        config_group = QGroupBox("访问方式")
        config_layout = QVBoxLayout(config_group)
        
        mode_help = QLabel(
            "推荐使用Playwright模式（自动绕过Cloudflare）\n"
            "如果失败，可以尝试使用curl_cffi或手动配置Cookie"
        )
        mode_help.setObjectName("gameMeta")
        mode_help.setWordWrap(True)
        config_layout.addWidget(mode_help)

        self._playwright_checkbox = QCheckBox("Playwright模式（推荐）")
        self._playwright_checkbox.setChecked(True)
        config_layout.addWidget(self._playwright_checkbox)

        self._curl_checkbox = QCheckBox("curl_cffi模式（TLS伪装）")
        config_layout.addWidget(self._curl_checkbox)

        self._cookie_input = QLineEdit()
        self._cookie_input.setPlaceholderText("粘贴Cookie（可选，作为备用方案）")
        if cookie_header:
            self._cookie_input.setText(cookie_header)
        config_layout.addWidget(self._cookie_input)

        layout.addWidget(config_group)

        # 进度条
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        layout.addWidget(self._progress)

        # 状态标签
        self._status = QLabel("准备就绪，点击「开始爬取」")
        self._status.setObjectName("gameMeta")
        layout.addWidget(self._status)

        # 日志区域
        log_label = QLabel("爬取日志：")
        log_label.setObjectName("gameMeta")
        layout.addWidget(log_label)
        
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(180)
        layout.addWidget(self._log, 1)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)

        self._start_btn = QPushButton("开始爬取")
        self._start_btn.setProperty("btnRole", "primary")
        self._start_btn.clicked.connect(self._on_start)
        btn_layout.addWidget(self._start_btn)

        self._cancel_btn = QPushButton("取消")
        self._cancel_btn.setProperty("btnRole", "danger")
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self._cancel_btn)

        self._close_btn = QPushButton("关闭")
        self._close_btn.setProperty("btnRole", "secondary")
        self._close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self._close_btn)

        layout.addLayout(btn_layout)

        # 爬虫服务和线程
        self._service = None
        self._thread = None
        self._max_pages = max_pages
        self._save_only = save_only
        
        # 加载状态信息
        self._load_state_info()

    def _load_state_info(self) -> None:
        """Load and display current crawl state."""
        try:
            db_path = default_twodfan_sqlite_path()
            
            # Add crawler dir for db access
            crawler_dir = str(Path(__file__).resolve().parent.parent.parent / "tools" / "2dfan-save-crawler")
            if crawler_dir not in sys.path:
                sys.path.insert(0, crawler_dir)
            from dfan_save_crawler.db import connect, init_db, get_last_page
            
            init_db(db_path)
            
            stats = twodfan_db_stats(db_path)
            with connect(db_path) as conn:
                last_page = get_last_page(conn)
            
            if stats:
                pages, hints = stats
                state_text = f"已爬取: {pages} 个页面, {hints} 条线索\n"
            else:
                state_text = "数据库为空，尚未爬取任何数据\n"
            
            if last_page > 0:
                state_text += f"上次中断于: 第 {last_page} 页"
            else:
                state_text += "尚未开始爬取"
            
            self._state_label.setText(state_text)
        except Exception as e:
            self._state_label.setText(f"无法读取状态: {str(e)}")

    def _on_start(self) -> None:
        self._start_btn.setEnabled(False)
        self._cancel_btn.setEnabled(True)
        self._playwright_checkbox.setEnabled(False)
        self._curl_checkbox.setEnabled(False)
        self._cookie_input.setEnabled(False)
        self._resume_checkbox.setEnabled(False)
        self._skip_existing_checkbox.setEnabled(False)
        self._log.clear()

        use_playwright = self._playwright_checkbox.isChecked()
        use_curl = self._curl_checkbox.isChecked()
        cookie = self._cookie_input.text().strip() or None
        resume = self._resume_checkbox.isChecked()
        skip_existing = self._skip_existing_checkbox.isChecked()

        self._log.append(f"模式: {'Playwright' if use_playwright else 'httpx/curl_cffi'}")
        self._log.append(f"断点续传: {'是' if resume else '否'}")
        self._log.append(f"跳过已存在: {'是' if skip_existing else '否'}")
        if use_curl:
            self._log.append(f"使用curl_cffi: 是")
        if cookie:
            self._log.append(f"Cookie: 已配置")
        self._log.append("---")

        self._service = TwodfanCrawlerService(
            max_pages=self._max_pages,
            save_only=self._save_only,
            cookie_header=cookie,
            use_playwright=use_playwright,
            resume=resume,
            skip_existing=skip_existing,
            parent=self,
        )
        self._service.progress.connect(self._on_progress)
        self._service.page_done.connect(self._on_page_done)
        self._service.finished.connect(self._on_finished)
        self._service.log.connect(self._on_log)

        self._thread = QThread(self)
        self._service.moveToThread(self._thread)
        self._thread.started.connect(self._service.run)
        self._thread.start()

    def start(self) -> None:
        """Do nothing here, wait for user to click start button."""
        pass

    def _on_progress(self, processed: int, total: int, title: str) -> None:
        if total > 0:
            pct = min(100, int((processed / total) * 100))
            self._progress.setValue(pct)
        self._status.setText(f"正在处理: {title}")
        self._log.append(f"处理进度: {processed}")

    def _on_log(self, msg: str) -> None:
        """Handle log messages from service."""
        self._log.append(msg)

    def _on_page_done(self, download_id: int, title: str, hints_count: int) -> None:
        self._log.append(
            f"[{download_id}] {title[:50]} — {hints_count} 条线索"
        )

    def _on_finished(self, success: bool, message: str) -> None:
        self._finished = True
        if self._thread:
            self._thread.quit()
            self._thread.wait(3000)

        self._cancel_btn.setEnabled(False)
        self._start_btn.setEnabled(True)
        self._playwright_checkbox.setEnabled(True)
        self._curl_checkbox.setEnabled(True)
        self._cookie_input.setEnabled(True)
        self._resume_checkbox.setEnabled(True)
        self._skip_existing_checkbox.setEnabled(True)
        self._progress.setValue(100 if success else self._progress.value())

        if success:
            self._status.setText(message)
            self._log.append(f"✓ {message}")

            # Show stats
            db_path = default_twodfan_sqlite_path()
            stats = twodfan_db_stats(db_path)
            if stats:
                pages, hints = stats
                self._log.append(
                    f"线索库统计: {pages} 个页面, {hints} 条线索"
                )
            
            # Update state info
            self._load_state_info()
        else:
            self._status.setText("爬取失败")
            self._log.append(f"✗ 爬取失败")
            self._log.append(message)
            
            # Update state info even on failure
            self._load_state_info()

    def _on_cancel(self) -> None:
        self._cancel_btn.setEnabled(False)
        self._status.setText("正在取消...")
        self._log.append("正在取消...")
        if self._service:
            self._service.request_cancel()

    def reject(self) -> None:
        if not self._finished:
            self._on_cancel()
            return
        super().reject()
