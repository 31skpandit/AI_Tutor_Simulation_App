"""Textbook-grounded answers with citations (blueprint FR-04, FR-11)."""

import re
from dataclasses import dataclass, replace

from app.llm.router import LLMRouter
from app.rag import answer_cache
from app.rag.store import Hit, SearchFilters, VectorStore

EMBED_TASK = "embed"
# Below this cosine similarity, a passage is treated as unrelated to the question.
# Calibrated on a real chapter with qwen3-embedding:0.6b + the query instruction below (blueprint §8.4):
# questions answered in the chapter scored 0.70–0.84, unrelated questions 0.22–0.34.
MIN_RELEVANCE = 0.50
QUERY_INSTRUCTION = "Instruct: Given a student's question, retrieve textbook passages that answer it\nQuery: "
NOT_FOUND = "This is not covered in the uploaded textbook pages."

LANGUAGES = {
    "English": "Answer in simple English.",
    "Hindi": "Answer in simple Hindi (Devanagari script). Keep scientific terms and formulas in English "
    "in brackets, e.g. अम्ल (acid).",
    "Marathi": "Answer in simple Marathi (Devanagari script). Keep scientific terms and formulas in English "
    "in brackets, e.g. आम्ल (acid).",
}


@dataclass(frozen=True)
class TutorAnswer:
    text: str
    hits: list[Hit]
    grounded: bool
    model_ref: str | None = None
    cost_usd: float = 0.0
    cached: bool = False
    reused_from: str | None = None  # the earlier, similar question whose answer was reused
    similarity: float | None = None


def embed_question(router: LLMRouter, question: str) -> list[float]:
    return router.embed(EMBED_TASK, [QUERY_INSTRUCTION + question]).vectors[0]


def retrieve(
    router: LLMRouter, store: VectorStore, question: str, filters: SearchFilters | None = None, k: int = 5
) -> list[Hit]:
    model = router.config.tasks[EMBED_TASK].primary
    return store.search(embed_question(router, question), model, k=k, filters=filters)


def build_messages(question: str, hits: list[Hit], language: str, class_level: str = "") -> list[dict]:
    audience = f"Class {class_level} students" if class_level else "school students"
    system = (
        f"You are a patient teaching assistant for {audience}.\n"
        "Rules:\n"
        "1. Use ONLY facts stated in the numbered textbook extracts. Do not add analogies, examples or facts "
        "that are not in the extracts.\n"
        "2. After each sentence, cite the extract it comes from, like [1] or [2].\n"
        "3. If the extracts answer only part of the question, answer that part and say which part is not in "
        "the extracts.\n"
        f'4. Only if the extracts contain nothing relevant at all, reply exactly: "{NOT_FOUND}"\n'
        "5. Be clear and short: a few sentences or bullet points.\n"
        f"{LANGUAGES.get(language, LANGUAGES['English'])}"
    )
    extracts = "\n\n".join(f"[{n}] ({hit.label})\n{hit.text}" for n, hit in enumerate(hits, start=1))
    user = f"Textbook extracts:\n\n{extracts}\n\nStudent's question: {question}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def clean_answer(text: str) -> str:
    """Drop a stray 'not covered' sentence that a small model sometimes appends to a real answer."""
    stripped = text.strip()
    if stripped.strip('"') == NOT_FOUND or NOT_FOUND not in stripped:
        return stripped
    without = re.sub(r'\s*"?' + re.escape(NOT_FOUND) + r'"?\s*', " ", stripped).strip()
    return without if len(without) > 40 else stripped


PASSAGES_PER_DESCRIPTION = 2


def original_passages(
    store: VectorStore, matched: list[Hit], vector: list[float], embed_model: str, k: int
) -> list[Hit]:
    """Turn search matches into ORIGINAL textbook passages only.

    Generated summaries / table / figure descriptions help to FIND a page, but they are written by a
    small model and can be wrong (measured: one swapped 'acidity' and 'basicity'). So the tutor never
    sees them: a matched description is replaced by the best original passages of the same page.
    """
    evidence: list[Hit] = []
    seen: set[int] = set()
    for hit in matched:
        if hit.kind == "text":
            candidates = [hit]
        else:
            page_passages = store.page_text_hits(hit.document_id, hit.page_no, vector, embed_model)
            candidates = [replace(p, via=hit.kind) for p in page_passages[:PASSAGES_PER_DESCRIPTION]]
        for candidate in candidates:
            if candidate.chunk_id not in seen:
                evidence.append(candidate)
                seen.add(candidate.chunk_id)
        if len(evidence) >= k:
            break
    return evidence[:k]


def answer(
    router: LLMRouter,
    store: VectorStore,
    question: str,
    *,
    filters: SearchFilters | None = None,
    language: str = "English",
    k: int = 5,
    min_relevance: float = MIN_RELEVANCE,
    semantic_cache_min: float | None = None,  # None = do not reuse answers of similar questions
    cloud: bool = False,  # English answers by the cloud model (better with tables)
) -> TutorAnswer:
    embed_model = router.config.tasks[EMBED_TASK].primary
    vector = embed_question(router, question)
    scope = answer_cache.scope_key(filters, language) + (":cloud" if cloud else "")
    index_version = store.version_key(embed_model)
    if semantic_cache_min is not None:
        found = answer_cache.lookup(store.engine, vector, scope, index_version, semantic_cache_min, question)
        if found is not None:
            entry, similarity, hits = found
            return TutorAnswer(
                text=entry.answer_text,
                hits=hits,
                grounded=True,
                model_ref=entry.model_ref,
                cached=True,
                reused_from=entry.question,
                similarity=similarity,
            )

    hits = store.search(vector, embed_model, k=k * 2, filters=filters)
    matched = [h for h in hits if h.score >= min_relevance]
    if not matched:
        return TutorAnswer(text=NOT_FOUND, hits=hits[:k], grounded=False)
    relevant = original_passages(store, matched, vector, embed_model, k)
    if not relevant:
        return TutorAnswer(text=NOT_FOUND, hits=matched[:k], grounded=False)
    if language != "English":
        task = "tutor_answer_indic"
    elif cloud and "tutor_answer_cloud" in router.config.tasks:
        task = "tutor_answer_cloud"
    else:
        task = "tutor_answer"
    class_level = relevant[0].class_level
    result = router.complete(task, build_messages(question, relevant, language, class_level))
    text = clean_answer(result.text)
    grounded = text != NOT_FOUND
    if grounded and semantic_cache_min is not None:
        answer_cache.save(
            store.engine, question, vector, scope, index_version, text, relevant, result.model_ref
        )
    return TutorAnswer(
        text=text,
        hits=relevant,
        grounded=grounded,
        model_ref=result.model_ref,
        cost_usd=result.cost_usd,
        cached=result.cached,
    )
