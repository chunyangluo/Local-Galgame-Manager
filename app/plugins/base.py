from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable, Any


@dataclass
class PluginContext:
    data_dir: str


@runtime_checkable
class LocalGameManagerPlugin(Protocol):
    name: str

    def transform_scan_results(
        self, *, root: str, results: list[Any], context: PluginContext
    ) -> list[Any]:
        """
        Allow plugin to post-process scanner results.
        Implementations should return a NEW list.
        """
        ...

