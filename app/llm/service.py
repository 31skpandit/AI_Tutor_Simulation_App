"""Builds the router after the security checks pass. LiteLLM is imported only here, and only then."""

from app.core.config import Settings, get_settings
from app.core.logging import setup_logging
from app.core.secrets import get_secret
from app.core.startup_checks import assert_safe_to_start
from app.db.session import make_engine
from app.llm.config import load_models_config
from app.llm.router import LLMRouter


def build_router(settings: Settings | None = None) -> LLMRouter:
    settings = settings or get_settings()
    setup_logging(settings)
    assert_safe_to_start()  # raises StartupCheckError before litellm is ever imported

    from app.llm.litellm_backend import LiteLLMBackend

    config = load_models_config(settings.models_config)
    return LLMRouter(
        config,
        LiteLLMBackend(),
        make_engine(settings.db_path),
        secret_getter=get_secret,
        budget_cap_usd=settings.monthly_budget_usd,
    )
