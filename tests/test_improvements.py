"""Phase 1 improvements: OCR clean-up & table repair, cloud re-read, page enrichment, answer cache, migration."""

import sqlite3

from sqlmodel import Session, select

from app.db.models import Chunk
from app.db.session import make_engine
from app.ingestion.enrich import parse_enrichment
from app.ingestion.ocr import clean_ocr_text, normalize_markdown_tables
from app.rag import answer_cache, tutor
from app.rag.store import SearchFilters
from tests.conftest import FakeBackend
from tests.test_ingestion import TEXT_PAGE, env, make_scanned_pdf, make_text_pdf, pages_of  # noqa: F401

LOCAL_TABLE = """2. Basicity and acidity
| Acid : Number of H⁺ obtained from one molecule. | | | | | |
|---|---|---|---|---|---|
| HCl | HNO₃ | H₂SO₄ | H₂CO₃ | H₃BO₃ | H₃PO₄ | CH₃COOH |
| | | | | | |
Acids and bases are also classified."""

LONG_PAGE = (TEXT_PAGE + " ") * 3


# ---------------------------------------------------------------- Step 1: clean-up & tables


def test_table_repair_keeps_every_column_and_blank_rows():
    """Real local-model output from page 61: 6 header cells but 7 data cells."""
    rows = [line for line in normalize_markdown_tables(LOCAL_TABLE).splitlines() if line.startswith("|")]
    assert all(row.count("|") == 8 for row in rows)  # 7 columns everywhere
    assert rows[1] == "| --- | --- | --- | --- | --- | --- | --- |"
    assert "CH₃COOH" in rows[2]
    assert rows[3].replace("|", "").strip() == ""  # the blank exercise row is kept


def test_correct_table_is_unchanged_and_plain_text_untouched():
    good = "| a | b |\n| --- | --- |\n| 1 | 2 |"
    assert normalize_markdown_tables(good) == good
    assert normalize_markdown_tables("No table here.\nJust text.") == "No table here.\nJust text."


def test_placeholder_figure_lines_are_removed_but_real_ones_kept():
    text = (
        "Text.\n[Figure: chemical formulas are shown in the text, but no figure is present in the image.]\n"
        "[Figure: 5.2 Dissociation of salt; labels: NaCl, Water]"
    )
    cleaned = clean_ocr_text(text)
    assert "no figure is present" not in cleaned and "5.2 Dissociation of salt" in cleaned


def test_clean_extracted_text_never_touches_your_edits(env):  # noqa: F811
    service, backend, source = env
    backend.ocr_text = "Line.\n[Figure: no figure is present.]"
    make_scanned_pdf(source / "scan.pdf", ["one", "two"])
    document = service.add_file(source / "scan.pdf", enqueue=False).document
    service.extract_document(document.id)
    # simulate pages extracted by an older version (before the clean-up existed)
    from app.db.models import Page

    with Session(service.engine) as s:
        for page in s.exec(select(Page)).all():
            page.text = page.raw_text = backend.ocr_text
            s.add(page)
        s.commit()
    service.update_page(document.id, 2, "My own edited text.", reviewed=False)
    assert service.clean_extracted_text(document.id) == 1
    pages = pages_of(service, document.id)
    assert pages[1].text == "Line." and pages[2].text == "My own edited text."


# ---------------------------------------------------------------- Step 2: cloud re-read


def test_pages_with_tables_or_figures_are_suggested_for_cloud(env):  # noqa: F811
    service, backend, source = env
    make_scanned_pdf(source / "scan.pdf", ["table page", "plain page"])
    document = service.add_file(source / "scan.pdf", enqueue=False).document
    backend.script = []
    service.extract_document(document.id)
    service.update_page(document.id, 1, LOCAL_TABLE, reviewed=False)
    service.update_page(document.id, 2, "Only plain text.", reviewed=False)
    assert service.pages_suggested_for_cloud(document.id) == [1]


def test_cloud_reread_replaces_text_and_requires_review_again(env):  # noqa: F811
    service, backend, source = env
    make_scanned_pdf(source / "scan.pdf", ["page"])
    document = service.add_file(source / "scan.pdf", enqueue=False).document
    service.extract_document(document.id)
    service.mark_all_reviewed(document.id)
    service.index_document(document.id)
    stats = service.reread_pages_cloud(document.id, [1])
    page = pages_of(service, document.id)[1]
    assert stats == {"pages": 1, "failed": 0}
    assert page.method == "ocr_cloud" and "H₂SO₄" in page.text and page.model_ref == "ollama/cloudvision"
    assert not page.reviewed and not page.indexed
    with Session(service.engine) as s:
        assert not s.exec(select(Chunk)).all()  # old passages of that page removed


# ---------------------------------------------------------------- Step 3: enrichment


def test_parse_enrichment_tolerates_text_around_json():
    result = parse_enrichment(
        'Here you go:\n{"summary": "S", "tables": [{"title": "T", "description": "D"}]}'
    )
    assert result.summary == "S" and result.tables == [("T", "D")] and result.figures == []
    assert result.entries(4) == [("summary", "Summary of page 4: S"), ("table", "Table on page 4: T. D")]


def test_indexing_adds_summary_and_table_descriptions(env):  # noqa: F811
    service, backend, source = env
    make_text_pdf(source / "chapter.pdf", [LONG_PAGE])
    document = service.add_file(source / "chapter.pdf", enqueue=False).document
    service.extract_document(document.id)
    service.mark_all_reviewed(document.id)
    stats = service.index_document(document.id)
    assert stats["enrichments"] == 2 and stats["enrich_failed"] == 0
    with Session(service.engine) as s:
        kinds = sorted(c.kind for c in s.exec(select(Chunk)).all())
    assert "summary" in kinds and "table" in kinds and "text" in kinds
    assert any(call.get("json_output") for call in backend.calls)


