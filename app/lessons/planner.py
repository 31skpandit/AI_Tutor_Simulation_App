"""Lesson planner: textbook passages → structured lesson (JSON) → checked equations and molecules.

Evidence comes ONLY from original reviewed passages (never generated summaries — blueprint D21).
Every section cites the passages it uses; the citations are mapped back to page numbers.
"""

import json
import re
from dataclasses import dataclass

from app.lessons import history, maths
from app.lessons.chemistry import check_equation
from app.llm.router import LLMRouter
from app.rag.store import Hit, SearchFilters, VectorStore
from app.rag.tutor import EMBED_TASK, embed_question, original_passages

PLAN_TASK = "lesson_plan"
EVIDENCE_PASSAGES = 8
# A history lesson usually spans a whole chapter (dates and events on every page).
HISTORY_EVIDENCE_PASSAGES = 16
WHOLE_CHAPTER_MAX_CHARS = 60_000  # ≈ 15 000 tokens: a whole chapter costs ≈ 1 ¢ with gpt-5.4-mini
MIN_RELEVANCE = 0.45  # slightly below the tutor's 0.50: a topic name is shorter than a question

SYSTEM_PROMPT = """You are an experienced {audience} teacher preparing a lesson for your own class.
Build the lesson ONLY from the numbered textbook extracts. Do not add facts that are not in them.
Return ONE JSON object with exactly these keys:
{{
 "title": "short lesson title",
 "objectives": ["what students will be able to do", "... (3 to 4 items)"],
 "sections": [ {{"heading": "...", "content": "teaching text in simple English, short paragraphs or bullet points; cite extracts like [1] or [2]", "cites": [1, 2]}} ],
 "key_points": ["one-line takeaways (4 to 6 items)"],
 "equations": [ {{"equation": "balanced equation with Unicode subscripts and charges, e.g. HCl + NaOH → NaCl + H₂O", "meaning": "one sentence"}} ],
 "molecules": [ {{"name": "water", "formula": "H₂O"}} ],
 "simulation": {{"title": "...", "brief": "what the interactive experiment shows, the controls the student can use, what changes on screen and the correct result according to the extracts"}},
 "vocabulary": [ {{"term": "...", "meaning": "..."}} ]
}}
Rules: 3 to 5 sections; equations must be balanced and come from or follow directly from the extracts;
molecules: at most 5 small substances that appear in the lesson; write formulas with Unicode subscripts (H₂SO₄)
and charges with superscripts (Na⁺, Ca²⁺, OH⁻). Output the JSON object only."""


@dataclass
class PlanResult:
    plan: dict
    evidence: list[Hit]
    model_ref: str | None
    cost_usd: float
    warnings: list[str]


class PlanningError(RuntimeError):
    pass


def gather_evidence(
    router: LLMRouter,
    store: VectorStore,
    topic: str,
    filters: SearchFilters | None,
    min_relevance: float = MIN_RELEVANCE,
    count: int = EVIDENCE_PASSAGES,
) -> list[Hit]:
    embed_model = router.config.tasks[EMBED_TASK].primary
    vector = embed_question(router, topic)
    matched = [
        h for h in store.search(vector, embed_model, k=count * 2, filters=filters) if h.score >= min_relevance
    ]
    return original_passages(store, matched, vector, embed_model, count)


