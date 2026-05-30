#!/usr/bin/env python3
"""Entry point: python scripts/migrate_game_paths.py [--apply] [--backup]"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.maintenance.migrate_paths import main

if __name__ == "__main__":
    raise SystemExit(main())
