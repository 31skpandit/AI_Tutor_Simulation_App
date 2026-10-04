"""Ingestion pipeline (blueprint Fig. 3).

    register (SHA-256 dedup) → extract pages (text layer / OCR, resumable, OCR reuse by image hash)
    → your review → index (chunk → skip duplicate passages → embed → store)

Every step is idempotent: running it again never repeats finished work.
"""

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger
from sqlalchemy import Engine
from sqlmodel import Session, col, delete, func, select

from app.core.config import PROJECT_ROOT, Settings
from app.db.models import Document, Job, Page, utcnow
from app.ingestion.chunking import chunk_text, text_hash
from app.ingestion.enrich import enrich_page
from app.ingestion.extract import count_pages, iter_pages, page_image
from app.ingestion.files import file_kind, guess_metadata, sha256_bytes, sha256_file, unique_target
from app.ingestion.ocr import clean_ocr_text, normalize_markdown_tables, ocr_page
from app.llm.router import AllModelsFailed, LLMRouter
from app.rag.store import VectorStore

Progress = Callable[[float, str], None]
EMBED_TASK = "embed"
EMBED_BATCH = 16
CLOUD_OCR_TASK = "ocr_cloud"
# Measured on the owner's chapter with gpt-5.4-mini (≈ 2,400 input + 560–790 output tokens per page).
CLOUD_OCR_COST_PER_PAGE_USD = 0.005


def _noop(_fraction: float, _message: str) -> None:
    pass


@dataclass
class AddResult:
    status: str  # new | duplicate | unsupported | error
    path: Path
    document: Document | None = None
    duplicate_of: Document | None = None
    message: str = ""


@dataclass
class ScanReport:
    new: list[AddResult] = field(default_factory=list)
    duplicates: list[AddResult] = field(default_factory=list)
    unsupported: list[Path] = field(default_factory=list)
    errors: list[AddResult] = field(default_factory=list)
    known: int = 0


