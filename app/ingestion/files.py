"""File types, content hashing and metadata guessing."""

import hashlib
import re
from pathlib import Path

SUPPORTED_KINDS: dict[str, str] = {
    ".pdf": "pdf",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
    ".bmp": "image",
    ".tif": "image",
    ".tiff": "image",
    ".docx": "docx",
    ".txt": "text",
    ".md": "text",
}
UPLOAD_TYPES = sorted(ext.lstrip(".") for ext in SUPPORTED_KINDS)

KNOWN_SUBJECTS = [
    "Science",
    "Physics",
    "Chemistry",
    "Biology",
    "Mathematics",
    "Maths",
    "Math",
    "Geography",
    "History",
    "Civics",
    "Political Science",
    "Economics",
    "English",
    "Hindi",
    "Marathi",
    "Sanskrit",
    "Computer",
    "Environmental Studies",
    "EVS",
]


def file_kind(path: Path | str) -> str | None:
    return SUPPORTED_KINDS.get(Path(path).suffix.lower())


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def guess_metadata(filename: str) -> dict:
    """Best-effort guess from names like 'Class 9 - Science - 5th Chapter.pdf'. Always editable later."""
    stem = re.sub(r"[_\-.]+", " ", Path(filename).stem)  # "std10_maths_chapter-3" → "std10 maths chapter 3"
    meta: dict = {"class_level": "", "subject": "", "chapter_no": None, "chapter_title": ""}
    if m := re.search(r"(?:class|std|standard|grade)\s*[-_ ]?\s*(\d{1,2})", stem, re.I):
        meta["class_level"] = m.group(1)
    if m := re.search(r"(?:chapter|ch|lesson|unit)\s*[-_.: ]?\s*(\d{1,2})\b", stem, re.I) or re.search(
        r"\b(\d{1,2})(?:st|nd|rd|th)\s*(?:chapter|lesson|unit)", stem, re.I
    ):
        meta["chapter_no"] = int(m.group(1))
    for subject in sorted(KNOWN_SUBJECTS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(subject)}\b", stem, re.I):
            meta["subject"] = "Mathematics" if subject.lower() in {"maths", "math"} else subject
            break
    return meta


def unique_target(directory: Path, filename: str) -> Path:
    """A path in `directory` for `filename` that does not overwrite an existing file."""
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", Path(filename).name).strip() or "upload"
    target = directory / safe
    counter = 2
    while target.exists():
        target = directory / f"{Path(safe).stem} ({counter}){Path(safe).suffix}"
        counter += 1
    return target
