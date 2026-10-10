"""Automatic quality check of an extracted page (the checks the teacher would otherwise do by eye).

Each page gets 'clean' (safe to make searchable without waiting) or 'check' (please look) with plain reasons.
The checks are deliberately simple and explainable; anything doubtful is sent to the teacher, never hidden:
  - no text / very little text (a picture-only page, or a page the reader missed);
  - unreadable characters (a PDF font without proper text encoding gives private-use or replacement characters);
  - mostly symbols or numbers, or many words split into single letters (bad OCR or broken text layer);
  - an OCR warning (e.g. a line repeated in a loop and removed);
  - a table read by OCR (the local model sometimes misaligns tables — compare it, or use the cloud re-read);
  - Marathi/Hindi (Devanagari) text: lesson fact checks support English-medium books only so far.
Exercise pages are labelled (they are fine to search, and are never used as lesson facts).
"""

import re
from dataclasses import dataclass, field

MIN_WORDS = 30
MAX_ODD_CHARS = 0.005  # share of private-use / replacement / control characters
MIN_LETTER_SHARE = 0.55
MAX_SINGLE_LETTER_WORDS = 0.15
MAX_DEVANAGARI = 0.3
OCR_METHODS = {"ocr", "ocr_reused", "ocr_cloud"}


@dataclass
class Quality:
    status: str  # clean | check
    reasons: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)  # e.g. 'exercises' (information, not a problem)


def _odd(char: str) -> bool:
    code = ord(char)
    return 0xE000 <= code <= 0xF8FF or char == "�" or (code < 32 and char not in "\n\r\t")


def assess(text: str, method: str = "text_layer", warning: str | None = None) -> Quality:
    from app.lessons.history import is_exercise  # same exercise detector as the lesson planner

    reasons: list[str] = []
    labels: list[str] = []
    words = re.findall(r"\S+", text)
    visible = [c for c in text if not c.isspace()]
    if not words:
        return Quality(
            "check", ["no text was found on this page (a picture-only page, or the reader missed it)"]
        )
    if len(words) < MIN_WORDS:
        reasons.append(f"very little text ({len(words)} words) — a mostly-picture page, or text was missed")
    odd = sum(_odd(c) for c in text)
    if odd / max(len(text), 1) > MAX_ODD_CHARS:
        reasons.append(
            f"{odd} unreadable characters (the PDF's font has no proper text) — use the cloud re-read"
        )
    devanagari = sum("ऀ" <= c <= "ॿ" for c in visible)
    if devanagari / max(len(visible), 1) > MAX_DEVANAGARI:
        reasons.append("Marathi/Hindi text — the lesson fact checks support English-medium books only so far")
    else:
        letters = sum(c.isalpha() for c in visible)
        if letters / max(len(visible), 1) < MIN_LETTER_SHARE:
            reasons.append("mostly symbols or numbers — check that the text was read correctly")
        single = [w for w in words if len(w) == 1 and w.isalpha() and w not in {"a", "A", "I"}]
        if len(single) / len(words) > MAX_SINGLE_LETTER_WORDS:
            reasons.append("many words are split into single letters — the text layer or OCR is broken")
    if warning:
        reasons.append(f"OCR warning: {warning}")
    # tables by the LOCAL OCR model only (the cloud re-read was measured correct on tables)
    if (
        method in {"ocr", "ocr_reused"}
        and sum(line.strip().startswith("|") for line in text.splitlines()) >= 2
    ):
        reasons.append("has a table read by OCR — compare it with the page (or use the cloud re-read)")
    if is_exercise(text):
        labels.append("exercises")
    return Quality("check" if reasons else "clean", reasons, labels)


def guess_chapter_title(first_page_text: str) -> str:
    """'4 Economic Development\\n\\nWe are going to study…' → 'Economic Development'. Empty if unsure."""
    for line in first_page_text.splitlines()[:8]:
        line = re.sub(r"^#+\s*", "", line.strip())  # Markdown headings from OCR
        line = re.sub(r"^(chapter|lesson|unit)\s*\d+\s*[:.\-–]?\s*", "", line, flags=re.I)
        line = re.sub(r"^\d{1,2}\s*[.:\-–]?\s+", "", line).strip(" :.-–")
        words = line.split()
        if 1 <= len(words) <= 8 and sum(c.isalpha() for c in line) >= 4 and not line.endswith((".", ",")):
            if line.isdigit():
                continue
            return line
    return ""


_NOT_TITLE = re.compile(
    r"^(example|practice|exercise|let.?s|now i know|figure|fig\.|table|activity|note)\b", re.I
)


def _title_line(line: str) -> str:
    line = line.strip().strip(":.-–").strip()
    words = line.split()
    if not (1 <= len(words) <= 8) or sum(c.isalpha() for c in line) < 4 or line.endswith((".", ",", "?")):
        return ""
    if not line[0].isupper() or _NOT_TITLE.match(line) or re.search(r"[=×÷+<>()\[\]]", line):
        return ""
    return line


def _chapter_start(text: str) -> tuple[int, str] | None:
    """'3 HCF and LCM …' or '4\n\nAngles and Pairs of Angles …' or 'Chapter 5: Acids …' at the top of a page."""
    lines = [x.strip() for x in text.splitlines() if x.strip()][:3]
    for i, line in enumerate(lines[:2]):
        line = re.sub(r"^#+\s*", "", line)
        match = re.match(r"^(?:chapter|lesson|unit)?\s*(\d{1,2})\s*[.:\-–]?\s*(.*)$", line, re.I)
        if not match or not 1 <= int(match.group(1)) <= 40:
            continue
        title = _title_line(match.group(2)) if match.group(2) else ""
        if not title and not match.group(2) and i + 1 < len(lines):
            title = _title_line(lines[i + 1])
        if title:
            return int(match.group(1)), title
    return None


def find_chapters(pages: list[tuple[int, str]]) -> list[dict]:
    """Several chapters in one file → [{'no', 'title', 'start', 'end'}] (page ranges). Empty for a single chapter.

    A chapter start must be on page 1 and the numbers must run on (3 → 4 → 5), so a page beginning with a stray
    number ('2 40 …' in a division) is never mistaken for a chapter."""
    pages = sorted((n, t or "") for n, t in pages)
    starts = []
    for page_no, text in pages:
        found = _chapter_start(text)
        if found and (not starts and page_no == pages[0][0] or starts and found[0] == starts[-1]["no"] + 1):
            starts.append({"no": found[0], "title": found[1], "start": page_no})
    if len(starts) < 2:
        return []
    for chapter, following in zip(starts, starts[1:] + [None], strict=True):
        chapter["end"] = following["start"] - 1 if following else pages[-1][0]
    return starts
