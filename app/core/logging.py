"""Logging with automatic redaction of anything that looks like an API key."""

import re
import sys

from loguru import logger

from app.core.config import Settings

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),  # OpenAI, OpenRouter
    re.compile(r"hf_[A-Za-z0-9]{8,}"),  # Hugging Face
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),  # Google
    re.compile(r"gsk_[A-Za-z0-9]{8,}"),  # Groq
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{8,}"),
]

_configured = False


def redact(text: str) -> str:
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(lambda m: (m.group(1) if m.groups() else "") + "[REDACTED]", text)
    return text


def setup_logging(settings: Settings) -> None:
    """Configure loguru once per process (Streamlit reruns scripts, so this must be idempotent)."""
    global _configured
    if _configured:
        return
    logger.remove()
    logger.configure(patcher=lambda record: record.update(message=redact(record["message"])))
    logger.add(sys.stderr, level=settings.log_level)
    logger.add(
        settings.logs_dir / "app.log",
        level=settings.log_level,
        rotation="5 MB",
        retention=5,
        encoding="utf-8",
    )
    _configured = True
