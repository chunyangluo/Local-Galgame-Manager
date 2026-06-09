from __future__ import annotations

from pathlib import Path

import pytest

from app.services.fdm_service import (
    add_download_task,
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
