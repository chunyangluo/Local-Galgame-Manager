"""Bridge to integrations/hbe-decryptor (Hexo Blog Encrypt offline HTML decrypt)."""

from __future__ import annotations

import importlib.util
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Callable

from app.services.paths import hbe_decryptor_dir

logger = logging.getLogger(__name__)

_single_mod: ModuleType | None = None
_batch_mod: ModuleType | None = None


class HbeDependencyError(RuntimeError):
    """cryptography or integration files missing."""


@dataclass
class HbeSingleResult:
    success: bool
    password_used: str | None = None
    plaintext_path: Path | None = None
    report_path: Path | None = None
    message: str = ""


@dataclass
class HbeBatchResult:
    ok_count: int
    fail_count: int
    output_dir: Path
    summary_csv: Path | None = None
    summary_json: Path | None = None
    message: str = ""


def is_hbe_available() -> bool:
    if hbe_decryptor_dir() is None:
        return False
    try:
        import cryptography  # noqa: F401
    except ImportError:
        return False
    return True


def hbe_missing_reason() -> str:
    if hbe_decryptor_dir() is None:
        return "未找到 integrations/hbe-decryptor，请确认仓库完整。"
    try:
        import cryptography  # noqa: F401
    except ImportError:
        return "缺少依赖 cryptography，请执行：pip install cryptography"
    return ""


def default_ciphertext_dir() -> Path | None:
    d = hbe_decryptor_dir()
    return d / "ciphertext" if d else None


def default_plaintext_dir() -> Path | None:
    d = hbe_decryptor_dir()
    return d / "output" / "plaintext" if d else None


def default_output_root() -> Path | None:
    d = hbe_decryptor_dir()
    return d / "output" if d else None


def password_dict_path() -> Path | None:
    d = hbe_decryptor_dir()
    return d / "password_dict.txt" if d else None


def _import_module(filename: str) -> ModuleType:
    root = hbe_decryptor_dir()
    if root is None:
        raise FileNotFoundError("hbe-decryptor not found")
    file_path = root / filename
    if not file_path.is_file():
        raise FileNotFoundError(f"missing {file_path}")
    root_str = str(root.resolve())
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    module_name = f"hbe_{file_path.stem}_{abs(hash(root_str))}"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {file_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _single_module() -> ModuleType:
    global _single_mod
    if _single_mod is None:
        _single_mod = _import_module("decry-chunyang.py")
    return _single_mod


def _batch_module() -> ModuleType:
    global _batch_mod
    if _batch_mod is None:
        _batch_mod = _import_module("batch_decrypt_known.py")
    return _batch_mod


def _newest_file(directory: Path, pattern: str) -> Path | None:
    if not directory.is_dir():
        return None
    files = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def decrypt_single_known(
    cipher_path: str | Path,
    password: str,
    *,
    log: Callable[[str], None] | None = None,
) -> HbeSingleResult:
    if not is_hbe_available():
        return HbeSingleResult(False, message=hbe_missing_reason())
    path = str(Path(cipher_path).resolve())
    mod = _single_module()
    mod.failed_attempts = []
    if log:
        log(f"使用密码解密: {path}")
    ok = mod.attempt_and_report(path, password, generate_report=True)
    out_dir = Path(mod.OUTPUT_DIR)
    plain = _newest_file(Path(mod.PLAINTEXT_DIR), "plaintext_*.html")
    report = _newest_file(out_dir, "decrypt_report_*.txt")
    if ok:
        return HbeSingleResult(
            True,
            password_used=password,
            plaintext_path=plain,
            report_path=report,
            message="解密成功",
        )
    return HbeSingleResult(
        False,
        password_used=password,
        report_path=report,
        message="解密失败，请检查密码或密文格式",
    )


def decrypt_single_auto(
    cipher_path: str | Path,
    *,
    log: Callable[[str], None] | None = None,
) -> HbeSingleResult:
    if not is_hbe_available():
        return HbeSingleResult(False, message=hbe_missing_reason())
    path = str(Path(cipher_path).resolve())
    mod = _single_module()
    import time

    mod.failed_attempts = []
    auto_start = time.time()

    dict_pwds = mod.load_password_dict()
    if dict_pwds:
        if log:
            log(f"尝试密码字典（{len(dict_pwds)} 条）…")
        for pw in dict_pwds:
            if mod.attempt_and_report(path, pw, generate_report=False):
                plain = _newest_file(Path(mod.PLAINTEXT_DIR), "plaintext_*.html")
                report = _newest_file(Path(mod.OUTPUT_DIR), "decrypt_report_*.txt")
                return HbeSingleResult(
                    True,
                    password_used=pw,
                    plaintext_path=plain,
                    report_path=report,
                    message="AUTO：字典命中",
                )
    else:
        if log:
            log("密码字典为空，跳过。")

    cand_pwds = mod.read_candidates()
    if cand_pwds:
        if log:
            log(f"尝试 candidates.txt（{len(cand_pwds)} 条）…")
        for pw in cand_pwds:
            if mod.attempt_and_report(path, pw, generate_report=False):
                plain = _newest_file(Path(mod.PLAINTEXT_DIR), "plaintext_*.html")
                report = _newest_file(Path(mod.OUTPUT_DIR), "decrypt_report_*.txt")
                return HbeSingleResult(
                    True,
                    password_used=pw,
                    plaintext_path=plain,
                    report_path=report,
                    message="AUTO：候选密码命中",
                )
    elif log:
        log("无 candidates.txt，跳过。")

    if log:
        log("开始 4～6 位纯数字穷举（可能耗时较长）…")
    if mod.brute_force_numeric(path):
        plain = _newest_file(Path(mod.PLAINTEXT_DIR), "plaintext_*.html")
        report = _newest_file(Path(mod.OUTPUT_DIR), "decrypt_report_*.txt")
        pw = plain.name if plain else "numeric"
        return HbeSingleResult(
            True,
            password_used="(numeric brute-force)",
            plaintext_path=plain,
            report_path=report,
            message="AUTO：数字穷举成功",
        )

    auto_end = time.time()
    if mod.failed_attempts:
        report_path = mod.write_summary_failed_report(
            path, auto_start, auto_end, str(mod.OUTPUT_DIR)
        )
        return HbeSingleResult(
            False,
            report_path=Path(report_path),
            message="AUTO：全部尝试失败",
        )
    return HbeSingleResult(False, message="AUTO：全部尝试失败")


def batch_decrypt_known(
    password: str,
    ciphertext_dir: str | Path,
    output_dir: str | Path,
    *,
    log: Callable[[str], None] | None = None,
) -> HbeBatchResult:
    if not is_hbe_available():
        return HbeBatchResult(0, 0, Path("."), message=hbe_missing_reason())
    ct = Path(ciphertext_dir).resolve()
    out = Path(output_dir).resolve()
    if log:
        log(f"批量解密: {ct} → {out}")
    mod = _batch_module()
    ok_count, fail_count = mod.batch_decrypt(password, ct, out)
    output_root = out.parent
    csv_p = _newest_file(output_root, "decrypt_summary_*.csv")
    json_p = _newest_file(output_root, "decrypt_summary_*.json")
    msg = f"完成：成功 {ok_count}，失败 {fail_count}"
    if log:
        log(msg)
    return HbeBatchResult(
        ok_count=ok_count,
        fail_count=fail_count,
        output_dir=out,
        summary_csv=csv_p,
        summary_json=json_p,
        message=msg,
    )
