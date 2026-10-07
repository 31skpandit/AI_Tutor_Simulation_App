"""Pictures from the teacher's own textbook PDF, with their printed captions (for slides and people cards).

Only pictures that have a caption printed right under them are used (e.g. 'Bhilai Steel Plant', 'P. V. Narasimha
Rao'); decorations without a caption (chapter icons, the 'Do you know?' cartoon, QR codes) are skipped. Nothing is
generated — these are the textbook's own illustrations, shown for teaching in your own class.
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pymupdf

MIN_SIDE_PT = 60  # smaller images are icons
CAPTION_GAP_PT = 30  # a caption starts at most this far below the picture
MAX_CAPTION_CHARS = 60
PAGE_PX = 1100


@dataclass(frozen=True)
class Figure:
    page_no: int
    caption: str
    png: bytes


def _caption_below(page: "pymupdf.Page", rect: "pymupdf.Rect") -> str:
    best = ""
    for x0, y0, x1, _y1, text, _n, kind in page.get_text("blocks"):
        if kind != 0:
            continue
        line = " ".join(text.split())
        overlaps = min(x1, rect.x1) - max(x0, rect.x0) > 0.3 * (rect.x1 - rect.x0) or (
            x0 >= rect.x0 - 10 and x1 <= rect.x1 + 10
        )
        # measured: captions in the owner's textbook start 1–2 pt INSIDE the picture's bottom edge
        if -10 <= y0 - rect.y1 <= CAPTION_GAP_PT and overlaps and 2 < len(line) <= MAX_CAPTION_CHARS:
            if not best or y0 < best[1]:
                best = (line, y0)
    return best[0] if best else ""


@lru_cache(maxsize=8)
def extract_figures(pdf_path: str, mtime: float = 0.0) -> tuple[Figure, ...]:
    """Captioned pictures of a PDF, in page order. (mtime only makes the cache notice a changed file.)"""
    figures = []
    with pymupdf.open(pdf_path) as doc:
        for page in doc:
            seen = set()
            for info in page.get_images(full=True):
                xref = info[0]
                for rect in page.get_image_rects(xref):
                    if (
                        rect.width < MIN_SIDE_PT
                        or rect.height < MIN_SIDE_PT
                        or (xref, round(rect.y0)) in seen
                    ):
                        continue
                    seen.add((xref, round(rect.y0)))
                    caption = _caption_below(page, rect)
                    if not caption or re.fullmatch(r"[A-Z0-9]{4,8}", caption):  # QR-code labels like 'RM9DAS'
                        continue
                    zoom = min(3.0, PAGE_PX / max(rect.width, rect.height))
                    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=rect, alpha=False)
                    figures.append(Figure(page.number + 1, caption, pix.tobytes("png")))
    return tuple(figures)


def figures_for(pdf: Path, pages: set[int] | None = None) -> list[Figure]:
    if not pdf.is_file():
        return []
    found = extract_figures(str(pdf), pdf.stat().st_mtime)
    return [f for f in found if pages is None or f.page_no in pages]


def portrait_of(name: str, figures: list[Figure]) -> Figure | None:
    """A textbook picture whose caption is this person's name ('P. V. Narasimha Rao', 'Dr Manmohan Singh')."""
    from app.lessons.history import name_in_text

    for figure in figures:
        if name_in_text(name, figure.caption) and name_in_text(figure.caption, name):
            return figure
    return None
