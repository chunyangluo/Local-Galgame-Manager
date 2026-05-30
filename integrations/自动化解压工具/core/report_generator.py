from __future__ import annotations
from pathlib import Path
from datetime import datetime
from typing import Any, Optional
from .extractor import ExtractResult
from . import logger


class ExtractReportGenerator:
    """自动生成解压验收报告"""

    def __init__(self, settings):
        self._settings = settings
        self._report_dir = Path(__file__).resolve().parent.parent / "extract_report"
        self._report_dir.mkdir(exist_ok=True, parents=True)

        self._results = []
        self._start_time = None
        self._end_time = None
        self._monitor_dir = ""
        self._game_save_dir = ""
        self._cover_count = 0
        self._nested_count = 0
        self._skipped_count = 0
        self._failed_results = []
        self._processed_files = set()  # 避免重复记录文件

    def start(self, monitor_dir, game_save_dir):
        self._start_time = datetime.now()
        self._monitor_dir = monitor_dir
        self._game_save_dir = game_save_dir
        self._results = []
        self._failed_results = []
        self._cover_count = 0
        self._nested_count = 0
        self._skipped_count = 0
        self._processed_files = set()
        
    def record_skipped(self, count=1):
        self._skipped_count += count

    def add_result(self, result, final_path=None, is_cover=False, elapsed=None):
        """添加单个处理结果"""
        if result.depth != 0:
            self._nested_count += 1
            return  # 只记录外层解压

        file_name = result.file_name
        # 避免重复记录相同文件
        if file_name in self._processed_files:
            return
        self._processed_files.add(file_name)
        
        file_size = ""
        try:
            file_size = self._format_size(Path(result.file_path).stat().st_size)
        except Exception:
            pass

        elapsed_str = ""
        if elapsed:
            elapsed_str = self._format_duration(elapsed)

        entry = {
            "file_name": file_name,
            "file_size": file_size,
            "archive_type": result.archive_type,
            "used_password": self._mask_pwd(result.used_password),
            "elapsed": elapsed_str,
            "success": result.success,
            "is_cover": is_cover,
            "extract_dir": result.extract_dir,
            "final_path": final_path or "",
            "error": result.error,
        }
        self._results.append(entry)

        if not result.success:
            self._failed_results.append(entry)

    def _mask_pwd(self, pwd):
        if not pwd:
            return "(无密码)"
        if len(pwd) <= 2:
            return "*" * len(pwd)
        return pwd[0] + "*" * (len(pwd) - 2) + pwd[-1]

    @staticmethod
    def _format_size(size):
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    def record_cover_operation(self):
        self._cover_count += 1

    def end(self):
        self._end_time = datetime.now()

    def generate_report(self):
        if not self._start_time or not self._end_time:
            return None

        report_name = f"解压验收报告_{self._end_time.strftime('%Y%m%d_%H%M%S')}.txt"
        report_path = self._report_dir / report_name

        elapsed = self._end_time - self._start_time
        elapsed_str = self._format_duration(elapsed.total_seconds())

        total_count = len(self._results)
        success_count = sum(1 for r in self._results if r["success"])
        fail_count = total_count - success_count

        # 构建报告
        lines = []
        lines.append("# 解压验收报告")
        lines.append("=" * 80)
        lines.append("")

        # 第一部分：简易摘要
        lines.append("## 一、简易摘要")
        lines.append("-" * 80)
        lines.append("")

        lines.append("### 1. 基础运行信息")
        lines.append(f"- 报告生成时间: {self._end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"- 任务整体运行时长: {elapsed_str}")
        lines.append(f"- 监控目录: {self._monitor_dir}")
        lines.append(f"- 游戏存储目录: {self._game_save_dir}")
        lines.append("")

        lines.append("### 2. 核心数据统计")
        lines.append(f"- 本次扫描文件总数量: {total_count + self._skipped_count}")
        lines.append(f"- 处理成功数量: {success_count}")
        lines.append(f"- 处理失败数量: {fail_count}")
        lines.append(f"- 跳过数量(小于200MB): {self._skipped_count}")
        lines.append(f"- 执行同名目录覆盖操作总次数: {self._cover_count}")
        lines.append(f"- 嵌套压缩包处理总数量: {self._nested_count}")
        lines.append("")

        lines.append("### 3. 验收结论")
        if fail_count == 0:
            lines.append(u"✅ 全部执行正常，验收通过")
        else:
            lines.append(f"⚠️ 存在 {fail_count} 个失败任务，请人工核查")
        lines.append("")

        lines.append("=" * 80)
        lines.append("")

        # 第二部分：详细报告
        lines.append("## 二、详细报告")
        lines.append("-" * 80)
        lines.append("")

        lines.append("### 模块1：单文件逐条明细")
        for i, entry in enumerate(self._results, 1):
            lines.append("")
            lines.append(f"{i}. **{entry['file_name']}** ({entry['file_size']})")
            lines.append(f"   - 识别格式: {entry['archive_type']}")
            lines.append(f"   - 实际密码: {entry['used_password']}")
            lines.append(f"   - 处理耗时: {entry['elapsed']}")
            lines.append(f"   - 处理结果: {'✅ 成功' if entry['success'] else '❌ 失败'}")
            if entry['extract_dir']:
                lines.append(f"   - 解压目录: {entry['extract_dir']}")
            lines.append(f"   - 是否执行目录覆盖: {'是' if entry['is_cover'] else '否'}")
            if entry['final_path']:
                lines.append(f"   - 最终落地路径: {entry['final_path']}")
            elif entry['success']:
                lines.append(f"   - 说明: 解压成功但未识别到游戏目录")
            if not entry['success'] and entry['error']:
                lines.append(f"   - 错误描述: {entry['error']}")

        lines.append("")
        lines.append("### 模块2：异常问题汇总")
        if not self._failed_results:
            lines.append("")
            lines.append("本次无异常问题")
        else:
            for entry in self._failed_results:
                lines.append("")
                lines.append(f"- {entry['file_name']}: {entry['error']}")

        lines.append("")
        lines.append("### 模块3：收尾总结")
        lines.append("")
        lines.append("=" * 80)
        if fail_count == 0:
            lines.append(u"✅ 任务整体状态：全部成功")
        else:
            lines.append(u"⚠️ 任务整体状态：部分成功")
        lines.append(f"- 扫描文件数: {total_count}，成功 {success_count} 个，失败 {fail_count} 个")
        lines.append(f"- 嵌套压缩包处理数: {self._nested_count}")
        lines.append(f"- 同名目录覆盖次数: {self._cover_count}")
        lines.append("=" * 80)
        lines.append("")

        report_path.write_text("\n".join(lines), encoding="utf-8")
        logger.print_success(f"验收报告已生成: {report_path}")
        return report_path

    @staticmethod
    def _format_duration(seconds):
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h}时{m}分{s}秒"
        if m > 0:
            return f"{m}分{s}秒"
        return f"{s}秒"
