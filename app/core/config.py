"""Application settings (non-secret). Values come from environment variables or `.env`, prefixed ATS_."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        env_prefix="ATS_",
        extra="ignore",
    )

    data_dir: Path = PROJECT_ROOT / "data"
    models_config: Path = PROJECT_ROOT / "config" / "models.yaml"
    # Overrides budget.monthly_usd_cap in models.yaml when set.
    monthly_budget_usd: float | None = None
    log_level: str = "INFO"

    # ---- Phase 1: ingestion ----
    # Folder watched for new textbook files (PDF, images, DOCX, TXT/MD). Uploads are saved here too.
    source_dir: Path = PROJECT_ROOT / "source"
    # Register + extract new files automatically when the Syllabus Library page is opened.
    auto_ingest: bool = True
    # Pages must be reviewed by you before they are searchable (blueprint FR-02). Set false to index straight away.
    require_review: bool = True
    # A PDF page with at least this many words in its text layer is read directly; otherwise it is OCR'd.
    pdf_text_min_words: int = 25
    # Longest side (pixels) of page images sent to the OCR model. Larger = slower, more GPU memory.
    ocr_max_image_px: int = 1600
    # Search chunks: target size and overlap in characters (~4 characters per token).
    chunk_chars: int = 1500
    chunk_overlap_chars: int = 200
    # When indexing, also store a short page summary + table/figure descriptions as searchable entries.
    enrich_pages: bool = True
    # Reuse a tutor answer for a question that means the same as an earlier one (same filters, unchanged index).
    semantic_cache: bool = True
    # Minimum similarity of two questions to reuse an answer (calibrated: see blueprint §8.4).
    semantic_cache_min: float = 0.97

    # ---- Phase 2: lessons ----
    # Minimum similarity for a textbook passage to be used as lesson evidence.
    lesson_min_relevance: float = 0.45
    # Run every new simulation in a hidden (headless) Edge/Chrome and press all its controls before it is
    # accepted — catches errors that only appear when the code runs. Skipped if no browser is found.
    browser_check: bool = True
    # Optional path to msedge.exe / chrome.exe when it is not in the usual Windows location.
    browser_path: Path | None = None

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.source_dir.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
