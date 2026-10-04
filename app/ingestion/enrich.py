"""Extra searchable entries per page: a short summary + one description per table and per figure.

Students rarely word a question like the textbook. A plain-language description of a table ("lists acids
HCl, HNO₃ ... to classify them by basicity") or a figure lets the search find that page anyway; the
tutor still cites the page and shows the original passage. Generated once per page text (cached).
"""

import json
import re
from dataclasses import dataclass, field

from app.llm.router import LLMRouter

ENRICH_TASK = "enrich"
MIN_PAGE_CHARS = 300  # very short pages (e.g. a title page) are not worth summarising

PROMPT = """Below is the text of ONE page of a school textbook ({heading}).
Return a JSON object with exactly these keys:
"summary": 2 or 3 sentences saying what this page teaches,
"tables": a list with one object {{"title": ..., "description": ...}} per table on the page; the description says what the table lists or compares and names its rows and columns,
"figures": a list with one object {{"title": ..., "description": ...}} per "[Figure: ...]" line; the description says what the figure shows.
Use ONLY information in the page text. Use empty lists when there are no tables or figures. Output the JSON object only.

Page text:
{text}"""


@dataclass
class Enrichment:
    summary: str = ""
    tables: list[tuple[str, str]] = field(default_factory=list)
    figures: list[tuple[str, str]] = field(default_factory=list)

    def entries(self, page_no: int) -> list[tuple[str, str]]:
        """(kind, text) pairs to index."""
        items: list[tuple[str, str]] = []
        if self.summary:
            items.append(("summary", f"Summary of page {page_no}: {self.summary}"))
        items += [("table", f"Table on page {page_no}: {t}. {d}".strip()) for t, d in self.tables]
        items += [("figure", f"Figure on page {page_no}: {t}. {d}".strip()) for t, d in self.figures]
        return items


def parse_enrichment(text: str) -> Enrichment:
    """Parse the model's JSON (tolerating text around it). Raises ValueError if unusable."""
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("no JSON object in model output")
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("JSON is not an object")

    def pairs(key: str) -> list[tuple[str, str]]:
        result = []
        for item in data.get(key) or []:
            if isinstance(item, dict):
                title = str(item.get("title") or "").strip()
                description = str(item.get("description") or "").strip()
                if title or description:
                    result.append((title, description))
        return result

    return Enrichment(
        summary=str(data.get("summary") or "").strip(), tables=pairs("tables"), figures=pairs("figures")
    )


def enrich_page(router: LLMRouter, page_text: str, heading: str) -> Enrichment | None:
    """None for pages too short to be worth it. Raises AllModelsFailed / ValueError on failure."""
    if len(page_text.strip()) < MIN_PAGE_CHARS or ENRICH_TASK not in router.config.tasks:
        return None
    result = router.complete(
        ENRICH_TASK, [{"role": "user", "content": PROMPT.format(heading=heading, text=page_text.strip())}]
    )
    return parse_enrichment(result.text)
