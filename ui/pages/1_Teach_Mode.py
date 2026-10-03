import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make ui/common.py importable

import common  # noqa: E402,F401
import streamlit as st  # noqa: E402
from common import coming_soon, page  # noqa: E402

page("Teach Mode", "🧑‍🏫")
st.title("🧑‍🏫 Teach Mode")
coming_soon(
    2,
    [
        "Full-screen presentation of an approved lesson",
        "Slides, interactive simulations, rotatable 3D molecules",
        "Animated videos (Phase 3) and an end-of-lesson quiz (Phase 4)",
    ],
)
