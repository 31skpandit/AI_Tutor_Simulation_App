"""Shared helpers for all Streamlit pages."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from app.core.startup_checks import StartupCheckError  # noqa: E402

SYMBOL = {"ok": "✅", "warning": "⚠️", "error": "❌"}


def page(title: str, icon: str) -> None:
    st.set_page_config(page_title=f"{title} · AI Teaching Studio", page_icon=icon, layout="wide")


@st.cache_resource(show_spinner="Starting the AI gateway…")
def get_router():
    from app.llm.service import build_router

    return build_router()


def router_or_stop():
    """Return the router, or explain why AI features are disabled and stop the page."""
    try:
        return get_router()
    except StartupCheckError as err:
        st.error("Security checks failed — AI features stay disabled until these are fixed:")
        for failure in err.failures:
            st.markdown(f"❌ **{failure.name}** — {failure.detail}")
        st.stop()


def coming_soon(phase: int, items: list[str]) -> None:
    st.info(f"This page is built in **Phase {phase}**. It will include:")
    for item in items:
        st.markdown(f"- {item}")
