from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.fdm_service import (
    _popen,
    add_download_task,
    open_fdm,
    resolve_fdm_exe,
)


def test_resolve_fdm_custom(tmp_path: Path) -> None:
    exe = tmp_path / "fdm.exe"
    exe.write_bytes(b"")
    assert resolve_fdm_exe(str(exe)) == exe.resolve()


def test_resolve_fdm_missing() -> None:
    with pytest.raises(FileNotFoundError):
        resolve_fdm_exe(str(Path("Z:/nonexistent/fdm.exe")))


def test_add_task_rejects_empty_url(tmp_path: Path) -> None:
    exe = tmp_path / "fdm.exe"
    exe.write_bytes(b"")
    with pytest.raises(ValueError, match="不能为空"):
        add_download_task("  ", custom_path=str(exe))


@pytest.mark.skipif(sys.platform != "win32", reason="Windows startup flags")
def test_popen_shows_gui_window(tmp_path: Path) -> None:
    exe = tmp_path / "fdm.exe"
    exe.write_bytes(b"")

    with patch("app.services.fdm_service.subprocess.Popen") as popen:
        open_fdm(custom_path=str(exe))

    kwargs = popen.call_args.kwargs
    startupinfo = kwargs["startupinfo"]
    assert startupinfo.wShowWindow == 1  # SW_SHOWNORMAL
    assert "creationflags" not in kwargs


@pytest.mark.skipif(sys.platform != "win32", reason="Windows startup flags")
def test_popen_can_hide_window(tmp_path: Path) -> None:
    exe = tmp_path / "fdm.exe"
    exe.write_bytes(b"")

    with patch("app.services.fdm_service.subprocess.Popen") as popen:
        _popen([str(exe)], show_window=False)

    kwargs = popen.call_args.kwargs
    startupinfo = kwargs["startupinfo"]
    assert startupinfo.wShowWindow == subprocess.SW_HIDE
    assert kwargs["creationflags"] == subprocess.CREATE_NO_WINDOW
