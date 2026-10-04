"""Vector search and textbook-grounded answers (fake models, offline)."""

from sqlmodel import Session

from app.db.models import Document
from app.rag import tutor
from app.rag.store import SearchFilters, VectorStore
from tests.conftest import FakeBackend, bag_of_words_vector

PASSAGES = {
    "acids": "Acids turn blue litmus red and taste sour.",
    "metals": "Metals are good conductors of heat and electricity.",
    "plants": "Plants make food by photosynthesis using sunlight.",
}


def seed(engine, chapter_for=None):
    store = VectorStore(engine)
    with Session(engine) as s:
        docs = {}
        for name in PASSAGES:
            doc = Document(
                sha256=name,
                filename=f"{name}.pdf",
                rel_path=f"source/{name}.pdf",
                kind="pdf",
                class_level="9",
                subject="Science",
                chapter_no=(chapter_for or {}).get(name, 1),
            )
            s.add(doc)
            s.commit()
            s.refresh(doc)
            docs[name] = doc.id
    for name, text in PASSAGES.items():
        store.add(
            document_id=docs[name],
            page_no=3,
            chunk_index=0,
            text=text,
            text_sha256=name,
            embed_model="ollama/embedder",
            vector=bag_of_words_vector(text),
        )
    return store, docs


def test_search_ranks_the_matching_passage_first(engine):
    store, _ = seed(engine)
    hits = store.search(
        bag_of_words_vector("Which conductors of electricity are good?"), "ollama/embedder", k=2
    )
    assert hits[0].text == PASSAGES["metals"] and hits[0].score > hits[1].score
    assert hits[0].citation == "Ch. 1, page 3"


def test_search_filters_by_chapter(engine):
    store, _ = seed(engine, chapter_for={"acids": 5, "metals": 4, "plants": 6})
    hits = store.search(
        bag_of_words_vector("metals conductors"), "ollama/embedder", k=3, filters=SearchFilters(chapter_no=5)
    )
    assert [h.text for h in hits] == [PASSAGES["acids"]]


def test_search_cache_sees_new_passages(engine):
    store, docs = seed(engine)
    store.search(bag_of_words_vector("acids"), "ollama/embedder")
    store.add(
        document_id=docs["acids"],
        page_no=4,
        chunk_index=0,
        text="Vinegar contains acetic acid.",
        text_sha256="vinegar",
        embed_model="ollama/embedder",
        vector=bag_of_words_vector("vinegar acetic acid"),
    )
    hits = store.search(bag_of_words_vector("vinegar acetic"), "ollama/embedder", k=1)
    assert hits[0].text == "Vinegar contains acetic acid."


def test_search_sees_reindexed_page_even_when_row_ids_are_reused(engine):
    """SQLite reuses ids after deletes; the in-memory vector cache must still refresh."""
    store, docs = seed(engine)
    assert (
        store.search(bag_of_words_vector("acids litmus"), "ollama/embedder", k=1)[0].text == PASSAGES["acids"]
    )
    store.delete_page(docs["plants"], 3)  # removes the highest id
    store.add(
        document_id=docs["plants"],
        page_no=3,
        chunk_index=0,
        text="Copper sulphate crystals are blue.",
        text_sha256="cuso4",
        embed_model="ollama/embedder",
        vector=bag_of_words_vector("copper sulphate blue"),
    )
    hit = store.search(bag_of_words_vector("copper sulphate"), "ollama/embedder", k=1)[0]
    assert hit.text == "Copper sulphate crystals are blue." and hit.score > 0.5


def test_answer_cites_textbook_extracts(make_router, engine):
    store, _ = seed(engine)
    backend = FakeBackend()
    router = make_router(backend)
    result = tutor.answer(router, store, "Why do acids turn blue litmus red?", min_relevance=0.2)
    assert result.grounded and result.text == "answer"
    prompt = backend.calls[-1]["messages"][1]["content"]
    assert "[1] (Ch. 1, page 3)" in prompt and PASSAGES["acids"] in prompt
    assert (
        "Use ONLY facts stated in the numbered textbook extracts"
        in backend.calls[-1]["messages"][0]["content"]
    )


def test_unrelated_question_is_not_answered_from_general_knowledge(make_router, engine):
    store, _ = seed(engine)
    backend = FakeBackend()
    result = tutor.answer(
        make_router(backend), store, "Who won the 1983 cricket world cup?", min_relevance=0.5
    )
    assert not result.grounded and result.text == tutor.NOT_FOUND
    assert not backend.calls  # no chat model call at all


def test_stray_not_found_sentence_is_removed_from_real_answers():
    answer_text = (
        "The bulb glows because the solution contains ions that carry current [1]. " + tutor.NOT_FOUND
    )
    assert tutor.clean_answer(answer_text) == (
        "The bulb glows because the solution contains ions that carry current [1]."
    )
    assert tutor.clean_answer(tutor.NOT_FOUND) == tutor.NOT_FOUND
    assert tutor.clean_answer(f'"{tutor.NOT_FOUND}"') == f'"{tutor.NOT_FOUND}"'


def test_model_saying_not_found_marks_answer_ungrounded(make_router, engine):
    from app.llm.backend import BackendResult

    store, _ = seed(engine)
    backend = FakeBackend([BackendResult(tutor.NOT_FOUND, 10, 10)])
    result = tutor.answer(make_router(backend), store, "acids litmus red", min_relevance=0.2)
    assert not result.grounded


def test_language_examples_are_intact_devanagari():
    assert "अम्ल" in tutor.LANGUAGES["Hindi"] and "आम्ल" in tutor.LANGUAGES["Marathi"]


def test_cloud_switch_uses_the_cloud_task(make_router, engine, config):
    config.tasks["tutor_answer_cloud"] = config.tasks["tutor_answer"].model_copy(
        update={"primary": "openai/cheap"}
    )
    store, _ = seed(engine)
    backend = FakeBackend()
    tutor.answer(make_router(backend), store, "acids litmus red", min_relevance=0.2, cloud=True)
    assert backend.calls[-1]["route"] == "openai/cheap"


def test_hindi_or_marathi_uses_the_indic_task(make_router, engine):
    store, _ = seed(engine)
    backend = FakeBackend()
    tutor.answer(make_router(backend), store, "acids litmus red", language="Marathi", min_relevance=0.2)
    assert "Marathi" in backend.calls[-1]["messages"][0]["content"]
