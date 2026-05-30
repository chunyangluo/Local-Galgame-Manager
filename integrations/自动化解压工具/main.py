from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from pathlib import Path

import uvicorn
from loguru import logger

from core.config import init_settings, get_settings
from core.logger import init_logger, show_banner, show_startup_info
from core.password_manager import PasswordManager
from core.extractor import Extractor
from core.file_manager import FileManager
from core.watcher import WatcherService
from api.app import create_app
from api.deps import init_services


def parse_args():
    parser = argparse.ArgumentParser(description="自动解压工具")
    parser.add_argument(
        "-c", "--config",
        type=str,
        default=None,
        help="配置文件路径",
    )
    parser.add_argument(
        "--no-watch",
        action="store_true",
        help="禁用目录监控",
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="启动后立即扫描监控目录",
    )
    return parser.parse_args()


async def run_watcher(watcher: WatcherService, do_scan: bool = False) -> None:
    try:
        if do_scan:
            result = await watcher.scan_directory()
        await watcher.start()
    except Exception as e:
        logger.error(f"目录监控异常: {e}")


async def run_api(settings) -> None:
    config = uvicorn.Config(
        app=create_app(),
        host=settings.app.host,
        port=settings.app.port,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    await server.serve()


async def main() -> None:
    args = parse_args()

    config_path = args.config
    if config_path is None:
        config_path = Path(__file__).resolve().parent / "config" / "config.yaml"

    settings = init_settings(config_path)
    init_logger()

    show_banner()
    show_startup_info(settings)

    password_manager = PasswordManager()
    extractor = Extractor(password_manager)
    file_manager = FileManager()
    watcher_service = WatcherService(extractor, file_manager)

    init_services(extractor, file_manager, password_manager, watcher_service)

    tasks = []
    tasks.append(asyncio.create_task(run_api(settings)))

    if args.no_watch:
        if args.scan:
            await watcher_service.scan_directory()
            raise SystemExit(0)
    else:
        tasks.append(asyncio.create_task(run_watcher(watcher_service, do_scan=args.scan)))

    loop = asyncio.get_running_loop()

    def _signal_handler():
        logger.info("收到停止信号，正在关闭...")
        for t in tasks:
            t.cancel()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            pass

    try:
        await asyncio.gather(*tasks, return_exceptions=True)
    except asyncio.CancelledError:
        pass
    finally:
        if not args.no_watch:
            await watcher_service.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
