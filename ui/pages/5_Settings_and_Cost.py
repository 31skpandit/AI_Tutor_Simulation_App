import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make ui/common.py importable

import common  # noqa: E402,F401
import streamlit as st  # noqa: E402
from common import get_router, page, router_or_stop  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app.core.secrets import KNOWN_SECRETS, delete_secret, has_secret, set_secret  # noqa: E402
from app.db.models import LLMCall  # noqa: E402
from app.tools.verify_models import verify  # noqa: E402

page("Settings & Cost", "⚙️")
st.title("⚙️ Settings & Cost")
router = router_or_stop()
config = router.config

# ---------------- Budget ----------------
st.subheader("Paid AI budget")
spent, cap = router.month_spend_usd(), router.budget_cap_usd
c1, c2, c3 = st.columns(3)
c1.metric("Spent this month", f"${spent:.4f}")
c2.metric("Monthly cap", f"${cap:.2f}")
c3.metric("Remaining", f"${max(cap - spent, 0):.4f}")
st.caption(
    "Change the cap with `ATS_MONTHLY_BUDGET_USD` in `.env` (or `budget.monthly_usd_cap` in "
    "`config/models.yaml`), then click *Reload configuration* below. Also set a limit in your OpenAI dashboard."
)

# ---------------- API keys ----------------
st.subheader("API keys")
st.caption("Saved in Windows Credential Manager (encrypted for your Windows user) — never written to files.")
for name, label in KNOWN_SECRETS.items():
    st.markdown(f"{'✅ stored' if has_secret(name) else '— not set'} · **{label}** (`{name}`)")

with st.form("set_key", clear_on_submit=True):
    name = st.selectbox("Key", list(KNOWN_SECRETS), format_func=lambda n: KNOWN_SECRETS[n])
    value = st.text_input("Paste key", type="password")
    save, remove = st.columns(2)
    if save.form_submit_button("Save key"):
        try:
            set_secret(name, value)
            st.success(f"{KNOWN_SECRETS[name]} saved.")
        except ValueError as err:
            st.error(str(err))
    if remove.form_submit_button("Delete key"):
        if delete_secret(name):
            st.success("Deleted.")
        else:
            st.info("Nothing was stored.")

# ---------------- Models ----------------
st.subheader("Model routing (config/models.yaml)")
st.dataframe(
    [
        {
            "task": task,
            "primary": spec.primary,
            "fallbacks": ", ".join(spec.fallbacks) or "—",
            "max tokens": spec.max_tokens,
            "reasoning": spec.reasoning_effort or "—",
            "cache": spec.cache,
        }
        for task, spec in config.tasks.items()
    ],
    hide_index=True,
)
st.caption(
    f"Allowed hosts: {', '.join(config.allowed_hosts)} · Premium (needs approval): "
    f"{', '.join(config.premium_models) or 'none'}"
)

left, right = st.columns(2)
if left.button("Verify models & prices"):
    with st.spinner("Checking Ollama, OpenAI and prices (no tokens used)…"):
        for finding in verify(config):
            icon = {"ok": "✅", "warning": "⚠️", "error": "❌"}[finding.level]
            st.markdown(f"{icon} {finding.message}")
if right.button("Reload configuration"):
    get_router.clear()
    st.rerun()

# ---------------- Call log ----------------
st.subheader("Recent AI calls")
with Session(router.engine) as session:
    calls = session.exec(select(LLMCall).order_by(LLMCall.id.desc()).limit(100)).all()
if not calls:
    st.caption("No calls yet.")
else:
    st.dataframe(
        [
            {
                "time": c.created_at.astimezone().strftime("%d %b %H:%M:%S"),
                "task": c.task,
                "model": c.model_ref,
                "tokens in/out": f"{c.input_tokens}/{c.output_tokens}",
                "cost $": round(c.cost_usd, 6),
                "cached": c.cached,
                "ok": c.success,
                "ms": c.latency_ms,
                "error": c.error or "",
            }
            for c in calls
        ],
        hide_index=True,
    )
