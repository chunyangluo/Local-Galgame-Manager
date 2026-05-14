"""Global settings UI for 2DFan crawler SQLite linkage (friendly entry from main window)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from app.paths import (
    default_twodfan_sqlite_path,
    existing_twodfan_sqlite_files,
    twodfan_crawler_dir,
    twodfan_crawler_readme,
)
from app.services.twodfan_hints import twodfan_db_stats
from app.ui.game_detail_dialog import reveal_in_explorer

if TYPE_CHECKING:
    from app.ui.main_window import MainWindow


def _open_local_file(path: Path) -> bool:
    url = QUrl.fromLocalFile(str(path.resolve()))
    return QDesktopServices.openUrl(url)


class TwodfanLibraryDialog(QDialog):
    """Configure the optional 2DFan hints database and jump to the bundled crawler tool."""

    def __init__(self, main: MainWindow) -> None:
        super().__init__(main)
        self._main = main
        self.setWindowTitle("2DFan 线索库与爬虫")
        self.setMinimumWidth(520)

        root = QVBoxLayout(self)
        intro = QLabel(
            "本程序可读取仓库内 <b>dfan_save_crawler</b> 生成的 SQLite，在「存档管理 → 自动发现」里"
            "合并社区里写的存档路径线索（仅当解析出的文件夹在您电脑上真实存在时才会出现）。"
            "<br><br>"
            "此为<strong>全局设置</strong>：配置一次后，所有游戏的自动发现共用该库。"
        )
        intro.setWordWrap(True)
        intro.setTextFormat(Qt.TextFormat.RichText)
        intro.setStyleSheet("color:#93A1B6;font-size:12px;")
        root.addWidget(intro)

        row = QHBoxLayout()
        row.addWidget(QLabel("SQLite 路径"))
        self._edit = QLineEdit()
        self._edit.setPlaceholderText("例如 …/tools/2dfan-save-crawler/data/2dfan_saves.sqlite3")
        row.addWidget(self._edit, 1)
        self._btn_browse = QPushButton("浏览…")
        self._btn_browse.clicked.connect(self._browse)
        row.addWidget(self._btn_browse)
        self._btn_save = QPushButton("保存到本程序")
        self._btn_save.clicked.connect(self._save)
        row.addWidget(self._btn_save)
        root.addLayout(row)

        self._stats = QLabel("")
        self._stats.setWordWrap(True)
        self._stats.setStyleSheet("color:#7FA7D9;font-size:11px;")
        root.addWidget(self._stats)

        link_row = QHBoxLayout()
        self._btn_fill = QPushButton("填入推荐路径")
        self._btn_fill.setToolTip("使用本仓库 tools/2dfan-save-crawler/data/2dfan_saves.sqlite3（文件可尚未生成）")
        self._btn_fill.clicked.connect(self._fill_default)
        link_row.addWidget(self._btn_fill)
        self._btn_open_tool = QPushButton("打开爬虫目录")
        self._btn_open_tool.setToolTip("在资源管理器中打开 tools/2dfan-save-crawler")
        self._btn_open_tool.clicked.connect(self._open_crawler_dir)
        link_row.addWidget(self._btn_open_tool)
        self._btn_readme = QPushButton("打开说明 (README)")
        self._btn_readme.clicked.connect(self._open_readme)
        link_row.addWidget(self._btn_readme)
        link_row.addStretch(1)
        root.addLayout(link_row)

        tip = QLabel(
            "若列表页抓取遇到 HTTP 403，请在爬虫目录按 README 使用 <code>--curl-cffi</code> 或浏览器 Cookie；"
            "爬取完成后无需重启本程序，保存路径即可。"
        )
        tip.setWordWrap(True)
        tip.setTextFormat(Qt.TextFormat.RichText)
        tip.setStyleSheet("color:#586E75;font-size:11px;")
        root.addWidget(tip)

        box = QDialogButtonBox(QDialogButtonBox.Close)
        box.rejected.connect(self.reject)
        root.addWidget(box)

        self._load()
        self._refresh_stats()

    def _db(self):
        return self._main.db

    def _load(self) -> None:
        self._edit.setText(self._db().get_twodfan_hints_db_path())

    def _refresh_stats(self) -> None:
        raw = self._edit.text().strip()
        if not raw:
            self._stats.setText("当前未配置线索库。")
            return
        p = Path(raw)
        if not p.is_file():
            self._stats.setText("文件不存在：保存后也不会参与自动发现，请先运行爬虫生成 SQLite。")
            return
        stats = twodfan_db_stats(p)
        if stats is None:
            self._stats.setText("无法读取该文件（可能不是 dfan_save_crawler 生成的库）。")
            return
        np, nh = stats
        self._stats.setText(f"已检测到线索库：收录下载页 {np} 条，存档线索 {nh} 条。")

    def _browse(self) -> None:
        start = self._edit.text().strip() or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 2DFan 线索 SQLite",
            start,
            "SQLite (*.sqlite3 *.db);;All (*.*)",
        )
        if path:
            self._edit.setText(path)
            self._refresh_stats()

    def _save(self) -> None:
        raw = self._edit.text().strip()
        if raw and not Path(raw).is_file():
            QMessageBox.warning(
                self,
                "文件不存在",
                "请确认 SQLite 已生成。可先点击「填入推荐路径」，再在 tools/2dfan-save-crawler 目录运行：\n"
                "python -m dfan_save_crawler crawl --db data/2dfan_saves.sqlite3 …",
            )
            return
        self._db().set_twodfan_hints_db_path(raw)
        self._refresh_stats()
        QMessageBox.information(
            self,
            "已保存",
            "2DFan 线索库路径已写入全局设置。\n在任意游戏的「存档管理」中使用「自动发现」即可合并线索。",
        )

    def _fill_default(self) -> None:
        cand = default_twodfan_sqlite_path()
        if cand is not None:
            self._edit.setText(str(cand))
            self._refresh_stats()
            return
        found = existing_twodfan_sqlite_files()
        if found:
            self._edit.setText(str(found[0]))
            self._refresh_stats()
            return
        QMessageBox.information(
            self,
            "未找到仓库内爬虫",
            "当前运行环境旁没有检测到 tools/2dfan-save-crawler（例如使用打包版时）。\n"
            "请手动浏览选择您已生成的 .sqlite3 文件。",
        )

    def _open_crawler_dir(self) -> None:
        d = twodfan_crawler_dir()
        if d is None:
            QMessageBox.information(
                self,
                "未找到爬虫目录",
                "未检测到本仓库下的 tools/2dfan-save-crawler。\n"
                "请从源码树启动本程序，或自行在资源管理器中打开克隆目录里的上述文件夹。",
            )
            return
        try:
            reveal_in_explorer(str(d))
        except OSError as e:
            QMessageBox.warning(self, "无法打开", str(e))

    def _open_readme(self) -> None:
        p = twodfan_crawler_readme()
        if p is None or not p.is_file():
            QMessageBox.information(self, "无说明文件", "未找到 tools/2dfan-save-crawler/README.md。")
            return
        if not _open_local_file(p):
            QMessageBox.warning(self, "无法打开", "系统未关联打开方式，请手动打开 README.md。")
