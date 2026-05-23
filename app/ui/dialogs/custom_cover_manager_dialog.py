from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class CustomCoverManagerDialog(QDialog):
    """自定义封面管理对话框"""
    
    def __init__(self, parent, game_id: int, game_name: str, root_dir: str, current_cover_path: str | None):
        super().__init__(parent)
        self.setWindowTitle("自定义封面管理")
        self.setMinimumWidth(600)
        
        self._parent = parent
        self._game_id = game_id
        self._game_name = game_name
        self._root_dir = root_dir
        self._current_cover_path = current_cover_path
        self._selected_cover = None
        
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # 当前封面预览
        current_group = QGroupBox("当前封面")
        current_layout = QVBoxLayout(current_group)
        
        self._current_cover_label = QLabel()
        self._current_cover_label.setFixedSize(200, 300)
        self._current_cover_label.setAlignment(Qt.AlignCenter)
        self._current_cover_label.setStyleSheet("background:#252C36;border-radius:8px;")
        
        current_layout.addWidget(self._current_cover_label, alignment=Qt.AlignCenter)
        
        self._current_cover_info = QLabel()
        self._current_cover_info.setAlignment(Qt.AlignCenter)
        self._current_cover_info.setStyleSheet("font-size:11px;color:#93A1B6;")
        current_layout.addWidget(self._current_cover_info)
        
        layout.addWidget(current_group)
        
        # 操作按钮
        button_group = QGroupBox("封面操作")
        button_layout = QHBoxLayout(button_group)
        
        self._btn_upload = QPushButton("上传自定义封面")
        self._btn_upload.clicked.connect(self._on_upload_cover)
        button_layout.addWidget(self._btn_upload)
        
        self._btn_search = QPushButton("从游戏目录搜索")
        self._btn_search.clicked.connect(self._on_search_covers)
        button_layout.addWidget(self._btn_search)
        
        self._btn_reset = QPushButton("恢复默认封面")
        self._btn_reset.clicked.connect(self._on_reset_cover)
        button_layout.addWidget(self._btn_reset)
        
        layout.addWidget(button_group)
        
        # 搜索结果
        search_group = QGroupBox("找到的图片")
        search_layout = QVBoxLayout(search_group)
        
        self._cover_list = QListWidget()
        self._cover_list.setViewMode(QListWidget.IconMode)
        self._cover_list.setIconSize(QSize(100, 150))
        self._cover_list.setSelectionMode(QListWidget.SingleSelection)
        self._cover_list.doubleClicked.connect(self._on_select_cover_from_list)
        search_layout.addWidget(self._cover_list)
        
        self._btn_select = QPushButton("选择选中的图片作为封面")
        self._btn_select.clicked.connect(self._on_select_cover)
        self._btn_select.setEnabled(False)
        search_layout.addWidget(self._btn_select)
        
        layout.addWidget(search_group)
        
        # 预览区域
        preview_group = QGroupBox("选中预览")
        preview_layout = QVBoxLayout(preview_group)
        
        self._preview_label = QLabel()
        self._preview_label.setFixedSize(200, 300)
        self._preview_label.setAlignment(Qt.AlignCenter)
        self._preview_label.setStyleSheet("background:#252C36;border-radius:8px;")
        preview_layout.addWidget(self._preview_label, alignment=Qt.AlignCenter)
        
        self._preview_info = QLabel("（请选择一张图片）")
        self._preview_info.setAlignment(Qt.AlignCenter)
        self._preview_info.setStyleSheet("font-size:11px;color:#93A1B6;")
        preview_layout.addWidget(self._preview_info)
        
        layout.addWidget(preview_group)
        
        # 确认按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._on_ok)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        # 加载当前封面
        self._load_current_cover()
        
        # 连接列表选择信号
        self._cover_list.currentItemChanged.connect(self._on_list_item_changed)
    
    def _load_current_cover(self):
        """加载当前封面预览"""
        if self._current_cover_path and Path(self._current_cover_path).exists():
            pixmap = QPixmap(self._current_cover_path)
            pixmap = pixmap.scaled(200, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._current_cover_label.setPixmap(pixmap)
            self._current_cover_info.setText(f"当前封面\n{os.path.basename(self._current_cover_path)}")
        else:
            self._current_cover_label.setStyleSheet("background:#252C36;border-radius:8px;")
            self._current_cover_label.setText("无封面")
            self._current_cover_info.setText("（暂无封面）")
    
    def _on_upload_cover(self):
        """上传自定义封面"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择封面图片", "", 
            "图片文件 (*.png *.jpg *.jpeg *.webp *.bmp *.gif)"
        )
        if file_path:
            self._selected_cover = file_path
            self._preview_cover(file_path)
    
    def _on_search_covers(self):
        """从游戏目录搜索图片"""
        self._cover_list.clear()
        
        image_extensions = ('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif')
        found_images = []
        
        try:
            root = Path(self._root_dir)
            if root.exists() and root.is_dir():
                for file in root.rglob('*'):
                    if file.is_file() and file.suffix.lower() in image_extensions:
                        # 过滤常见的图标文件和小图片
                        try:
                            if file.stat().st_size > 1024 * 10:  # 大于 10KB
                                found_images.append(str(file))
                        except:
                            pass
        except Exception as e:
            QMessageBox.warning(self, "搜索失败", f"无法搜索游戏目录: {str(e)}")
            return
        
        if not found_images:
            QMessageBox.information(self, "未找到图片", "在游戏目录中未找到图片文件")
            return
        
        # 按文件大小排序（大的优先）
        found_images.sort(key=lambda x: -os.path.getsize(x))
        
        for img_path in found_images[:20]:  # 最多显示 20 张
            item = QListWidgetItem()
            pixmap = QPixmap(img_path)
            pixmap = pixmap.scaled(100, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            item.setIcon(pixmap)
            item.setToolTip(img_path)
            self._cover_list.addItem(item)
        
        QMessageBox.information(self, "搜索完成", f"找到 {len(found_images)} 张图片")
    
    def _on_list_item_changed(self, current, previous):
        """列表项变化时更新预览"""
        if current:
            self._btn_select.setEnabled(True)
            img_path = current.toolTip()
            self._selected_cover = img_path
            self._preview_cover(img_path)
        else:
            self._btn_select.setEnabled(False)
            self._selected_cover = None
            self._preview_label.clear()
            self._preview_info.setText("（请选择一张图片）")
    
    def _on_select_cover_from_list(self, index):
        """双击选择封面"""
        item = self._cover_list.item(index.row())
        if item:
            self._selected_cover = item.toolTip()
            self._preview_cover(self._selected_cover)
            self._on_ok()
    
    def _on_select_cover(self):
        """选择列表中的封面"""
        if self._selected_cover:
            self._on_ok()
    
    def _preview_cover(self, file_path):
        """预览封面"""
        pixmap = QPixmap(file_path)
        pixmap = pixmap.scaled(200, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._preview_label.setPixmap(pixmap)
        self._preview_info.setText(f"选中: {os.path.basename(file_path)}")
    
    def _on_reset_cover(self):
        """恢复默认封面"""
        reply = QMessageBox.question(
            self, "确认重置", 
            "确定要恢复默认封面吗？自定义封面将被清除。",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._selected_cover = None
            self._preview_label.clear()
            self._preview_info.setText("（将恢复为默认封面）")
            QMessageBox.information(self, "已标记", "点击确定以应用更改")
    
    def _on_ok(self):
        """应用更改"""
        try:
            if self._selected_cover is None:
                # 重置封面
                self._parent.db.update_game_custom_cover(self._game_id, None)
                self._parent.status.setText("封面已恢复为默认")
            else:
                # 设置自定义封面
                cover = self._parent.cover_manager.import_custom_cover(self._game_id, self._selected_cover)
                self._parent.db.update_game_custom_cover(self._game_id, cover)
                self._parent.status.setText("封面已更新")
            
            self._parent.refresh_games()
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "操作失败", str(exc))
            self.reject()