class IngestionService:
    def __init__(self, engine: Engine, router: LLMRouter, settings: Settings):
        self.engine = engine
        self.router = router
        self.settings = settings
        self.store = VectorStore(engine)
        # path → (size, mtime_ns, sha256): avoids re-hashing unchanged files on every scan
        self._hash_cache: dict[str, tuple[int, int, str]] = {}

    @property
    def embed_model(self) -> str:
        return self.router.config.tasks[EMBED_TASK].primary

    # ------------------------------------------------------------ registration
    def scan_source(self, *, enqueue: bool = True) -> ScanReport:
        """Register every supported file in the source folder that is not already known."""
        report = ScanReport()
        for path in sorted(p for p in self.settings.source_dir.rglob("*") if p.is_file()):
            if path.name.startswith(("~$", ".")):
                continue  # Office lock files, hidden files
            if file_kind(path) is None:
                report.unsupported.append(path)
                continue
            result = self.add_file(path, enqueue=enqueue)
            if result.status == "new":
                report.new.append(result)
            elif result.status == "duplicate":
                if result.duplicate_of and Path(result.duplicate_of.rel_path) == self._rel(path):
                    report.known += 1  # the file itself, already registered
                else:
                    report.duplicates.append(result)
            elif result.status == "error":
                report.errors.append(result)
        return report

    def add_file(self, path: Path, meta: dict | None = None, *, enqueue: bool = True) -> AddResult:
        path = Path(path)
        kind = file_kind(path)
        if kind is None:
            return AddResult("unsupported", path, message=f"Unsupported file type: {path.suffix}")
        try:
            digest = self._hash(path)
        except OSError as exc:
            return AddResult("error", path, message=f"Cannot read file: {exc}")
        with Session(self.engine) as s:
            existing = s.exec(select(Document).where(Document.sha256 == digest)).first()
            if existing:
                return AddResult(
                    "duplicate",
                    path,
                    duplicate_of=existing,
                    message=f"Same content as already registered '{existing.filename}'",
                )
        try:
            pages = count_pages(path, kind)
        except Exception as exc:  # noqa: BLE001 — corrupt / password-protected files
            return AddResult("error", path, message=f"Cannot open file: {type(exc).__name__}: {exc}")
        info = guess_metadata(path.name) | {k: v for k, v in (meta or {}).items() if v not in (None, "")}
        document = Document(
            sha256=digest,
            filename=path.name,
            rel_path=str(self._rel(path)),
            kind=kind,
            size_bytes=path.stat().st_size,
            page_count=pages,
            class_level=str(info.get("class_level") or ""),
            subject=info.get("subject") or "",
            chapter_no=info.get("chapter_no"),
            chapter_title=info.get("chapter_title") or "",
        )
        with Session(self.engine) as s:
            s.add(document)
            s.commit()
            s.refresh(document)
        logger.info(f"Registered document {document.id}: {document.filename} ({kind}, {pages} pages)")
        if enqueue:
            self.enqueue("extract", document.id)
        return AddResult("new", path, document=document)

    def save_upload(
        self, filename: str, data: bytes, meta: dict | None = None, *, enqueue: bool = True
    ) -> AddResult:
        """Save an uploaded file into the source folder (unless identical content is already registered)."""
        kind = file_kind(filename)
        if kind is None:
            return AddResult(
                "unsupported", Path(filename), message=f"Unsupported file type: {Path(filename).suffix}"
            )
        digest = sha256_bytes(data)
        with Session(self.engine) as s:
            existing = s.exec(select(Document).where(Document.sha256 == digest)).first()
        if existing:
            return AddResult(
                "duplicate",
                Path(filename),
                duplicate_of=existing,
                message=f"Same content as already registered '{existing.filename}' — skipped",
            )
        target = unique_target(self.settings.source_dir, filename)
        target.write_bytes(data)
        return self.add_file(target, meta, enqueue=enqueue)

    # ------------------------------------------------------------ extraction
    def extract_document(self, document_id: int, progress: Progress = _noop) -> dict:
        """Extract every page that is not done yet. Safe to re-run; resumes after interruptions."""
        document = self._document(document_id)
        path = PROJECT_ROOT / document.rel_path
        if not path.exists():
            self._set_status(document_id, "failed", f"File not found: {document.rel_path}")
            raise FileNotFoundError(path)
        self._set_status(document_id, "extracting")
        done_pages = self._done_page_numbers(document_id)
        stats = {"text": 0, "ocr": 0, "reused": 0, "failed": 0, "warnings": 0, "skipped": len(done_pages)}
        total = max(document.page_count, 1)
        for page_input in iter_pages(
            path,
            document.kind,
            min_words=self.settings.pdf_text_min_words,
            max_px=self.settings.ocr_max_image_px,
        ):
            number = page_input.page_no
            progress((number - 1) / total, f"Page {number} of {total}")
            if number in done_pages:
                continue
            page = self._page(document_id, number)
            page.error = None
            if page_input.text is not None:
                page.raw_text = page.text = page_input.text
                page.method, page.status, page.model_ref = page_input.method, "done", None
                stats["text"] += 1
            else:
                image_hash = sha256_bytes(page_input.image_png or b"")
                page.image_sha256 = image_hash
                reused = self._reusable_ocr(image_hash, exclude_page_id=page.id)
                if reused is not None:
                    page.raw_text, page.text = reused.raw_text, reused.text
                    page.method, page.status, page.model_ref = "ocr_reused", "done", reused.model_ref
                    page.reviewed = reused.reviewed
                    stats["reused"] += 1
                else:
                    try:
                        result = ocr_page(self.router, page_input.image_png or b"")
                    except AllModelsFailed as exc:
                        page.status, page.error = "failed", str(exc)[:500]
                        stats["failed"] += 1
                    else:
                        page.raw_text = page.text = result.text
                        page.method, page.status, page.model_ref = "ocr", "done", result.model_ref
                        page.error = result.warning  # e.g. repetition removed — shown on Review Text
                        stats["ocr"] += 1
                        stats["warnings"] += bool(result.warning)
            page.indexed = False
            page.updated_at = utcnow()
            with Session(self.engine) as s:
                s.add(page)
                s.commit()
        progress(1.0, "Extraction finished")
        status = "failed" if stats["failed"] else "review"
        message = f"{stats['failed']} page(s) failed — open Review to retry" if stats["failed"] else None
        self._set_status(document_id, status, message)
        if status == "review" and not self.settings.require_review:
            self.enqueue("index", document_id, options="include_unreviewed")
        logger.info(f"Extracted document {document_id}: {stats}")
        return stats

    # ------------------------------------------------------------ review
    def update_page(self, document_id: int, page_no: int, text: str, *, reviewed: bool) -> Page:
        with Session(self.engine) as s:
            page = s.exec(select(Page).where(Page.document_id == document_id, Page.page_no == page_no)).one()
            if page.text != text:
                page.text = text
                page.indexed = False
            page.reviewed = reviewed
            page.updated_at = utcnow()
            s.add(page)
            s.commit()
            s.refresh(page)
        self._refresh_status(document_id)
        return page

    def mark_all_reviewed(self, document_id: int) -> int:
        with Session(self.engine) as s:
            pages = s.exec(
                select(Page).where(
                    Page.document_id == document_id, Page.status == "done", col(Page.reviewed).is_(False)
                )
            ).all()
            for page in pages:
                page.reviewed = True
                page.updated_at = utcnow()
                s.add(page)
            s.commit()
        self._refresh_status(document_id)
        return len(pages)

    def retry_page(self, document_id: int, page_no: int) -> None:
        """Forget a page's extraction so the next extract job redoes it (fresh OCR, cache bypassed by reset)."""
        with Session(self.engine) as s:
            page = s.exec(
                select(Page).where(Page.document_id == document_id, Page.page_no == page_no)
            ).first()
            if page:
                s.delete(page)
                s.commit()
        self.store.delete_page(document_id, page_no)
        self.enqueue("extract", document_id)

    def clean_extracted_text(self, document_id: int) -> int:
        """Apply the latest OCR clean-up (empty figure lines, table repair) to pages you have not edited."""
        changed = 0
        with Session(self.engine) as s:
            pages = s.exec(
                select(Page).where(Page.document_id == document_id, col(Page.reviewed).is_(False))
            ).all()
            for page in pages:
                if page.text != page.raw_text or page.method not in {"ocr", "ocr_reused", "ocr_cloud"}:
                    continue  # your edits are never touched
                cleaned = clean_ocr_text(page.text)
                if cleaned != page.text:
                    page.raw_text = page.text = cleaned
                    page.indexed = False
                    page.updated_at = utcnow()
                    s.add(page)
                    changed += 1
            s.commit()
        return changed

    # ------------------------------------------------------------ cloud re-read (better tables / figures)
    def pages_suggested_for_cloud(self, document_id: int) -> list[int]:
        """OCR'd pages with a table or an OCR warning — where the cloud model is clearly better.

        Figures are NOT a trigger: many textbooks have a figure on almost every page (16 of 17 pages in the
        owner's chapter), which would make the suggestion meaningless. Use ocr_page_numbers() for "all pages".
        """
        return [
            p.page_no
            for p in self.pages(document_id)
            if p.status == "done"
            and p.method in {"ocr", "ocr_reused"}
            and (bool(p.error) or sum(line.strip().startswith("|") for line in p.text.splitlines()) >= 2)
        ]

    def ocr_page_numbers(self, document_id: int) -> list[int]:
        """All pages that were read by OCR (for 're-read the whole document')."""
        return [
            p.page_no
            for p in self.pages(document_id)
            if p.status == "done" and p.method in {"ocr", "ocr_reused"}
        ]

    def reindex_document(self, document_id: int) -> int:
        """Rebuild the search entries of all indexed pages (e.g. to add summaries/descriptions)."""
        with Session(self.engine) as s:
            pages = s.exec(
                select(Page).where(Page.document_id == document_id, col(Page.indexed).is_(True))
            ).all()
            for page in pages:
                page.indexed = False
                s.add(page)
            s.commit()
        self.enqueue("index", document_id)
        return len(pages)

    def reread_pages_cloud(
        self, document_id: int, page_numbers: list[int], progress: Progress = _noop
    ) -> dict:
        """Re-read pages with the cloud vision model (task `ocr_cloud`). Pages become 'not reviewed' again."""
        document = self._document(document_id)
        path = PROJECT_ROOT / document.rel_path
        stats = {"pages": 0, "failed": 0}  # actual cost is in the AI call log (Settings & Cost)
        for position, page_no in enumerate(page_numbers):
            progress(position / max(len(page_numbers), 1), f"Cloud re-read of page {page_no}")
            image = page_image(path, document.kind, page_no, self.settings.ocr_max_image_px)
            if image is None:
                continue
            try:
                outcome = ocr_page(self.router, image, task=CLOUD_OCR_TASK, retry_task=None)
            except AllModelsFailed as exc:
                stats["failed"] += 1
                logger.warning(f"Cloud re-read of page {page_no} failed: {exc}")
                continue
            page = self._page(document_id, page_no)
            page.raw_text = page.text = outcome.text
            page.method, page.status, page.model_ref = "ocr_cloud", "done", outcome.model_ref
            page.error, page.reviewed, page.indexed = outcome.warning, False, False
            page.updated_at = utcnow()
            with Session(self.engine) as s:
                s.add(page)
                s.commit()
            self.store.delete_page(document_id, page_no)
            stats["pages"] += 1
        progress(1.0, "Cloud re-read finished")
        self._refresh_status(document_id)
        return stats

    # ------------------------------------------------------------ indexing
    def index_document(
        self, document_id: int, *, include_unreviewed: bool = False, progress: Progress = _noop
    ) -> dict:
        """Chunk + embed every eligible page whose current text is not indexed yet."""
        self._set_status(document_id, "indexing")
        document = self._document(document_id)
        with Session(self.engine) as s:
            query = select(Page).where(
                Page.document_id == document_id, Page.status == "done", col(Page.indexed).is_(False)
            )
            if not include_unreviewed:
                query = query.where(col(Page.reviewed).is_(True))
            pages = s.exec(query.order_by(Page.page_no)).all()
        stats = {"pages": 0, "chunks": 0, "duplicate_chunks": 0, "enrichments": 0, "enrich_failed": 0}
        try:
            for position, page in enumerate(pages):
                progress(position / max(len(pages), 1), f"Indexing page {page.page_no}")
                self._index_page(document, page, stats)
        except AllModelsFailed as exc:
            self._set_status(document_id, "failed", f"Indexing stopped: {exc}"[:500])
            raise
        progress(1.0, "Indexing finished")
        self._refresh_status(document_id)
        logger.info(f"Indexed document {document_id}: {stats}")
        return stats

    def _index_page(self, document: Document, page: Page, stats: dict) -> None:
        self.store.delete_page(document.id, page.page_no)  # replace any older version of this page
        heading = self._heading(document)
        # Lossless table repair (pads rows to equal width) so search passages have well-formed tables;
        # the reviewed page text itself is never changed.
        searchable_text = normalize_markdown_tables(page.text)
        items: list[tuple[str, int, str]] = [  # (kind, index, text)
            ("text", index, piece)
            for index, piece in enumerate(
                chunk_text(searchable_text, self.settings.chunk_chars, self.settings.chunk_overlap_chars)
            )
        ]
        if self.settings.enrich_pages:
            try:
                enrichment = enrich_page(self.router, searchable_text, heading)
            except (AllModelsFailed, ValueError) as exc:  # optional extra — never blocks indexing
                stats["enrich_failed"] += 1
                logger.warning(f"Page {page.page_no}: summary/descriptions skipped ({exc})")
            else:
                if enrichment is not None:
                    entries = enrichment.entries(page.page_no)
                    items += [(kind, 1000 + n, text) for n, (kind, text) in enumerate(entries)]
                    stats["enrichments"] += len(entries)
        fresh: list[tuple[str, int, str, str]] = []
        seen: set[str] = set()
        for kind, index, piece in items:
            digest = text_hash(piece)
            if digest in seen or self.store.has_text(digest, self.embed_model):
                stats["duplicate_chunks"] += 1
                continue
            seen.add(digest)
            fresh.append((kind, index, piece, digest))
        for start in range(0, len(fresh), EMBED_BATCH):
            batch = fresh[start : start + EMBED_BATCH]
            result = self.router.embed(EMBED_TASK, [f"{heading}\n{piece}" for _, _, piece, _ in batch])
            for (kind, index, piece, digest), vector in zip(batch, result.vectors, strict=True):
                self.store.add(
                    document_id=document.id,
                    page_no=page.page_no,
                    chunk_index=index,
                    text=piece,
                    text_sha256=digest,
                    embed_model=self.embed_model,
                    vector=vector,
                    kind=kind,
                )
                stats["chunks"] += 1
        with Session(self.engine) as s:
            stored = s.get(Page, page.id)
            stored.indexed = True
            stored.updated_at = utcnow()
            s.add(stored)
            s.commit()
        stats["pages"] += 1

    # ------------------------------------------------------------ management
    def update_metadata(self, document_id: int, **fields) -> Document:
        allowed = {"class_level", "subject", "chapter_no", "chapter_title"}
        with Session(self.engine) as s:
            document = s.get(Document, document_id)
            for key, value in fields.items():
                if key in allowed:
                    setattr(document, key, value)
            document.updated_at = utcnow()
            s.add(document)
            s.commit()
            s.refresh(document)
            return document

    def delete_document(self, document_id: int, *, delete_file: bool = False) -> None:
        document = self._document(document_id)
        self.store.delete_document(document_id)
        with Session(self.engine) as s:
            s.exec(delete(Page).where(Page.document_id == document_id))
            s.exec(delete(Job).where(Job.document_id == document_id, Job.status != "running"))
            s.delete(s.get(Document, document_id))
            s.commit()
        if delete_file:
            (PROJECT_ROOT / document.rel_path).unlink(missing_ok=True)
        logger.info(f"Deleted document {document_id} ({document.filename}); file deleted: {delete_file}")

    def enqueue(self, kind: str, document_id: int, *, page_no: int | None = None, options: str = "") -> Job:
        """Queue a job unless an identical one is already waiting or running."""
        with Session(self.engine) as s:
            existing = s.exec(
                select(Job).where(
                    Job.kind == kind,
                    Job.document_id == document_id,
                    Job.page_no == page_no,
                    col(Job.status).in_(["queued", "running"]),
                )
            ).first()
            if existing:
                return existing
            job = Job(kind=kind, document_id=document_id, page_no=page_no, options=options)
            s.add(job)
            s.commit()
            s.refresh(job)
            return job

    def documents(self) -> list[Document]:
        with Session(self.engine) as s:
            return list(s.exec(select(Document).order_by(Document.id)).all())

    def pages(self, document_id: int) -> list[Page]:
        with Session(self.engine) as s:
            return list(
                s.exec(select(Page).where(Page.document_id == document_id).order_by(Page.page_no)).all()
            )

    def page_counts(self, document_id: int) -> dict:
        with Session(self.engine) as s:

            def count(*conditions) -> int:
                return int(
                    s.exec(
                        select(func.count(Page.id)).where(Page.document_id == document_id, *conditions)
                    ).one()
                )

            return {
                "done": count(Page.status == "done"),
                "failed": count(Page.status == "failed"),
                "reviewed": count(Page.reviewed == True),  # noqa: E712
                "indexed": count(Page.indexed == True),  # noqa: E712
            }

    # ------------------------------------------------------------ internals
    def _rel(self, path: Path) -> Path:
        try:
            return Path(os.path.relpath(path.resolve(), PROJECT_ROOT))
        except ValueError:  # different drive
            return path.resolve()

    def _hash(self, path: Path) -> str:
        stat = path.stat()
        key = str(path.resolve())
        cached = self._hash_cache.get(key)
        if cached and cached[0] == stat.st_size and cached[1] == stat.st_mtime_ns:
            return cached[2]
        digest = sha256_file(path)
        self._hash_cache[key] = (stat.st_size, stat.st_mtime_ns, digest)
        return digest

    def _document(self, document_id: int) -> Document:
        with Session(self.engine) as s:
            document = s.get(Document, document_id)
        if document is None:
            raise KeyError(f"Document {document_id} not found")
        return document

    def _page(self, document_id: int, page_no: int) -> Page:
        with Session(self.engine) as s:
            page = s.exec(
                select(Page).where(Page.document_id == document_id, Page.page_no == page_no)
            ).first()
            if page is None:
                page = Page(document_id=document_id, page_no=page_no)
                s.add(page)
                s.commit()
                s.refresh(page)
            return page

    def _done_page_numbers(self, document_id: int) -> set[int]:
        with Session(self.engine) as s:
            return set(
                s.exec(
                    select(Page.page_no).where(Page.document_id == document_id, Page.status == "done")
                ).all()
            )

    def _reusable_ocr(self, image_hash: str, exclude_page_id: int | None) -> Page | None:
        with Session(self.engine) as s:
            return s.exec(
                select(Page).where(
                    Page.image_sha256 == image_hash, Page.status == "done", Page.id != exclude_page_id
                )
            ).first()

    def _set_status(self, document_id: int, status: str, error: str | None = None) -> None:
        with Session(self.engine) as s:
            document = s.get(Document, document_id)
            if document is None:
                return
            document.status, document.error, document.updated_at = status, error, utcnow()
            s.add(document)
            s.commit()

    def _refresh_status(self, document_id: int) -> None:
        document = self._document(document_id)
        if document.status in {"extracting", "registered"}:
            return
        counts = self.page_counts(document_id)
        if counts["failed"]:
            status = "failed"
            error = f"{counts['failed']} page(s) failed — open Review to retry"
        elif counts["done"] and counts["indexed"] == counts["done"]:
            status, error = "indexed", None
        else:
            status, error = "review", None
        self._set_status(document_id, status, error)

    @staticmethod
    def _heading(document: Document) -> str:
        parts = []
        if document.subject:
            parts.append(document.subject)
        if document.class_level:
            parts.append(f"Class {document.class_level}")
        if document.chapter_no:
            parts.append(f"Chapter {document.chapter_no}")
        if document.chapter_title:
            parts.append(document.chapter_title)
        return " · ".join(parts) or document.filename
