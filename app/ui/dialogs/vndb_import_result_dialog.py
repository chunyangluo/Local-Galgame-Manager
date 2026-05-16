from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.vndb_service import VndbOutcome

_FAILURE_REASON_LABELS = {
    "timeout": "请求超时",
    "no_match": "未匹配到 VNDB 条目",
    "http_error": "HTTP 错误",
    "parse_error": "响应解析失败",
    "rate_limit": "触发 VNDB 限流",
    "network_error": "网络错误",
    "missing_requests": "缺少 requests 依赖",
}


def _humanize_failure(reason: str | None) -> str:
    if not reason:
        return "未知错误"
    return _FAILURE_REASON_LABELS.get(reason, reason)


class VndbImportResultDialog(QDialog):
    def __init__(
        self,
        total: int,
        success: int,
        cancelled: bool,
        outcomes: list[VndbOutcome],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("VNDB 批量导入结果")
        self.resize(680, 460)
        layout = QVBoxLayout(self)

        failed = total - success
        status = "已取消" if cancelled else "已完成"
        summary = QLabel(
            f"{status}：共 {total} 个，成功 {success}，失败 {failed}"
        )
        summary.setObjectName("vndbResultHeadline")
        layout.addWidget(summary)

        if failed > 0:
            tip = QLabel("失败明细：")
            layout.addWidget(tip)
            tree = QTreeWidget()
            tree.setRootIsDecorated(False)
            tree.setHeaderLabels(["游戏名", "失败原因", "详情"])
            tree.setColumnWidth(0, 240)
            tree.setColumnWidth(1, 140)
            for outcome in outcomes:
                if outcome.success:
                    continue
                item = QTreeWidgetItem(
                    [
                        outcome.query or "(空)",
                        _humanize_failure(outcome.error_kind),
                        (outcome.error_detail or "").strip()[:200],
                    ]
                )
                tree.addTopLevelItem(item)
            tree.header().setSectionResizeMode(2, QHeaderView.Stretch)
            layout.addWidget(tree, 1)
        else:
            ok_label = QLabel("全部条目均已通过 VNDB 导入。")
            ok_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(ok_label, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
