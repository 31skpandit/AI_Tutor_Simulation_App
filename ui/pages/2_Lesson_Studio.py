import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make ui/common.py importable

import json  # noqa: E402
import re  # noqa: E402

import common  # noqa: E402,F401
import streamlit as st  # noqa: E402
from common import ingestion_or_stop, page  # noqa: E402
from lesson_views import (  # noqa: E402
    available_scenes,
    lesson_figures,
    lesson_profile,
    render_cause_effect,
    render_concept,
    render_equations,
    render_figures,
    render_map,
    render_molecules,
    render_people,
    render_scene,
    render_simulation,
    render_timeline,
    scene_or_reason,
)

from app.jobs.runner import queue_summary  # noqa: E402
from app.lessons.service import LessonService, photo_queries  # noqa: E402

page("Lesson Studio", "🛠️")
st.title("🛠️ Lesson Studio")
st.caption(
    "Create a lesson from your reviewed textbook pages → check and edit it → approve → present it in Teach Mode. "
    "Lesson text and simulations are written by gpt-5.4-mini (≈ 2–5 ¢ per lesson, made once); equations are checked "
    "automatically; simulations pass safety and syntax checks, a run in a hidden browser (every control is used) and "
    "an automatic picture check before you see them. 3D bonding & reaction scenes are computed without AI."
)
service, worker = ingestion_or_stop()
lessons = LessonService(
    service.engine, service.router, service.settings.lesson_min_relevance, service.settings
)
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
newer_pages = lessons.pages_added_after(lesson)
if newer_pages:
    n1, n2 = st.columns([4, 1])
    n1.info(
        f"Textbook page(s) {', '.join(map(str, newer_pages))} became searchable after this lesson was written "
        "(e.g. pages you reviewed later). Rebuild the lesson to include them — your edits to this version are "
        "replaced."
    )
    if n2.button("🔁 Rebuild lesson (≈ 2–3 ¢)"):
        lessons.enqueue("lesson_plan", lesson.id)
        st.toast("Lesson queued — it is rewritten from the whole chapter in about a minute.")

is_history = lesson_profile(plan) == "history"
is_maths = lesson_profile(plan) == "maths"
if (
    is_maths
):  # maths lessons: concepts with checked examples, real-life stories and photos, 2D and 3D pictures
    content_tab, concepts_tab, src_tab = st.tabs(
        ["📄 Content", "🧮 Concepts & visuals", "📚 Textbook sources"]
    )
elif (
    is_history
):  # history / social-science lessons: timeline, map, causes & effects, people and textbook pictures
    content_tab, time_tab, map_tab, cause_tab, people_tab, src_tab = st.tabs(
        [
            "📄 Content",
            "🕰️ Timeline",
            "🗺️ Map",
            "🔗 Causes & effects",
            "👤 People & pictures",
            "📚 Textbook sources",
        ]
    )
