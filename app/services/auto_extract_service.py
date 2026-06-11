"""Bridge to integrations/自动化解压工具 — automated archive extraction."""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

from app.services.app_data_dir import get_app_data_dir
from app.services.paths import auto_extract_config_path as bundled_auto_extract_config_path
from app.services.paths import auto_extract_tool_dir

MIN_ARCHIVE_SIZE_MB = 200
MIN_ARCHIVE_SIZE_BYTES = MIN_ARCHIVE_SIZE_MB * 1024 * 1024

ProgressCallback = Callable[[dict], None]

_lock = threading.Lock()
_runtime_ready = False

_INTEGRATION_DEPS = (
    ("loguru", "loguru"),
    ("yaml", "pyyaml"),
    ("watchdog", "watchdog"),
    ("pyzipper", "pyzipper"),
    ("lz4", "lz4"),
    ("cryptography", "cryptography"),
    ("pydantic", "pydantic"),
    ("pydantic_settings", "pydantic-settings"),
    ("fastapi", "fastapi"),
    ("uvicorn", "uvicorn"),
)


@dataclass
class AutoExtractResult:
    success: bool
    file_name: str = ""
    extract_dir: str = ""
    used_password: str = ""
    error: str = ""
    archive_type: str = ""
    post_process: dict[str, Any] = field(default_factory=dict)


@dataclass
class AutoExtractScanResult:
    total: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0
    cancelled: bool = False


def is_auto_extract_available() -> bool:
    if auto_extract_tool_dir() is None:
        return False
    for _mod, _pip in _INTEGRATION_DEPS:
        try:
            __import__(_mod)
        except ImportError:
            return False
    seven_zip = auto_extract_tool_dir() / "bin" / "7za.exe"
    return seven_zip.is_file()


def auto_extract_missing_reason() -> str:
    root = auto_extract_tool_dir()
    if root is None:
        return "未找到 integrations/自动化解压工具，请确认仓库完整。"
    if not (root / "main.py").is_file():
        return "自动化解压工具目录不完整（缺少 main.py）。"
    if not (root / "bin" / "7za.exe").is_file():
        return "缺少 bin/7za.exe，请确认 7-Zip 组件已随工具一并提供。"
    missing: list[str] = []
    for _mod, pip_name in _INTEGRATION_DEPS:
        try:
            __import__(_mod)
        except ImportError:
            missing.append(pip_name)
    if missing:
        return "缺少依赖：" + "、".join(missing) + "。请执行：pip install " + " ".join(missing)
    return ""


def _runtime_config_dir() -> Path:
    return get_app_data_dir() / "auto_extract" / "config"


def _runtime_config_path() -> Path:
    return _runtime_config_dir() / "config.yaml"


def _runtime_passwords_path() -> Path:
    return _runtime_config_dir() / "passwords.json"


def _bundled_seven_zip_path() -> Path | None:
    root = auto_extract_tool_dir()
    if root is None:
        return None
    p = root / "bin" / "7za.exe"
    return p.resolve() if p.is_file() else None


