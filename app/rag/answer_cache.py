"""Semantic answer cache: reuse a tutor answer when a new question means the same as an earlier one.

Safety rules (a wrong reused answer is worse than a slow fresh one):
- same filters and same answer language only;
- only while the search index is unchanged (any page re-indexed → old answers are ignored);
- only above a high similarity threshold, calibrated on real question pairs (blueprint §8.4) so that
  look-alike but different questions (e.g. "gas at the cathode" vs "gas at the anode") are NOT merged.
"""

import json
import re
from dataclasses import asdict

import numpy as np
from sqlalchemy import Engine
from sqlmodel import Session, delete, select

from app.db.models import AnswerCache
from app.rag.store import Hit, SearchFilters, normalise

# Second safety layer: words whose swap changes the meaning ("cathode" vs "anode" scored 0.94 similar).
# If two questions differ by any of these words, the cached answer is never reused.
CONTRAST_WORDS = {
    "cathode",
    "anode",
    "cation",
    "anion",
    "positive",
    "negative",
    "strong",
    "weak",
    "acid",
    "base",
    "acidic",
    "basic",
    "alkali",
    "dilute",
    "concentrated",
    "monobasic",
    "dibasic",
    "tribasic",
    "monoacidic",
    "diacidic",
    "triacidic",
    "oxidation",
    "reduction",
    "oxidising",
    "reducing",
    "endothermic",
    "exothermic",
    "metal",
    "nonmetal",
    "soluble",
    "insoluble",
    "increase",
    "decrease",
    "high",
    "low",
    "hot",
    "cold",
    "before",
    "after",
    "solid",
    "liquid",
    "gas",
    "hydrogen",
    "oxygen",
    "red",
    "blue",
    "not",
    "never",
    "why",
    "how",
}


def _words(text: str) -> set[str]:
    words = set()
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        words.add(word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word)
    return words


def contrast_conflict(question_a: str, question_b: str) -> bool:
    return bool((_words(question_a) ^ _words(question_b)) & CONTRAST_WORDS)


def scope_key(filters: SearchFilters | None, language: str) -> str:
    f = filters or SearchFilters()
    return json.dumps(
        {
            "class": f.class_level,
            "subject": f.subject,
            "chapter": f.chapter_no,
            "docs": sorted(f.document_ids),
            "language": language,
        },
        sort_keys=True,
    )


def lookup(
    engine: Engine,
    vector: list[float],
    scope: str,
    index_version: str,
    min_similarity: float,
    question: str = "",
) -> tuple[AnswerCache, float, list[Hit]] | None:
    query = normalise(vector)
    with Session(engine) as s:
        rows = s.exec(
            select(AnswerCache).where(AnswerCache.scope == scope, AnswerCache.index_version == index_version)
        ).all()
        best, best_score = None, -1.0
        for row in rows:
            if question and contrast_conflict(question, row.question):
                continue
            score = float(np.frombuffer(row.vector, dtype=np.float32) @ query)
            if score > best_score:
                best, best_score = row, score
        if best is None or best_score < min_similarity:
            return None
        best.uses += 1
        s.add(best)
        s.commit()
        s.refresh(best)
    hits = [Hit(**item) for item in json.loads(best.sources)]
    return best, best_score, hits


def save(
    engine: Engine,
    question: str,
    vector: list[float],
    scope: str,
    index_version: str,
    answer_text: str,
    hits: list[Hit],
    model_ref: str | None,
) -> None:
    with Session(engine) as s:
        s.add(
            AnswerCache(
                question=question,
                vector=normalise(vector).tobytes(),
                scope=scope,
                index_version=index_version,
                answer_text=answer_text,
                sources=json.dumps([asdict(h) for h in hits], ensure_ascii=False),
                model_ref=model_ref,
            )
        )
        s.commit()


def clear(engine: Engine) -> int:
    with Session(engine) as s:
        result = s.exec(delete(AnswerCache))
        s.commit()
        return result.rowcount or 0
