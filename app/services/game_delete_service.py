"""Remove a game from the library DB and optionally its install folder on disk."""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from app.data.database import Database

logger = logging.getLogger(__name__)

UI_PREF_SKIP_DELETE_CONFIRM = "skip_delete_game_confirm"

_MIN_INSTALL_PATH_PARTS = 3  # e.g. D:/Games/Title on Windows


@dataclass(frozen=True)
class DeleteGameDecision:
    """User choices for a delete operation."""

    delete_install_folder: bool = False


def get_skip_delete_game_confirm(db: Database) -> bool:
    return bool(db.get_ui_preferences().get(UI_PREF_SKIP_DELETE_CONFIRM))


def set_skip_delete_game_confirm(db: Database, skip: bool) -> None:
    prefs = dict(db.get_ui_preferences())
    if skip:
        prefs[UI_PREF_SKIP_DELETE_CONFIRM] = True
    else:
        prefs.pop(UI_PREF_SKIP_DELETE_CONFIRM, None)
    db.set_ui_preferences(prefs)


def confirm_delete_game(
    parent,
    db: Database,
    game_name: str,
    *,
    install_dir: str = "",
    fallback_delete_install: bool = False,
) -> DeleteGameDecision | None:
    """
    Ask for delete confirmation when required.

    Returns None if cancelled, otherwise the user's choices.
    When confirmation is skipped, ``fallback_delete_install`` applies (e.g. data manager toolbar).
    """
    install_path = Path(install_dir) if install_dir else None
    can_delete_install = bool(install_dir) and install_path is not None and install_path.is_dir()

    if get_skip_delete_game_confirm(db):
        delete_install = bool(fallback_delete_install and can_delete_install)
        if delete_install:
            from PySide6.QtWidgets import QMessageBox

            answer = QMessageBox.warning(
                parent,
                "确认删除安装文件夹",
                f"将永久删除游戏安装目录（不可恢复）：\n{install_path.resolve()}\n\n是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                delete_install = False
        return DeleteGameDecision(delete_install_folder=delete_install)

    from PySide6.QtWidgets import QDialog

    from app.ui.dialogs.delete_game_confirm_dialog import DeleteGameConfirmDialog

    dlg = DeleteGameConfirmDialog(
        game_name,
        install_dir=install_dir if can_delete_install else "",
        parent=parent,
    )
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None
    if dlg.dont_ask_again():
        set_skip_delete_game_confirm(db, True)
    return DeleteGameDecision(delete_install_folder=dlg.delete_install_folder())


def _is_unsafe_install_path(root: Path) -> bool:
    try:
        resolved = root.resolve()
    except OSError:
        return True
    if not resolved.is_dir():
        return True
    parts = resolved.parts
    if len(parts) < _MIN_INSTALL_PATH_PARTS:
        return True
    if os.name == "nt":
        if len(parts) == 1 or (len(parts) == 2 and parts[1] in {"", os.sep}):
            return True
        if len(parts) == 2 and len(parts[1]) <= 3 and parts[1].endswith(":"):
            return True
    elif resolved == Path("/"):
        return True
    return False


def delete_game_install_folder(root_dir: str, launch_exe: str) -> None:
    """Permanently remove the game installation directory. Raises on unsafe or failed paths."""
    root = Path(root_dir)
    if not root.is_dir():
        raise ValueError(f"安装目录不存在或不是文件夹：{root_dir}")

    if _is_unsafe_install_path(root):
        raise ValueError("安装路径过短或位于磁盘根目录，为保护数据已拒绝删除")

    root_resolved = root.resolve()
    if launch_exe:
        launch = Path(launch_exe)
        if launch.exists():
            try:
                launch.resolve().relative_to(root_resolved)
            except ValueError:
                raise ValueError("启动程序不在安装目录内，为保护数据已拒绝删除整个文件夹")

    try:
        shutil.rmtree(root_resolved)
    except OSError as exc:
        raise OSError(f"无法删除安装目录：{root_resolved}\n{exc}") from exc


def _cleanup_game_cache_files(
    db: Database,
    game_id: int,
    zip_paths: list[str],
    cover_candidates: list[Path],
) -> None:
    for zp in zip_paths:
        try:
            Path(zp).unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("failed to delete backup zip %s: %s", zp, exc)

    backups_root = db.base_dir / "save-backups"
    if backups_root.is_dir():
        for user_dir in backups_root.iterdir():
            if not user_dir.is_dir():
                continue
            game_dir = user_dir / str(game_id)
            if game_dir.is_dir():
                try:
                    shutil.rmtree(game_dir, ignore_errors=True)
                except OSError as exc:
                    logger.warning("failed to remove save-backups dir %s: %s", game_dir, exc)

    covers_dir = db.base_dir / "covers"
    seen: set[str] = set()
    for cp in cover_candidates:
        try:
            key = str(cp.resolve()).lower()
        except OSError:
            key = str(cp).lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            if cp.is_file() and cp.parent.resolve() == covers_dir.resolve():
                cp.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("failed to delete cover %s: %s", cp, exc)


def delete_game_from_library(
    db: Database,
    game_id: int,
    *,
    delete_install_folder: bool = False,
) -> str:
    """
    Delete one game row and clean save-backup zips / cover cache files under data dir.
    Optionally delete ``root_dir`` on disk when ``delete_install_folder`` is True.

    Install folder and cache files are removed before the DB row so a failure leaves
    the library record intact.
    """
    row = db.conn.execute(
        """
        SELECT
            name,
            custom_name,
            root_dir,
            launch_exe,
            custom_launch_exe,
            cover_path,
            custom_cover_path
        FROM games WHERE id = ?
        """,
        (game_id,),
    ).fetchone()
    if row is None:
        raise ValueError("游戏记录不存在")

    display = (str(row["custom_name"]).strip() if row["custom_name"] else "") or str(row["name"])
    root_dir = str(row["root_dir"])
    custom_launch = str(row["custom_launch_exe"]).strip() if row["custom_launch_exe"] else ""
    launch_exe = custom_launch or str(row["launch_exe"] or "")

    zip_paths = [
        str(r["zip_path"])
        for r in db.conn.execute(
            "SELECT zip_path FROM save_backups WHERE game_id = ?", (game_id,)
        ).fetchall()
    ]

    cover_candidates: list[Path] = []
    for key in ("cover_path", "custom_cover_path"):
        raw = row[key]
        if raw:
            cover_candidates.append(Path(str(raw)))

    covers_dir = db.base_dir / "covers"
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"):
        p = covers_dir / f"{game_id}{ext}"
        if p.is_file():
            cover_candidates.append(p)

    if delete_install_folder:
        delete_game_install_folder(root_dir, launch_exe)

    _cleanup_game_cache_files(db, game_id, zip_paths, cover_candidates)

    if not db.delete_game(game_id):
        raise ValueError("删除失败")

    return display
