import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make ui/common.py importable

import json  # noqa: E402

import common  # noqa: E402,F401
import streamlit as st  # noqa: E402
from common import ingestion_or_stop, page  # noqa: E402
from lesson_views import render_equations, render_molecules, render_simulation  # noqa: E402

from app.jobs.runner import queue_summary  # noqa: E402
from app.lessons.service import LessonService  # noqa: E402

page("Lesson Studio", "🛠️")
st.title("🛠️ Lesson Studio")
st.caption(
    "Create a lesson from your reviewed textbook pages → check and edit it → approve → present it in Teach Mode. "
    "Lesson text and simulations are written by gpt-5.4-mini (≈ 2–5 ¢ per lesson, made once); equations are checked "
    "automatically and simulations pass safety and syntax checks before you see them."
)
service, worker = ingestion_or_stop()
lessons = LessonService(service.engine, service.router, service.settings.lesson_min_relevance)
STATUS = {"generating": "⏳ writing", "draft": "📝 draft", "approved": "✅ approved", "failed": "❌ failed"}
PILOT_TOPICS = ["Neutralization reaction", "Electrolysis of water", "Water of crystallisation"]

# ---------------------------------------------------------------- new lesson
searchable = [d for d in service.documents() if service.page_counts(d.id)["indexed"]]
with st.expander("➕ New lesson", expanded=not lessons.lessons()):
    if not searchable:
        st.info("First make some textbook pages searchable (Syllabus Library → Review Text).")
    else:
        document = st.selectbox(
            "From chapter",
            searchable,
            format_func=lambda d: (
                f"{d.filename} · Class {d.class_level} {d.subject} Ch {d.chapter_no or '?'}"
            ),
        )
        topic = st.text_input("Topic", placeholder="e.g. Neutralization reaction")
        c1, c2 = st.columns([1, 3])
        if c1.button("Create lesson", type="primary", disabled=not topic.strip()):
            lessons.create(topic, document_id=document.id, chapter_no=document.chapter_no)
            st.toast("Lesson queued — it appears below in about a minute.")
        with c2:
            st.caption("Pilot topics (Phase 2):")
            cols = st.columns(len(PILOT_TOPICS))
            for column, pilot in zip(cols, PILOT_TOPICS, strict=True):
                if column.button(pilot):
                    lessons.create(pilot, document_id=document.id, chapter_no=document.chapter_no)
                    st.toast(f"'{pilot}' queued.")


# ---------------------------------------------------------------- live list
@st.fragment(run_every=4)
def live() -> None:
    for job in queue_summary(service.engine)["running"]:
        st.progress(
            job.progress, text=f"{job.kind.replace('_', ' ')} · lesson #{job.lesson_id} — {job.message}"
        )
    rows = [
        {
            "#": lesson.id,
            "title": lesson.title,
            "topic": lesson.topic,
            "status": STATUS.get(lesson.status, lesson.status),
            "simulation": lesson.simulation_status,
            "version": lesson.version,
            "cost $": round(lesson.cost_usd, 4),
            "note": lesson.error or "",
        }
        for lesson in lessons.lessons()
    ]
    if rows:
        st.dataframe(rows, hide_index=True)
    else:
        st.caption("No lessons yet.")


st.subheader("Lessons")
live()

# ---------------------------------------------------------------- open a lesson
ready = [lesson for lesson in lessons.lessons() if lesson.status in {"draft", "approved", "failed"}]
if not ready:
    st.stop()
lesson = st.selectbox(
    "Open lesson", ready, format_func=lambda x: f"#{x.id} · {x.title} · {STATUS.get(x.status, x.status)}"
)
lesson = lessons.get(lesson.id)
if lesson.status == "failed":
    st.error(f"Lesson could not be created: {lesson.error}")
    if st.button("Delete this lesson"):
        lessons.delete(lesson.id)
        st.rerun()
    st.stop()

plan = lessons.plan(lesson)
warnings = json.loads(lesson.warnings or "[]")
st.markdown(f"### {lesson.title}")
st.caption(
    f"Version {lesson.version} · {STATUS[lesson.status]} · model {lesson.model_ref} · cost ${lesson.cost_usd:.4f}"
)
for warning in warnings:
    st.warning(warning)

content_tab, chem_tab, sim_tab, src_tab = st.tabs(
    ["📄 Content", "⚗️ Equations & molecules", "🧪 Simulation", "📚 Textbook sources"]
)

with content_tab, st.form(f"edit_{lesson.id}_{lesson.version}"):
    title = st.text_input("Title", plan.get("title", lesson.title))
    objectives = st.text_area("Objectives (one per line)", "\n".join(plan.get("objectives", [])), height=110)
    new_sections = []
    for index, section in enumerate(plan.get("sections", [])):
        pages = ", ".join(map(str, section.get("pages", []))) or "—"
        heading = st.text_input(
            f"Section {index + 1} heading · textbook pages {pages}", section.get("heading", "")
        )
        text = st.text_area(f"Section {index + 1} text", section.get("content", ""), height=170)
        new_sections.append(dict(section, heading=heading, content=text))
    key_points = st.text_area("Key points (one per line)", "\n".join(plan.get("key_points", [])), height=120)
    equations = st.text_area(
        "Equations (one per line: equation | meaning) — re-checked when you save",
        "\n".join(f"{e.get('equation', '')} | {e.get('meaning', '')}" for e in plan.get("equations", [])),
        height=100,
    )
    if st.form_submit_button("💾 Save changes"):
        plan.update(
            title=title.strip(),
            objectives=[x.strip() for x in objectives.splitlines() if x.strip()],
            sections=new_sections,
            key_points=[x.strip() for x in key_points.splitlines() if x.strip()],
            equations=[
                {
                    "equation": line.split("|")[0].strip(),
                    "meaning": line.split("|", 1)[1].strip() if "|" in line else "",
                }
                for line in equations.splitlines()
                if line.strip()
            ],
        )
        lessons.save_plan(lesson.id, plan, title.strip())
        st.success("Saved (equations re-checked).")
        st.rerun()

with chem_tab:
    render_equations(plan)
    st.divider()
    render_molecules(plan, show_3d=st.toggle("Show 3D (rotatable)", value=True))

with sim_tab:
    sim = plan.get("simulation", {})
    st.markdown(f"**{sim.get('title', 'Simulation')}** — {sim.get('brief', '')}")
    render_simulation(lesson)
    instruction = st.text_input(
        "Change request (optional)", placeholder="e.g. make the beaker bigger and show the pH number larger"
    )
    if st.button("🔁 Regenerate simulation (≈ 2–4 ¢)"):
        lessons.enqueue("simulation", lesson.id, options=instruction.strip())
        st.toast("Simulation queued.")
    with st.expander("Code (advanced)"):
        code = st.text_area(
            "p5.js sketch", lesson.simulation_js, height=300, key=f"code_{lesson.id}_{lesson.version}"
        )
        if st.button("Save code and re-check"):
            problems = lessons.save_simulation_code(lesson.id, code)
            st.warning("; ".join(problems)) if problems else st.success("Code passed all checks.")

with src_tab:
    for source in plan.get("sources", []):
        with st.expander(f"[{source['n']}] {source['citation']}"):
            st.text(source["text"])

st.divider()
a1, a2 = st.columns([1, 4])
if lesson.status != "approved" and a1.button("✅ Approve for Teach Mode", type="primary"):
    lessons.approve(lesson.id)
    st.success("Approved — open Teach Mode to present it.")
    st.rerun()
with a2.popover("Delete lesson"):
    if st.button("Yes, delete this lesson"):
        lessons.delete(lesson.id)
        st.rerun()
