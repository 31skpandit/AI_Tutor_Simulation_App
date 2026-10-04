"""OCR of one page image through the model router (tasks `ocr` / `ocr_retry` in config/models.yaml).

Small vision models sometimes get stuck repeating one line (measured on a real chapter: one line
196 times). Such output is detected, retried once with a repetition penalty (task `ocr_retry`), and,
if still repetitive, cleaned and flagged for the teacher's review.
"""

import base64
import re
import zlib
from collections import Counter
from dataclasses import dataclass

from app.llm.router import AllModelsFailed, LLMResult, LLMRouter

OCR_PROMPT = """You are transcribing ONE page of a school textbook so a teacher can search it.
Transcribe ALL text exactly as printed, in reading order, in the original language and script.
Rules:
- Keep headings, numbered points, activity / box titles and captions on their own lines.
- Write chemical formulas and equations exactly (for example H₂SO₄ and 2Na + 2H₂O → 2NaOH + H₂).
- Write every table as a Markdown table: a header row, a separator row (| --- |), then one row per printed
  row. Keep empty cells empty (exercise tables often have blank cells for students to fill in).
- ONLY if the page shows a figure, diagram, photo or drawing, add one line per figure:
  [Figure: <figure number and caption if printed>; <what it shows>; labels: <labels written on it>].
  If there is no figure, do not write any [Figure: ...] line.
- Do not explain, summarise, translate or add anything that is not on the page.
Output only the transcription."""

# Lines like "[Figure: ... no figure is present ...]" that small models write when there is no figure.
_EMPTY_FIGURE_LINE = re.compile(
    r"^\s*\[Figure:[^\]]*\b(no (figure|diagram|image)s? (is |are )?(present|shown|visible)|"
    r"not (present|shown|visible)|there is no (figure|diagram))[^\]]*\]\s*$",
    re.I | re.M,
)


_SEPARATOR_CELL = re.compile(r"^:?-{3,}:?$")


def _cells(line: str) -> list[str]:
    inner = line.strip()
    inner = inner[1:] if inner.startswith("|") else inner
    inner = inner[:-1] if inner.endswith("|") else inner
    return [cell.strip() for cell in inner.split("|")]


def normalize_markdown_tables(text: str) -> str:
    """Make every Markdown table renderable: same number of cells in every row, and a separator row.

    Small OCR models often write a header with fewer cells than the data rows (measured on a real page:
    6 header cells, 7 data cells), which makes the last column disappear when the table is displayed.
    """
    lines = text.split("\n")
    output: list[str] = []
    index = 0
    while index < len(lines):
        if not lines[index].strip().startswith("|"):
            output.append(lines[index])
            index += 1
            continue
        block = []
        while index < len(lines) and lines[index].strip().startswith("|"):
            block.append(_cells(lines[index]))
            index += 1

        def is_separator(row: list[str]) -> bool:  # "| --- | --- |" (an all-empty row is NOT a separator)
            filled = [c for c in row if c]
            return bool(filled) and all(_SEPARATOR_CELL.match(c) for c in filled)

        rows = [row for row in block if not is_separator(row)]
        if not rows:
            continue
        width = max(len(row) for row in rows)
        padded = [row + [""] * (width - len(row)) for row in rows]
        output.append("| " + " | ".join(padded[0]) + " |")
        output.append("| " + " | ".join(["---"] * width) + " |")
        output.extend("| " + " | ".join(row) + " |" for row in padded[1:])
    return "\n".join(output)


def clean_ocr_text(text: str) -> str:
    """Remove placeholder figure lines for figures that do not exist; repair Markdown tables."""
    text = _EMPTY_FIGURE_LINE.sub("", text)
    text = normalize_markdown_tables(text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


MIN_COMPRESSION_RATIO = 0.2  # normal textbook pages measured at ~0.42–0.48; the stuck page at 0.07
MAX_SAME_LINE = 6  # the same (non-trivial) line more often than this = stuck


@dataclass(frozen=True)
class OcrOutcome:
    text: str
    model_ref: str
    warning: str | None = None  # shown on the Review screen


def ocr_page_once(router: LLMRouter, image_png: bytes, task: str = "ocr") -> LLMResult:
    image_b64 = base64.b64encode(image_png).decode("ascii")
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": OCR_PROMPT},
                # detail=high: cloud models read small print (subscripts) at full resolution; Ollama ignores it
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_b64}", "detail": "high"},
                },
            ],
        }
    ]
    return router.complete(task, messages)


def looks_degenerate(text: str) -> bool:
    data = text.encode("utf-8")
    if len(data) > 1500 and len(zlib.compress(data)) / len(data) < MIN_COMPRESSION_RATIO:
        return True
    lines = [line.strip() for line in text.splitlines() if len(line.strip()) > 10]
    return bool(lines) and Counter(lines).most_common(1)[0][1] > MAX_SAME_LINE


def collapse_repeats(text: str, keep: int = 2) -> str:
    """Keep at most `keep` copies of any non-trivial line."""
    seen: Counter = Counter()
    output = []
    for line in text.splitlines():
        key = line.strip()
        if len(key) > 10:
            seen[key] += 1
            if seen[key] > keep:
                continue
        output.append(line)
    return "\n".join(output)


def ocr_page(
    router: LLMRouter, image_png: bytes, *, task: str = "ocr", retry_task: str | None = "ocr_retry"
) -> OcrOutcome:
    """OCR with automatic recovery from repetition loops. Raises AllModelsFailed if nothing works."""
    retry_task = retry_task if retry_task in router.config.tasks else None
    first: LLMResult | None = None
    try:
        first = ocr_page_once(router, image_png, task)
        if not looks_degenerate(first.text):
            return OcrOutcome(clean_ocr_text(first.text), first.model_ref)
    except AllModelsFailed:
        if retry_task is None:
            raise
    if retry_task is not None:
        try:
            second = ocr_page_once(router, image_png, retry_task)
        except AllModelsFailed:
            if first is None:
                raise
        else:
            if not looks_degenerate(second.text):
                return OcrOutcome(clean_ocr_text(second.text), second.model_ref)
            first = first or second
    assert first is not None
    return OcrOutcome(
        clean_ocr_text(collapse_repeats(first.text)),
        first.model_ref,
        warning="The OCR model repeated some text; repeats were removed. Please check this page carefully.",
    )
