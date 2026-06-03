"""Detect disc-image extract outcomes and build UI guidance for manual install."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.loose_install_consolidator import (
    detect_loose_install_at_root,
    suggest_install_folder_name,
    suggested_install_directory,
)


@dataclass(frozen=True)
class DiscInstallGuide:
    """User must run setup.exe from extract output, then scan install folder."""

    extract_dir: str
    installer_exe: str | None
    iso_names: tuple[str, ...]
    archive_file_name: str = ""
    game_save_dir: str = ""

    @property
    def needs_guide(self) -> bool:
        return bool(self.installer_exe or self.iso_names)

    @property
    def installer_path(self) -> Path | None:
        if not self.installer_exe:
            return None
        p = Path(self.installer_exe)
        return p if p.is_file() else None

    def installer_display(self) -> str:
        if self.installer_path is not None:
            return str(self.installer_path)
        if self.installer_exe:
            return self.installer_exe
        return ""

    @property
    def suggested_folder_name(self) -> str:
        return suggest_install_folder_name(
            installer_exe=self.installer_exe,
            iso_names=self.iso_names,
            archive_file_name=self.archive_file_name,
        )

    @property
    def suggested_install_path(self) -> str:
        if not self.game_save_dir:
            return ""
        return str(
            suggested_install_directory(
                self.game_save_dir,
                folder_name=self.suggested_folder_name,
            )
        )


def guide_from_post_process(
    post_process: dict[str, Any] | None,
    *,
    extract_dir: str = "",
) -> DiscInstallGuide | None:
    pp = post_process or {}
    expanded = pp.get("iso_expanded") or []
    if isinstance(expanded, str):
        expanded = [expanded]
    iso_names = tuple(str(x) for x in expanded if str(x).strip())

    # Only consider installer_exe when ISO images were actually expanded.
    # Regular game archives may contain setup.exe but don't need manual
    # install guidance — they are already playable after extraction.
    if iso_names:
        installer = pp.get("installer_exe")
        installer_str = str(installer).strip() if installer else ""
    else:
        installer_str = ""

    out_dir = str(extract_dir or pp.get("extract_dir") or "").strip()
    if not out_dir and not installer_str and not iso_names:
        return None

    game_save = str(pp.get("game_save_dir") or "").strip()
    guide = DiscInstallGuide(
        extract_dir=out_dir,
        installer_exe=installer_str or None,
        iso_names=iso_names,
        archive_file_name=str(pp.get("archive_file_name") or "").strip(),
        game_save_dir=game_save,
    )
    return guide if guide.needs_guide else None


_INSTALLER_CANDIDATES = ("setup.exe", "install.exe", "autorun.exe", "inst.exe")


def resolve_installer_on_disk(guide: DiscInstallGuide) -> DiscInstallGuide:
    """Re-resolve setup.exe on disk (path may have moved since post_process)."""
    root = Path(guide.extract_dir) if guide.extract_dir else None
    if root is None or not root.is_dir():
        if guide.installer_path is not None:
            return guide
        return guide

    candidates: list[Path] = []
    if guide.installer_exe:
        candidates.append(Path(guide.installer_exe))
    for name in _INSTALLER_CANDIDATES:
        candidates.append(root / name)
        try:
            candidates.extend(root.glob(f"*/{name}"))
        except OSError:
            pass

    seen: set[str] = set()
    for cand in candidates:
        try:
            resolved = cand.resolve()
        except OSError:
            continue
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        if resolved.is_file():
            return DiscInstallGuide(
                extract_dir=str(root.resolve()),
                installer_exe=str(resolved),
                iso_names=guide.iso_names,
                archive_file_name=guide.archive_file_name,
                game_save_dir=guide.game_save_dir,
            )
    return DiscInstallGuide(
        extract_dir=str(root.resolve()),
        installer_exe=None,
        iso_names=guide.iso_names,
        archive_file_name=guide.archive_file_name,
        game_save_dir=guide.game_save_dir,
    )


def guide_from_progress_payload(payload: dict[str, Any]) -> DiscInstallGuide | None:
    if not payload.get("needs_install_guide"):
        return None
    return DiscInstallGuide(
        extract_dir=str(payload.get("extract_dir") or ""),
        installer_exe=str(payload.get("installer_exe") or "").strip() or None,
        iso_names=tuple(payload.get("iso_expanded") or ()),
        archive_file_name=str(payload.get("archive_file_name") or "").strip(),
        game_save_dir=str(payload.get("game_save_dir") or "").strip(),
    )


def enrich_guide_with_config(guide: DiscInstallGuide, game_save_dir: str) -> DiscInstallGuide:
    if guide.game_save_dir:
        return guide
    return DiscInstallGuide(
        extract_dir=guide.extract_dir,
        installer_exe=guide.installer_exe,
        iso_names=guide.iso_names,
        archive_file_name=guide.archive_file_name,
        game_save_dir=game_save_dir.strip(),
    )
