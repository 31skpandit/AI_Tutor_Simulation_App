import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make ui/common.py importable

import common  # noqa: E402,F401
import streamlit as st  # noqa: E402
from common import ingestion_or_stop, page  # noqa: E402
from lesson_views import render_equations, render_molecules, render_simulation  # noqa: E402

from app.lessons.service import LessonService  # noqa: E402

page("Teach Mode", "🧑‍🏫")
service, _ = ingestion_or_stop()
lessons = LessonService(service.engine, service.router)

# Larger text for the projector (pure CSS, no scripts).
st.markdown(
    "<style>.teach h1{font-size:2.6rem!important}.teach p,.teach li{font-size:1.45rem!important;line-height:1.6}"
    "</style>",
    unsafe_allow_html=True,
)

show_drafts = st.sidebar.toggle("Also show draft lessons", value=False)
available = [x for x in lessons.lessons() if x.status == "approved" or (show_drafts and x.status == "draft")]
if not available:
    st.title("🧑‍🏫 Teach Mode")
    st.info("No approved lessons yet. Create and approve one in **Lesson Studio**.")
    st.stop()

lesson = st.sidebar.selectbox("Lesson", available, format_func=lambda x: f"{x.title} ({x.status})")
lesson = lessons.get(lesson.id)
plan = lessons.plan(lesson)

slides: list[tuple[str, str]] = [("title", "")]
slides += [("section", str(i)) for i in range(len(plan.get("sections", [])))]
if plan.get("equations"):
    slides.append(("equations", ""))
if plan.get("molecules"):
    slides.append(("molecules", ""))
if lesson.simulation_js:
    slides.append(("simulation", ""))
slides.append(("summary", ""))

key = f"slide_{lesson.id}"
st.session_state.setdefault(key, 0)
st.session_state[key] = min(st.session_state[key], len(slides) - 1)
kind, arg = slides[st.session_state[key]]

st.markdown("<div class='teach'>", unsafe_allow_html=True)
if kind == "title":
    st.title(plan.get("title", lesson.title))
    st.markdown("#### In this lesson you will")
    for objective in plan.get("objectives", []):
        st.markdown(f"- {objective}")
elif kind == "section":
    section = plan["sections"][int(arg)]
    st.title(section.get("heading", ""))
    st.markdown(section.get("content", ""))
    if section.get("pages"):
        st.caption("📖 Textbook page(s): " + ", ".join(map(str, section["pages"])))
elif kind == "equations":
    st.title("Equations")
    render_equations(plan, big=True)
elif kind == "molecules":
    st.title("Molecules — rotate them!")
    render_molecules(plan, show_3d=True, height=420)
elif kind == "simulation":
    st.title(plan.get("simulation", {}).get("title", "Try it yourself"))
    render_simulation(lesson, height=680)
else:
    st.title("Key points")
    for point in plan.get("key_points", []):
        st.markdown(f"- {point}")
    if plan.get("vocabulary"):
        st.markdown("#### Words to remember")
        for item in plan["vocabulary"]:
            st.markdown(f"- **{item.get('term', '')}** — {item.get('meaning', '')}")
st.markdown("</div>", unsafe_allow_html=True)

st.divider()
left, middle, right = st.columns([1, 3, 1])
if left.button("◀ Previous", disabled=st.session_state[key] == 0):
    st.session_state[key] -= 1
    st.rerun()
middle.progress(
    (st.session_state[key] + 1) / len(slides), text=f"Slide {st.session_state[key] + 1} of {len(slides)}"
)
if right.button("Next ▶", disabled=st.session_state[key] == len(slides) - 1):
    st.session_state[key] += 1
    st.rerun()
st.caption("Tip: press F11 for full screen and collapse the sidebar (‹ at top left) when presenting.")
