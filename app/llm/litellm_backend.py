"""The ONLY module that imports litellm (blueprint §14.2).

Before import we force LiteLLM to use its bundled data files instead of downloading them
from GitHub at start-up, and we disable all callbacks, so the library only talks to the
model endpoint we pass explicitly on each call.
"""

import os
import re

os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
os.environ["LITELLM_LOCAL_ANTHROPIC_BETA_HEADERS"] = "True"

import litellm  # noqa: E402

from app.llm.backend import BackendResult, EmbedResult  # noqa: E402

litellm.telemetry = False
litellm.drop_params = True  # silently drop parameters a given model does not support
litellm.suppress_debug_info = True
litellm.callbacks = []
litellm.success_callback = []
litellm.failure_callback = []

# Safety net: drop any reasoning text a local model still emits (with or without the opening tag).
_THINK_BLOCK = re.compile(r"^(?:.*?<think>)?.*?</think>\s*", re.S)


class LiteLLMBackend:
    def complete(
        self,
        *,
        route: str,
        messages: list[dict],
        api_base: str,
        api_key: str | None,
        max_tokens: int,
        temperature: float | None,
        reasoning_effort: str | None,
        timeout_s: float,
        extra_options: dict | None = None,
        json_output: bool = False,
    ) -> BackendResult:
        kwargs: dict = {
            "model": route,
            "messages": messages,
            "api_base": api_base,
            "max_tokens": max_tokens,
            "timeout": timeout_s,
            "num_retries": 0,  # retries are decided by our router
        }
        if api_key:
            kwargs["api_key"] = api_key
        if temperature is not None:
            kwargs["temperature"] = temperature
        if route.startswith("ollama") and reasoning_effort is None:
            # LiteLLM maps any value other than low/medium/high to Ollama `think=false`, so Qwen3
            # hybrid models answer directly instead of spending tokens on hidden reasoning.
            reasoning_effort = "minimal"
        if reasoning_effort is not None:
            kwargs["reasoning_effort"] = reasoning_effort
        if json_output:
            kwargs["response_format"] = {"type": "json_object"}  # LiteLLM maps this to Ollama format=json
        if route.startswith("ollama") and extra_options:
            kwargs.update(extra_options)  # LiteLLM forwards these as Ollama "options" (e.g. num_ctx)
        response = litellm.completion(**kwargs)
        text = response.choices[0].message.content or ""
        text = _THINK_BLOCK.sub("", text).strip()
        usage = getattr(response, "usage", None)
        return BackendResult(
            text=text,
            input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
        )

    def embed(
        self,
        *,
        route: str,
        texts: list[str],
        api_base: str,
        api_key: str | None,
        timeout_s: float,
    ) -> EmbedResult:
        kwargs: dict = {"model": route, "input": texts, "api_base": api_base, "timeout": timeout_s}
        if api_key:
            kwargs["api_key"] = api_key
        response = litellm.embedding(**kwargs)
        items = sorted(response.data, key=lambda d: d["index"] if isinstance(d, dict) else d.index)
        vectors = [list(d["embedding"] if isinstance(d, dict) else d.embedding) for d in items]
        usage = getattr(response, "usage", None)
        return EmbedResult(vectors=vectors, input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0))


def bundled_price(model: str) -> tuple[float, float] | None:
    """USD per 1M tokens (input, output) from LiteLLM's bundled price list — used only to cross-check config."""
    entry = litellm.model_cost.get(model)
    if not entry:
        return None
    return (
        round(float(entry.get("input_cost_per_token") or 0) * 1e6, 4),
        round(float(entry.get("output_cost_per_token") or 0) * 1e6, 4),
    )