def _load_template_config() -> dict[str, Any]:
    template = bundled_auto_extract_config_path()
    if template is None or not template.is_file():
        return {}
    with open(template, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _default_runtime_directories() -> dict[str, str]:
    dirs = _default_directories()
    dirs.setdefault("logs", str(get_app_data_dir() / "auto_extract" / "logs"))
    dirs.setdefault("upload", str(Path(dirs["watch"]) / "_upload"))
    return dirs


def _sanitize_runtime_config(data: dict[str, Any], *, preserve_directories: bool) -> dict[str, Any]:
    cleaned = dict(data)
    defaults = _default_runtime_directories()
    current_dirs = dict(cleaned.get("directories") or {}) if preserve_directories else {}
    cleaned["directories"] = {
        key: str(current_dirs.get(key) or value)
        for key, value in defaults.items()
    }

    seven_zip = dict(cleaned.get("seven_zip") or {})
    bundled_7za = _bundled_seven_zip_path()
    if bundled_7za is not None:
        seven_zip["path"] = str(bundled_7za)
    cleaned["seven_zip"] = seven_zip

    passwords = dict(cleaned.get("passwords") or {})
    passwords["file"] = str(_runtime_passwords_path())
    passwords.setdefault("encrypt", False)
    passwords.setdefault("encryption_key", "")
    cleaned["passwords"] = passwords
    return cleaned


def _ensure_runtime_files() -> Path:
    cfg_path = _runtime_config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)

    if cfg_path.is_file():
        with open(cfg_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        data = _sanitize_runtime_config(data, preserve_directories=True)
    else:
        data = _sanitize_runtime_config(_load_template_config(), preserve_directories=False)

    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

    pwd_path = _runtime_passwords_path()
    if not pwd_path.is_file():
        with open(pwd_path, "w", encoding="utf-8") as f:
            f.write('{\n  "passwords": [],\n  "success_map": {},\n  "success_counts": {}\n}\n')
    return cfg_path


def config_yaml_path() -> Path | None:
    if auto_extract_tool_dir() is None:
        return None
    return _ensure_runtime_files()


def _default_directories() -> dict[str, str]:
    """Provide reasonable default directories based on system."""
    import os
    from pathlib import Path
    
    home = Path.home()
    downloads = home / "Downloads"
    default_watch = str(downloads / "galgame")
    default_target = str(downloads / "galgame" / "_extract")
    default_archive = str(downloads / "galgame" / "_archive")
    default_failed = str(downloads / "galgame" / "_failed")
    default_temp = str(downloads / "galgame" / "_temp")
    default_game_save = str(home / "Documents" / "galgame")
    
    return {
        "watch": default_watch,
        "target": default_target,
        "archive": default_archive,
        "failed": default_failed,
        "temp": default_temp,
        "game_save": default_game_save,
    }


def read_directory_config() -> dict[str, str]:
    path = config_yaml_path()
    if path is None or not path.is_file():
        return _default_directories()
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    dirs = data.get("directories") or {}
    
    defaults = _default_runtime_directories()
    keys = ("watch", "target", "archive", "failed", "temp", "game_save")
    result = {}
    for k in keys:
        result[k] = str(dirs.get(k, defaults.get(k, "")))
    return result


def write_directory_config(updates: dict[str, str]) -> None:
    path = config_yaml_path()
    if path is None:
        raise FileNotFoundError("config.yaml not found")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    directories = dict(data.get("directories") or {})
    for key, value in updates.items():
        if value.strip():
            directories[key] = value.strip()
    data["directories"] = directories
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    reset_runtime()


def reset_runtime() -> None:
    global _runtime_ready
    with _lock:
        _runtime_ready = False
    root = auto_extract_tool_dir()
    if root is None:
        return
    root_str = str(root.resolve())
    if root_str in sys.path:
        try:
            import core.config as tool_config  # type: ignore[import-not-found]

            tool_config._settings = None  # noqa: SLF001
        except ImportError:
            pass


def _tool_root_str() -> str:
    root = auto_extract_tool_dir()
    if root is None:
        raise FileNotFoundError("auto extract tool not found")
    return str(root.resolve())


def _ensure_runtime() -> None:
    global _runtime_ready
    if not is_auto_extract_available():
        raise RuntimeError(auto_extract_missing_reason())
    with _lock:
        if _runtime_ready:
            return
        root_str = _tool_root_str()
        if root_str not in sys.path:
            sys.path.insert(0, root_str)
        from core.config import init_settings  # type: ignore[import-not-found]
        from core.extractor import Extractor  # type: ignore[import-not-found]
        from core.file_manager import FileManager  # type: ignore[import-not-found]
        from core.password_manager import PasswordManager  # type: ignore[import-not-found]
        from core.watcher import WatcherService  # type: ignore[import-not-found]

        cfg = config_yaml_path()
        init_settings(cfg if cfg else None)
        password_manager = PasswordManager()
        extractor = Extractor(password_manager)
        file_manager = FileManager()
        watcher = WatcherService(extractor, file_manager)
        globals()["_extractor"] = extractor
        globals()["_file_manager"] = file_manager
        globals()["_watcher"] = watcher
        _runtime_ready = True


def _result_from_tool(result: Any, post_process: dict | None) -> AutoExtractResult:
    return AutoExtractResult(
        success=bool(result.success),
        file_name=str(result.file_name or ""),
        extract_dir=str(result.extract_dir or ""),
        used_password=str(result.used_password or ""),
        error=str(result.error or ""),
        archive_type=str(result.archive_type or ""),
        post_process=dict(post_process or {}),
    )


async def _extract_async(
    file_path: str,
    *,
    password: str | None,
    target_dir: str | None,
) -> AutoExtractResult:
    _ensure_runtime()
    extractor = globals()["_extractor"]
    file_manager = globals()["_file_manager"]
    custom_password = password if password else None
    output_dir = target_dir if target_dir else None

    # Generate extraction report
    report_gen = None
    try:
        from core.report_generator import ExtractReportGenerator  # type: ignore[import-not-found]
        from core.config import get_settings  # type: ignore[import-not-found]
        settings = get_settings()
        report_gen = ExtractReportGenerator(settings)
        cfg = read_directory_config()
        report_gen.start(
            monitor_dir=str(Path(file_path).parent),
            game_save_dir=cfg.get("game_save", ""),
        )
    except Exception:
        pass

    import time
    start_time = time.monotonic()
    result = await extractor.extract(
        file_path=file_path,
        custom_password=custom_password,
        output_dir=output_dir,
    )
    elapsed = time.monotonic() - start_time
    post_result, _ = file_manager.handle_extract_result(result)

    # Record result in report
    if report_gen is not None:
        try:
            final_path = ""
            is_cover = False
            if post_result:
                final_path = post_result.get("final_path", "")
                is_cover = bool(post_result.get("cover_moved", False))
            report_gen.add_result(result, final_path=final_path, is_cover=is_cover, elapsed=elapsed)
            report_gen.end()
            report_path = report_gen.generate_report()
            if report_path:
                logging.getLogger(__name__).info("Extraction report generated: %s", report_path)
        except Exception:
            pass

    return _result_from_tool(result, post_result)


def _collect_archive_entries(watch_dir: Path) -> tuple[list[tuple[Path, str]], int]:
    """Enumerate archive entry files under watch_dir.

    Returns (entries, skipped_count). Mirrors the bundled watcher's grouping/size
    rules but without report generation or the print_warning bug.
    """
    from core.archive_detector import (  # type: ignore[import-not-found]
        detect_7z_split_volume_set,
        detect_archive_type,
        detect_rar_multipart_volume_set,
        detect_split_volume_set,
        is_7z_split_part,
        is_download_temp_file,
        is_rar_multipart_part,
    )
    from core.config import get_settings  # type: ignore[import-not-found]

    settings = get_settings()
    skip_dirs = set()
    for key in ("archive", "temp", "target", "failed"):
        try:
            skip_dirs.add(Path(getattr(settings.directories, key)).resolve())
        except (TypeError, ValueError):
            pass

    entries: list[tuple[Path, str]] = []
    skipped = 0
    processed_bases: set[str] = set()
    processed_files: set[str] = set()

    all_items = []
    for item in watch_dir.rglob("*"):
        if not item.is_file():
            continue
        if any(item.is_relative_to(d) for d in skip_dirs if d.exists()):
            continue
        all_items.append(item)
    all_items.sort(key=lambda x: x.name)

    for item in all_items:
        if str(item) in processed_files:
            continue
        if is_download_temp_file(item):
            continue
        atype = detect_archive_type(item)
        if atype is None:
            continue

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
            except OSError:
                continue
            if total_size < MIN_ARCHIVE_SIZE_BYTES:
                skipped += 1
            else:
                processed_bases.add(base)
                for f in split_7z["all_files"]:
                    processed_files.add(str(f))
                entries.append((Path(split_7z["extract_entry"]), atype))
            continue

        # ---- RAR multi-part (part1.rar / part2.rar / …) ----
        rar_multipart = detect_rar_multipart_volume_set(item)
        if not rar_multipart:
            rar_part = is_rar_multipart_part(item)
            if rar_part:
                rar_multipart = detect_rar_multipart_volume_set(rar_part["first_part"])
        if rar_multipart:
            base = rar_multipart["base_name"]
            if base in processed_bases:
                continue
            try:
                total_size = sum(
                    Path(f).stat().st_size
                    for f in rar_multipart["all_files"]
                    if Path(f).exists()
                )
            except OSError:
                continue
            if total_size < MIN_ARCHIVE_SIZE_BYTES:
                skipped += 1
            else:
                processed_bases.add(base)
                for f in rar_multipart["all_files"]:
                    processed_files.add(str(f))
                entries.append((Path(rar_multipart["extract_entry"]), "rar"))
            continue

        split_info = detect_split_volume_set(item)
        if split_info:
            base = split_info["base_name"]
            if base in processed_bases:
                continue
            try:
                total_size = sum(
                    Path(f).stat().st_size
                    for f in split_info["all_files"]
                    if Path(f).exists()
                )
            except OSError:
                total_size = 0
            if total_size < MIN_ARCHIVE_SIZE_BYTES:
                skipped += 1
            else:
                processed_bases.add(base)
                for f in split_info["all_files"]:
                    processed_files.add(str(f))
                entries.append((item, atype))
            continue

        try:
            if item.stat().st_size < MIN_ARCHIVE_SIZE_BYTES:
                skipped += 1
                continue
        except OSError:
            continue
        entries.append((item, atype))

    return entries, skipped


async def _scan_async(
    progress: ProgressCallback | None,
    should_cancel: Callable[[], bool] | None,
) -> AutoExtractScanResult:
    _ensure_runtime()
    extractor = globals()["_extractor"]
    file_manager = globals()["_file_manager"]

    def emit(payload: dict) -> None:
        if progress is not None:
            progress(payload)

    def cancelled() -> bool:
        return bool(should_cancel and should_cancel())

    cfg = read_directory_config()
    watch_dir = Path(cfg.get("watch", "")).resolve()
    if not cfg.get("watch") or not watch_dir.is_dir():
        emit({"phase": "error", "message": f"监控目录不存在：{watch_dir}"})
        return AutoExtractScanResult()

    emit({"phase": "collecting", "message": f"正在枚举压缩包：{watch_dir}"})
    entries, skipped = _collect_archive_entries(watch_dir)
    total = len(entries)
    emit({"phase": "collected", "total": total, "skipped": skipped})

    result = AutoExtractScanResult(skipped=skipped)
    if total == 0:
        emit({"phase": "empty", "message": "未发现满足条件的压缩包（≥200MB）"})
        return result

    # Initialize report generator for batch scan
    report_gen = None
    try:
        from core.report_generator import ExtractReportGenerator  # type: ignore[import-not-found]
        from core.config import get_settings  # type: ignore[import-not-found]
        settings = get_settings()
        report_gen = ExtractReportGenerator(settings)
        report_gen.start(
            monitor_dir=str(watch_dir),
            game_save_dir=cfg.get("game_save", ""),
        )
        if skipped > 0:
            report_gen.record_skipped(skipped)
    except Exception:
        pass

    import time

    for index, (item, _atype) in enumerate(entries, start=1):
        if cancelled():
            result.cancelled = True
            emit({"phase": "cancelled", "index": index - 1, "total": total})
            break
        emit({
            "phase": "extracting",
            "index": index,
            "total": total,
            "name": item.name,
        })
        result.total += 1
        start_time = time.monotonic()
        try:
            extract_result = await extractor.extract(str(item))
            elapsed = time.monotonic() - start_time
            post_result, _moved = file_manager.handle_extract_result(extract_result)

            # Record in report
            if report_gen is not None:
                try:
                    final_path = ""
                    is_cover = False
                    if post_result:
                        final_path = post_result.get("final_path", "")
                        is_cover = bool(post_result.get("cover_moved", False))
                    report_gen.add_result(
                        extract_result,
                        final_path=final_path,
                        is_cover=is_cover,
                        elapsed=elapsed,
                    )
                except Exception:
                    pass

            if extract_result.success:
                result.success += 1
                msg_parts = [str(extract_result.extract_dir or "")]
                expanded = post_result.get("iso_expanded") if post_result else None
                if expanded:
                    msg_parts.append(f"已展开光盘: {', '.join(expanded)}")
                installer = post_result.get("installer_exe") if post_result else None
                if installer:
                    msg_parts.append(f"安装程序: {Path(installer).name}")
                iso_errors = post_result.get("iso_errors") if post_result else None
                if iso_errors:
                    msg_parts.append(
                        "光盘展开失败: "
                        + "; ".join(f"{e.get('iso', '?')}" for e in iso_errors)
                    )
                needs_guide = bool(expanded)
                emit({
                    "phase": "file_done",
                    "index": index,
                    "total": total,
                    "name": item.name,
                    "success": True,
                    "message": " | ".join(p for p in msg_parts if p),
                    "extract_dir": str(extract_result.extract_dir or ""),
                    "installer_exe": installer or "",
                    "iso_expanded": list(expanded) if expanded else [],
                    "needs_install_guide": needs_guide,
                    "archive_file_name": item.name,
                    "game_save_dir": read_directory_config().get("game_save", ""),
                    "post_process": dict(post_result or {}),
                })
            else:
                result.failed += 1
                emit({
                    "phase": "file_done",
                    "index": index,
                    "total": total,
                    "name": item.name,
                    "success": False,
                    "message": str(extract_result.error or "未知错误"),
                })
        except Exception as exc:
            result.failed += 1
            emit({
                "phase": "file_done",
                "index": index,
                "total": total,
                "name": item.name,
                "success": False,
                "message": str(exc),
            })

    # Generate report
    if report_gen is not None:
        try:
            report_gen.end()
            report_path = report_gen.generate_report()
            if report_path:
                logging.getLogger(__name__).info("Scan extraction report generated: %s", report_path)
        except Exception:
            pass

    emit({"phase": "finished", "total": total})
    return result


def extract_archive(
    file_path: str | Path,
    *,
    password: str = "",
    target_dir: str = "",
) -> AutoExtractResult:
    path = Path(file_path).resolve()
    if not path.is_file():
        return AutoExtractResult(success=False, error="文件不存在")
    return asyncio.run(
        _extract_async(
            str(path),
            password=password.strip() or None,
            target_dir=target_dir.strip() or None,
        )
    )


def scan_watch_directory(
    *,
    progress: ProgressCallback | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> AutoExtractScanResult:
    return asyncio.run(_scan_async(progress, should_cancel))


def report_output_dir() -> Path | None:
    root = auto_extract_tool_dir()
    if root is None:
        return None
    d = root / "extract_report"
    return d if d.is_dir() else d


# ---------------------------------------------------------------------------
# 密码管理桥接
# ---------------------------------------------------------------------------

def get_password_manager():
    """返回 PasswordManager 单例，供 UI 调用。"""
    _ensure_runtime()
    return _extractor.password_manager  # type: ignore[attr-defined]


def get_passwords_with_stats() -> list[dict]:
    """获取所有密码及其统计信息。"""
    pm = get_password_manager()
    return pm.get_all_with_stats()


def add_password(password: str) -> tuple[bool, str]:
    """添加密码。"""
    pm = get_password_manager()
    return pm.add_password(password)


def remove_password(password: str) -> tuple[bool, str]:
    """删除密码。"""
    pm = get_password_manager()
    return pm.remove_password(password)


def set_password_pinned(password: str, pinned: bool) -> tuple[bool, str]:
    """置顶/取消置顶密码。"""
    pm = get_password_manager()
    return pm.set_pinned(password, pinned)


def move_password(password: str, direction: int) -> tuple[bool, str]:
    """上移/下移密码。direction: -1=上移, +1=下移。"""
    pm = get_password_manager()
    return pm.move_password(password, direction)


def clear_password_stats() -> tuple[bool, str]:
    """清空密码使用统计。"""
    pm = get_password_manager()
    return pm.clear_stats()
