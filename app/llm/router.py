"""Task-based model router (blueprint Fig. 4).

For each candidate model of a task, in order:
  premium approval → host allow-list → cache → API key → budget → call (retry once) → log → cache.
A candidate that is skipped or fails moves on to the next one in the fallback chain.
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
from app.llm.config import ModelsConfig, TaskConfig

DEFAULT_TIMEOUT_S = 180.0


@dataclass(frozen=True)
class LLMResult:
    text: str
    model_ref: str
    cost_usd: float
    cached: bool
    input_tokens: int
    output_tokens: int
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


def month_start_utc(now_local: datetime | None = None) -> datetime:
    """First instant of the current *local* calendar month, in UTC.

    `now_local` must be timezone-aware; defaults to the laptop's local time.
    """
    local = (now_local or datetime.now().astimezone()).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    return local.astimezone(UTC)


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
        if task not in self.config.tasks:
            raise KeyError(f"Unknown task '{task}' — add it to config/models.yaml")
        spec = self.config.tasks[task]
        attempts: list[Attempt] = []
        for model_ref in spec.chain:
            result = self._try_model(task, spec, model_ref, messages, allow_premium, attempts)
            if result is not None:
                return result
        error = AllModelsFailed(task, attempts)
        logger.warning(str(error))
        raise error

    def month_spend_usd(self) -> float:
        with Session(self.engine) as s:
            total = s.exec(
                select(func.coalesce(func.sum(LLMCall.cost_usd), 0.0)).where(
                    LLMCall.created_at >= month_start_utc()
                )
            ).one()
        return float(total)

    def estimate_cost_usd(self, model_ref: str, messages: list[dict], max_tokens: int) -> float:
        """Worst case: ~4 characters per input token, and the full max_tokens of output."""
        price = self.config.prices.get(model_ref)
        if price is None:
            return 0.0
        input_tokens = sum(len(json.dumps(m.get("content", ""), ensure_ascii=False)) for m in messages) / 4
        return (input_tokens * price.input_per_million + max_tokens * price.output_per_million) / 1_000_000

    def actual_cost_usd(self, model_ref: str, input_tokens: int, output_tokens: int) -> float:
        price = self.config.prices.get(model_ref)
        if price is None:
            return 0.0
        return (input_tokens * price.input_per_million + output_tokens * price.output_per_million) / 1_000_000

    # ---------- internals ----------
    def _try_model(
        self,
        task: str,
        spec: TaskConfig,
        model_ref: str,
        messages: list[dict],
        allow_premium: bool,
        attempts: list[Attempt],
    ) -> LLMResult | None:
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

        api_key = None
        if provider.secret:
            api_key = self.secret_getter(provider.secret)
            if not api_key:
                attempts.append(Attempt(model_ref, f"skipped: no '{provider.secret}' key stored"))
                return None

        if provider.paid:
            spent = self.month_spend_usd()
            estimate = self.estimate_cost_usd(model_ref, messages, spec.max_tokens)
            if spent + estimate > self.budget_cap_usd:
                attempts.append(
                    Attempt(
                        model_ref,
                        f"skipped: monthly budget (spent ${spent:.4f} + up to ${estimate:.4f} > cap ${self.budget_cap_usd:.2f})",
                    )
                )
                return None

        last_error = ""
        for _ in range(2):  # one call + one retry
            started = time.perf_counter()
            try:
                out = self.backend.complete(
                    route=f"{provider.litellm_prefix}/{model}",
                    messages=messages,
                    api_base=provider.api_base,
                    api_key=api_key,
                    max_tokens=spec.max_tokens,
                    temperature=spec.temperature,
                    reasoning_effort=spec.reasoning_effort,
                    timeout_s=self.timeout_s,
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