def parse_json_object(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise PlanningError("The model did not return a JSON object.")
    value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise PlanningError("The model did not return a JSON object.")
    return value


def parse_plan(text: str) -> dict:
    plan = parse_json_object(text)
    for key in ("title", "sections"):
        if not plan.get(key):
            raise PlanningError(f"The lesson plan has no '{key}'.")
    for key in ("objectives", "key_points", "equations", "molecules", "vocabulary"):
        plan.setdefault(key, [])
    for key in ("timeline", "periods", "people", "places", "cause_effect"):
        plan.setdefault(key, [])
    plan.setdefault("concepts", [])
    plan.setdefault("simulation", {})
    return plan


def lesson_profile(subject: str) -> str:
    """Which lesson design a subject gets: 'maths', 'history' or 'science' (the default)."""
    return "maths" if maths.profile_is_maths(subject) else history.profile(subject)


def check_equations(plan: dict) -> list[dict]:
    """Annotate each equation with the checker's verdict; return the unbalanced ones."""
    bad = []
    for item in plan.get("equations", []):
        result = check_equation(item.get("equation", ""))
        item["balanced"], item["check"] = result.balanced, result.message
        if not result.balanced:
            bad.append(item)
    return bad


def plan_lesson(
    router: LLMRouter,
    store: VectorStore,
    topic: str,
    *,
    filters: SearchFilters | None = None,
    class_level: str = "",
    subject: str = "",
    min_relevance: float = MIN_RELEVANCE,
    whole_chapter: bool = False,  # the lesson IS the chapter (autopilot): give the model the complete chapter
    pages: tuple[int, int]
    | None = None,  # the chapter's first and last page when a file holds several chapters
) -> PlanResult:
    kind = lesson_profile(subject)
    count = HISTORY_EVIDENCE_PASSAGES if kind == "history" else EVIDENCE_PASSAGES
    evidence = []
    if (kind == "history" or whole_chapter) and filters and len(filters.document_ids) == 1:
        # Measured on the owner's history chapter: searching for the topic 'Economic Development' found passages
        # from only 3 of 8 pages (bank nationalisation, the 1975 programme and the 1982 strike were missed). A
        # history lesson follows its whole chapter, so a chapter that fits is given complete, in page order.
        chapter = store.document_text_hits(filters.document_ids[0], router.config.tasks[EMBED_TASK].primary)
        chapter = [h for h in chapter if not pages or pages[0] <= h.page_no <= pages[1]]
        if chapter and sum(len(h.text) for h in chapter) <= WHOLE_CHAPTER_MAX_CHARS:
            evidence = chapter
    if not evidence:
        evidence = gather_evidence(router, store, topic, filters, min_relevance, count)
        evidence = [h for h in evidence if not pages or pages[0] <= h.page_no <= pages[1]]
    evidence = history.without_exercises(evidence)  # no quiz blanks / deliberately wrong pairs
    if not evidence:
        raise PlanningError(
            f"No reviewed textbook pages match '{topic}'. Check the chapter filter or review/index pages."
        )
    audience = " ".join(x for x in [f"Class {class_level}" if class_level else "", subject] if x) or "school"
    extracts = "\n\n".join(f"[{n}] ({hit.citation})\n{hit.text}" for n, hit in enumerate(evidence, start=1))
    prompt = {"history": history.SYSTEM_PROMPT, "maths": maths.SYSTEM_PROMPT}.get(kind, SYSTEM_PROMPT)
    messages = [
        {"role": "system", "content": prompt.format(audience=audience, kinds=", ".join(maths.KINDS))},
        {"role": "user", "content": f"Lesson topic: {topic}\n\nTextbook extracts:\n\n{extracts}"},
    ]
    result = router.complete(PLAN_TASK, messages)
    cost, model_ref = result.cost_usd, result.model_ref
    plan = parse_plan(result.text)
    plan["profile"] = kind
    warnings = []

    if kind == "history":  # dates, names and places must be in the cited textbook text
        warnings += history.verify(plan, {n: hit.text for n, hit in enumerate(evidence, start=1)})
        plan["equations"], plan["molecules"], plan["simulation"] = [], [], {}
    if kind == "maths":  # every answer that can be computed is re-computed; wrong AI answers are corrected
        warnings += maths.verify(plan)
        plan["equations"], plan["molecules"], plan["simulation"] = [], [], {}
    bad = check_equations(plan)
    if bad:  # one correction round with the checker's exact findings
        listing = "\n".join(f"- {item['equation']}: {item['check']}" for item in bad)
        fix = router.complete(
            PLAN_TASK,
            messages
            + [
                {"role": "assistant", "content": result.text},
                {
                    "role": "user",
                    "content": "These equations are not balanced:\n"
                    + listing
                    + "\nReturn the complete JSON object again with these equations corrected.",
                },
            ],
        )
        cost += fix.cost_usd
        try:
            plan = parse_plan(fix.text)
        except (PlanningError, json.JSONDecodeError):
            warnings.append("The correction attempt returned invalid JSON; kept the first plan.")
        bad = check_equations(plan)
        warnings += [f"Equation still not balanced: {item['equation']} — {item['check']}" for item in bad]

    pages = {n: hit.page_no for n, hit in enumerate(evidence, start=1)}
    for section in plan["sections"]:
        cites = [c for c in section.get("cites", []) if isinstance(c, int) and c in pages]
        cites += [int(c) for c in re.findall(r"\[(\d+)\]", section.get("content", "")) if int(c) in pages]
        section["pages"] = sorted({pages[c] for c in cites})
        if not section["pages"]:
            warnings.append(f"Section '{section.get('heading', '?')}' cites no textbook extract — check it.")
    for key in ("timeline", "periods", "people", "places", "cause_effect", "concepts"):
        for item in plan.get(key, []):
            item["pages"] = history.pages_of(item, pages)
    plan["sources"] = [
        {"n": n, "page": hit.page_no, "citation": hit.citation, "text": hit.text}
        for n, hit in enumerate(evidence, start=1)
    ]
    return PlanResult(plan, evidence, model_ref, cost, warnings)


def simulation_facts(plan: dict, limit: int = 6000) -> str:
    """The textbook facts a simulation must agree with: equations + cited source passages."""
    parts = [f"Equation: {e['equation']}" for e in plan.get("equations", []) if e.get("balanced", True)]
    parts += [f"[page {s['page']}] {s['text']}" for s in plan.get("sources", [])]
    return "\n".join(parts)[:limit]
