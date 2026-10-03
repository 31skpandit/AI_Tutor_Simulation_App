"""Database tables. Timestamps are timezone-aware UTC (SQLModel stores and returns them as UTC)."""

from datetime import UTC, datetime

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
