"""Split any supported file into pages. Each page is either ready text or an image that needs OCR."""

import io
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from PIL import Image, ImageOps

PART_CHARS = 3000  # DOCX / TXT have no pages: they are split into parts of about this size


@dataclass(frozen=True)
class PageInput:
    page_no: int  # 1-based
    text: str | None = None  # set when text could be read directly
    image_png: bytes | None = None  # set when the page must be OCR'd
    method: str = ""  # text_layer | ocr | docx | text


def count_pages(path: Path, kind: str) -> int:
    if kind == "pdf":
        with pymupdf.open(path) as doc:
            return doc.page_count
    if kind == "image":
        with Image.open(path) as img:
            return getattr(img, "n_frames", 1)
    return len(_split_parts(_read_text(path, kind)))


def iter_pages(path: Path, kind: str, *, min_words: int, max_px: int) -> Iterator[PageInput]:
    if kind == "pdf":
        yield from _pdf_pages(path, min_words, max_px)
    elif kind == "image":
        yield from _image_pages(path, max_px)
    elif kind in {"docx", "text"}:
        for no, part in enumerate(_split_parts(_read_text(path, kind)), start=1):
            yield PageInput(page_no=no, text=part, method=kind)
    else:
        raise ValueError(f"Unsupported kind: {kind}")


def page_image(path: Path, kind: str, page_no: int, max_px: int) -> bytes | None:
    """The page image as sent to OCR (None for DOCX/TXT, which have no page images)."""
    if kind == "pdf":
        with pymupdf.open(path) as doc:
            return _render_pdf_page(doc[page_no - 1], max_px)
    if kind == "image":
        with Image.open(path) as img:
            img.seek(page_no - 1)
            return _to_png(img, max_px)
    return None


def render_page_preview(path: Path, kind: str, page_no: int, max_px: int = 1100) -> bytes | None:
    """PNG preview of a page for the review screen (None for DOCX/TXT)."""
    if kind == "pdf":
        with pymupdf.open(path) as doc:
            return _render_pdf_page(doc[page_no - 1], max_px)
    if kind == "image":
        with Image.open(path) as img:
            img.seek(page_no - 1)
            return _to_png(img, max_px)
    return None


# ---------------------------------------------------------------- PDF


def _pdf_pages(path: Path, min_words: int, max_px: int) -> Iterator[PageInput]:
    with pymupdf.open(path) as doc:
        for index, page in enumerate(doc):
            text = page.get_text("text").strip()
            if len(text.split()) >= min_words:
                yield PageInput(page_no=index + 1, text=text, method="text_layer")
            else:
                yield PageInput(page_no=index + 1, image_png=_render_pdf_page(page, max_px), method="ocr")


def _render_pdf_page(page: "pymupdf.Page", max_px: int) -> bytes:
    zoom = max_px / max(page.rect.width, page.rect.height)
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    return pixmap.tobytes("png")


# ---------------------------------------------------------------- images


def _image_pages(path: Path, max_px: int) -> Iterator[PageInput]:
    with Image.open(path) as img:
        for frame in range(getattr(img, "n_frames", 1)):
            img.seek(frame)
            yield PageInput(page_no=frame + 1, image_png=_to_png(img, max_px), method="ocr")


def _to_png(img: Image.Image, max_px: int) -> bytes:
    picture = ImageOps.exif_transpose(img.copy())  # phone photos: honour the rotation flag
    picture = picture.convert("RGB")
    picture.thumbnail((max_px, max_px))
    buffer = io.BytesIO()
    picture.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


# ---------------------------------------------------------------- DOCX / TXT / MD


def _read_text(path: Path, kind: str) -> str:
    if kind == "text":
        return path.read_text(encoding="utf-8", errors="replace")
    import docx  # python-docx

    document = docx.Document(str(path))
    blocks = [p.text for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                blocks.append(" | ".join(cells))
    return "\n\n".join(blocks)


def _split_parts(text: str, size: int = PART_CHARS) -> list[str]:
    paragraphs = [p.strip() for p in text.replace("\r\n", "\n").split("\n\n") if p.strip()]
    parts: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if current and len(current) + len(paragraph) + 2 > size:
            parts.append(current)
            current = paragraph
        else:
            current = f"{current}\n\n{paragraph}" if current else paragraph
    if current:
        parts.append(current)
    return parts