else:
    content_tab, chem_tab, scenes_tab, sim_tab, src_tab = st.tabs(
        [
            "📄 Content",
            "⚗️ Equations & molecules",
            "🎬 3D bonding & reactions",
            "🧪 Simulation",
            "📚 Textbook sources",
        ]
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
    equations = (
        ""
        if is_history or is_maths
        else st.text_area(
            "Equations (one per line: equation | meaning) — re-checked when you save",
            "\n".join(f"{e.get('equation', '')} | {e.get('meaning', '')}" for e in plan.get("equations", [])),
            height=100,
        )
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

if is_history:
    with time_tab:
        st.caption(
            "Every date below was checked against your textbook pages; entries the AI could not prove were removed "
            "(listed in the yellow warnings above). Step through it in class with Next ▶."
        )
        render_timeline(plan)
    with map_tab:
        unplaced = render_map(plan)
        if unplaced:
            st.markdown(
                "**Not on the map yet** — add a hint (state or nearby city) or the position (lat, lon):"
            )
            with st.form(f"places_{lesson.id}_{lesson.version}"):
                answers = {}
                for item in unplaced:
                    answers[item["name"]] = st.text_input(
                        f"{item['name']} — {item['reason']}",
                        placeholder="e.g. Jharkhand   or   near Dhanbad   or   23.65, 86.48",
                        key=f"hint_{lesson.id}_{item['name']}",
                    )
                if st.form_submit_button("📍 Save and place again"):
                    for place in plan.get("places", []):
                        answer = answers.get(place.get("name"), "").strip()
                        numbers = re.findall(r"-?\d+(?:\.\d+)?", answer)
                        if len(numbers) == 2 and "," in answer:
                            place["lat"], place["lon"] = float(numbers[0]), float(numbers[1])
                        elif answer:
                            place["near"] = re.sub(r"^near\s+", "", answer, flags=re.I)
                    lessons.save_plan(lesson.id, plan)
                    st.rerun()
    with cause_tab:
        st.caption(
            "Written by the AI from the cited pages — read them once before teaching (pages are shown)."
        )
        render_cause_effect(plan)
    with people_tab:
        figures = lesson_figures(lesson.document_id, plan, service.engine)
        render_people(plan, figures)
        st.divider()
        st.markdown("**Pictures from your textbook** (with their printed captions)")
        render_figures(figures)

if is_maths:
    with concepts_tab:
        st.caption(
            "Every answer below was re-computed by the app (wrong AI answers are corrected and listed in the warnings). "
            "The 2D and 3D pictures are drawn from those computed numbers — no AI drawing, no cost. Real-life photos "
            "come from Wikimedia Commons / Openverse (free licences only, credit shown) and are checked by the local "
            "vision model before you see them."
        )
        waiting = photo_queries(plan)
        p1, p2 = st.columns([3, 1])
        if waiting:
            p1.info(f"{len(waiting)} real-life example(s) still need a photo.")
        if p2.button(
            "🔎 Find photos now", disabled=not waiting, help="Free: Wikimedia + the local vision model"
        ):
            lessons.enqueue("media", lesson.id)
            st.toast("Looking for photos — they appear here in a minute or two.")
        concepts = plan.get("concepts", [])
        if not concepts:
            st.info("This lesson has no concepts — rebuild it to get them.")
        for index, concept in enumerate(concepts):
            with st.container(border=True):
                render_concept(
                    concept,
                    index,
                    lessons.photos,
                    service.settings.data_dir,
                    key=f"s{lesson.id}",
                    on_reject=lambda asset_id: lessons.reject_photo(lesson.id, asset_id),
                )
                if st.button(
                    "➕ More real-life examples (≈ 0.2 ¢)",
                    key=f"more_{lesson.id}_{index}",
                    help="Two new everyday examples for this concept, then photos for them",
                ):
                    lessons.enqueue("real_life", lesson.id, options=concept.get("name", ""))
                    st.toast("Queued — the new examples appear here in about a minute.")

if not is_history and not is_maths:  # science lessons: chemistry, 3D scenes, simulation
    with chem_tab:
        render_equations(plan)
        st.divider()
        m1, m2 = st.columns(2)
        show_3d = m1.toggle("Show 3D (rotatable)", value=True)
        atom_labels = m2.toggle("Atom labels with charges (e.g. Cu²⁺, O⁻)", value=True)
        render_molecules(plan, show_3d=show_3d, show_atom_labels=atom_labels)

    with scenes_tab:
        st.caption(
            "Electrons and atoms move step by step: ionic bonds (electron transfer), covalent bonds (shared pairs) and "
            "reactions (atoms change partners). Computed from the checked molecule table and balanced equations — no AI, "
            "no cost. These scenes appear in Teach Mode after the molecules."
        )
        shown, reasons = available_scenes(plan)
        if shown:
            choice = st.selectbox("Show", shown, key=f"scene_{lesson.id}")
            render_scene(choice)
        else:
            st.info(
                "None of this lesson's molecules or equations can be shown as a 3D scene yet — add one below."
            )
        if reasons:
            with st.expander(f"Not shown ({len(reasons)}) and why"):
                for source, reason in reasons.items():
                    st.markdown(f"- **{source}** — {reason}")
        extras = list(plan.get("scenes_3d", []))
        with st.form(f"scenes_{lesson.id}_{lesson.version}"):
            added = st.text_input(
                "Add a formula or an equation for this lesson",
                placeholder="e.g. MgO   or   2H₂O → 2H₂ + O₂   (the 3D Chemistry Lab page shows what works)",
            )
            if st.form_submit_button("➕ Add") and added.strip():
                _, problem = scene_or_reason(added.strip())
                if problem:
                    st.error(f"Cannot show **{added.strip()}**: {problem}")
                else:
                    plan["scenes_3d"] = extras + [added.strip()]
                    lessons.save_plan(lesson.id, plan)
                    st.rerun()
        for extra in extras:
            c1, c2 = st.columns([5, 1])
            c1.caption(f"Added by you: {extra}")
            if c2.button("Remove", key=f"rm_{lesson.id}_{extra}"):
                plan["scenes_3d"] = [x for x in extras if x != extra]
                lessons.save_plan(lesson.id, plan)
                st.rerun()

    with sim_tab:
        sim = plan.get("simulation", {})
        st.markdown(f"**{sim.get('title', 'Simulation')}** — {sim.get('brief', '')}")
        render_simulation(lesson)
        instruction = st.text_input(
            "Change request (optional)",
            placeholder="e.g. make the beaker bigger and show the pH number larger",
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
