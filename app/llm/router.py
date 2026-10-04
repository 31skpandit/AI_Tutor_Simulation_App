"""Task-based model router (blueprint Fig. 4).

For each candidate model of a task, in order:
  premium approval → host allow-list → cache → API key → budget → call (retry once) → log → cache.
A candidate that is skipped or fails moves on to the next one in the fallback chain.
Embedding tasks follow the same checks but never fall back to a different model.
"""

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import Engine, func
from sqlmodel import Session, select

from app.core.logging import redact
from app.db.models import CacheEntry, LLMCall, utcnow
from app.llm.backend import Backend
from app.llm.config import ModelsConfig, ProviderConfig, TaskConfig

DEFAULT_TIMEOUT_S = 180.0
IMAGE_TOKEN_ESTIMATE = 1500  # worst-case input tokens assumed per image when estimating cost


@dataclass(frozen=True)
class LLMResult:
    text: str
    model_ref: str
    cost_usd: float
    cached: bool
    input_tokens: int
    output_tokens: int
    latency_ms: int


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: list[list[float]]
    model_ref: str
    cost_usd: float
    input_tokens: int
    latency_ms: int


@dataclass
class Attempt:
    model_ref: str
    outcome: str  # e.g. "skipped: budget", "failed: TimeoutError ..."


class AllModelsFailed(RuntimeError):
    def __init__(self, task: str, attempts: list[Attempt]):
        self.task = task
        self.attempts = attempts
        detail = "; ".join(f"{a.model_ref} → {a.outcome}" for a in attempts)
        super().__init__(f"No model could complete task '{task}': {detail}")

    @property
    def budget_blocked(self) -> bool:
        return any(a.outcome.startswith("skipped: monthly budget") for a in self.attempts)


@dataclass(frozen=True)
class _Ready:
    provider: ProviderConfig
    model: str
    api_key: str | None


def month_start_utc(now_local: datetime | None = None) -> datetime:
    """First instant of the current *local* calendar month, in UTC.

    `now_local` must be timezone-aware; defaults to the laptop's local time.
    """
    local = (now_local or datetime.now().astimezone()).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    return local.astimezone(UTC)


def estimate_input_tokens(messages: list[dict]) -> float:
    """~4 characters per token for text; a fixed allowance per image (base64 data is not counted)."""
    tokens = 0.0
    for message in messages:
        content = message.get("content", "")
        if isinstance(content, str):
            tokens += len(content) / 4
            continue
        for part in content or []:
            if part.get("type") == "image_url":
                tokens += IMAGE_TOKEN_ESTIMATE
            else:
                tokens += len(json.dumps(part, ensure_ascii=False)) / 4
    return tokens


