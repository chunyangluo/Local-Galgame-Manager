from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Optional

from loguru import logger
from watchdog.events import (
    FileSystemEventHandler,
    FileCreatedEvent,
    FileModifiedEvent,
    FileMovedEvent,
)
from watchdog.observers import Observer

from core.archive_detector import (
    detect_archive_type,
    detect_split_volume_set,
    detect_7z_split_volume_set,
    is_7z_split_part,
    is_download_temp_file,
)
from core.config import get_settings
from core.extractor import Extractor
from core.file_manager import FileManager
from core.report_generator import ExtractReportGenerator
from core.logger import (
    ui_file_detected, ui_waiting_download, ui_download_stable,
    ui_split_detected, ui_split_integrity_ok,
    ui_task_start, ui_task_done, ui_task_skipped, ui_scan_start, ui_scan_progress, ui_scan_done,
    ui_waiting_new_files, show_monitoring,
    format_size, format_duration,
    print_warning,
)


class ArchiveEventHandler(FileSystemEventHandler):
    def __init__(
        self,
        extractor: Extractor,
        file_manager: FileManager,
        loop: asyncio.AbstractEventLoop,
        debounce_seconds: float = 3.0,
        stable_check_interval: float = 0.5,
        stable_threshold: int = 2,
    ) -> None:
        super().__init__()
        self._extractor = extractor
        self._file_manager = file_manager
        self._loop = loop
        self._debounce_seconds = debounce_seconds
        self._stable_check_interval = stable_check_interval
        self._stable_threshold = stable_threshold
        self._pending: dict[str, float] = {}
        self._processing: set[str] = set()

    def on_created(self, event: FileCreatedEvent) -> None:
        if event.is_directory:
            return
        self._schedule_process(event.src_path)

    def on_modified(self, event: FileModifiedEvent) -> None:
        if event.is_directory:
            return
        self._schedule_process(event.src_path)

    def on_moved(self, event: FileMovedEvent) -> None:
        if event.is_directory:
            return
        dest_path = event.dest_path
        self._schedule_process(dest_path)

    def _schedule_process(self, file_path: str) -> None:
        p = Path(file_path)
        if is_download_temp_file(file_path):
            ui_file_detected(p.name, is_temp=True)
            return
        file_path = self._normalize_archive_path(file_path)
        p = Path(file_path)
        atype = detect_archive_type(file_path)
        if atype is None:
            return
        ui_file_detected(p.name, is_temp=False)
        self._pending[file_path] = time.time()

    @staticmethod
    def _normalize_archive_path(file_path: str) -> str:
        """7z 分卷非首卷 → 统一到 .001，避免重复解压。"""
        part = is_7z_split_part(file_path)
        if part:
            return part["first_part"]
        split_7z = detect_7z_split_volume_set(file_path)
        if split_7z:
            return split_7z["extract_entry"]
        split_sfx = detect_split_volume_set(file_path)
        if split_sfx:
            return split_sfx["extract_entry"]
        return file_path

    async def _wait_stable_and_process(self, file_path: str) -> None:
        file_path = self._normalize_archive_path(file_path)
        p = Path(file_path)
        if not p.exists():
            return

        split_7z = detect_7z_split_volume_set(file_path)
        if split_7z:
            for vol in split_7z["all_files"]:
                if not Path(vol).exists():
                    logger.warning(f"7z 分卷未齐，等待后续分卷: {Path(vol).name}")
                    return

        ui_waiting_download(p.name)
        stable_count = 0
        last_size = -1
        while stable_count < self._stable_threshold:
            await asyncio.sleep(self._stable_check_interval)
            if not p.exists():
                return
            try:
                current_size = p.stat().st_size
            except OSError:
                return
            if current_size == last_size and current_size > 0:
                stable_count += 1
            else:
                stable_count = 0
                last_size = current_size

        size_mb = p.stat().st_size / 1024 / 1024
        ui_download_stable(p.name, size_mb)

        split_info = detect_split_volume_set(file_path)
        if split_info:
            ui_split_detected(split_info["base_name"], split_info["volume_count"])
            for vol_path in split_info["all_files"]:
                if not Path(vol_path).exists():
                    logger.warning(f"分卷文件缺失: {vol_path}")

        ui_task_start(p.name, format_size(p.stat().st_size))
        t0 = time.monotonic()
        result = await self._extractor.extract(file_path)
        elapsed = time.monotonic() - t0
        self._file_manager.handle_extract_result(result)
        ui_task_done(p.name, result.success, elapsed)

    async def process_pending(self) -> None:
        now = time.time()
        ready = []
        for fp, t in list(self._pending.items()):
            if now - t >= self._debounce_seconds:
                ready.append(fp)

        for fp in ready:
            self._pending.pop(fp, None)
            if fp in self._processing:
                continue
            if not Path(fp).exists():
                continue
            self._processing.add(fp)
            try:
                await self._wait_stable_and_process(fp)
            except Exception as e:
                logger.error(f"处理文件异常: {Path(fp).name} | {e}")
            finally:
                self._processing.discard(fp)


