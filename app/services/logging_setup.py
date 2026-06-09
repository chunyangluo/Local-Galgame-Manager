"""Central logging configuration for Local Galgame Manager.

Use standard library logging in all modules::

    import logging
    log = logging.getLogger(__name__)

Call :func:`setup_logging` once at process entry (``app.main`` / ``app.cli``).

Environment:

* ``LGM_LOG_LEVEL`` — ``DEBUG``, ``INFO``, ``WARNING``, ``ERROR`` (default: ``INFO``).
* ``LGM_LOG_FILE`` — ``0`` / ``false`` / ``no`` to disable the rotating file under the data directory.
* ``LGM_LOG_CONSOLE`` — ``0`` / ``false`` / ``no`` to disable stderr output (file-only).

Log file: ``<data_dir>/logs/app.log`` (with rotated backups ``app.log.1``, …).
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_ENV_LEVEL = "LGM_LOG_LEVEL"
_ENV_FILE = "LGM_LOG_FILE"
_ENV_CONSOLE = "LGM_LOG_CONSOLE"

_LOG_FORMAT = "%(asctime)s | %(levelname)-5s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_DEFAULT_MAX_BYTES = 2 * 1024 * 1024
_DEFAULT_BACKUP_COUNT = 5

_configured: bool = False
_log_file: Path | None = None

# Global callback list for bridging standard logging to LogWindow
_log_bridge_callbacks: list = []


def add_log_bridge(callback) -> None:
    """Register a callback to receive all standard logging messages.

    The callback signature is: callback(level_name: str, message: str, timestamp: float)
    This bridges standard Python logging to the GUI LogWindow.
    """
    if callback not in _log_bridge_callbacks:
        _log_bridge_callbacks.append(callback)


def remove_log_bridge(callback) -> None:
    """Remove a previously registered log bridge callback."""
    if callback in _log_bridge_callbacks:
        _log_bridge_callbacks.remove(callback)


class _BridgeHandler(logging.Handler):
    """Custom logging handler that forwards all log records to bridge callbacks."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            level_name = record.levelname
            import time
            ts = getattr(record, 'created', time.time())
            for cb in list(_log_bridge_callbacks):
                try:
                    cb(level_name, msg, ts)
                except Exception:
                    pass
        except Exception:
            pass


def log_file_path(data_dir: Path) -> Path:
    """Path to the primary rotating application log (may not exist yet)."""
    return data_dir / "logs" / "app.log"


def _parse_bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off")


def _parse_level(value: str | int | None) -> int:
    if value is None:
        return logging.INFO
    if isinstance(value, int):
        return value
    key = str(value).strip().upper()
    mapping = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "WARN": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    return mapping.get(key, logging.INFO)


def _quiet_noisy_libraries() -> None:
    for name in ("urllib3", "urllib3.connectionpool"):
        logging.getLogger(name).setLevel(logging.WARNING)


def setup_logging(
    *,
    data_dir: Path | None = None,
    level: str | int | None = None,
    console: bool | None = None,
    file: bool | None = None,
    force: bool = False,
) -> Path | None:
    """Configure the root logger for the application.

    Safe to call twice; the second call is a no-op unless ``force`` is True.

    :param data_dir: Application data directory; required for file logging.
    :param level: Override log level (else ``LGM_LOG_LEVEL`` or INFO).
    :param console: If None, honor ``LGM_LOG_CONSOLE`` (default True).
    :param file: If None, honor ``LGM_LOG_FILE`` (default True when ``data_dir`` is set).
    :param force: Remove handlers added by a previous ``setup_logging`` and reconfigure.
    :return: Path to the rotating log file if file logging is enabled, else None.
    """
    global _configured, _log_file

    if _configured and not force:
        return _log_file

    if force:
        root = logging.getLogger()
        for h in list(root.handlers):
            if getattr(h, "_lgm_managed", False):
                root.removeHandler(h)
                h.close()
        _configured = False
        _log_file = None

    env_level = os.environ.get(_ENV_LEVEL)
    resolved_level = _parse_level(level if level is not None else env_level)

    use_console = _parse_bool_env(_ENV_CONSOLE, True) if console is None else console
    use_file_default = data_dir is not None and _parse_bool_env(_ENV_FILE, True)
    use_file = use_file_default if file is None else file

    root = logging.getLogger()
    root.setLevel(resolved_level)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    if use_console:
        ch = logging.StreamHandler(sys.stderr)
        ch.setLevel(resolved_level)
        ch.setFormatter(formatter)
        ch._lgm_managed = True  # type: ignore[attr-defined]
        root.addHandler(ch)

    log_path: Path | None = None
    if use_file and data_dir is not None:
        logs_dir = data_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_file_path(data_dir)
        fh = RotatingFileHandler(
            log_path,
            maxBytes=_DEFAULT_MAX_BYTES,
            backupCount=_DEFAULT_BACKUP_COUNT,
            encoding="utf-8",
            delay=True,
        )
        fh.setLevel(resolved_level)
        fh.setFormatter(formatter)
        fh._lgm_managed = True  # type: ignore[attr-defined]
        root.addHandler(fh)
        _log_file = log_path
    else:
        _log_file = None

    _quiet_noisy_libraries()

    # Bridge handler: forwards all standard logging to LogWindow via callbacks
    bridge = _BridgeHandler()
    bridge.setLevel(resolved_level)
    bridge.setFormatter(formatter)
    bridge._lgm_managed = True  # type: ignore[attr-defined]
    root.addHandler(bridge)
    _configured = True

    logging.getLogger(__name__).debug(
        "Logging initialized level=%s console=%s file=%s path=%s",
        logging.getLevelName(resolved_level),
        use_console,
        use_file,
        str(log_path) if log_path else None,
    )
    return log_path


def shutdown_logging() -> None:
    """Flush and close managed handlers (e.g. before exit in tests)."""
    global _configured, _log_file
    root = logging.getLogger()
    for h in list(root.handlers):
        if getattr(h, "_lgm_managed", False):
            root.removeHandler(h)
            h.close()
    _configured = False
    _log_file = None
    logging.shutdown()
