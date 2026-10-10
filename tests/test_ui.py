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
    "ui/pages/7_Chemistry_3D_Lab.py",
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
    assert at.tabs and len(at.tabs) == 5  # content, chemistry, 3D scenes, simulation, sources


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
    # title, 1 section, equations, molecules, 3D scenes (molecule, then equation), simulation, key points
    assert titles == [
        "Neutralisation",
        "What happens",
        "Equations",
        "Molecules — rotate them!",
        "See it happen — H₂O",
        "See it happen — HCl + NaOH → NaCl + H₂O",
        "Titration",
        "Key points",
    ]


HISTORY_PLAN = {
    "title": "Economic Development",
    "profile": "history",
    "objectives": ["Explain the five year plans"],
    "sections": [{"heading": "Mixed economy", "content": "Public and private sector [1].", "cites": [1], "pages": [1]}],
    "key_points": ["India chose a mixed economy"],
    "timeline": [{"date": "19th July 1969", "year": 1969, "event": "14 banks nationalised", "pages": [1]}],
    "periods": [{"name": "First Five Year Plan", "start": 1951, "end": 1956, "focus": "agriculture", "pages": [1]}],
    "people": [{"name": "Dr Datta Samant", "role": "led the mill workers' strike", "pages": [1]}],
    "places": [{"name": "Bhilai", "what": "steel plant", "pages": [1]}, {"name": "Damodar", "what": "dam"}],
    "cause_effect": [{"event": "Mill workers' strike", "causes": ["bonus cut"], "effects": ["mills closed"], "pages": [1]}],
    "sources": [{"n": 1, "page": 1, "citation": "Ch. 4, page 1", "text": "Acids are sour."}],
}  # fmt: skip


@pytest.fixture
def approved_history_lesson(library_with_a_document):
    import json

    from sqlmodel import Session

    from app.db.models import Lesson
    from app.db.session import make_engine

    with Session(make_engine(get_settings().db_path)) as s:
        lesson = Lesson(topic="Economic Development", title="Economic Development", status="approved",
                        plan_json=json.dumps(HISTORY_PLAN, ensure_ascii=False), document_id=library_with_a_document.id)  # fmt: skip
        s.add(lesson)
        s.commit()
        s.refresh(lesson)
        return lesson.id


def test_history_lesson_has_its_own_tabs_and_slides(approved_history_lesson):
    at = AppTest.from_file(str(PROJECT_ROOT / "ui/pages/2_Lesson_Studio.py"), default_timeout=90).run()
    assert not at.exception, [e.value for e in at.exception]
    assert len(at.tabs) == 6  # content, timeline, map, causes & effects, people & pictures, sources
    assert any("Damodar" in t.label for t in at.text_input)  # unplaced place → hint box for the teacher
    at = AppTest.from_file(str(PROJECT_ROOT / "ui/pages/1_Teach_Mode.py"), default_timeout=90).run()
    titles = [at.title[0].value]
    for _ in range(12):
        nxt = next(b for b in at.button if b.label == "Next ▶")
        if nxt.disabled:
            break
        nxt.click().run()
        assert not at.exception, [e.value for e in at.exception]
        titles.append(at.title[0].value)
    assert titles == ["Economic Development", "Mixed economy", "Timeline", "On the map", "Mill workers' strike",
                      "People in this lesson", "Key points"]  # fmt: skip


MATHS_PLAN = {
    "title": "HCF and LCM",
    "profile": "maths",
    "objectives": ["Find the HCF"],
    "sections": [{"heading": "Factors", "content": "Common factors [1].", "cites": [1], "pages": [1]}],
    "key_points": ["HCF divides both numbers"],
    "concepts": [
        {"name": "HCF", "kind": "hcf", "explain": "The biggest common factor.", "pages": [1],
         "examples": [{"text": "HCF of 144 and 252", "numbers": [144, 252], "answer": "36", "computed": "36", "ok": True}],
         "real_life": [{"title": "Equal teams", "story": "Split two classes into equal teams.", "image_query": "school children", "photos": []}]},
        {"name": "Complementary angles", "kind": "complementary_angles", "examples": [{"angles": [70], "computed": "20°"}],
         "real_life": []},
    ],
    "sources": [{"n": 1, "page": 1, "citation": "Ch. 3, page 1", "text": "Acids are sour."}],
}  # fmt: skip


def test_maths_lesson_has_concepts_with_visualise_buttons(library_with_a_document):
    import json

    from sqlmodel import Session

    from app.db.models import Lesson
    from app.db.session import make_engine

    with Session(make_engine(get_settings().db_path)) as s:
        s.add(Lesson(topic="HCF and LCM", title="HCF and LCM", status="approved",
                     plan_json=json.dumps(MATHS_PLAN, ensure_ascii=False), document_id=library_with_a_document.id))  # fmt: skip
        s.commit()
    at = AppTest.from_file(str(PROJECT_ROOT / "ui/pages/2_Lesson_Studio.py"), default_timeout=90).run()
    assert not at.exception, [e.value for e in at.exception]
    assert len(at.tabs) == 3  # content, concepts & visuals, sources
    toolbars = at.get("button_group")
    assert len(toolbars) == 2  # one Visualise toolbar per concept
    assert any("More real-life examples" in b.label for b in at.button)
    at = AppTest.from_file(str(PROJECT_ROOT / "ui/pages/1_Teach_Mode.py"), default_timeout=90).run()
    titles = [at.title[0].value]
    for _ in range(8):
        nxt = next(b for b in at.button if b.label == "Next ▶")
        if nxt.disabled:
            break
        nxt.click().run()
        assert not at.exception, [e.value for e in at.exception]
        titles.append(at.title[0].value)
    assert titles == ["HCF and LCM", "Factors", "HCF", "Complementary angles", "Key points"]


def test_chemistry_lab_example_buttons_and_typed_input():
    at = AppTest.from_file(str(PROJECT_ROOT / "ui/pages/7_Chemistry_3D_Lab.py"), default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
    next(b for b in at.button if b.label == "2H₂ + O₂ → 2H₂O").click().run()
    assert not at.exception and at.session_state["lab3d"] == "2H₂ + O₂ → 2H₂O"
    at.text_input[0].input("H2SO4").run()  # cannot be shown: a clear reason, not a crash
    assert not at.exception
    assert any("H2SO4" in i.value and "12 electrons" in i.value for i in at.info)
