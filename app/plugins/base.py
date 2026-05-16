from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.core.scanner import ScanResult


@dataclass
class PluginContext:
    data_dir: str


@runtime_checkable
class LocalGameManagerPlugin(Protocol):
    name: str

    def transform_scan_results(
        self, *, root: str, results: list[ScanResult], context: PluginContext
    ) -> list[ScanResult]:
        """
        Allow plugin to post-process scanner results.
        Implementations should return a NEW list.
        """
        ...
