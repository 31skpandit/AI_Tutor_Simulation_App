from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlmodel import Session, select

from app.db.models import LLMCall
from app.llm.backend import BackendResult
from app.llm.router import AllModelsFailed, month_start_utc
from tests.conftest import FakeBackend

MSG = [{"role": "user", "content": "What is H2O?"}]


def test_local_call_is_free_and_logged(make_router, engine):
    router = make_router()
    result = router.complete("local_only", MSG)
    assert result.text == "answer" and result.cost_usd == 0.0 and not result.cached
    with Session(engine) as s:
        rows = s.exec(select(LLMCall)).all()
    assert len(rows) == 1 and rows[0].success and rows[0].model_ref == "ollama/small"


def test_paid_call_cost_uses_config_prices(make_router):
    backend = FakeBackend([BackendResult("ok", 1_000, 2_000)])
    result = make_router(backend).complete("paid_then_local", MSG)
    # 1,000 in * $1/M + 2,000 out * $2/M = $0.005
    assert result.model_ref == "openai/cheap"
    assert result.cost_usd == pytest.approx(0.005)
    assert backend.calls[0]["api_key"] == "sk-test-key-123456"
    assert backend.calls[0]["api_base"] == "https://api.openai.com/v1"
    assert backend.calls[0]["route"] == "openai/cheap"


def test_identical_request_hits_cache_and_costs_nothing(make_router):
    backend = FakeBackend()
    router = make_router(backend)
    first = router.complete("paid_then_local", MSG)
    second = router.complete("paid_then_local", MSG)
    assert len(backend.calls) == 1
    assert second.cached and second.cost_usd == 0.0 and second.text == first.text


def test_cache_can_be_disabled_per_task(make_router):
    backend = FakeBackend()
    router = make_router(backend)
    router.complete("no_cache", MSG)
    router.complete("no_cache", MSG)
    assert len(backend.calls) == 2


def test_budget_exceeded_falls_back_to_local(make_router):
    # cap $0.001; worst-case estimate for 1000 output tokens at $2/M = $0.002 > cap
    backend = FakeBackend()
    result = make_router(backend, cap=0.001).complete("paid_then_local", MSG)
    assert result.model_ref == "ollama/small"
    assert [c["route"] for c in backend.calls] == ["ollama_chat/small"]


def test_budget_blocks_when_no_free_fallback(make_router):
    with pytest.raises(AllModelsFailed) as err:
        make_router(cap=0.0).complete("premium_then_cheap", MSG, allow_premium=True)
    assert err.value.budget_blocked


def test_spend_counts_toward_budget(make_router):
    backend = FakeBackend([BackendResult("a", 1_000_000, 0), BackendResult("b", 10, 10)])
    router = make_router(backend, cap=1.5)
    router.complete("paid_then_local", MSG)  # costs $1.00
    assert router.month_spend_usd() == pytest.approx(1.0)
    other = [{"role": "user", "content": "different question"}]
    result = router.complete("paid_then_local", other)  # $1.00 + est $0.002 <= $1.5 → allowed
    assert result.model_ref == "openai/cheap"


def test_previous_month_spend_is_not_counted(make_router, engine):
    with Session(engine) as s:
        s.add(
            LLMCall(
                task="t",
                model_ref="openai/cheap",
                paid=True,
                cost_usd=5.0,
                created_at=month_start_utc() - timedelta(minutes=1),
            )
        )
        s.add(
            LLMCall(
                task="t",
                model_ref="openai/cheap",
                paid=True,
                cost_usd=0.25,
                created_at=month_start_utc() + timedelta(minutes=1),
            )
        )
        s.commit()
    assert make_router().month_spend_usd() == pytest.approx(0.25)


def test_premium_needs_approval(make_router):
    backend = FakeBackend()
    result = make_router(backend).complete("premium_then_cheap", MSG)
    assert result.model_ref == "openai/cheap"
    approved = make_router(FakeBackend()).complete(
        "premium_then_cheap", [{"role": "user", "content": "x"}], allow_premium=True
    )
    assert approved.model_ref == "openai/premium"


def test_missing_key_skips_paid_model(make_router):
    result = make_router(key=None).complete("paid_then_local", MSG)
    assert result.model_ref == "ollama/small"


def test_retry_once_then_fallback(make_router, engine):
    backend = FakeBackend([TimeoutError("t1"), TimeoutError("t2"), BackendResult("local", 5, 5)])
    result = make_router(backend).complete("paid_then_local", MSG)
    assert result.model_ref == "ollama/small"
    assert [c["route"] for c in backend.calls] == ["openai/cheap", "openai/cheap", "ollama_chat/small"]
    with Session(engine) as s:
        failures = s.exec(select(LLMCall).where(LLMCall.success == False)).all()  # noqa: E712
    assert len(failures) == 2


def test_empty_response_is_treated_as_failure(make_router):
    backend = FakeBackend([BackendResult("  ", 5, 0), BackendResult("", 5, 0), BackendResult("local", 1, 1)])
    assert make_router(backend).complete("paid_then_local", MSG).model_ref == "ollama/small"


def test_errors_are_redacted_in_log(make_router, engine):
    backend = FakeBackend([ValueError("bad key sk-abcdefghijklmnop"), ValueError("again")])
    with pytest.raises(AllModelsFailed):
        make_router(backend).complete("local_only", MSG)
    with Session(engine) as s:
        errors = [r.error for r in s.exec(select(LLMCall)).all()]
    assert all("sk-abcdefghijklmnop" not in e for e in errors)


def test_non_allowlisted_host_is_refused(config, engine):
    from app.llm.router import LLMRouter

    config.allowed_hosts.remove("api.openai.com")  # simulate a provider outside the allow-list
    backend = FakeBackend()
    router = LLMRouter(config, backend, engine, secret_getter=lambda n: "sk-x")
    result = router.complete("paid_then_local", MSG)
    assert result.model_ref == "ollama/small"
    assert all(not c["route"].startswith("openai") for c in backend.calls)


def test_unknown_task_raises(make_router):
    with pytest.raises(KeyError):
        make_router().complete("nope", MSG)


def test_month_start_uses_local_calendar_month():
    ist = timezone(timedelta(hours=5, minutes=30))
    start = month_start_utc(datetime(2026, 10, 3, 12, 0, tzinfo=ist))
    # 1 Oct 2026 00:00 IST == 30 Sep 2026 18:30 UTC
    assert start == datetime(2026, 9, 30, 18, 30, tzinfo=UTC)
    assert start.utcoffset() == timedelta(0)
