"""Autopilot: automatic page quality check → clean pages searchable → chapter lesson written automatically;
flagged pages wait for the teacher, and the lesson then offers a rebuild."""

import json

import pytest

from app.core.config import Settings
from app.ingestion.quality import assess, guess_chapter_title
from app.ingestion.service import IngestionService
from app.jobs.runner import run_until_empty
from app.lessons.service import LessonService
from app.llm.backend import BackendResult
from tests.conftest import FakeBackend
from tests.test_ingestion import TEXT_PAGE, make_text_pdf
from tests.test_lessons import PLAN

# ---------------------------------------------------------------- the quality check


@pytest.mark.parametrize(
    ("text", "method", "warning", "expected"),
    [
        (TEXT_PAGE, "text_layer", None, None),  # normal page: clean
        ("Figure 5.2 Bhilai Steel Plant", "ocr", None, "very little text"),
        (TEXT_PAGE + " ", "text_layer", None, "unreadable characters"),
        (TEXT_PAGE.replace("a", "a ").replace("e", " e "), "ocr", None, "split into single letters"),
        ("१२३ अर्थव्यवस्था " * 20, "text_layer", None, "Marathi/Hindi"),
        (TEXT_PAGE, "ocr", "a repeated line was removed", "OCR warning"),
        (TEXT_PAGE + "\n| Acid | Base |\n| HCl | NaOH |", "ocr", None, "table read by OCR"),
        (
            TEXT_PAGE + "\n| Acid | Base |\n| HCl | NaOH |",
            "ocr_cloud",
            None,
            None,
        ),  # cloud tables are trusted
    ],
)
def test_quality_check(text, method, warning, expected):
    result = assess(text, method, warning)
    if expected is None:
        assert result.status == "clean", result.reasons
    else:
        assert result.status == "check" and any(expected in r for r in result.reasons), result.reasons


def test_exercise_pages_are_labelled_not_flagged():
    text = TEXT_PAGE + " Exercises 1. Choose the correct option ... (B) Identify and write the wrong pair."
    result = assess(text)
    assert result.status == "clean" and result.labels == ["exercises"]


@pytest.mark.parametrize(
    ("first_page", "title"),
    [
        ("4 Economic Development\n\nWe are going to study India's economic policy.", "Economic Development"),
        ("# Chapter 5: Acids, Bases and Salts\nAcids are sour.", "Acids, Bases and Salts"),
        ("15\nEnvironmental Balance\nText follows here.", "Environmental Balance"),
        ("Acids are sour substances and they turn blue litmus red, which every student sees.", ""),
    ],
)
def test_chapter_title_is_found_on_the_first_page(first_page, title):
    assert guess_chapter_title(first_page) == title


# ---------------------------------------------------------------- the whole autopilot


@pytest.fixture
def autopilot(tmp_path, make_router):
    source = tmp_path / "source"
    source.mkdir()
    settings = Settings(
        data_dir=tmp_path / "data", source_dir=source, require_review=True, auto_review_clean=True,
        auto_lesson=True, enrich_pages=False, lesson_min_relevance=0.1,
    )  # fmt: skip
    backend = FakeBackend(ocr_text="Figure: a mostly picture page.")
    router = make_router(backend)
    router.config.tasks["lesson_plan"] = router.config.tasks["local_only"]
    return IngestionService(router.engine, router, settings), backend, source


def test_upload_to_lesson_without_the_teacher(autopilot):
    service, backend, source = autopilot
    plan = dict(PLAN, simulation={})  # no simulation job in this test
    backend.script = [BackendResult(json.dumps(plan), 100, 100)]
    # page 1: a normal text page; page 2: only 27 words (a mostly-picture page) → flagged for the teacher
    short = " ".join(f"word{i}" for i in range(27))
    make_text_pdf(
        source / "Class 9 - Science - 5th Chapter.pdf", ["5 Acids, Bases and Salts\n" + TEXT_PAGE, short]
    )
    document = service.scan_source(enqueue=True).new[0].document

    assert run_until_empty(service) == 3  # extract → index (clean page) → lesson plan, with nobody clicking
    pages = {p.page_no: p for p in service.pages(document.id)}
    assert pages[1].auto_reviewed and pages[1].indexed and pages[1].quality == "clean"
    assert not pages[2].reviewed and not pages[2].indexed and pages[2].quality == "check"
    assert "very little text" in json.loads(pages[2].quality_notes)[0]
    counts = service.page_counts(document.id)
    assert counts["to_check"] == 1 and counts["auto_reviewed"] == 1
    assert service.documents()[0].chapter_title == "Acids, Bases and Salts"  # found on page 1

    lessons = LessonService(service.engine, service.router, 0.1)
    [lesson] = lessons.lessons()
    assert lesson.topic == "Acids, Bases and Salts" and lesson.document_id == document.id
    assert lesson.status == "draft"  # the teacher still approves before Teach Mode
    assert lessons.auto_create_for_document(document.id) == []  # only one automatic lesson per chapter

    # The teacher reviews the flagged page → it becomes searchable → the lesson offers a rebuild.
    service.update_page(
        document.id, 2, "Figure 5.1: litmus paper turns red in an acid. " + TEXT_PAGE, reviewed=True
    )
    service.enqueue("index", document.id)
    run_until_empty(service)
    assert lessons.pages_added_after(lessons.get(lesson.id)) == [2]
    assert len(lessons.lessons()) == 1


def test_a_file_with_two_chapters_is_split_into_chapters():
    from app.ingestion.quality import find_chapters

    pages = [
        (1, "3 HCF and LCM\n\nLet's recall. Which is the smallest prime number?"),
        (
            2,
            "2 40 2 20 40 = 10 × 4\nPrime factors of 40",
        ),  # a division layout starting with numbers: not a chapter
        (3, "Example Find the LCM of 60 and 48."),
        (4, "4\n\nAngles and Pairs of Angles\n\nLet's recall."),
        (5, "Now I know ! Adjacent angles"),
        (6, "7 Example of something"),  # number does not follow 4: not a chapter
    ]
    assert find_chapters(pages) == [
        {"no": 3, "title": "HCF and LCM", "start": 1, "end": 3},
        {"no": 4, "title": "Angles and Pairs of Angles", "start": 4, "end": 6},
    ]
    assert find_chapters(pages[:3]) == []  # one chapter: the whole file is the chapter
    assert find_chapters([(1, "Acids are sour."), (2, "4\nAngles")]) == []  # must start on the first page
