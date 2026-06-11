from __future__ import annotations

from pathlib import Path

from app.services.help_content import (
    DEMO_STEPS,
    SUPPORT_EMAIL,
    UI_PREF_WELCOME_SHOWN,
    guide_html,
    notice_html,
    resolve_help_screenshot,
    should_show_welcome_guide,
)


def test_should_show_welcome_guide_default() -> None:
    assert should_show_welcome_guide({}) is True
    assert should_show_welcome_guide({UI_PREF_WELCOME_SHOWN: True}) is False


def test_demo_steps_have_titles() -> None:
    assert len(DEMO_STEPS) >= 4
    for step in DEMO_STEPS:
        assert step.get("title")
        assert step.get("body")


def test_resolve_help_screenshot_dev_tree() -> None:
    path = resolve_help_screenshot()
    if path is not None:
        assert path.is_file()
        assert path.suffix.lower() == ".png"


def test_notice_in_help_html() -> None:
    assert SUPPORT_EMAIL in notice_html()
    assert SUPPORT_EMAIL in guide_html()
    assert "郑重声明" in guide_html()
    assert "mailto:" in notice_html()
