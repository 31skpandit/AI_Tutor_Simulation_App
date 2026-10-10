"""Database tables. Timestamps are timezone-aware UTC (SQLModel stores and returns them as UTC)."""

from datetime import UTC, datetime

from sqlalchemy import Column, LargeBinary, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class LLMCall(SQLModel, table=True):
    """One row per model call attempt (including cache hits and failures) — feeds the cost dashboard."""

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    task: str = Field(index=True)
    model_ref: str  # e.g. "openai/gpt-5-nano"
    paid: bool = False
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    cached: bool = False
    success: bool = True
    latency_ms: int = 0
    error: str | None = None


class CacheEntry(SQLModel, table=True):
    """Stored model responses so an identical request is never paid for twice."""

    key: str = Field(primary_key=True)
    task: str = Field(index=True)
    model_ref: str
    response_text: str
    input_tokens: int = 0
    output_tokens: int = 0
    created_at: datetime = Field(default_factory=utcnow)


# ---------------------------------------------------------------- Phase 1: ingestion


class Document(SQLModel, table=True):
    """One unique source file. Uniqueness is the SHA-256 of the file bytes, so a renamed copy is a duplicate."""

    id: int | None = Field(default=None, primary_key=True)
    sha256: str = Field(index=True, unique=True)
    filename: str
    rel_path: str  # path relative to the project folder
    kind: str  # pdf | image | docx | text
    size_bytes: int = 0
    page_count: int = 0
    class_level: str = ""
    subject: str = ""
    chapter_no: int | None = None
    chapter_title: str = ""
    # registered → extracting → review → indexing → indexed   (or failed)
    status: str = Field(default="registered", index=True)
    error: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Page(SQLModel, table=True):
    """Extracted text of one page (PDF page, image, or a ~3,000-character part of a DOCX/TXT file)."""

    __table_args__ = (UniqueConstraint("document_id", "page_no"),)

    id: int | None = Field(default=None, primary_key=True)
    document_id: int = Field(foreign_key="document.id", index=True)
    page_no: int
    # text_layer | ocr | ocr_reused | docx | text
    method: str = ""
    image_sha256: str | None = Field(default=None, index=True)  # identical page images are OCR'd only once
    raw_text: str = ""  # as extracted (kept for comparison)
    text: str = ""  # after your review/edits — this is what gets indexed
    status: str = "pending"  # pending | done | failed
    error: str | None = None
    model_ref: str | None = None
    reviewed: bool = False
    indexed: bool = False  # True when the current `text` is in the search index
    # Autopilot (app/ingestion/quality.py): clean | check | '' (not checked yet); reasons as a JSON list
    quality: str = ""
    quality_notes: str = "[]"
    auto_reviewed: bool = False  # True = marked reviewed by the automatic check, not (yet) by the teacher
    updated_at: datetime = Field(default_factory=utcnow)


class Chunk(SQLModel, table=True):
    """A searchable passage with its embedding vector (float32, L2-normalised)."""

    id: int | None = Field(default=None, primary_key=True)
    document_id: int = Field(foreign_key="document.id", index=True)
    page_no: int
    chunk_index: int
    # text = passage of the page; summary / table / figure = generated description of that page (Phase 1+)
    kind: str = Field(default="text", index=True)
    text: str
    text_sha256: str = Field(index=True)  # identical passages are stored once
    embed_model: str
    dim: int
    vector: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    created_at: datetime = Field(default_factory=utcnow)


class IndexState(SQLModel, table=True):
    """A counter that increases on every change to the search index (SQLite may reuse row ids, so
    'count + max id' is not a safe change detector)."""

    id: int = Field(default=1, primary_key=True)
    generation: int = 0


class AnswerCache(SQLModel, table=True):
    """Tutor answers reused for a question that means the same as an earlier one (semantic cache).

    Valid only while the search index is unchanged (`index_version`) and for the same filters + language.
    """

    id: int | None = Field(default=None, primary_key=True)
    question: str
    vector: bytes = Field(sa_column=Column(LargeBinary, nullable=False))  # normalised question embedding
    scope: str = Field(index=True)  # filters + language
    index_version: str = Field(index=True)
    answer_text: str
    sources: str  # JSON list of chunk ids used
    model_ref: str | None = None
    uses: int = 0
    created_at: datetime = Field(default_factory=utcnow)


class Lesson(SQLModel, table=True):
    """A lesson for one topic (Phase 2). The plan is JSON so sections can be edited freely."""

    id: int | None = Field(default=None, primary_key=True)
    topic: str
    document_id: int | None = Field(default=None, index=True)  # source chapter (optional)
    chapter_no: int | None = None
    title: str = ""
    # generating → draft → approved   (or failed)
    status: str = Field(default="generating", index=True)
    plan_json: str = "{}"
    warnings: str = "[]"  # JSON list of checker warnings
    simulation_js: str = ""
    simulation_status: str = "none"  # none | generating | ok | failed
    simulation_problems: str = "[]"
    model_ref: str | None = None
    cost_usd: float = 0.0
    version: int = 1
    error: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class MediaAsset(SQLModel, table=True):
    """A real photo found for a lesson (Wikimedia Commons / Wikidata / Openverse), stored offline with its credit."""

    id: int | None = Field(default=None, primary_key=True)
    query: str = Field(index=True)  # what was searched, e.g. 'railway level crossing gate'
    lesson_id: int | None = Field(default=None, index=True)
    concept: str = ""  # concept name it illustrates
    source: str = ""  # commons | wikidata | openverse
    page_url: str = ""  # the file's page (for the credit link)
    title: str = ""
    author: str = ""
    license: str = ""  # e.g. 'CC BY-SA 4.0', 'Public domain'
    license_url: str = ""
    sha256: str = Field(default="", index=True)
    local_path: str = ""  # relative to the data folder
    caption: str = ""  # what the vision check saw
    fits: bool = False  # passed the relevance check
    check_note: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class Job(SQLModel, table=True):
    """Background work (extraction / indexing). Survives restarts; resumes where it stopped."""

    id: int | None = Field(default=None, primary_key=True)
    kind: str  # extract | index | reread_cloud | lesson_plan | simulation
    document_id: int = Field(index=True)  # 0 for lesson jobs without a source document
    lesson_id: int | None = None
    page_no: int | None = None
    options: str = ""  # e.g. "include_unreviewed"
    status: str = Field(default="queued", index=True)  # queued | running | done | failed
    progress: float = 0.0
    message: str = ""
    error: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    heartbeat_at: datetime | None = None
