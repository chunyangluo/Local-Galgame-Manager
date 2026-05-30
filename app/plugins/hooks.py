"""Registered plugin hook identifiers."""

from __future__ import annotations

# Scan pipeline
HOOK_SCAN_TRANSFORM = "scan_transform"
HOOK_SCAN_FILTER = "scan_filter"

# Launch pipeline
HOOK_LAUNCH_MODIFY = "launch_modify"

# Library lifecycle
HOOK_ON_LOAD = "on_load"
HOOK_ON_UNLOAD = "on_unload"

ALL_HOOKS: tuple[str, ...] = (
    HOOK_SCAN_TRANSFORM,
    HOOK_SCAN_FILTER,
    HOOK_LAUNCH_MODIFY,
    HOOK_ON_LOAD,
    HOOK_ON_UNLOAD,
)
