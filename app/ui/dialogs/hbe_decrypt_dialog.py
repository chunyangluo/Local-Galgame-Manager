"""GUI for integrations/hbe-decryptor — Hexo Blog Encrypt HTML decrypt."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.services.hbe_decrypt_service import (
    HbeBatchResult,
    HbeSingleResult,
    default_ciphertext_dir,
    default_plaintext_dir,
    hbe_missing_reason,
    is_hbe_available,
)
from app.services.paths import hbe_decryptor_dir, hbe_decryptor_readme
from app.ui.dialogs.game_detail_dialog import reveal_in_explorer
from app.workers.hbe_decrypt_worker import HbeBatchDecryptTask, HbeSingleDecryptTask

if TYPE_CHECKING:
    from app.ui.main_window import MainWindow


class HbeDecryptDialog(QDialog):
    def __init__(self, main: MainWindow, parent: QWidget | None = None) -> None:
        super().__init__(parent if parent is not None else main)
        self._main = main
        self.setWindowTitle("HBE 解密工具")
        self.setMinimumSize(640, 520)
        self._pool = QThreadPool.globalInstance()
        self._running = False

        root = QVBoxLayout(self)
        intro = QLabel(
            "离线解密 <b>Hexo Blog Encrypt</b> 保存的 HTML 页面。"
            "仅用于您拥有合法授权的内容。"
        )
        intro.setWordWrap(True)
        intro.setTextFormat(Qt.TextFormat.RichText)
        intro.setStyleSheet("color:#93A1B6;font-size:12px;")
        root.addWidget(intro)

        if not is_hbe_available():
            warn = QLabel(hbe_missing_reason())
            warn.setWordWrap(True)
            warn.setStyleSheet("color:#E8605D;")
            root.addWidget(warn)

        link_row = QHBoxLayout()
        btn_tool = QPushButton("打开工具目录")
        btn_tool.clicked.connect(self._open_tool_dir)
        link_row.addWidget(btn_tool)
        btn_readme = QPushButton("打开说明 (README)")
        btn_readme.clicked.connect(self._open_readme)
        link_row.addWidget(btn_readme)
        btn_out = QPushButton("打开 output 目录")
        btn_out.clicked.connect(self._open_output_dir)
        link_row.addWidget(btn_out)
        link_row.addStretch(1)
        root.addLayout(link_row)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_single_tab(), "单文件")
        self._tabs.addTab(self._build_batch_tab(), "批量")
        root.addWidget(self._tabs, 1)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(5000)
        self._log.setPlaceholderText("运行日志…")
        root.addWidget(self._log, 1)

        close_box = QDialogButtonBox(QDialogButtonBox.Close)
        close_box.rejected.connect(self.reject)
        root.addWidget(close_box)

        self._fill_defaults()

    def _build_single_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        row = QHBoxLayout()
        row.addWidget(QLabel("密文 HTML"))
        self._single_cipher = QLineEdit()
        self._single_cipher.setPlaceholderText("选择加密的 .html 文件")
        row.addWidget(self._single_cipher, 1)
        btn = QPushButton("浏览…")
        btn.clicked.connect(self._browse_single_cipher)
        row.addWidget(btn)
        layout.addLayout(row)

        prow = QHBoxLayout()
        prow.addWidget(QLabel("密码"))
        self._single_password = QLineEdit()
        self._single_password.setPlaceholderText("已知密码；勾选 AUTO 时忽略")
        prow.addWidget(self._single_password, 1)
        layout.addLayout(prow)

        self._single_auto = QCheckBox("AUTO（字典 → candidates → 4～6 位数字穷举，可能很慢）")
        layout.addWidget(self._single_auto)

        self._btn_single = QPushButton("开始解密")
        self._btn_single.setProperty("btnRole", "primary")
        self._btn_single.clicked.connect(self._run_single)
        layout.addWidget(self._btn_single)

        hint = QLabel("成功后明文在 integrations/hbe-decryptor/output/plaintext/")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#586E75;font-size:11px;")
        layout.addWidget(hint)
        layout.addStretch(1)
        return w

    def _build_batch_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        g = QGroupBox("目录")
        gl = QVBoxLayout(g)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("密文目录"))
        self._batch_cipher_dir = QLineEdit()
        r1.addWidget(self._batch_cipher_dir, 1)
        b1 = QPushButton("浏览…")
        b1.clicked.connect(self._browse_batch_cipher_dir)
        r1.addWidget(b1)
        gl.addLayout(r1)

        r2 = QHBoxLayout()
        r2.addWidget(QLabel("明文输出"))
        self._batch_output_dir = QLineEdit()
        r2.addWidget(self._batch_output_dir, 1)
        b2 = QPushButton("浏览…")
        b2.clicked.connect(self._browse_batch_output_dir)
        r2.addWidget(b2)
        gl.addLayout(r2)

        layout.addWidget(g)

        r3 = QHBoxLayout()
        r3.addWidget(QLabel("统一密码"))
        self._batch_password = QLineEdit()
        self._batch_password.setPlaceholderText("批量模式需已知密码")
        r3.addWidget(self._batch_password, 1)
        layout.addLayout(r3)

        self._btn_batch = QPushButton("批量解密")
        self._btn_batch.setProperty("btnRole", "primary")
        self._btn_batch.clicked.connect(self._run_batch)
        layout.addWidget(self._btn_batch)

        hint = QLabel("仅处理密文目录顶层的 *.html（不递归子文件夹）。汇总 CSV/JSON 在 output/ 根目录。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#586E75;font-size:11px;")
        layout.addWidget(hint)
        layout.addStretch(1)
        return w

    def _fill_defaults(self) -> None:
        ct = default_ciphertext_dir()
        if ct:
            self._batch_cipher_dir.setText(str(ct))
        out = default_plaintext_dir()
        if out:
            self._batch_output_dir.setText(str(out))

    def _append_log(self, line: str) -> None:
        self._log.appendPlainText(line)

    def _set_busy(self, busy: bool) -> None:
        self._running = busy
        self._btn_single.setEnabled(not busy)
        self._btn_batch.setEnabled(not busy)

    def reject(self) -> None:
        if self._running:
            QMessageBox.information(self, "任务运行中", "请等待当前解密任务完成后再关闭。")
            return
        super().reject()

    def _browse_single_cipher(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择密文 HTML", "", "HTML (*.html *.htm);;All (*.*)"
        )
        if path:
            self._single_cipher.setText(path)

    def _browse_batch_cipher_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择密文目录")
        if path:
            self._batch_cipher_dir.setText(path)

    def _browse_batch_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择明文输出目录")
        if path:
            self._batch_output_dir.setText(path)

    def _run_single(self) -> None:
        if not is_hbe_available():
            QMessageBox.warning(self, "不可用", hbe_missing_reason())
            return
        cipher = self._single_cipher.text().strip()
        if not cipher:
            QMessageBox.information(self, "提示", "请选择密文 HTML 文件。")
            return
        use_auto = self._single_auto.isChecked()
        password = self._single_password.text()
        if not use_auto and not password.strip():
            QMessageBox.information(self, "提示", "请输入密码，或勾选 AUTO。")
            return
        if use_auto:
            r = QMessageBox.warning(
                self,
                "AUTO 模式",
                "AUTO 可能在字典失败后穷举 4～6 位数字密码，耗时很长。\n是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if r != QMessageBox.StandardButton.Yes:
                return

        self._set_busy(True)
        self._append_log("—— 单文件解密开始 ——")
        task = HbeSingleDecryptTask(
            cipher,
            password.strip(),
            use_auto=use_auto,
            signal_parent=self,
        )
        task.signals.log_line.connect(self._append_log)
        task.signals.single_finished.connect(self._on_single_done)
        task.signals.failed.connect(self._on_task_failed)
        self._pool.start(task)

    def _run_batch(self) -> None:
        if not is_hbe_available():
            QMessageBox.warning(self, "不可用", hbe_missing_reason())
            return
        password = self._batch_password.text().strip()
        if not password:
            QMessageBox.information(self, "提示", "批量解密需要输入统一密码。")
            return
        ct = self._batch_cipher_dir.text().strip()
        out = self._batch_output_dir.text().strip()
        if not ct or not out:
            QMessageBox.information(self, "提示", "请指定密文目录与输出目录。")
            return

        self._set_busy(True)
        self._append_log("—— 批量解密开始 ——")
        task = HbeBatchDecryptTask(password, ct, out, signal_parent=self)
        task.signals.log_line.connect(self._append_log)
        task.signals.batch_finished.connect(self._on_batch_done)
        task.signals.failed.connect(self._on_task_failed)
        self._pool.start(task)

    def _on_single_done(self, result: HbeSingleResult) -> None:
        self._set_busy(False)
        self._append_log(result.message)
        if result.password_used:
            self._append_log(f"使用密码: {result.password_used}")
        if result.plaintext_path:
            self._append_log(f"明文: {result.plaintext_path}")
        if result.report_path:
            self._append_log(f"报告: {result.report_path}")
        if result.success:
            self._main.status.setText("HBE 解密成功")
            if result.plaintext_path and result.plaintext_path.is_file():
                r = QMessageBox.question(
                    self,
                    "解密成功",
                    f"明文已保存。\n{result.plaintext_path}\n\n是否在资源管理器中打开？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if r == QMessageBox.StandardButton.Yes:
                    try:
                        reveal_in_explorer(str(result.plaintext_path), select_file=True)
                    except OSError as exc:
                        QMessageBox.warning(self, "无法打开", str(exc))
        else:
            QMessageBox.warning(self, "解密失败", result.message)

    def _on_batch_done(self, result: HbeBatchResult) -> None:
        self._set_busy(False)
        self._append_log(result.message)
        if result.summary_csv:
            self._append_log(f"汇总 CSV: {result.summary_csv}")
        if result.summary_json:
            self._append_log(f"汇总 JSON: {result.summary_json}")
        self._main.status.setText(result.message)
        QMessageBox.information(
            self,
            "批量完成",
            f"{result.message}\n输出目录:\n{result.output_dir}",
        )

    def _on_task_failed(self, message: str) -> None:
        self._set_busy(False)
        self._append_log(f"[错误] {message}")
        QMessageBox.critical(self, "运行失败", message)

    def _open_tool_dir(self) -> None:
        d = hbe_decryptor_dir()
        if d is None:
            QMessageBox.warning(self, "未找到", "integrations/hbe-decryptor 不存在。")
            return
        try:
            reveal_in_explorer(str(d), select_file=False)
        except OSError as exc:
            QMessageBox.warning(self, "无法打开", str(exc))

    def _open_readme(self) -> None:
        p = hbe_decryptor_readme()
        if p is None:
            QMessageBox.information(self, "说明", "README 未找到。")
            return
        try:
            reveal_in_explorer(str(p), select_file=True)
        except OSError as exc:
            QMessageBox.warning(self, "无法打开", str(exc))

    def _open_output_dir(self) -> None:
        d = hbe_decryptor_dir()
        if d is None:
            return
        out = d / "output"
        out.mkdir(parents=True, exist_ok=True)
        try:
            reveal_in_explorer(str(out), select_file=False)
        except OSError as exc:
            QMessageBox.warning(self, "无法打开", str(exc))