def test_enrichment_failure_never_blocks_indexing(env):  # noqa: F811
    from app.llm.backend import BackendResult

    service, backend, source = env
    make_text_pdf(source / "chapter.pdf", [LONG_PAGE])
    document = service.add_file(source / "chapter.pdf", enqueue=False).document
    service.extract_document(document.id)
    service.mark_all_reviewed(document.id)
    backend.script = [BackendResult("not json at all", 10, 10)]
    stats = service.index_document(document.id)
    assert stats["enrich_failed"] == 1 and stats["pages"] == 1
    assert service.documents()[0].status == "indexed"


def test_tutor_never_sees_generated_descriptions(env):  # noqa: F811
    """Descriptions are written by a small model and can be wrong — only original passages are evidence."""
    service, backend, source = env
    make_text_pdf(source / "chapter.pdf", [LONG_PAGE])
    document = service.add_file(source / "chapter.pdf", enqueue=False).document
    service.extract_document(document.id)
    service.mark_all_reviewed(document.id)
    service.index_document(document.id)
    # a question that matches the generated table description best ("basicity", "H2SO4", "H3PO4")
    result = tutor.answer(service.router, service.store, "basicity table HCl H2SO4 H3PO4", min_relevance=0.1)
    prompt = backend.calls[-1]["messages"][1]["content"]
    assert "Lists HCl, H2SO4 and H3PO4" not in prompt and "Summary of page" not in prompt
    assert all(hit.kind == "text" for hit in result.hits)
    assert any(hit.via == "table" for hit in result.hits)
    assert "found via table description" in next(h.label for h in result.hits if h.via == "table")


# ---------------------------------------------------------------- semantic answer cache


def _indexed(service, source):
    make_text_pdf(source / "chapter.pdf", [LONG_PAGE])
    document = service.add_file(source / "chapter.pdf", enqueue=False).document
    service.extract_document(document.id)
    service.mark_all_reviewed(document.id)
    service.index_document(document.id)
    return document


def test_same_question_is_answered_from_cache_without_model_call(env):  # noqa: F811
    service, backend, source = env
    _indexed(service, source)
    q = "What happens when an acid reacts with a base?"
    first = tutor.answer(service.router, service.store, q, min_relevance=0.1, semantic_cache_min=0.97)
    calls = len(backend.calls)
    second = tutor.answer(service.router, service.store, q, min_relevance=0.1, semantic_cache_min=0.97)
    assert first.grounded and not first.reused_from
    assert second.reused_from == q and second.text == first.text and len(backend.calls) == calls
    assert second.hits and second.hits[0].citation == first.hits[0].citation


def test_contrast_words_block_reuse(env):  # noqa: F811
    service, backend, source = env
    _indexed(service, source)
    tutor.answer(
        service.router, service.store, "What is a strong acid?", min_relevance=0.1, semantic_cache_min=0.5
    )
    other = tutor.answer(
        service.router, service.store, "What is a weak acid?", min_relevance=0.1, semantic_cache_min=0.5
    )
    assert other.reused_from is None
    assert answer_cache.contrast_conflict("gas at the cathode", "gas at the anode")
    assert not answer_cache.contrast_conflict("What is basicity of an acid?", "Define the basicity of acids.")


def test_cache_is_ignored_after_reindexing_and_for_other_language(env):  # noqa: F811
    service, backend, source = env
    document = _indexed(service, source)
    q = "What happens when an acid reacts with a base?"
    tutor.answer(service.router, service.store, q, min_relevance=0.1, semantic_cache_min=0.97)
    marathi = tutor.answer(
        service.router, service.store, q, language="Marathi", min_relevance=0.1, semantic_cache_min=0.97
    )
    assert marathi.reused_from is None
    service.update_page(document.id, 1, LONG_PAGE + " Extra corrected sentence.", reviewed=True)
    service.index_document(document.id)
    again = tutor.answer(service.router, service.store, q, min_relevance=0.1, semantic_cache_min=0.97)
    assert again.reused_from is None  # pages changed → fresh answer


def test_cache_disabled_by_default_in_answer(env):  # noqa: F811
    service, backend, source = env
    _indexed(service, source)
    q = "What happens when an acid reacts with a base?"
    tutor.answer(service.router, service.store, q, min_relevance=0.1)
    assert tutor.answer(service.router, service.store, q, min_relevance=0.1).reused_from is None
    assert answer_cache.scope_key(SearchFilters(chapter_no=5), "English") != answer_cache.scope_key(
        None, "English"
    )


# ---------------------------------------------------------------- migration


def test_old_database_gets_new_column(tmp_path):
    db = tmp_path / "old.db"
    with sqlite3.connect(db) as conn:  # chunk table as created by the first Phase 1 version (no `kind`)
        conn.execute(
            "CREATE TABLE chunk (id INTEGER PRIMARY KEY, document_id INTEGER, page_no INTEGER, chunk_index INTEGER,"
            " text VARCHAR, text_sha256 VARCHAR, embed_model VARCHAR, dim INTEGER, vector BLOB, created_at DATETIME)"
        )
        conn.execute("INSERT INTO chunk (id, text) VALUES (1, 'old passage')")
    make_engine(db)
    with sqlite3.connect(db) as conn:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(chunk)")]
        kind = conn.execute("SELECT kind FROM chunk WHERE id = 1").fetchone()[0]
    assert "kind" in columns and kind == "text"
    make_engine(db)  # running again is harmless


def test_fake_backend_unused_marker():
    assert FakeBackend  # imported for fixtures
