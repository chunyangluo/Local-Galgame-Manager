from __future__ import annotations

from app.services.disc_install_guide import (
    DiscInstallGuide,
    guide_from_post_process,
    guide_from_progress_payload,
)


def test_guide_from_post_process_with_installer() -> None:
    g = guide_from_post_process(
        {
            "iso_expanded": ["MOMOERO.ISO"],
            "installer_exe": r"D:\out\setup.exe",
        },
        extract_dir=r"D:\out",
    )
    assert g is not None
    assert g.installer_exe == r"D:\out\setup.exe"
    assert g.iso_names == ("MOMOERO.ISO",)


def test_guide_from_post_process_empty() -> None:
    assert guide_from_post_process({}) is None


def test_guide_from_progress_payload() -> None:
    g = guide_from_progress_payload(
        {
            "needs_install_guide": True,
            "extract_dir": r"D:\extract",
            "installer_exe": r"D:\extract\setup.exe",
            "iso_expanded": ["a.iso"],
        }
    )
    assert g is not None
    assert isinstance(g, DiscInstallGuide)
