from __future__ import annotations

import sys
import time
from pathlib import Path

from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn, DownloadColumn, TransferSpeedColumn
from rich.live import Live

from core.config import get_settings

if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

console = Console(legacy_windows=False)

CONSOLE_FORMAT = (
    "<green>{time:HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<level>{message}</level>"
)

FILE_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"


def init_logger() -> None:
    settings = get_settings()
    log_cfg = settings.logging
    log_dir = Path(settings.directories.logs)
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.remove()

    logger.add(
        sys.stderr,
        format=CONSOLE_FORMAT,
        level=log_cfg.level,
        colorize=True,
    )

    logger.add(
        str(log_dir / "extract_{time:YYYY-MM-DD}.log"),
        format=FILE_FORMAT,
        level=log_cfg.level,
        rotation=log_cfg.rotation,
        retention=log_cfg.retention,
        encoding="utf-8",
    )


def mask_password(pwd: str) -> str:
    if not pwd:
        return ""
    if len(pwd) <= 2:
        return "*" * len(pwd)
    return pwd[0] + "*" * (len(pwd) - 2) + pwd[-1]


def format_size(size_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    if minutes < 60:
        return f"{minutes}m {secs:.0f}s"
    hours = int(minutes // 60)
    mins = minutes % 60
    return f"{hours}h {mins}m {secs:.0f}s"


def show_banner() -> None:
    console.print()
    banner = Text()
    banner.append("  ╔═══════════════════════════════════════════╗\n", style="bold cyan")
    banner.append("  ║                                           ║\n", style="bold cyan")
    banner.append("  ║     ", style="bold cyan")
    banner.append("🎮 自动解压工具", style="bold white on cyan")
    banner.append("     ║\n", style="bold cyan")
    banner.append("  ║     ", style="bold cyan")
    banner.append("Auto Extract Tool v1.0", style="dim cyan")
    banner.append("  ║\n", style="bold cyan")
    banner.append("  ║                                           ║\n", style="bold cyan")
    banner.append("  ╚═══════════════════════════════════════════╝\n", style="bold cyan")
    console.print(banner)
    console.print()


def show_startup_info(settings) -> None:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="dim", width=18)
    table.add_column()

    table.add_row("📁 监控目录", f"[cyan]{settings.directories.watch}[/cyan]")
    table.add_row("📂 游戏保存目录", f"[cyan]{settings.directories.game_save}[/cyan]")
    table.add_row("🔑 密码本", f"[cyan]{len(__import__('core.password_manager', fromlist=['PasswordManager']).PasswordManager().get_passwords())} 个密码[/cyan]")

    sz = Path(settings.seven_zip.path).exists()
    table.add_row("🔧 7-Zip", "[green]✓ 可用[/green]" if sz else "[red]✗ 不可用[/red]")

    post = settings.post_process
    if post.enabled:
        table.add_row("⚙ 收尾功能", "[green]已启用[/green]")
        table.add_row("  ├ 移动游戏目录", "[green]开启[/green]" if post.move_game_dir else "[dim]关闭[/dim]")
        table.add_row("  └ 游戏识别", f"[green]开启[/green] (最小{post.game_detection.min_size_mb}MB)")

    panel = Panel(table, title="[bold]启动信息[/bold]", border_style="cyan", padding=(1, 2))
    console.print(panel)
    console.print()


def show_monitoring() -> None:
    console.print("[dim]⏳ 正在监控目录，等待新文件...[/dim]")


def ui_file_detected(file_name: str, is_temp: bool = False) -> None:
    if is_temp:
        console.print(f"  [dim]🔍 检测到临时文件: {file_name} (已跳过)[/dim]")
    else:
        console.print(f"  [blue]🔍 检测到新文件: {file_name}[/blue]")


def ui_waiting_download(file_name: str) -> None:
    console.print(f"  [yellow]⏳ 等待下载完成: {file_name}[/yellow]")


def ui_download_stable(file_name: str, size_mb: float) -> None:
    console.print(f"  [green]✓ 下载完成: {file_name} ({format_size(size_mb * 1024 * 1024)})[/green]")


def ui_split_detected(base_name: str, count: int) -> None:
    console.print(f"  [blue]📦 分卷自解压包: {base_name} (共{count}个文件)[/blue]")


def ui_split_integrity_ok() -> None:
    console.print(f"  [green]✓ 分卷完整性校验通过[/green]")


def ui_split_integrity_fail(msg: str) -> None:
    console.print(f"  [red]✗ 分卷不完整: {msg}[/red]")


def ui_extract_start(file_name: str, engine: str = "7-Zip") -> None:
    console.print(f"  [cyan]🔄 使用{engine}解压: {file_name}[/cyan]")


def ui_merge_progress(step: str, detail: str = "") -> None:
    msg = f"    [dim]├ {step}[/dim]"
    if detail:
        msg += f"  [dim]{detail}[/dim]"
    console.print(msg)


def ui_extract_progress(current: int, total: int, file_name: str = "") -> None:
    bar_len = 25
    if total > 0:
        filled = int(bar_len * current / total)
        bar = "█" * filled + "░" * (bar_len - filled)
        pct = current / total * 100
        msg = f"    [dim]├ 解压进度 [{bar}] {current}/{total} ({pct:.0f}%)[/dim]"
    else:
        msg = f"    [dim]├ 解压中... ({current} 个文件)[/dim]"
    if file_name:
        msg += f"  [dim]{file_name}[/dim]"
    console.print(msg)


def ui_password_try(attempt: int, total: int, masked_pwd: str) -> None:
    console.print(f"  [dim]🔑 尝试密码 ({attempt}/{total}): {masked_pwd}[/dim]")


def ui_password_success(masked_pwd: str) -> None:
    console.print(f"  [green]🔑 密码匹配成功: {masked_pwd}[/green]")


def ui_extract_success(file_name: str, detail: str = "", elapsed: float = 0) -> None:
    msg = f"  [bold green]🎉 解压成功: {file_name}[/bold green]"
    parts = []
    if detail:
        parts.append(detail)
    if elapsed > 0:
        parts.append(f"耗时 {format_duration(elapsed)}")
    if parts:
        msg += f"  [dim]{' | '.join(parts)}[/dim]"
    console.print(msg)


def ui_extract_fail(file_name: str, reason: str, elapsed: float = 0) -> None:
    console.print(f"  [bold red]❌ 解压失败: {file_name}[/bold red]")
    elapsed_str = f"  [dim]耗时 {format_duration(elapsed)}[/dim]" if elapsed > 0 else ""
    console.print(f"  [red]   原因: {reason}[/red]" + elapsed_str)


def ui_game_found(game_name: str, size_mb: float) -> None:
    console.print(f"  [blue]🎮 识别游戏: {game_name} ({format_size(size_mb * 1024 * 1024)})[/blue]")


def ui_game_moved(game_name: str, dest: str) -> None:
    console.print(f"  [bold green]📁 游戏已整理: {game_name}[/bold green]")
    console.print(f"    [dim]└ → {dest}[/dim]")


def ui_game_move_fail(game_name: str, reason: str) -> None:
    console.print(f"  [red]📁 移动失败: {game_name} | {reason}[/red]")


def ui_archive_done(file_name: str) -> None:
    console.print(f"  [dim]📦 已归档: {file_name}[/dim]")


def ui_scan_start(total: int) -> None:
    console.print()
    console.print(f"[bold cyan]📋 扫描发现 {total} 个压缩包[/bold cyan]")
    console.print()


def ui_scan_progress(current: int, total: int, file_name: str) -> None:
    console.print(f"  [cyan]({current}/{total})[/cyan] 处理: {file_name}")


def ui_scan_done(success: int, failed: int, elapsed: float = 0) -> None:
    console.print()
    msg = f"[bold]扫描完成[/bold] | "
    msg += f"[green]成功={success}[/green] | "
    msg += f"[red]失败={failed}[/red]"
    if elapsed > 0:
        msg += f"  [dim]总耗时 {format_duration(elapsed)}[/dim]"
    console.print(msg)
    console.print()


def ui_separator(title: str = "") -> None:
    if title:
        console.print(f"[dim]{'─' * 20} {title} {'─' * 20}[/dim]")
    else:
        console.print(f"[dim]{'─' * 50}[/dim]")


def ui_task_start(file_name: str, size_str: str = "") -> None:
    console.print()
    title = f"[bold]{file_name}[/bold]"
    if size_str:
        title += f"  [dim]({size_str})[/dim]"
    console.print(Panel(title, border_style="cyan", padding=(0, 2)))


def ui_task_done(file_name: str, success: bool, elapsed: float = 0) -> None:
    if success:
        msg = f"  [bold green]✅ 处理完成: {file_name}[/bold green]"
        if elapsed > 0:
            msg += f"  [dim]({format_duration(elapsed)})[/dim]"
        console.print(msg)
    else:
        console.print(f"  [bold red]❌ 处理失败: {file_name}[/bold red]")
    console.print()


def ui_task_skipped(file_name: str, reason: str = "") -> None:
    console.print()
    title = f"[bold]{file_name}[/bold]"
    console.print(Panel(title, border_style="yellow", padding=(0, 2)))
    console.print(f"  [bold yellow]⚠️  跳过: {file_name}[/bold yellow]")
    if reason:
        console.print(f"  [dim]{reason}[/dim]")
    console.print()


def ui_waiting_new_files() -> None:
    console.print("[dim]⏳ 监控中，等待新文件...[/dim]", end="\r")


def print_step(step: str, detail: str = "") -> None:
    msg = f"▶ {step}"
    if detail:
        msg += f" | {detail}"
    logger.info(msg)


def print_success(msg: str) -> None:
    logger.info(f"✅ {msg}")


def print_warning(msg: str) -> None:
    logger.warning(f"⚠ {msg}")


def print_error(msg: str) -> None:
    logger.error(f"❌ {msg}")


def print_progress(step: str, current: int, total: int, detail: str = "") -> None:
    bar_len = 30
    if total > 0:
        filled = int(bar_len * current / total)
        bar = "█" * filled + "░" * (bar_len - filled)
        pct = current / total * 100
        msg = f"[{bar}] {pct:5.1f}% | {step}"
    else:
        msg = f"{' ' * (bar_len + 10)} | {step}"

    if detail:
        msg += f" | {detail}"

    logger.info(msg)


def print_separator(title: str = "") -> None:
    if title:
        logger.info(f"{'=' * 20} {title} {'=' * 20}")
    else:
        logger.info("=" * 50)
