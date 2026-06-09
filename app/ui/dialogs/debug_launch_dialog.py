"""Dialog to display game launch debug results with diagnostic info and suggestions."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class DebugLaunchResultDialog(QDialog):
    """Show detailed diagnostic info after a debug launch attempt."""

    def __init__(self, result: dict, game_name: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"调试启动结果 — {game_name}")
        self.setMinimumSize(560, 480)
        self.resize(640, 560)
        self._result = result
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # --- 状态概览 ---
        status_group = QGroupBox("状态概览")
        status_layout = QVBoxLayout(status_group)

        started = self._result.get("started", False)
        exit_code = self._result.get("exit_code")
        duration = self._result.get("duration_seconds", 0)
        use_le = self._result.get("use_le", False)
        error_msg = self._result.get("error_message", "")

        # Status icon + text
        if not started:
            status_text = "❌ 启动失败 — 进程未能创建"
            status_color = "#E74C3C"
        elif exit_code is None and duration >= 30:
            status_text = "✅ 进程运行正常 — 超过 30 秒未退出"
            status_color = "#27AE60"
        elif exit_code == 0:
            status_text = "✅ 进程正常退出"
            status_color = "#27AE60"
        elif error_msg:
            status_text = f"⚠️ {error_msg}"
            status_color = "#E67E22"
        else:
            status_text = f"⚠️ 进程异常退出（退出码 {exit_code}）"
            status_color = "#E67E22"

        status_label = QLabel(status_text)
        status_label.setStyleSheet(f"color:{status_color};font-size:14px;font-weight:bold;")
        status_label.setWordWrap(True)
        status_layout.addWidget(status_label)

        # Detail info
        info_parts = [f"启动方式: {'LE 转区' if use_le else '普通启动'}"]
        if exit_code is not None:
            info_parts.append(f"退出码: {exit_code} (0x{exit_code & 0xFFFFFFFF:08X})")
        info_parts.append(f"运行时长: {duration:.1f}s")
        info_label = QLabel("  |  ".join(info_parts))
        info_label.setStyleSheet("color:#93A1B6;font-size:12px;")
        status_layout.addWidget(info_label)

        exe_path = self._result.get("exe_path", "")
        exe_label = QLabel(f"目标: {exe_path}")
        exe_label.setStyleSheet("color:#7FA7D9;font-size:11px;")
        exe_label.setWordWrap(True)
        exe_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        status_layout.addWidget(exe_label)

        layout.addWidget(status_group)

        # --- 建议 ---
        suggestions = self._result.get("suggestions", [])
        if suggestions:
            sug_group = QGroupBox("建议")
            sug_layout = QVBoxLayout(sug_group)
            for i, sug in enumerate(suggestions, 1):
                sug_label = QLabel(f"{i}. {sug}")
                sug_label.setWordWrap(True)
                sug_label.setStyleSheet("font-size:12px;")
                sug_layout.addWidget(sug_label)
            layout.addWidget(sug_group)

        # --- 输出 ---
        stdout_text = self._result.get("stdout", "")
        stderr_text = self._result.get("stderr", "")
        if stdout_text or stderr_text:
            output_group = QGroupBox("进程输出")
            output_layout = QVBoxLayout(output_group)
            output_edit = QTextEdit()
            output_edit.setReadOnly(True)
            output_edit.setFont(QFont("Consolas", 9))
            parts = []
            if stdout_text:
                parts.append(f"--- stdout ---\n{stdout_text}")
            if stderr_text:
                parts.append(f"--- stderr ---\n{stderr_text}")
            output_edit.setPlainText("\n\n".join(parts))
            output_edit.moveCursor(QTextCursor.MoveOperation.End)
            output_layout.addWidget(output_edit)
            layout.addWidget(output_group, 1)

        # --- 按钮 ---
        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)

        btn_copy = QPushButton("复制诊断信息")
        btn_copy.setToolTip("将完整诊断信息复制到剪贴板")
        btn_copy.clicked.connect(self._copy_to_clipboard)
        btn_layout.addWidget(btn_copy)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btn_box.accepted.connect(self.accept)
        btn_layout.addWidget(btn_box)

        layout.addLayout(btn_layout)

    def _copy_to_clipboard(self):
        from PySide6.QtGui import QApplication
        lines = []
        r = self._result
        lines.append("=== 游戏调试启动诊断 ===")
        lines.append(f"目标: {r.get('exe_path', '')}")
        lines.append(f"启动方式: {'LE 转区' if r.get('use_le') else '普通启动'}")
        lines.append(f"进程创建: {'是' if r.get('started') else '否'}")
        ec = r.get("exit_code")
        if ec is not None:
            lines.append(f"退出码: {ec} (0x{ec & 0xFFFFFFFF:08X})")
        lines.append(f"运行时长: {r.get('duration_seconds', 0):.1f}s")
        if r.get("error_message"):
            lines.append(f"错误: {r['error_message']}")
        for i, s in enumerate(r.get("suggestions", []), 1):
            lines.append(f"建议{i}: {s}")
        if r.get("stdout"):
            lines.append(f"\n--- stdout ---\n{r['stdout']}")
        if r.get("stderr"):
            lines.append(f"\n--- stderr ---\n{r['stderr']}")
        QApplication.clipboard().setText("\n".join(lines))
