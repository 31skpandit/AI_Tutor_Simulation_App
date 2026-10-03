import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make ui/common.py importable

import common  # noqa: E402,F401
import streamlit as st  # noqa: E402
from common import coming_soon, page  # noqa: E402

page("Lesson Studio", "🛠️")
st.title("🛠️ Lesson Studio")
coming_soon(
    2,
    [
        "Generate a lesson for a topic from your textbook",
        "Preview, edit and regenerate sections",
        "Approve and save to the lesson library",
    ],
)
