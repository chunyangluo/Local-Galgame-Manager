from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.data.database import VndbImportRow
from app.services.vndb_service import VndbOutcome, VndbRecord
from app.ui.dialogs.vndb_candidate_selector import VndbCandidateSelector


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
        targets: list[tuple[str, str, str]] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("VNDB 批量导入结果")
        self.resize(680, 460)
        self._outcomes = outcomes
        self._targets = targets or []
        self._selected_records: list[tuple[int, VndbRecord]] = []
        self._cancelled = cancelled

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)

        failed = len(self._outcomes) - sum(1 for o in self._outcomes if o.success)
        status = "已取消" if self._cancelled else "已完成"
        summary = QLabel(
            f"{status}：共 {len(self._outcomes)} 个，成功 {sum(1 for o in self._outcomes if o.success)}，失败 {failed}"
        )
        summary.setObjectName("vndbResultHeadline")
        layout.addWidget(summary)

        has_multi_candidates = any(
            o.success and o.candidates and len(o.candidates) > 1 
            for o in self._outcomes
        )
        
        if has_multi_candidates:
            self._candidates_tree = QTreeWidget()
            self._candidates_tree.setRootIsDecorated(False)
            self._candidates_tree.setHeaderLabels(["游戏名", "匹配数", "操作"])
            self._candidates_tree.setColumnWidth(0, 240)
            self._candidates_tree.setColumnWidth(1, 80)
            
            for idx, outcome in enumerate(self._outcomes):
                if not outcome.success or not outcome.candidates or len(outcome.candidates) <= 1:
                    continue
                target_name = self._targets[idx][0] if idx < len(self._targets) else outcome.query
                item = QTreeWidgetItem([
                    target_name,
                    str(len(outcome.candidates)),
                    ""
                ])
                item.setData(Qt.UserRole, (idx, outcome))
                self._candidates_tree.addTopLevelItem(item)
            
            self._candidates_tree.header().setSectionResizeMode(2, QHeaderView.Stretch)
            layout.addWidget(self._candidates_tree)
            
            self._select_btn = QPushButton("选择正确的条目")
            self._select_btn.setProperty("btnRole", "primary")
            self._select_btn.clicked.connect(self._on_select_candidates)
            layout.addWidget(self._select_btn)
        
        if failed > 0:
            tip = QLabel("失败明细：")
            layout.addWidget(tip)
            tree = QTreeWidget()
            tree.setRootIsDecorated(False)
            tree.setHeaderLabels(["游戏名", "失败原因", "详情"])
            tree.setColumnWidth(0, 240)
            tree.setColumnWidth(1, 140)
            for idx, outcome in enumerate(self._outcomes):
                if outcome.success:
                    continue
                target_name = self._targets[idx][0] if idx < len(self._targets) else outcome.query
                item = QTreeWidgetItem(
                    [
                        target_name or "(空)",
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

    def _on_select_candidates(self) -> None:
        selected_items = self._candidates_tree.selectedItems()
        if not selected_items:
            return
        
        for item in selected_items:
            idx, outcome = item.data(Qt.UserRole)
            if outcome.candidates and len(outcome.candidates) > 1:
                target_name = self._targets[idx][0] if idx < len(self._targets) else outcome.query
                selected = VndbCandidateSelector.select_candidate(
                    target_name, outcome.candidates, self
                )
                if selected:
                    self._selected_records.append((idx, selected))
                    item.setText(2, f"已选择: {selected.title_localized or selected.title_original}")

    def get_selected_records(self) -> list[tuple[int, VndbRecord]]:
        return self._selected_records