class WatcherService:
    def __init__(
        self,
        extractor: Extractor,
        file_manager: FileManager,
    ) -> None:
        self._settings = get_settings()
        self._extractor = extractor
        self._file_manager = file_manager
        self._observer: Optional[Observer] = None
        self._handler: Optional[ArchiveEventHandler] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._running = False

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        watch_dir = Path(self._settings.directories.watch)
        watch_dir.mkdir(parents=True, exist_ok=True)

        self._handler = ArchiveEventHandler(
            extractor=self._extractor,
            file_manager=self._file_manager,
            loop=self._loop,
            debounce_seconds=self._settings.watcher.debounce_seconds,
            stable_check_interval=self._settings.watcher.stable_check_interval,
            stable_threshold=self._settings.watcher.stable_threshold,
        )

        self._observer = Observer()
        self._observer.schedule(self._handler, str(watch_dir), recursive=True)
        self._observer.start()
        self._running = True
        show_monitoring()

        while self._running:
            if self._handler:
                await self._handler.process_pending()
            await asyncio.sleep(1)

    async def stop(self) -> None:
        self._running = False
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)

    async def scan_directory(self) -> dict:
        watch_dir = Path(self._settings.directories.watch)
        
        if not watch_dir.exists():
            return {"total": 0, "success": 0, "failed": 0, "skipped": 0}

        skip_dirs = {
            Path(self._settings.directories.archive).resolve(),
            Path(self._settings.directories.temp).resolve(),
            Path(self._settings.directories.target).resolve(),
            Path(self._settings.directories.failed).resolve(),
        }

        results = {"total": 0, "success": 0, "failed": 0, "skipped": 0}
        processed_bases: set[str] = set()
        processed_files: set[str] = set()

        # 初始化报告生成器
        report_gen = ExtractReportGenerator(self._settings)
        report_gen.start(
            monitor_dir=str(watch_dir),
            game_save_dir=str(self._settings.directories.game_save)
        )

        all_items = []
        for item in watch_dir.rglob("*"):
            if not item.is_file():
                continue
            if any(item.is_relative_to(d) for d in skip_dirs if d.exists()):
                continue
            all_items.append(item)
        all_items = sorted(all_items, key=lambda x: x.name)
        
        archive_items = []
        MIN_SIZE_MB = 200
        MIN_SIZE_BYTES = MIN_SIZE_MB * 1024 * 1024

        for item in all_items:
            if item.is_dir():
                continue
            if str(item) in processed_files:
                continue
            if is_download_temp_file(item):
                continue
            atype = detect_archive_type(item)
            if atype is None:
                continue
            
            # 文件体积过滤
            split_7z = detect_7z_split_volume_set(item)
            if not split_7z:
                part_7z = is_7z_split_part(item)
                if part_7z:
                    split_7z = detect_7z_split_volume_set(part_7z["first_part"])
            if split_7z:
                base = split_7z["base_name"]
                if base in processed_bases:
                    continue
                try:
                    total_size = sum(
                        Path(f).stat().st_size
                        for f in split_7z["all_files"]
                        if Path(f).exists()
                    )
                    if total_size < MIN_SIZE_BYTES:
                        results["skipped"] += 1
                        report_gen.record_skipped()
                        print_warning(f"跳过文件 {item.name}：7z 分卷组总大小小于200MB")
                        ui_task_skipped(item.name, "7z 分卷组总大小小于200MB")
                    else:
                        processed_bases.add(base)
                        for f in split_7z["all_files"]:
                            processed_files.add(str(f))
                        entry = Path(split_7z["extract_entry"])
                        archive_items.append((entry, atype))
                except Exception:
                    continue
                continue

            split_info = detect_split_volume_set(item)
            if split_info:
                # 分卷包：判断整个分卷组的总大小
                base = split_info["base_name"]
                if base in processed_bases:
                    continue
                
                # 计算分卷组所有文件的总大小
                try:
                    total_size = 0
                    for f in split_info["all_files"]:
                        try:
                            total_size += Path(f).stat().st_size
                        except Exception:
                            pass
                    
                    if total_size < MIN_SIZE_BYTES:
                        results["skipped"] += 1
                        report_gen.record_skipped()
                        print_warning(f"跳过文件 {item.name}：分卷组总大小小于200MB")
                        ui_task_skipped(item.name, f"分卷组总大小小于200MB")
                    else:
                        # 分卷包满足，保留处理
                        processed_bases.add(base)
                        for f in split_info["all_files"]:
                            processed_files.add(str(f))
                        archive_items.append((item, atype))
                except Exception as e:
                    continue
            else:
                # 单个文件
                try:
                    if item.stat().st_size < MIN_SIZE_BYTES:
                        results["skipped"] +=1
                        report_gen.record_skipped()
                        print_warning(f"跳过文件 {item.name}：小于200MB")
                        ui_task_skipped(item.name, f"小于200MB")
                        continue
                    archive_items.append((item, atype))
                except Exception as e:
                    continue

        total = len(archive_items)
        ui_scan_start(total)

        t_scan_start = time.monotonic()
        for i, (item, atype) in enumerate(archive_items):
            ui_scan_progress(i + 1, total, item.name)
            results["total"] += 1
            try:
                ui_task_start(item.name, format_size(item.stat().st_size))
                t0 = time.monotonic()
                result = await self._extractor.extract(str(item))
                elapsed = time.monotonic() - t0

                post_result, moved_games = self._file_manager.handle_extract_result(
                    result,
                    cover_callback=report_gen.record_cover_operation
                )
                
                # 添加文件记录到报告中
                final_paths = []
                has_cover = any(is_cover for (_, is_cover) in moved_games)
                for final_path, _ in moved_games:
                    final_paths.append(final_path)
                
                report_gen.add_result(
                    result,
                    final_path="; ".join(final_paths),
                    is_cover=has_cover,
                    elapsed=elapsed
                )

                ui_task_done(item.name, result.success, elapsed)
                if result.success:
                    results["success"] += 1
                else:
                    results["failed"] += 1
            except Exception as e:
                logger.error(f"扫描处理异常: {item.name} | {e}")
                results["failed"] += 1

        report_gen.end()
        report_gen.generate_report()
        ui_scan_done(results["success"], results["failed"], time.monotonic() - t_scan_start)
        return results
