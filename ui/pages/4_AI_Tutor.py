import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make ui/common.py importable

import common  # noqa: E402,F401
import streamlit as st  # noqa: E402
from common import page, router_or_stop  # noqa: E402

from app.llm.router import AllModelsFailed  # noqa: E402

page("AI Tutor", "💬")
st.title("💬 AI Tutor")
st.warning(
    "**Phase 0 connectivity test.** Answers are NOT yet based on your textbook — "
    "textbook-grounded answers with page citations arrive in Phase 1."
)

router = router_or_stop()

SYSTEM_PROMPT = (
    "You are a friendly teaching assistant for school students. Explain clearly and briefly, "
    "using simple language and an everyday example where helpful. Answer in English unless the "
    "user explicitly asks for Hindi or Marathi."
)
CHOICES = {
    "Local model (free, on this laptop)": "test_local",
    "OpenAI gpt-5-nano (paid, counts toward budget)": "test_openai",
}

choice = st.radio("Model", list(CHOICES), horizontal=True)
st.session_state.setdefault("tutor_history", [])

for turn in st.session_state.tutor_history:
    with st.chat_message(turn["role"]):
        st.markdown(turn["content"])
        if turn.get("meta"):
            st.caption(turn["meta"])

if question := st.chat_input("Ask a question…"):
    st.session_state.tutor_history.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"), st.spinner("Thinking…"):
        try:
            # Each question is sent on its own (no chat history) to keep token use low.
            result = router.complete(
                CHOICES[choice],
                [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": question}],
            )
        except AllModelsFailed as err:
            st.error("No model could answer:")
            for attempt in err.attempts:
                st.markdown(f"- `{attempt.model_ref}` → {attempt.outcome}")
        else:
            meta = (
                f"{result.model_ref} · {result.input_tokens}+{result.output_tokens} tokens · "
                f"${result.cost_usd:.6f}"
                + (" · from cache" if result.cached else f" · {result.latency_ms / 1000:.1f} s")
            )
            st.markdown(result.text)
            st.caption(meta)
            st.session_state.tutor_history.append({"role": "assistant", "content": result.text, "meta": meta})

if st.session_state.tutor_history and st.button("Clear conversation"):
    st.session_state.tutor_history = []
    st.rerun()
