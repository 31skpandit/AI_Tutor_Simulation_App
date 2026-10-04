import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make ui/common.py importable

import common  # noqa: E402,F401
import streamlit as st  # noqa: E402
from common import ingestion_or_stop, page  # noqa: E402

from app.llm.router import AllModelsFailed  # noqa: E402
from app.rag import tutor  # noqa: E402
from app.rag.store import SearchFilters  # noqa: E402

page("AI Tutor", "💬")
st.title("💬 AI Tutor")
service, _ = ingestion_or_stop()
router = service.router

mode = st.radio(
    "Answer from", ["My textbook (uploaded pages)", "General knowledge (connectivity test)"], horizontal=True
)
textbook_mode = mode.startswith("My textbook")

if textbook_mode:
    searchable = [d for d in service.documents() if service.page_counts(d.id)["indexed"]]
    if not searchable:
        st.info(
            "No textbook pages are searchable yet. On **Syllabus Library** add a file, review its pages on "
            "**Review Text**, then click *Make reviewed pages searchable*."
        )
        st.stop()
    c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
    classes = sorted({d.class_level for d in searchable if d.class_level})
    subjects = sorted({d.subject for d in searchable if d.subject})
    chapters = sorted({d.chapter_no for d in searchable if d.chapter_no})
    class_level = c1.selectbox("Class", ["All", *classes])
    subject = c2.selectbox("Subject", ["All", *subjects])
    chapter = c3.selectbox("Chapter", ["All", *chapters])
    language = c4.radio(
        "Answer language",
        list(tutor.LANGUAGES),
        horizontal=True,
        help="English by default. Choose Hindi or Marathi only when a student asks for it.",
    )
    filters = SearchFilters(
        class_level=None if class_level == "All" else class_level,
        subject=None if subject == "All" else subject,
        chapter_no=None if chapter == "All" else int(chapter),
    )
    answer_model = st.radio(
        "Answer model (English)",
        ["Local (free)", "Cloud gpt-5-nano (≈ $0.001 per answer, better with tables)"],
        horizontal=True,
        help="Hindi / Marathi answers always use the stronger cloud model when available.",
    )
    t1, t2 = st.columns(2)
    fallback_general = t1.toggle(
        "If the answer is not in the textbook, give a general answer (clearly marked)", value=False
    )
    settings = common.get_settings()
    reuse_similar = t2.toggle(
        "Reuse answers to very similar earlier questions (instant)",
        value=settings.semantic_cache,
        help="Only when the question means the same, with the same filters and language, and the textbook "
        "pages have not changed since. Turn off to always get a fresh answer.",
    )
else:
    st.warning("General mode does not use your textbook. Use it only to test that the AI models work.")
    general_task = st.radio("Model", ["Local (free)", "OpenAI gpt-5-nano (paid)"], horizontal=True)

GENERAL_PROMPT = (
    "You are a friendly teaching assistant for school students. Explain clearly and briefly in English, "
    "unless the user explicitly asks for Hindi or Marathi."
)

st.session_state.setdefault("tutor_history", [])
for turn in st.session_state.tutor_history:
    with st.chat_message(turn["role"]):
        st.markdown(turn["content"])
        if turn.get("meta"):
            st.caption(turn["meta"])
        for source in turn.get("sources", []):
            with st.expander(source["title"]):
                st.text(source["text"])


def general_answer(question: str, task: str) -> tuple[str, str]:
    result = router.complete(
        task, [{"role": "system", "content": GENERAL_PROMPT}, {"role": "user", "content": question}]
    )
    meta = f"{result.model_ref} · ${result.cost_usd:.6f}" + (" · cached" if result.cached else "")
    return result.text, meta


if question := st.chat_input("Ask a question…"):
    st.session_state.tutor_history.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"), st.spinner("Searching the textbook and thinking…"):
        turn = {"role": "assistant", "content": "", "meta": "", "sources": []}
        try:
            if textbook_mode:
                result = tutor.answer(
                    router,
                    service.store,
                    question,
                    filters=filters,
                    language=language,
                    semantic_cache_min=settings.semantic_cache_min if reuse_similar else None,
                    cloud=answer_model.startswith("Cloud"),
                )
                turn["sources"] = [
                    {"title": f"[{n}] {hit.label} — relevance {hit.score:.2f}", "text": hit.text}
                    for n, hit in enumerate(result.hits, start=1)
                ]
                if result.grounded:
                    turn["content"] = result.text
                    if result.reused_from:
                        turn["meta"] = (
                            f"♻️ Reused the answer to an earlier, very similar question: “{result.reused_from}” "
                            f"(similarity {result.similarity:.3f}) · $0 · turn off *Reuse answers* for a fresh one"
                        )
                    else:
                        turn["meta"] = (
                            f"📖 From your textbook · {result.model_ref} · ${result.cost_usd:.6f}"
                            + (" · cached" if result.cached else "")
                        )
                elif fallback_general:
                    text, meta = general_answer(question, "test_local")
                    turn["content"] = f"⚠️ **Not found in your textbook pages.** General answer:\n\n{text}"
                    turn["meta"] = f"General knowledge · {meta}"
                else:
                    turn["content"] = f"📕 {tutor.NOT_FOUND}"
                    turn["meta"] = (
                        "Try another chapter filter, or check that the right pages are reviewed and searchable."
                    )
            else:
                task = "test_local" if general_task.startswith("Local") else "test_openai"
                turn["content"], turn["meta"] = general_answer(question, task)
        except AllModelsFailed as err:
            turn["content"] = "❌ No model could answer:\n\n" + "\n".join(
                f"- `{a.model_ref}` → {a.outcome}" for a in err.attempts
            )
        st.markdown(turn["content"])
        if turn["meta"]:
            st.caption(turn["meta"])
        for source in turn["sources"]:
            with st.expander(source["title"]):
                st.text(source["text"])
        st.session_state.tutor_history.append(turn)

if st.session_state.tutor_history and st.button("Clear conversation"):
    st.session_state.tutor_history = []
    st.rerun()
