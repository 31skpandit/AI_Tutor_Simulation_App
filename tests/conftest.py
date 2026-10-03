import pytest

from app.db.session import make_engine
from app.llm.backend import BackendResult
from app.llm.config import ModelsConfig
from app.llm.router import LLMRouter

CONFIG = {
    "budget": {"monthly_usd_cap": 1.0, "premium_requires_approval": True},
    "allowed_hosts": ["127.0.0.1:11434", "api.openai.com"],
    "providers": {
        "ollama": {"litellm_prefix": "ollama_chat", "api_base": "http://127.0.0.1:11434", "paid": False},
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
    },
}


class FakeBackend:
    """Records calls; returns scripted results or raises scripted exceptions."""

    def __init__(self, script=None):
        self.calls: list[dict] = []
        self.script = list(script or [])

    def complete(self, **kwargs) -> BackendResult:
        self.calls.append(kwargs)
        item = self.script.pop(0) if self.script else BackendResult("answer", 10, 20)
        if isinstance(item, Exception):
            raise item
        return item


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
