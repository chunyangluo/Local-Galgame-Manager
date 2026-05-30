"""
本模块目录为工具根路径。复制整个 hbe-decryptor 文件夹即可独立使用，不依赖上级仓库。
"""
from pathlib import Path
from typing import Optional
import os

ROOT = Path(__file__).resolve().parent
CIPHERTEXT_DIR = ROOT / "ciphertext"
OUTPUT_DIR = ROOT / "output"
PLAINTEXT_DIR = OUTPUT_DIR / "plaintext"
DICT_PATH = ROOT / "password_dict.txt"
CANDIDATES_PATH = ROOT / "candidates.txt"
DEFAULT_BACKUP_DIR = ROOT / "backup"


def backup_enabled() -> bool:
    v = os.environ.get("HBE_BACKUP", "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def backup_target_dir() -> Optional[Path]:
    """未启用备份时返回 None；否则为环境变量或 ./backup。"""
    if not backup_enabled():
        return None
    custom = os.environ.get("HBE_BACKUP_DIR", "").strip()
    if custom:
        return Path(custom).expanduser().resolve()
    return DEFAULT_BACKUP_DIR
