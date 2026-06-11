"""Tabbed help / welcome guide with interactive demo actions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.services.help_content import (
    APP_HELP_VERSION,
    DEMO_STEPS,
    HELP_BODY_FONT_PX,
    HELP_NOTICE_FONT_PX,
    USAGE_DISCLAIMER,
    WELCOME_STEPS,
    WELCOME_TAGLINE,
    faq_html,
    guide_html,
    links_html,
    resolve_help_screenshot,
    support_contact_html,
)
from app.services.app_branding import APP_DISPLAY_NAME

if TYPE_CHECKING:
    from app.ui.main_window import MainWindow


class HelpDialog(QDialog):
    """In-app help: welcome, manual, interactive demo, FAQ, and links."""

    action_requested = Signal(str)

    def __init__(
        self,
        main: MainWindow,
        *,
        first_run: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent if parent is not None else main)
        self._main = main
        self._first_run = first_run
        self._demo_index = 0

        self.setWindowTitle(
            f"欢迎使用 — {APP_DISPLAY_NAME}" if first_run else "使用帮助"
        )
        self.setMinimumSize(780 if first_run else 700, 640)
        self.resize(820, 700)

        root = QVBoxLayout(self)
        root.setSpacing(12)

        root.addWidget(self._build_notice_banner())

        if first_run:
            banner = QLabel(
                f"<b style='font-size:17px;color:#8AB4E0;'>👋 欢迎首次使用 {APP_DISPLAY_NAME}</b>"
                f"<br><span style='color:#93A1B6;font-size:14px;'>"
                f"下面用约 1 分钟了解基本流程；可随时点工具栏「帮助」再次打开。</span>"
            )
            banner.setWordWrap(True)
            banner.setTextFormat(Qt.TextFormat.RichText)
            root.addWidget(banner)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_welcome_tab(), "快速入门")
        self._tabs.addTab(self._build_demo_tab(), "交互演示")
        self._tabs.addTab(self._build_browser_tab(guide_html()), "功能手册")
        self._tabs.addTab(self._build_browser_tab(faq_html()), "常见问题")
        self._tabs.addTab(self._build_browser_tab(links_html()), "工具与链接")
        root.addWidget(self._tabs, 1)

        if first_run:
            self._skip_next = QCheckBox("下次启动不再自动显示本指南")
            self._skip_next.setChecked(True)
            root.addWidget(self._skip_next)

        btn_row = QHBoxLayout()
        if first_run:
            btn_start = QPushButton("🚀 开始：添加游戏目录")
            btn_start.setProperty("btnKind", "primary")
            btn_start.clicked.connect(self._start_with_add_root)
            btn_row.addWidget(btn_start)

            btn_demo = QPushButton("打开交互演示")
            btn_demo.clicked.connect(lambda: self._tabs.setCurrentIndex(1))
            btn_row.addWidget(btn_demo)

        btn_row.addStretch(1)

        shortcuts = QHBoxLayout()
        btn_project = QPushButton("📁 项目目录")
        btn_project.setToolTip("在资源管理器中打开程序所在目录")
        btn_project.clicked.connect(lambda: self._open_dir("project"))
        shortcuts.addWidget(btn_project)
        btn_data = QPushButton("💾 数据目录")
        btn_data.setToolTip("数据库、封面与存档备份")
        btn_data.clicked.connect(lambda: self._open_dir("data"))
        shortcuts.addWidget(btn_data)
        btn_row.addLayout(shortcuts)

        root.addLayout(btn_row)

        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        box.rejected.connect(self.reject)
        close_btn = box.addButton("关闭", QDialogButtonBox.ButtonRole.AcceptRole)
        close_btn.clicked.connect(self.accept)
        root.addWidget(box)

        if first_run:
            self._tabs.setCurrentIndex(0)

    def skip_welcome_on_next_launch(self) -> bool:
        if not self._first_run:
            return True
        return bool(getattr(self, "_skip_next", None) and self._skip_next.isChecked())

    def _build_notice_banner(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("helpNoticeBanner")
        frame.setStyleSheet(
            "QFrame#helpNoticeBanner {"
            "  background: #2A2230;"
            "  border: 1px solid #C97A4A;"
            "  border-radius: 8px;"
            "}"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        contact = QLabel(
            f"<b style='color:#E5E7EB;'>📧 反馈联系</b> — {support_contact_html()}"
        )
        contact.setWordWrap(True)
        contact.setTextFormat(Qt.TextFormat.RichText)
        contact.setOpenExternalLinks(True)
        contact.setStyleSheet(f"font-size: {HELP_NOTICE_FONT_PX}px; color: #C8D0DC;")
        layout.addWidget(contact)

        disclaimer = QLabel(USAGE_DISCLAIMER)
        disclaimer.setWordWrap(True)
        disclaimer.setStyleSheet(
            f"font-size: {HELP_NOTICE_FONT_PX}px; font-weight: 600; color: #E8B080; line-height: 1.6;"
        )
        layout.addWidget(disclaimer)

        return frame

    def _build_welcome_tab(self) -> QWidget:
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setSpacing(14)

        title = QLabel(f"{APP_DISPLAY_NAME} {APP_HELP_VERSION}")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #E5E7EB;")
        layout.addWidget(title)

        tagline = QLabel(WELCOME_TAGLINE)
        tagline.setWordWrap(True)
        tagline.setStyleSheet("color: #93A1B6; font-size: 15px; line-height: 1.55;")
        layout.addWidget(tagline)

        shot = self._screenshot_label(max_height=220)
        if shot is not None:
            layout.addWidget(shot, alignment=Qt.AlignmentFlag.AlignCenter)

        for step_title, step_body in WELCOME_STEPS:
            card = QFrame()
            card.setStyleSheet(
                "QFrame { background: #252B36; border: 1px solid #3D4759; "
                "border-radius: 8px; padding: 4px; }"
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 10, 12, 10)
            h = QLabel(f"<b style='color:#8AB4E0;font-size:15px;'>{step_title}</b>")
            h.setTextFormat(Qt.TextFormat.RichText)
            card_layout.addWidget(h)
            body = QLabel(step_body)
            body.setWordWrap(True)
            body.setStyleSheet(f"color: #C8D0DC; font-size: {HELP_BODY_FONT_PX}px; line-height: 1.6;")
            card_layout.addWidget(body)
            layout.addWidget(card)

        tip = QLabel(
            "💡 从网盘下载的资源包？用「一键工作流」或「自动化解压」处理后扫描入库。"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet(
            f"color: #93A1B6; font-size: {HELP_BODY_FONT_PX}px; "
            "background: rgba(106,159,216,0.1); padding: 10px; border-radius: 6px;"
        )
        layout.addWidget(tip)
        layout.addStretch()
        scroll.setWidget(inner)

        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        return page

    def _build_demo_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        intro = QLabel(
            "按步骤了解主要功能；带「试一试」的步骤会关闭本窗口并打开对应功能。"
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: #93A1B6; font-size: {HELP_BODY_FONT_PX}px;")
        layout.addWidget(intro)

        progress_row = QHBoxLayout()
        self._demo_progress = QLabel()
        self._demo_progress.setStyleSheet(
            f"color: #8AB4E0; font-size: {HELP_BODY_FONT_PX}px; font-weight: 600;"
        )
        progress_row.addWidget(self._demo_progress)
        progress_row.addStretch()
        layout.addLayout(progress_row)

        self._demo_stack = QStackedWidget()
        for step in DEMO_STEPS:
            self._demo_stack.addWidget(self._demo_step_widget(step))
        layout.addWidget(self._demo_stack, 1)

        nav = QHBoxLayout()
        self._btn_demo_prev = QPushButton("上一步")
        self._btn_demo_prev.clicked.connect(self._demo_prev)
        nav.addWidget(self._btn_demo_prev)
        nav.addStretch()
        self._btn_demo_next = QPushButton("下一步")
        self._btn_demo_next.clicked.connect(self._demo_next)
        nav.addWidget(self._btn_demo_next)
        layout.addLayout(nav)

        self._update_demo_page()
        return page

    def _demo_step_widget(self, step: dict[str, str | None]) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        title = QLabel(str(step["title"]))
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #E5E7EB;")
        layout.addWidget(title)

        summary = QLabel(str(step.get("summary", "")))
        summary.setStyleSheet(f"color: #8AB4E0; font-size: {HELP_BODY_FONT_PX}px;")
        layout.addWidget(summary)

        body = QTextBrowser()
        body.setOpenExternalLinks(True)
        body.setFrameShape(QFrame.Shape.NoFrame)
        body.setHtml(
            f"<style>body {{ font-family: 'Microsoft YaHei'; color: #C8D0DC; "
            f"font-size: {HELP_BODY_FONT_PX}px; line-height: 1.7; }}</style>"
            f"<p>{step['body']}</p>"
        )
        layout.addWidget(body, 1)

        action = step.get("action")
        button_text = str(step.get("button") or "")
        if action and button_text:
            btn_try = QPushButton(button_text)
            btn_try.setProperty("btnKind", "primary")

            def _run(act: str = str(action)) -> None:
                self._emit_action(act)

            btn_try.clicked.connect(_run)
            layout.addWidget(btn_try)

        hint = step.get("hint")
        if hint:
            hint_lbl = QLabel(str(hint))
            hint_lbl.setWordWrap(True)
            hint_lbl.setTextFormat(Qt.TextFormat.RichText)
            hint_lbl.setStyleSheet(f"color: #6B7C93; font-size: {HELP_BODY_FONT_PX}px;")
            layout.addWidget(hint_lbl)

        return w

    def _build_browser_tab(self, html: str) -> QWidget:
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setStyleSheet(
            f"QTextBrowser {{ font-size: {HELP_BODY_FONT_PX}px; padding: 4px; }}"
        )
        browser.setHtml(html)
        return browser

    def _screenshot_label(self, *, max_height: int) -> QLabel | None:
        path = resolve_help_screenshot()
        if path is None:
            return None
        pix = QPixmap(str(path))
        if pix.isNull():
            return None
        if pix.height() > max_height:
            pix = pix.scaledToHeight(max_height, Qt.TransformationMode.SmoothTransformation)
        lbl = QLabel()
        lbl.setPixmap(pix)
        lbl.setStyleSheet(
            "border: 1px solid #3D4759; border-radius: 6px; padding: 4px; background: #1C2230;"
        )
        lbl.setToolTip(str(path))
        return lbl

    def _update_demo_page(self) -> None:
        total = len(DEMO_STEPS)
        self._demo_stack.setCurrentIndex(self._demo_index)
        self._demo_progress.setText(
            f"步骤 {self._demo_index + 1} / {total}  ·  {DEMO_STEPS[self._demo_index]['title']}"
        )
        self._btn_demo_prev.setEnabled(self._demo_index > 0)
        self._btn_demo_next.setEnabled(self._demo_index < total - 1)
        if self._demo_index >= total - 1:
            self._btn_demo_next.setText("完成")
        else:
            self._btn_demo_next.setText("下一步")

    def _demo_prev(self) -> None:
        if self._demo_index > 0:
            self._demo_index -= 1
            self._update_demo_page()

    def _demo_next(self) -> None:
        if self._demo_index < len(DEMO_STEPS) - 1:
            self._demo_index += 1
            self._update_demo_page()

    def _start_with_add_root(self) -> None:
        self._emit_action("add_root")

    def _emit_action(self, action: str) -> None:
        self.action_requested.emit(action)
        self.accept()

    def _open_dir(self, kind: str) -> None:
        from app.ui.dialogs.game_detail_dialog import reveal_in_explorer

        if kind == "project":
            path = self._main._resolve_project_dir()
            title = "打开项目目录"
        else:
            path = self._main.db.base_dir
            title = "打开数据目录"
        try:
            reveal_in_explorer(str(path), select_file=False)
        except FileNotFoundError:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self, title, f"目录不存在：\n{path}")
