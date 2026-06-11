"""GUI for integrations/自动化解压工具 — archive extract & scan."""

from __future__ import annotations

import html
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.services.auto_extract_service import (
    AutoExtractResult,
    AutoExtractScanResult,
    auto_extract_missing_reason,
    is_auto_extract_available,
    read_directory_config,
    report_output_dir,
    write_directory_config,
)
from app.services.disc_install_guide import (
    DiscInstallGuide,
    enrich_guide_with_config,
    guide_from_post_process,
    guide_from_progress_payload,
    resolve_installer_on_disk,
)
from app.services.loose_install_consolidator import (
    consolidate_loose_install,
    detect_loose_install_at_root,
    suggested_install_directory,
)
from app.services.paths import auto_extract_readme, auto_extract_tool_dir
from app.ui.dialog_presenter import present_auxiliary_dialog
from app.ui.dialogs.game_detail_dialog import launch_executable, reveal_in_explorer
from app.workers.auto_extract_worker import AutoExtractFileTask, AutoExtractScanTask

if TYPE_CHECKING:
    from app.ui.main_window import MainWindow


CORE_DIR_FIELDS = {
    "watch": "监控目录",
    "target": "解压输出",
    "game_save": "游戏库目录",
}
DETAIL_DIR_FIELDS = {
    "archive": "已处理归档",
    "failed": "失败文件",
    "temp": "临时目录",
}


