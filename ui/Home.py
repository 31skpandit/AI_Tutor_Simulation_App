"""AI Teaching Studio — home page and system status.  Run:  uv run streamlit run ui/Home.py"""

import common  # noqa: F401  (must be first: sets up the import path)
import streamlit as st
from common import SYMBOL, page, router_or_stop

from app.core.secrets import KNOWN_SECRETS, has_secret
from app.core.startup_checks import run_all
from app.llm.health import configured_models, ollama_has, ollama_models

page("Home", "🎓")
st.title("🎓 AI Teaching Studio")
st.caption("Phase 0 — foundation: security, AI gateway, cost control.  Use the sidebar to open a page.")

st.subheader("Security checks")
for result in run_all():
    st.markdown(f"{SYMBOL[result.severity]} **{result.name}** — {result.detail}")

router = router_or_stop()
config = router.config

left, middle, right = st.columns(3)

with left:
    st.subheader("Local AI (Ollama)")
    installed = ollama_models(config.providers["ollama"].api_base)
    if installed is None:
        st.error("Ollama is not running. Start the Ollama app, then refresh.")
    else:
        for model in configured_models(config, "ollama"):
            ok = ollama_has(installed, model)
            st.markdown(f"{'✅' if ok else '❌'} `{model}`" + ("" if ok else f" — run `ollama pull {model}`"))

with middle:
    st.subheader("API keys")
    st.caption("Stored in Windows Credential Manager — never in files.")
    for name, label in KNOWN_SECRETS.items():
        st.markdown(f"{'✅ stored' if has_secret(name) else '— not set'} · {label}")

with right:
    st.subheader("Paid AI budget (this month)")
    spent, cap = router.month_spend_usd(), router.budget_cap_usd
    st.metric("Spent", f"${spent:.4f}", help="Calendar month, local time")
    st.progress(min(spent / cap, 1.0) if cap else 1.0, text=f"of ${cap:.2f} cap")

st.divider()
st.subheader("Roadmap")
st.markdown(
    """
| Phase | Scope | Status |
|---|---|---|
| 0 | Setup, security, AI gateway, cost control | **in progress** |
| 1 | Syllabus upload, OCR, RAG, AI tutor with citations | next |
| 2 | Lessons, chemistry visuals, simulations, Teach Mode | planned |
| 3 | Animated videos, narration (EN; HI/MR on request) | planned |
| 4 | Quizzes, library, PDF export, polish | planned |
"""
)
