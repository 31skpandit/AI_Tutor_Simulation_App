"""Render every Streamlit page headlessly and fail on any exception (no AI calls are made)."""

import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from app.core.config import PROJECT_ROOT, get_settings

PAGES = [
    "ui/Home.py",
    "ui/pages/1_Teach_Mode.py",
    "ui/pages/2_Lesson_Studio.py",
    "ui/pages/3_Syllabus_Library.py",
    "ui/pages/4_AI_Tutor.py",
    "ui/pages/5_Settings_and_Cost.py",
]


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    # Each page must import its helpers on its own, regardless of which page ran before.
    ui_dir = (PROJECT_ROOT / "ui").resolve()
    monkeypatch.setattr(sys, "path", [p for p in sys.path if p and Path(p).resolve() != ui_dir])
    monkeypatch.delitem(sys.modules, "common", raising=False)
    monkeypatch.setenv("ATS_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_without_errors(page):
    at = AppTest.from_file(str(PROJECT_ROOT / page), default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.title, f"{page} has no title"