class AutoExtractDialog(QDialog):
    def __init__(self, main: MainWindow, parent: QWidget | None = None) -> None:
        super().__init__(parent if parent is not None else main)
        self._main = main
        self.setWindowTitle("自动化解压工具")
        self.setMinimumSize(720, 640)
        self._pool = QThreadPool.globalInstance()
        self._running = False
        self._scan_task: AutoExtractScanTask | None = None
        self._dir_edits: dict[str, QLineEdit] = {}

        root = QVBoxLayout(self)
        root.setSpacing(10)

        root.addLayout(self._build_header())

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_config_tab(), "① 目录配置")
        self._tabs.addTab(self._build_scan_tab(), "② 扫描与解压")
        self._tabs.addTab(self._build_single_tab(), "③ 单次解压")
        root.addWidget(self._tabs, 1)

        self._install_guide_panel = self._build_install_guide_panel()
        self._install_guide_panel.setVisible(False)
        root.addWidget(self._install_guide_panel)

        root.addWidget(self._build_helper_bar())

        log_header = QHBoxLayout()
        log_title = QLabel("运行日志")
        log_title.setStyleSheet("color:#C7D1E0;font-weight:600;")
        log_header.addWidget(log_title)
        log_header.addStretch(1)
        btn_clear_log = QPushButton("清空日志")
        btn_clear_log.setFixedHeight(24)
        btn_clear_log.clicked.connect(lambda: self._log.clear())
        log_header.addWidget(btn_clear_log)
        root.addLayout(log_header)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.document().setMaximumBlockCount(2000)
        self._log.setPlaceholderText("运行日志将显示在这里…")
        self._log.setMinimumHeight(150)
        root.addWidget(self._log, 1)

        close_box = QDialogButtonBox(QDialogButtonBox.Close)
        close_box.rejected.connect(self.reject)
        root.addWidget(close_box)

        self._load_config_fields()
        if not is_auto_extract_available():
            self._log_line(auto_extract_missing_reason(), "error")
        # 默认标签页：未配置监控目录 → 配置；否则 → 扫描
        if read_directory_config().get("watch", "").strip():
            self._tabs.setCurrentIndex(1)
        else:
            self._tabs.setCurrentIndex(0)

    # ---------- header ----------
    def _build_header(self) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setSpacing(6)
        title = QLabel("自动化解压工具")
        title.setStyleSheet("font-size:16px;font-weight:700;color:#F2F4F7;")
        box.addWidget(title)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        for text in ("目录监控", "格式识别", "密码尝试", "嵌套解压", "光盘镜像", "整理入库"):
            chip = QLabel(text)
            chip.setStyleSheet(
                "background:rgba(127,167,217,0.18);color:#DCEBFF;"
                "border-radius:9px;padding:3px 10px;font-size:11px;"
            )
            chips.addWidget(chip)
        chips.addStretch(1)
        box.addLayout(chips)
        return box

    # ---------- config tab ----------
    def _build_config_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        hint = QLabel("只需配置 3 个常用目录即可开始使用；其余目录可展开「详细配置」按需调整。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#93A1B6;font-size:12px;")
        layout.addWidget(hint)

        core_group = QGroupBox("常用配置")
        core_form = QFormLayout(core_group)
        for key, label in CORE_DIR_FIELDS.items():
            core_form.addRow(label + "：", self._build_dir_row(key))
        layout.addWidget(core_group)

        self._detail_toggle = QCheckBox("显示详细配置（归档 / 失败 / 临时目录）")
        self._detail_toggle.toggled.connect(self._on_detail_toggled)
        layout.addWidget(self._detail_toggle)

        self._detail_group = QGroupBox("详细配置")
        detail_form = QFormLayout(self._detail_group)
        for key, label in DETAIL_DIR_FIELDS.items():
            detail_form.addRow(label + "：", self._build_dir_row(key))
        self._detail_group.setVisible(False)
        layout.addWidget(self._detail_group)

        row = QHBoxLayout()
        btn_fill = QPushButton("用库扫描目录填入监控目录")
        btn_fill.clicked.connect(self._fill_watch_from_scan_roots)
        row.addWidget(btn_fill)
        row.addStretch(1)
        self._btn_save_cfg = QPushButton("保存配置")
        self._btn_save_cfg.setProperty("btnKind", "primary")
        self._btn_save_cfg.clicked.connect(self._save_config)
        row.addWidget(self._btn_save_cfg)
        layout.addLayout(row)
        layout.addStretch(1)
        return w

    def _build_dir_row(self, key: str) -> QWidget:
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        edit = QLineEdit()
        self._dir_edits[key] = edit
        row.addWidget(edit, 1)
        btn = QPushButton("浏览…")
        btn.clicked.connect(lambda _=False, k=key: self._browse_dir(k))
        row.addWidget(btn)
        return container

    def _on_detail_toggled(self, checked: bool) -> None:
        self._detail_group.setVisible(checked)

    def _browse_dir(self, key: str) -> None:
        start = self._dir_edits[key].text().strip()
        path = QFileDialog.getExistingDirectory(self, "选择目录", start)
        if path:
            self._dir_edits[key].setText(path)

    # ---------- scan tab ----------
    def _build_scan_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        desc = QLabel(
            "扫描「监控目录」下的压缩包（≥200MB），自动尝试密码、嵌套解压，"
            "识别游戏目录并移动到「游戏库目录」。"
            "若包内为 ISO+MDS 光盘镜像，将自动展开并提示你运行 setup.exe 完成安装。"
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        risk = QLabel("⚠ 同名游戏会被直接覆盖；过程可能较久，可随时点「停止」中断后续文件。")
        risk.setWordWrap(True)
        risk.setStyleSheet("color:#E6B85C;font-size:12px;")
        layout.addWidget(risk)

        btn_row = QHBoxLayout()
        self._btn_scan = QPushButton("开始扫描并解压")
        self._btn_scan.setProperty("btnKind", "primary")
        self._btn_scan.setMinimumHeight(36)
        self._btn_scan.clicked.connect(self._run_scan)
        btn_row.addWidget(self._btn_scan, 1)
        self._btn_stop = QPushButton("停止")
        self._btn_stop.setMinimumHeight(36)
        self._btn_stop.setEnabled(False)
        self._btn_stop.clicked.connect(self._stop_scan)
        btn_row.addWidget(self._btn_stop)
        layout.addLayout(btn_row)

        self._scan_progress = QProgressBar()
        self._scan_progress.setVisible(False)
        layout.addWidget(self._scan_progress)

        self._scan_current = QLabel("")
        self._scan_current.setStyleSheet("color:#93A1B6;")
        self._scan_current.setVisible(False)
        layout.addWidget(self._scan_current)

        self._scan_summary = QLabel("尚未扫描")
        self._scan_summary.setStyleSheet("color:#93A1B6;")
        layout.addWidget(self._scan_summary)

        layout.addStretch(1)
        return w

    # ---------- single tab ----------
    def _build_single_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        row = QHBoxLayout()
        row.addWidget(QLabel("压缩包"))
        self._single_file = QLineEdit()
        self._single_file.setPlaceholderText("选择 .zip / .7z / .rar / 分卷等")
        row.addWidget(self._single_file, 1)
        btn = QPushButton("浏览…")
        btn.clicked.connect(self._browse_archive)
        row.addWidget(btn)
        layout.addLayout(row)

        prow = QHBoxLayout()
        prow.addWidget(QLabel("密码（可选）"))
        self._single_password = QLineEdit()
        self._single_password.setPlaceholderText("留空则按密码本自动尝试")
        prow.addWidget(self._single_password, 1)
        btn_pwd_mgr = QPushButton("管理密码本")
        btn_pwd_mgr.clicked.connect(self._open_password_manager)
        prow.addWidget(btn_pwd_mgr)
        layout.addLayout(prow)

        trow = QHBoxLayout()
        trow.addWidget(QLabel("输出目录（可选）"))
        self._single_target = QLineEdit()
        self._single_target.setPlaceholderText("留空使用配置中的解压输出目录")
        trow.addWidget(self._single_target, 1)
        layout.addLayout(trow)

        self._btn_single = QPushButton("开始解压")
        self._btn_single.setProperty("btnKind", "primary")
        self._btn_single.setMinimumHeight(34)
        self._btn_single.clicked.connect(self._run_single)
        layout.addWidget(self._btn_single)

        self._single_progress = QProgressBar()
        self._single_progress.setVisible(False)
        layout.addWidget(self._single_progress)

        hint = QLabel(
            "解压后会执行嵌套解压与游戏目录识别。"
            "若为 (iso+mds) 类资源，将展开光盘并引导你手动运行安装程序。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#586E75;font-size:11px;")
        layout.addWidget(hint)
        layout.addStretch(1)
        return w

    # ---------- disc install guide ----------
    def _build_install_guide_panel(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("discInstallGuide")
        frame.setStyleSheet(
            "#discInstallGuide{"
            "background:rgba(230,184,92,0.12);"
            "border:1px solid rgba(230,184,92,0.45);"
            "border-radius:8px;}"
            "#discInstallGuide QLabel{color:#E8DCC8;}"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        title = QLabel("💿 光盘镜像资源 · 需手动安装")
        title.setStyleSheet("font-weight:700;font-size:13px;color:#F5D78E;")
        layout.addWidget(title)

        self._install_guide_body = QLabel()
        self._install_guide_body.setWordWrap(True)
        self._install_guide_body.setTextFormat(Qt.TextFormat.RichText)
        self._install_guide_body.setOpenExternalLinks(False)
        layout.addWidget(self._install_guide_body)

        self._install_guide_path = QLabel("")
        self._install_guide_path.setWordWrap(True)
        self._install_guide_path.setStyleSheet(
            "font-family:Consolas,'Segoe UI',monospace;font-size:11px;color:#B8C8E0;"
        )
        layout.addWidget(self._install_guide_path)

        self._install_suggested_path = QLabel("")
        self._install_suggested_path.setWordWrap(True)
        self._install_suggested_path.setStyleSheet(
            "font-family:Consolas,'Segoe UI',monospace;font-size:12px;color:#F5D78E;"
        )
        layout.addWidget(self._install_suggested_path)

        btn_row = QHBoxLayout()
        self._btn_open_setup = QPushButton("打开 setup.exe")
        self._btn_open_setup.setProperty("btnKind", "primary")
        self._btn_open_setup.setToolTip("在资源管理器中打开安装程序所在文件夹并选中 setup.exe")
        self._btn_open_setup.clicked.connect(self._open_installer_in_explorer)
        btn_row.addWidget(self._btn_open_setup)

        self._btn_run_setup = QPushButton("运行 setup.exe")
        self._btn_run_setup.setToolTip(
            "在安装程序所在目录下启动 setup.exe（与手动双击效果一致）"
        )
        self._btn_run_setup.clicked.connect(self._run_installer)
        btn_row.addWidget(self._btn_run_setup)

        self._btn_open_extract_dir = QPushButton("打开解压目录")
        self._btn_open_extract_dir.clicked.connect(self._open_extract_dir_in_explorer)
        btn_row.addWidget(self._btn_open_extract_dir)

        self._btn_open_suggested_install = QPushButton("创建建议安装目录")
        self._btn_open_suggested_install.setProperty("btnKind", "primary")
        self._btn_open_suggested_install.setToolTip(
            "在游戏库下创建独立子文件夹并打开，安装时请选此路径，勿选游戏库根目录"
        )
        self._btn_open_suggested_install.clicked.connect(self._open_suggested_install_dir)
        btn_row.addWidget(self._btn_open_suggested_install)

        self._btn_consolidate_loose = QPushButton("整理散落安装")
        self._btn_consolidate_loose.setToolTip(
            "若已误装到游戏库根目录，将散落的 exe/数据文件夹移入单独子目录"
        )
        self._btn_consolidate_loose.clicked.connect(self._consolidate_loose_install)
        btn_row.addWidget(self._btn_consolidate_loose)

        self._btn_goto_add_root = QPushButton("去主界面添加目录")
        self._btn_goto_add_root.setToolTip("安装完成后，将安装目录加入库扫描路径")
        self._btn_goto_add_root.clicked.connect(self._goto_main_add_scan_root)
        btn_row.addWidget(self._btn_goto_add_root)

        btn_row.addStretch(1)
        btn_dismiss = QPushButton("知道了")
        btn_dismiss.clicked.connect(lambda: self._install_guide_panel.setVisible(False))
        btn_row.addWidget(btn_dismiss)
        layout.addLayout(btn_row)

        self._current_install_guide: DiscInstallGuide | None = None
        return frame

    def _format_install_guide_html(self, guide: DiscInstallGuide) -> str:
        iso_note = ""
        if guide.iso_names:
            iso_note = (
                f"<li>已自动展开光盘：<b>{html.escape(', '.join(guide.iso_names))}</b></li>"
            )
        setup_line = ""
        if guide.installer_display():
            setup_line = (
                "<li>在资源管理器中运行安装程序（或点击下方按钮）：</li>"
            )
        suggested = html.escape(guide.suggested_install_path) if guide.suggested_install_path else ""
        path_hint = ""
        if suggested:
            path_hint = (
                "<li><b>安装路径必须选下方「建议子文件夹」</b>，"
                f"不要选游戏库根目录：<br><code>{suggested}</code></li>"
            )
        else:
            path_hint = (
                "<li>安装路径请选游戏库下的<b>新建子文件夹</b>（纯英文），"
                "切勿直接选游戏库根目录。</li>"
            )
        return (
            "<ol style='margin:6px 0 6px 18px;padding:0;line-height:1.55;'>"
            f"{iso_note}"
            f"{setup_line}"
            f"{path_hint}"
            "<li>安装前可点「创建建议安装目录」；若已误装到根目录，点「整理散落安装」。</li>"
            "<li>安装完成后在主界面点击<b>「添加目录」</b>，选择该<b>子文件夹</b>扫描入库。</li>"
            "<li>老游戏若无法运行，可在游戏中使用 LE 转区启动。</li>"
            "</ol>"
        )

    def _game_save_dir(self) -> str:
        return read_directory_config().get("game_save", "").strip()

    def _prepare_install_guide(self, guide: DiscInstallGuide) -> DiscInstallGuide:
        guide = enrich_guide_with_config(guide, self._game_save_dir())
        guide = resolve_installer_on_disk(guide)
        return guide

    def _show_install_guide(self, guide: DiscInstallGuide) -> None:
        guide = self._prepare_install_guide(guide)
        self._current_install_guide = guide
        self._install_guide_body.setText(self._format_install_guide_html(guide))
        path_text = guide.installer_display() or guide.extract_dir
        if guide.installer_display() and guide.extract_dir:
            path_text = f"{guide.installer_display()}\n（解压目录：{guide.extract_dir}）"
        self._install_guide_path.setText(path_text)
        if guide.suggested_install_path:
            self._install_suggested_path.setText(
                f"建议安装到（子文件夹）：\n{guide.suggested_install_path}"
            )
            self._install_suggested_path.show()
        else:
            self._install_suggested_path.hide()
        has_installer = guide.installer_path is not None
        self._btn_open_setup.setEnabled(has_installer or bool(guide.installer_exe))
        self._btn_run_setup.setEnabled(has_installer)
        self._btn_open_suggested_install.setEnabled(bool(guide.game_save_dir))
        self._btn_consolidate_loose.setEnabled(bool(guide.game_save_dir))
        self._install_guide_panel.setVisible(True)
        self._log_line("检测到光盘镜像资源，请按上方黄色区域完成手动安装。", "warning")
        self._check_loose_install_warning(guide.game_save_dir)

    def _check_loose_install_warning(self, game_save: str) -> None:
        if not game_save:
            return
        cluster = detect_loose_install_at_root(game_save)
        if cluster is not None:
            self._log_line(
                f"检测到游戏库根目录有散落安装（{cluster.launcher_exe.name}），"
                "可点击「整理散落安装」。",
                "warning",
            )

    def _maybe_show_install_guide_from_result(self, result: AutoExtractResult) -> None:
        pp = dict(result.post_process or {})
        pp.setdefault("archive_file_name", result.file_name)
        pp.setdefault("game_save_dir", self._game_save_dir())
        guide = guide_from_post_process(pp, extract_dir=result.extract_dir)
        if guide is not None:
            guide = DiscInstallGuide(
                extract_dir=guide.extract_dir,
                installer_exe=guide.installer_exe,
                iso_names=guide.iso_names,
                archive_file_name=result.file_name,
                game_save_dir=self._game_save_dir(),
            )
            self._show_install_guide(guide)

    def _active_install_guide(self) -> DiscInstallGuide | None:
        if self._current_install_guide is None:
            return None
        guide = self._prepare_install_guide(self._current_install_guide)
        self._current_install_guide = guide
        return guide

    def _open_suggested_install_dir(self) -> None:
        guide = self._active_install_guide()
        game_save = guide.game_save_dir if guide else self._game_save_dir()
        if not game_save:
            QMessageBox.information(self, "提示", "请先在目录配置中设置「游戏库目录」。")
            return
        folder = guide.suggested_folder_name if guide else "InstalledGame"
        dest = suggested_install_directory(game_save, folder_name=folder)
        try:
            dest.mkdir(parents=True, exist_ok=True)
            reveal_in_explorer(str(dest), select_file=False)
            self._log_line(f"已创建并打开建议安装目录：{dest}", "success")
        except OSError as exc:
            QMessageBox.warning(self, "创建失败", str(exc))

    def _consolidate_loose_install(self) -> None:
        game_save = self._game_save_dir()
        if not game_save:
            QMessageBox.information(self, "提示", "请先在目录配置中设置「游戏库目录」。")
            return
        cluster = detect_loose_install_at_root(game_save)
        if cluster is None:
            QMessageBox.information(
                self,
                "无需整理",
                "未在游戏库根目录检测到散落的安装文件。\n"
                "若游戏已在子文件夹中，无需此操作。",
            )
            return
        dest_name = cluster.suggested_folder_name
        guide = self._active_install_guide()
        if guide is not None:
            dest_name = guide.suggested_folder_name
        msg = (
            f"将把游戏库根目录下 {len(cluster.items)} 项散落文件（含 "
            f"{cluster.launcher_exe.name}）移动到：\n\n"
            f"{Path(game_save) / dest_name}\n\n"
            "不会移动其他已有游戏子文件夹。是否继续？"
        )
        if (
            QMessageBox.question(self, "整理散落安装", msg) != QMessageBox.StandardButton.Yes
        ):
            return
        result = consolidate_loose_install(game_save, folder_name=dest_name)
        if result.success:
            self._log_line(
                f"已整理到 {result.destination}：{', '.join(result.moved)}",
                "success",
            )
            self._toast("散落安装已整理到子文件夹", "success")
            try:
                reveal_in_explorer(result.destination, select_file=False)
            except OSError:
                pass
        else:
            self._log_line(f"整理失败：{result.error}", "error")
            QMessageBox.warning(self, "整理失败", result.error or "未知错误")

    def _open_installer_in_explorer(self) -> None:
        guide = self._active_install_guide()
        if guide is None:
            return
        path = guide.installer_path
        if path is None:
            QMessageBox.information(
                self,
                "未找到安装程序",
                "未在解压目录中找到 setup.exe。\n请打开解压目录手动查找安装程序。",
            )
            self._open_extract_dir_in_explorer()
            return
        try:
            reveal_in_explorer(str(path), select_file=True)
        except OSError:
            try:
                reveal_in_explorer(str(path.parent), select_file=False)
                self._log_line(
                    f"无法在资源管理器中选中文件，已打开所在文件夹：{path.parent}",
                    "warning",
                )
            except OSError as exc:
                QMessageBox.warning(self, "打开失败", str(exc))
        except FileNotFoundError:
            QMessageBox.warning(self, "打开失败", f"文件不存在：\n{path}")

    def _run_installer(self) -> None:
        guide = self._active_install_guide()
        if guide is None or guide.installer_path is None:
            QMessageBox.information(self, "提示", "未找到可运行的 setup.exe。")
            return
        try:
            launch_executable(guide.installer_path)
            self._log_line(
                f"已启动安装程序：{guide.installer_path}（工作目录：{guide.installer_path.parent}）",
                "success",
            )
        except OSError as exc:
            QMessageBox.warning(self, "启动失败", str(exc))

    def _open_extract_dir_in_explorer(self) -> None:
        guide = self._current_install_guide
        if guide is None or not guide.extract_dir:
            target = read_directory_config().get("target", "").strip()
        else:
            target = guide.extract_dir
        if not target:
            QMessageBox.information(self, "提示", "请先在目录配置中设置「解压输出」。")
            return
        p = Path(target)
        if not p.is_dir():
            QMessageBox.warning(self, "打开失败", f"目录不存在：\n{p}")
            return
        reveal_in_explorer(str(p), select_file=False)

    def _goto_main_add_scan_root(self) -> None:
        self._log_line("请在主界面「库」分组中点击「添加目录」，选择安装完成后的游戏文件夹。", "info")
        self._toast("安装完成后请添加扫描目录", "info")
        manage = getattr(self._main, "_manage_scan_roots", None)
        if callable(manage):
            self.accept()
            manage()
        else:
            QMessageBox.information(
                self,
                "添加扫描目录",
                "请关闭本窗口，在主界面第一行「库」分组点击「添加目录」，"
                "选择你安装游戏时使用的文件夹。",
            )

    # ---------- helper bar ----------
    def _build_helper_bar(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame{border-top:1px solid rgba(255,255,255,0.08);}"
            "QPushButton{font-size:11px;padding:4px 10px;color:#9FB0C6;}"
        )
        row = QHBoxLayout(frame)
        row.setContentsMargins(0, 6, 0, 0)
        row.setSpacing(6)
        label = QLabel("辅助：")
        label.setStyleSheet("color:#6B7C93;font-size:11px;")
        row.addWidget(label)
        b1 = QPushButton("工具目录")
        b1.clicked.connect(self._open_tool_dir)
        row.addWidget(b1)
        b2 = QPushButton("说明 README")
        b2.clicked.connect(self._open_readme)
        row.addWidget(b2)
        b3 = QPushButton("验收报告")
        b3.clicked.connect(self._open_report_dir)
        row.addWidget(b3)
        b4 = QPushButton("启动独立服务")
        b4.setToolTip("在新控制台运行 main.py（含目录监控与 REST API）")
        b4.clicked.connect(self._launch_standalone_service)
        row.addWidget(b4)
        row.addStretch(1)
        return frame

    # ---------- config persistence ----------
    def _load_config_fields(self) -> None:
        cfg = read_directory_config()
        for key, edit in self._dir_edits.items():
            edit.setText(cfg.get(key, ""))

    def _fill_watch_from_scan_roots(self) -> None:
        roots = self._main.db.list_scan_roots()
        if not roots:
            QMessageBox.information(self, "提示", "请先在主界面添加扫描目录。")
            return
        self._dir_edits["watch"].setText(roots[0])
        self._log_line(f"监控目录已填入：{roots[0]}", "info")

    def _save_config(self) -> None:
        if not is_auto_extract_available():
            QMessageBox.warning(self, "不可用", auto_extract_missing_reason())
            return
        updates = {k: e.text().strip() for k, e in self._dir_edits.items()}
        if not updates.get("watch"):
            QMessageBox.information(self, "提示", "请填写监控目录。")
            return
        try:
            write_directory_config(updates)
        except OSError as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return
        self._log_line("配置已保存。", "success")
        self._toast("配置已保存", "success")

    # ---------- logging ----------
    def _log_line(self, message: str, level: str = "info") -> None:
        colors = {
            "info": "#C7D1E0",
            "success": "#4ADE80",
            "warning": "#FBBF24",
            "error": "#F87171",
        }
        color = colors.get(level, colors["info"])
        safe = html.escape(message)
        self._log.append(f'<span style="color:{color};">{safe}</span>')

    def _toast(self, message: str, level: str = "info") -> None:
        fn = getattr(self._main, "show_toast", None)
        if callable(fn):
            fn(message, level)

    # ---------- busy state ----------
    def _set_busy(self, busy: bool, *, scanning: bool = False) -> None:
        self._running = busy
        self._btn_single.setEnabled(not busy)
        self._btn_scan.setEnabled(not busy)
        self._btn_save_cfg.setEnabled(not busy)
        self._btn_stop.setEnabled(busy and scanning)
        if busy and scanning:
            self._btn_scan.setText("正在扫描解压…")
        else:
            self._btn_scan.setText("开始扫描并解压")

    def reject(self) -> None:
        if self._running:
            QMessageBox.information(self, "任务运行中", "请先停止或等待当前解压任务完成。")
            return
        super().reject()

    # ---------- single extract ----------
    def _browse_archive(self) -> None:
        start = self._dir_edits["watch"].text().strip()
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择压缩包",
            start,
            "Archives (*.zip *.7z *.rar *.exe *.001 *.lz4 *.iso);;All (*.*)",
        )
        if path:
            self._single_file.setText(path)

    def _open_password_manager(self) -> None:
        from app.ui.dialogs.password_manager_dialog import PasswordManagerDialog

        try:
            if getattr(self, "_pwd_dlg", None) is not None and self._pwd_dlg.isVisible():
                present_auxiliary_dialog(self, self._pwd_dlg)
                return
            self._pwd_dlg = PasswordManagerDialog(self)
            present_auxiliary_dialog(self, self._pwd_dlg)
        except Exception as e:
            QMessageBox.warning(self, "打开失败", str(e))

    def _run_single(self) -> None:
        if self._running:
            return
        if not is_auto_extract_available():
            QMessageBox.warning(self, "不可用", auto_extract_missing_reason())
            return
        archive = self._single_file.text().strip()
        if not archive:
            QMessageBox.information(self, "提示", "请选择压缩包文件。")
            return
        self._set_busy(True)
        self._single_progress.setVisible(True)
        self._single_progress.setRange(0, 0)  # indeterminate
        self._log_line("—— 单次解压开始 ——", "info")
        task = AutoExtractFileTask(
            archive,
            password=self._single_password.text(),
            target_dir=self._single_target.text().strip(),
            signal_parent=self,
        )
        task.signals.log_line.connect(lambda m: self._log_line(m, "info"))
        task.signals.extract_finished.connect(self._on_extract_done)
        task.signals.failed.connect(self._on_failed)
        self._pool.start(task)

    def _on_extract_done(self, result: AutoExtractResult) -> None:
        self._set_busy(False)
        self._single_progress.setVisible(False)
        if result.success:
            self._log_line(
                f"成功：{result.file_name} → {result.extract_dir or '(见配置目录)'}",
                "success",
            )
            if result.used_password:
                self._log_line(f"使用密码：{result.used_password}", "info")
            self._maybe_show_install_guide_from_result(result)
            guide = guide_from_post_process(
                result.post_process, extract_dir=result.extract_dir
            )
            if guide is not None:
                self._toast("解压完成，请按提示安装游戏", "warning")
            else:
                self._toast("解压完成", "success")
        else:
            self._log_line(f"失败：{result.error or '未知错误'}", "error")
            self._show_error("解压失败", result.error or "未知错误")

    # ---------- scan ----------
    def _run_scan(self) -> None:
        if self._running:
            return
        if not is_auto_extract_available():
            QMessageBox.warning(self, "不可用", auto_extract_missing_reason())
            return
        watch = read_directory_config().get("watch", "").strip()
        if not watch:
            QMessageBox.information(self, "提示", "请先在「目录配置」中设置并保存监控目录。")
            self._tabs.setCurrentIndex(0)
            return
        r = QMessageBox.question(
            self,
            "确认扫描并解压",
            f"将扫描并自动解压监控目录下的压缩包：\n{watch}\n\n"
            "识别到的游戏会移动到游戏库目录，同名将被覆盖。是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if r != QMessageBox.StandardButton.Yes:
            return
        self._set_busy(True, scanning=True)
        self._scan_progress.setVisible(True)
        self._scan_progress.setRange(0, 0)
        self._scan_current.setVisible(True)
        self._scan_current.setText("正在枚举压缩包…")
        self._scan_summary.setText("扫描中…")
        self._scan_counts = {"success": 0, "failed": 0}
        self._log_line("—— 扫描并解压开始 ——", "info")

        task = AutoExtractScanTask(signal_parent=self)
        task.signals.progress.connect(self._on_scan_progress)
        task.signals.scan_finished.connect(self._on_scan_done)
        task.signals.failed.connect(self._on_failed)
        self._scan_task = task
        self._pool.start(task)

    def _stop_scan(self) -> None:
        if self._scan_task is not None:
            self._scan_task.cancel()
            self._btn_stop.setEnabled(False)
            self._scan_current.setText("正在停止（等待当前文件完成）…")
            self._log_line("已请求停止，等待当前文件解压完成…", "warning")

    def _on_scan_progress(self, payload: dict) -> None:
        phase = payload.get("phase", "")
        if phase == "collecting":
            self._scan_current.setText(payload.get("message", ""))
        elif phase == "collected":
            total = int(payload.get("total", 0))
            skipped = int(payload.get("skipped", 0))
            self._scan_progress.setRange(0, max(1, total))
            self._scan_progress.setValue(0)
            self._scan_current.setText(f"待处理 {total} 个压缩包（已跳过 {skipped} 个 <200MB）")
            self._log_line(f"发现 {total} 个压缩包，跳过 {skipped} 个小于 200MB。", "info")
        elif phase == "extracting":
            index = int(payload.get("index", 0))
            total = int(payload.get("total", 0))
            name = payload.get("name", "")
            self._scan_progress.setValue(index)
            self._scan_current.setText(f"正在解压 {index}/{total}：{name}")
        elif phase == "file_done":
            name = payload.get("name", "")
            if payload.get("success"):
                self._scan_counts["success"] += 1
                self._log_line(f"✓ {name} → {payload.get('message', '')}", "success")
                guide = guide_from_progress_payload(payload)
                if guide is not None:
                    self._show_install_guide(guide)
            else:
                self._scan_counts["failed"] += 1
                self._log_line(f"✗ {name}：{payload.get('message', '未知错误')}", "error")
            ok = self._scan_counts["success"]
            fail = self._scan_counts["failed"]
            self._scan_summary.setText(f"成功 {ok} · 失败 {fail}")
        elif phase == "empty":
            self._log_line(payload.get("message", "未发现压缩包"), "warning")
        elif phase == "error":
            self._log_line(payload.get("message", "扫描错误"), "error")
        elif phase == "cancelled":
            self._log_line("已停止扫描。", "warning")

    def _on_scan_done(self, result: AutoExtractScanResult) -> None:
        self._set_busy(False)
        self._scan_progress.setVisible(False)
        self._scan_current.setVisible(False)
        self._scan_task = None
        summary = (
            f"合计 {result.total} · 成功 {result.success} · "
            f"失败 {result.failed} · 跳过 {result.skipped}"
        )
        if result.cancelled:
            summary = "已中断 · " + summary
        self._scan_summary.setText(summary)
        self._log_line(f"扫描结束：{summary}", "success" if not result.failed else "warning")
        if result.cancelled:
            self._toast("扫描已停止", "warning")
        else:
            self._toast(f"扫描完成：成功 {result.success}/{result.total}", "success")

    # ---------- shared ----------
    def _on_failed(self, message: str) -> None:
        self._set_busy(False)
        self._scan_progress.setVisible(False)
        self._scan_current.setVisible(False)
        self._single_progress.setVisible(False)
        self._scan_task = None
        self._log_line(f"错误：{message}", "error")
        self._show_error("执行失败", message)

    def _show_error(self, title: str, message: str) -> None:
        fn = getattr(self._main, "show_error", None)
        if callable(fn):
            fn(title, message, "可查看运行日志定位具体文件，或检查目录配置与磁盘空间。")
        else:
            QMessageBox.warning(self, title, message)

    # ---------- helper actions ----------
    def _open_tool_dir(self) -> None:
        d = auto_extract_tool_dir()
        if d:
            reveal_in_explorer(d)

    def _open_readme(self) -> None:
        p = auto_extract_readme()
        if p:
            reveal_in_explorer(p)

    def _open_report_dir(self) -> None:
        d = report_output_dir()
        if d:
            d.mkdir(parents=True, exist_ok=True)
            reveal_in_explorer(d)

    def _launch_standalone_service(self) -> None:
        root = auto_extract_tool_dir()
        if root is None:
            QMessageBox.warning(self, "不可用", auto_extract_missing_reason())
            return
        main_py = root / "main.py"
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NEW_CONSOLE  # type: ignore[attr-defined]
        try:
            subprocess.Popen(
                [sys.executable, str(main_py)],
                cwd=str(root),
                creationflags=creationflags,
            )
            self._log_line("已在独立控制台启动 main.py（监控 + API）。", "success")
        except OSError as exc:
            QMessageBox.warning(self, "启动失败", str(exc))
