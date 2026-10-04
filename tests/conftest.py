import hashlib
import re

import pytest

from app.db.session import make_engine
from app.llm.backend import BackendResult, EmbedResult
from app.llm.config import ModelsConfig
from app.llm.router import LLMRouter

CONFIG = {
    "budget": {"monthly_usd_cap": 1.0, "premium_requires_approval": True},
    "allowed_hosts": ["127.0.0.1:11434", "api.openai.com"],
    "providers": {
        "ollama": {
            "litellm_prefix": "ollama_chat",
            "litellm_embedding_prefix": "ollama",
            "api_base": "http://127.0.0.1:11434",
            "paid": False,
        },
        "openai": {
            "litellm_prefix": "openai",
            "api_base": "https://api.openai.com/v1",
            "secret": "openai",
            "paid": True,
        },
    },
    "premium_models": ["openai/premium"],
    "prices": {
        "openai/cheap": {"input_per_million": 1.0, "output_per_million": 2.0},
        "openai/premium": {"input_per_million": 10.0, "output_per_million": 20.0},
    },
    "tasks": {
        "local_only": {"primary": "ollama/small"},
        "paid_then_local": {"primary": "openai/cheap", "fallbacks": ["ollama/small"], "max_tokens": 1000},
        "premium_then_cheap": {"primary": "openai/premium", "fallbacks": ["openai/cheap"], "max_tokens": 100},
        "no_cache": {"primary": "ollama/small", "cache": False},
        "ocr": {"primary": "ollama/vision"},
        "ocr_retry": {"primary": "ollama/vision", "ollama_options": {"repeat_penalty": 1.1}},
        "embed": {"kind": "embedding", "primary": "ollama/embedder"},
        "ocr_cloud": {"primary": "ollama/cloudvision"},
        "enrich": {"primary": "ollama/small", "json_output": True},
        "tutor_answer": {"primary": "ollama/small"},
        "tutor_answer_indic": {"primary": "ollama/small"},
    },
}

DIM = 64


def bag_of_words_vector(text: str) -> list[float]:
    """Deterministic fake embedding: hashed word counts, so similar texts get similar vectors."""
    vector = [0.0] * DIM
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % DIM] += 1.0
    return vector


class FakeBackend:
    """Records calls; returns scripted results or raises scripted exceptions."""

    def __init__(self, script=None, ocr_text="OCR text of a page about acids and bases."):
        self.calls: list[dict] = []
        self.embed_calls: list[list[str]] = []
        self.script = list(script or [])
        self.ocr_text = ocr_text

    ENRICH_JSON = (
        '{"summary": "This page explains acids and bases.", '
        '"tables": [{"title": "Basicity of acids", "description": "Lists HCl, H2SO4 and H3PO4 to classify by basicity"}], '
        '"figures": []}'
    )

    def complete(self, **kwargs) -> BackendResult:
        self.calls.append(kwargs)
        if kwargs["route"].endswith("/vision") and not self.script:
            return BackendResult(self.ocr_text, 1000, 50)
        if kwargs["route"].endswith("/cloudvision") and not self.script:
            return BackendResult("Cloud transcription with H₂SO₄ and a table", 2400, 600)
        if kwargs.get("json_output") and not self.script:
            return BackendResult(self.ENRICH_JSON, 500, 80)
        item = self.script.pop(0) if self.script else BackendResult("answer", 10, 20)
        if isinstance(item, Exception):
            raise item
        return item

    def embed(self, **kwargs) -> EmbedResult:
        self.embed_calls.append(kwargs["texts"])
        return EmbedResult([bag_of_words_vector(t) for t in kwargs["texts"]], input_tokens=10)


@pytest.fixture
def config() -> ModelsConfig:
    return ModelsConfig.model_validate(CONFIG)


@pytest.fixture
def engine():
    return make_engine(":memory:")


@pytest.fixture
def make_router(config, engine):
    def _make(backend=None, key="sk-test-key-123456", cap=None):
        return LLMRouter(
            config, backend or FakeBackend(), engine, secret_getter=lambda name: key, budget_cap_usd=cap
        )

    return _make