class LLMRouter:
    def __init__(
        self,
        config: ModelsConfig,
        backend: Backend,
        engine: Engine,
        *,
        secret_getter: Callable[[str], str | None],
        budget_cap_usd: float | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ):
        self.config = config
        self.backend = backend
        self.engine = engine
        self.secret_getter = secret_getter
        self.budget_cap_usd = config.budget.monthly_usd_cap if budget_cap_usd is None else budget_cap_usd
        self.timeout_s = timeout_s

    # ---------- public API ----------
    def complete(self, task: str, messages: list[dict], *, allow_premium: bool = False) -> LLMResult:
        spec = self._task(task, "chat")
        attempts: list[Attempt] = []
        for model_ref in spec.chain:
            result = self._try_chat(task, spec, model_ref, messages, allow_premium, attempts)
            if result is not None:
                return result
        raise self._fail(task, attempts)

    def embed(self, task: str, texts: list[str]) -> EmbeddingResult:
        """Embed texts with the task's single model. Raises AllModelsFailed if it cannot run."""
        spec = self._task(task, "embedding")
        model_ref = spec.primary
        attempts: list[Attempt] = []
        estimate = sum(len(t) for t in texts) / 4
        ready = self._preflight(model_ref, estimate, 0, allow_premium=False, attempts=attempts)
        if ready is None:
            raise self._fail(task, attempts)
        route_prefix = ready.provider.litellm_embedding_prefix or ready.provider.litellm_prefix
        last_error = ""
        for _ in range(2):
            started = time.perf_counter()
            try:
                out = self.backend.embed(
                    route=f"{route_prefix}/{ready.model}",
                    texts=texts,
                    api_base=ready.provider.api_base,
                    api_key=ready.api_key,
                    timeout_s=self.timeout_s,
                )
            except Exception as exc:  # noqa: BLE001
                last_error = redact(f"{type(exc).__name__}: {exc}")[:400]
                latency = int((time.perf_counter() - started) * 1000)
                self._log_call(
                    task,
                    model_ref,
                    ready.provider.paid,
                    0,
                    0,
                    0.0,
                    success=False,
                    latency_ms=latency,
                    error=last_error,
                )
                continue
            latency = int((time.perf_counter() - started) * 1000)
            if len(out.vectors) != len(texts) or any(not v for v in out.vectors):
                last_error = f"expected {len(texts)} vectors, got {len(out.vectors)}"
                self._log_call(
                    task,
                    model_ref,
                    ready.provider.paid,
                    out.input_tokens,
                    0,
                    0.0,
                    success=False,
                    latency_ms=latency,
                    error=last_error,
                )
                continue
            cost = self.actual_cost_usd(model_ref, out.input_tokens, 0) if ready.provider.paid else 0.0
            self._log_call(
                task, model_ref, ready.provider.paid, out.input_tokens, 0, cost, latency_ms=latency
            )
            return EmbeddingResult(out.vectors, model_ref, cost, out.input_tokens, latency)
        attempts.append(Attempt(model_ref, f"failed: {last_error}"))
        raise self._fail(task, attempts)

    def month_spend_usd(self) -> float:
        with Session(self.engine) as s:
            total = s.exec(
                select(func.coalesce(func.sum(LLMCall.cost_usd), 0.0)).where(
                    LLMCall.created_at >= month_start_utc()
                )
            ).one()
        return float(total)

    def estimate_cost_usd(self, model_ref: str, messages: list[dict], max_tokens: int) -> float:
        """Worst case: estimated input tokens plus the full max_tokens of output."""
        return self._price(model_ref, estimate_input_tokens(messages), max_tokens)

    def actual_cost_usd(self, model_ref: str, input_tokens: int, output_tokens: int) -> float:
        return self._price(model_ref, input_tokens, output_tokens)

    # ---------- internals ----------
    def _task(self, task: str, kind: str) -> TaskConfig:
        if task not in self.config.tasks:
            raise KeyError(f"Unknown task '{task}' — add it to config/models.yaml")
        spec = self.config.tasks[task]
        if spec.kind != kind:
            raise ValueError(f"Task '{task}' is a {spec.kind} task, not {kind}")
        return spec

    @staticmethod
    def _fail(task: str, attempts: list[Attempt]) -> AllModelsFailed:
        error = AllModelsFailed(task, attempts)
        logger.warning(str(error))
        return error

    def _price(self, model_ref: str, input_tokens: float, output_tokens: float) -> float:
        price = self.config.prices.get(model_ref)
        if price is None:
            return 0.0
        return (input_tokens * price.input_per_million + output_tokens * price.output_per_million) / 1_000_000

    def _preflight(
        self,
        model_ref: str,
        est_input_tokens: float,
        max_output_tokens: int,
        *,
        allow_premium: bool,
        attempts: list[Attempt],
    ) -> _Ready | None:
        """Premium approval → allow-list → API key → budget. Returns None (with a reason) to skip."""
        _, provider, model = self.config.provider_of(model_ref)
        if (
            model_ref in self.config.premium_models
            and self.config.budget.premium_requires_approval
            and not allow_premium
        ):
            attempts.append(Attempt(model_ref, "skipped: premium model needs your approval"))
            return None
        if provider.host not in self.config.allowed_hosts:
            attempts.append(Attempt(model_ref, f"refused: host {provider.host} not in allowed_hosts"))
            logger.warning(f"Refused call to non-allow-listed host {provider.host} for {model_ref}")
            return None
        api_key = None
        if provider.secret:
            api_key = self.secret_getter(provider.secret)
            if not api_key:
                attempts.append(Attempt(model_ref, f"skipped: no '{provider.secret}' key stored"))
                return None
        if provider.paid:
            spent = self.month_spend_usd()
            estimate = self._price(model_ref, est_input_tokens, max_output_tokens)
            if spent + estimate > self.budget_cap_usd:
                attempts.append(
                    Attempt(
                        model_ref,
                        f"skipped: monthly budget (spent ${spent:.4f} + up to ${estimate:.4f} > cap ${self.budget_cap_usd:.2f})",
                    )
                )
                return None
        return _Ready(provider, model, api_key)

    def _try_chat(
        self,
        task: str,
        spec: TaskConfig,
        model_ref: str,
        messages: list[dict],
        allow_premium: bool,
        attempts: list[Attempt],
    ) -> LLMResult | None:
        _, provider, _ = self.config.provider_of(model_ref)
        # Cache first (after the cheap premium/allow-list checks), so cached answers cost nothing.
        if (
            model_ref in self.config.premium_models
            and self.config.budget.premium_requires_approval
            and not allow_premium
        ):
            attempts.append(Attempt(model_ref, "skipped: premium model needs your approval"))
            return None
        if provider.host not in self.config.allowed_hosts:
            attempts.append(Attempt(model_ref, f"refused: host {provider.host} not in allowed_hosts"))
            logger.warning(f"Refused call to non-allow-listed host {provider.host} for {model_ref}")
            return None
        cache_key = self._cache_key(task, model_ref, spec, messages)
        if spec.cache:
            hit = self._cache_get(cache_key)
            if hit is not None:
                self._log_call(
                    task, model_ref, provider.paid, hit.input_tokens, hit.output_tokens, 0.0, cached=True
                )
                return LLMResult(
                    hit.response_text, model_ref, 0.0, True, hit.input_tokens, hit.output_tokens, 0
                )

        ready = self._preflight(
            model_ref,
            estimate_input_tokens(messages),
            spec.max_tokens,
            allow_premium=allow_premium,
            attempts=attempts,
        )
        if ready is None:
            return None

        last_error = ""
        for _ in range(2):  # one call + one retry
            started = time.perf_counter()
            try:
                out = self.backend.complete(
                    route=f"{ready.provider.litellm_prefix}/{ready.model}",
                    messages=messages,
                    api_base=ready.provider.api_base,
                    api_key=ready.api_key,
                    max_tokens=spec.max_tokens,
                    temperature=spec.temperature,
                    reasoning_effort=spec.reasoning_effort,
                    timeout_s=self.timeout_s,
                    extra_options=spec.ollama_options or None,
                    json_output=spec.json_output,
                )
            except Exception as exc:  # noqa: BLE001 — any provider error moves us to retry/fallback
                last_error = redact(f"{type(exc).__name__}: {exc}")[:400]
                latency = int((time.perf_counter() - started) * 1000)
                self._log_call(
                    task,
                    model_ref,
                    provider.paid,
                    0,
                    0,
                    0.0,
                    success=False,
                    latency_ms=latency,
                    error=last_error,
                )
                continue
            latency = int((time.perf_counter() - started) * 1000)
            cost = (
                self.actual_cost_usd(model_ref, out.input_tokens, out.output_tokens) if provider.paid else 0.0
            )
            if not out.text.strip():
                last_error = "empty response"
                self._log_call(
                    task,
                    model_ref,
                    provider.paid,
                    out.input_tokens,
                    out.output_tokens,
                    cost,
                    success=False,
                    latency_ms=latency,
                    error=last_error,
                )
                continue
            self._log_call(
                task, model_ref, provider.paid, out.input_tokens, out.output_tokens, cost, latency_ms=latency
            )
            if spec.cache:
                self._cache_put(cache_key, task, model_ref, out.text, out.input_tokens, out.output_tokens)
            return LLMResult(out.text, model_ref, cost, False, out.input_tokens, out.output_tokens, latency)

        attempts.append(Attempt(model_ref, f"failed: {last_error}"))
        return None

    @staticmethod
    def _cache_key(task: str, model_ref: str, spec: TaskConfig, messages: list[dict]) -> str:
        payload = {
            "task": task,
            "model": model_ref,
            "messages": messages,
            "max_tokens": spec.max_tokens,
            "temperature": spec.temperature,
            "reasoning_effort": spec.reasoning_effort,
            "json_output": spec.json_output,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

    def _cache_get(self, key: str) -> CacheEntry | None:
        with Session(self.engine) as s:
            return s.get(CacheEntry, key)

    def _cache_put(self, key: str, task: str, model_ref: str, text: str, tin: int, tout: int) -> None:
        with Session(self.engine) as s:
            s.merge(
                CacheEntry(
                    key=key,
                    task=task,
                    model_ref=model_ref,
                    response_text=text,
                    input_tokens=tin,
                    output_tokens=tout,
                    created_at=utcnow(),
                )
            )
            s.commit()

    def _log_call(
        self,
        task: str,
        model_ref: str,
        paid: bool,
        tin: int,
        tout: int,
        cost: float,
        *,
        cached: bool = False,
        success: bool = True,
        latency_ms: int = 0,
        error: str | None = None,
    ) -> None:
        with Session(self.engine) as s:
            s.add(
                LLMCall(
                    task=task,
                    model_ref=model_ref,
                    paid=paid,
                    input_tokens=tin,
                    output_tokens=tout,
                    cost_usd=cost,
                    cached=cached,
                    success=success,
                    latency_ms=latency_ms,
                    error=error,
                )
            )
            s.commit()
        status = "cache hit" if cached else ("ok" if success else f"error: {error}")
        logger.info(
            f"LLM {task} via {model_ref}: {status}; tokens {tin}/{tout}; ${cost:.6f}; {latency_ms} ms"
        )
