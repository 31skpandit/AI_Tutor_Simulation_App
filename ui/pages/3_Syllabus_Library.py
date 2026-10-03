import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make ui/common.py importable

import common  # noqa: E402,F401
import streamlit as st  # noqa: E402
from common import coming_soon, page  # noqa: E402

page("Syllabus Library", "📚")
st.title("📚 Syllabus Library")
coming_soon(
    1,
    [
        "Upload syllabus and textbook pages (photos or PDFs)",
        "Text extraction (OCR) with a review screen to correct mistakes",
        "Organise by Class → Subject → Chapter → Topic, with page numbers",
    ],
)
