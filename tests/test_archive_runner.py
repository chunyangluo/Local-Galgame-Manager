from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_TOOL = _ROOT / "integrations" / "自动化解压工具"
if str(_TOOL) not in sys.path:
    sys.path.insert(0, str(_TOOL))

from core.archive_runner import (  # type: ignore[import-not-found]
    discover_extract_engines,
    path_needs_literal_switch,
)


def test_path_needs_literal_switch() -> None:
    assert path_needs_literal_switch(r"D:\a\[090319]\b.rar") is True
    assert path_needs_literal_switch(r"D:\a\plain.rar") is False


def test_discover_extract_engines_includes_unrar_on_windows() -> None:
    import os

    if os.name != "nt":
        return
    engines = discover_extract_engines(
        str(_TOOL / "bin" / "7za.exe"),
        r"D:\x\test.rar",
    )
    labels = [label for _, label in engines]
    assert "7za.exe" in labels or any("7za" in l for l in labels)
    has_rar_fallback = any("UnRAR" in l or "7z" in l for l in labels)
    assert has_rar_fallback
