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
    "ui/pages/4_Review_Text.py",
    "ui/pages/2_Lesson_Studio.py",
    "ui/pages/1_Teach_Mode.py",
    "ui/pages/5_AI_Tutor.py",
    "ui/pages/6_Settings_and_Cost.py",
]


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    # Each page must import its helpers on its own, regardless of which page ran before.
    ui_dir = (PROJECT_ROOT / "ui").resolve()
    monkeypatch.setattr(sys, "path", [p for p in sys.path if p and Path(p).resolve() != ui_dir])
    monkeypatch.delitem(sys.modules, "common", raising=False)
    monkeypatch.setenv("ATS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ATS_SOURCE_DIR", str(tmp_path / "source"))  # never touch the real source folder
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_without_errors(page):
    at = AppTest.from_file(str(PROJECT_ROOT / page), default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.title, f"{page} has no title"


@pytest.fixture
def library_with_a_document(tmp_path, config):
    """A real (text-layer) PDF registered, extracted, reviewed and indexed in the isolated data dir."""
    import streamlit as st

    from app.db.session import make_engine
    from app.ingestion.service import IngestionService
    from app.llm.router import LLMRouter
    from tests.conftest import FakeBackend
    from tests.test_ingestion import TEXT_PAGE, make_text_pdf

    st.cache_resource.clear()  # the pages must build their services on this data dir
    settings = get_settings()
    make_text_pdf(settings.source_dir / "Class 9 - Science - 5th Chapter.pdf", [TEXT_PAGE, TEXT_PAGE])
    router = LLMRouter(config, FakeBackend(), make_engine(settings.db_path), secret_getter=lambda n: None)
    service = IngestionService(router.engine, router, settings)
    document = service.scan_source(enqueue=False).new[0].document
    service.extract_document(document.id)
    service.mark_all_reviewed(document.id)
    service.index_document(document.id)
    yield document
    st.cache_resource.clear()


@pytest.mark.parametrize(
    "page",
    ["ui/pages/3_Syllabus_Library.py", "ui/pages/4_Review_Text.py", "ui/pages/5_AI_Tutor.py", "ui/Home.py"],
)
def test_pages_render_with_a_document(library_with_a_document, page):
    at = AppTest.from_file(str(PROJECT_ROOT / page), default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
    if page.endswith("Review_Text.py"):
        assert "Acids are sour" in at.text_area[0].value
    if page.endswith("AI_Tutor.py"):
        assert at.chat_input, "chat box should be shown when pages are searchable"
    if page.endswith("Syllabus_Library.py"):
        review = next(b for b in at.button if b.label == "📝 Review pages")
        review.click().run()
        assert not at.exception, [e.value for e in at.exception]


@pytest.fixture
def approved_lesson(library_with_a_document):
    """An approved lesson with equations, molecules and a checked simulation in the isolated data dir."""
    import json

    from app.db.models import Lesson
    from app.db.session import make_engine
    from tests.test_lessons import GOOD_SKETCH, PLAN

    plan = dict(PLAN, sources=[{"n": 1, "page": 1, "citation": "Ch. 5, page 1", "text": "Acids are sour."}])
    plan["equations"] = [dict(e, balanced=True, check="Balanced") for e in PLAN["equations"]]
    plan["sections"] = [dict(s, pages=[1]) for s in PLAN["sections"]]
    from sqlmodel import Session

    with Session(make_engine(get_settings().db_path)) as s:
        lesson = Lesson(
            topic="Neutralization reaction",
            title=plan["title"],
            status="approved",
            plan_json=json.dumps(plan, ensure_ascii=False),
            simulation_js=GOOD_SKETCH,
            simulation_status="ok",
            document_id=library_with_a_document.id,
        )
        s.add(lesson)
        s.commit()
        s.refresh(lesson)
        return lesson.id


def test_lesson_studio_shows_the_lesson(approved_lesson):
    at = AppTest.from_file(str(PROJECT_ROOT / "ui/pages/2_Lesson_Studio.py"), default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("Neutralisation" in m.value for m in at.markdown)
    assert at.tabs and len(at.tabs) == 4


def test_teach_mode_walks_through_every_slide(approved_lesson):
    at = AppTest.from_file(str(PROJECT_ROOT / "ui/pages/1_Teach_Mode.py"), default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
    titles = [at.title[0].value]
    for _ in range(10):
        nxt = next(b for b in at.button if b.label == "Next ▶")
        if nxt.disabled:
            break
        nxt.click().run()
        assert not at.exception, [e.value for e in at.exception]
        titles.append(at.title[0].value)
    # title, 1 section, equations, molecules, simulation, key points
    assert titles == [
        "Neutralisation",
        "What happens",
        "Equations",
        "Molecules — rotate them!",
        "Titration",
        "Key points",
    ]
