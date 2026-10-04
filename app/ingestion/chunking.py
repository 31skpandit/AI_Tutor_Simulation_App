"""Split page text into overlapping, paragraph-aware chunks for search."""

import hashlib
import re

_SENTENCE_END = re.compile(r"(?<=[.!?।])\s+")


def normalize_for_hash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def text_hash(text: str) -> str:
    return hashlib.sha256(normalize_for_hash(text).encode("utf-8")).hexdigest()


def chunk_text(text: str, max_chars: int = 1500, overlap_chars: int = 200) -> list[str]:
    """Paragraph-aware chunks of at most ~max_chars; each chunk repeats the end of the previous one."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text.replace("\r\n", "\n")) if p.strip()]
    pieces: list[str] = []
    for paragraph in paragraphs:  # break very long paragraphs at sentence ends
        if len(paragraph) <= max_chars:
            pieces.append(paragraph)
            continue
        sentence_buffer = ""
        for sentence in _SENTENCE_END.split(paragraph):
            if sentence_buffer and len(sentence_buffer) + len(sentence) + 1 > max_chars:
                pieces.append(sentence_buffer)
                sentence_buffer = sentence
            else:
                sentence_buffer = f"{sentence_buffer} {sentence}".strip()
        while len(sentence_buffer) > max_chars:  # no sentence breaks at all
            pieces.append(sentence_buffer[:max_chars])
            sentence_buffer = sentence_buffer[max_chars:]
        if sentence_buffer:
            pieces.append(sentence_buffer)

    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if current and len(current) + len(piece) + 2 > max_chars:
            chunks.append(current)
            tail = _overlap_tail(current, overlap_chars)
            current = f"{tail}\n\n{piece}" if tail else piece
        else:
            current = f"{current}\n\n{piece}" if current else piece
    if current.strip():
        chunks.append(current)
    return chunks


def _overlap_tail(text: str, overlap_chars: int) -> str:
    if overlap_chars <= 0:
        return ""
    tail = text[-overlap_chars:]
    cut = tail.find(" ")  # start at a word boundary
    return tail[cut + 1 :] if 0 <= cut < len(tail) - 1 else tail
