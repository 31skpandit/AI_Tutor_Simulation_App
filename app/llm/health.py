"""Reachability checks for model providers (no tokens are spent)."""

import httpx

from app.llm.config import ModelsConfig


def ollama_models(api_base: str, timeout_s: float = 3.0) -> list[str] | None:
    """Names of locally installed Ollama models, or None if Ollama is not reachable."""
    try:
        response = httpx.get(f"{api_base.rstrip('/')}/api/tags", timeout=timeout_s)
        response.raise_for_status()
    except httpx.HTTPError:
        return None
    return sorted(m["name"] for m in response.json().get("models", []))


def openai_models(api_base: str, api_key: str, timeout_s: float = 10.0) -> list[str]:
    """Model IDs your OpenAI key can access (GET /v1/models — free, no tokens used)."""
    response = httpx.get(
        f"{api_base.rstrip('/')}/models",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=timeout_s,
    )
    response.raise_for_status()
    return sorted(m["id"] for m in response.json().get("data", []))


def configured_models(config: ModelsConfig, provider: str) -> list[str]:
    refs = {ref for task in config.tasks.values() for ref in task.chain} | set(config.premium_models)
    return sorted(ref.partition("/")[2] for ref in refs if ref.partition("/")[0] == provider)


def ollama_has(installed: list[str], model: str) -> bool:
    return model in installed or f"{model}:latest" in installed
