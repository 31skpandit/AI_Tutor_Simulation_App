"""Shared display helpers for Lesson Studio and Teach Mode."""

import json

import streamlit as st
import streamlit.components.v1 as components

from app.lessons.figures import figures_for, portrait_of
from app.lessons.history import flow_scenes, map_scene, timeline_scene
from app.lessons.molecules import build
from app.lessons.reactions import SceneError, build_scene, lesson_scene_sources
from app.lessons.simulation import VISUAL_PREFIX, blocking
from app.lessons.viewers import VendorFileError, chem3d_html, history_html, molecule_html, simulation_html


def render_equations(plan: dict, big: bool = False) -> None:
    for item in plan.get("equations", []):
        mark = "✅" if item.get("balanced") else "⚠️"
        size = "1.6rem" if big else "1.15rem"
        st.markdown(
            f"<div style='font-size:{size};margin:6px 0'>{mark} {item.get('equation', '')}</div>",
            unsafe_allow_html=True,
        )
        caption = item.get("meaning", "")
        if not item.get("balanced"):
            caption += f" — {item.get('check', 'not checked')}"
        if caption:
            st.caption(caption)


@st.cache_data(max_entries=64, show_spinner=False)
def _molecule(name: str, formula: str):
    return build(name, formula)  # frozen dataclass — safe to cache


def render_molecules(
    plan: dict, show_3d: bool = True, height: int = 360, show_atom_labels: bool = True
) -> None:
    molecules = plan.get("molecules", [])
    if not molecules:
        st.caption("No molecules in this lesson.")
        return
    columns = st.columns(min(len(molecules), 3))
    for index, item in enumerate(molecules):
        with columns[index % len(columns)]:
            molecule = _molecule(item.get("name", ""), item.get("formula", ""))
            st.markdown(f"**{item.get('name', '')}** ({item.get('formula', '')})")
            if molecule is None:
                st.caption("Structure not available in the local molecule table.")
                continue
            if show_3d and molecule.molblock:
                try:
                    components.html(
                        molecule_html(
                            molecule.molblock,
                            molecule.atom_labels,
                            molecule.ion_labels,
                            height,
                            show_atom_labels,
                        ),
                        height=height + 8,
                    )
                except VendorFileError as err:
                    st.error(str(err))
            else:
                st.image(molecule.svg.encode("utf-8"))
            st.caption(
                molecule.name + (" — drag to rotate, scroll to zoom" if show_3d and molecule.molblock else "")
            )
            legend = " · ".join(f"**{symbol}** = {name}" for symbol, name in molecule.elements)
            st.markdown(f"<span style='font-size:0.9rem'>{legend}</span>", unsafe_allow_html=True)
            for note in molecule.notes:
                st.caption("ℹ️ " + note)


def scene_or_reason(source: str) -> tuple[dict | None, str]:
    """(scene, "") or (None, why it cannot be shown)."""
    try:
        return build_scene(source), ""
    except SceneError as exc:
        return None, str(exc)


def available_scenes(plan: dict) -> tuple[list[str], dict[str, str]]:
    """Sources of a lesson that can be shown in 3D, and the reasons for those that cannot."""
    shown, reasons = [], {}
    for source in lesson_scene_sources(plan):
        scene, reason = scene_or_reason(source)
        if scene:
            shown.append(source)
        else:
            reasons[source] = reason
    return shown, reasons


def render_scene(source: str, height: int = 600, big: bool = False) -> bool:
    """3D bonding / reaction player for a formula or an equation. False (with a note) if not possible."""
    scene, reason = scene_or_reason(source)
    if scene is None:
        st.info(f"No 3D electron/atom view for **{source}**: {reason}.")
        return False
    components.html(chem3d_html(scene, height=height, big=big), height=height + 10)
    return True


# ---------------------------------------------------------------- history lessons


def lesson_profile(plan: dict) -> str:
    return plan.get("profile", "science")


def render_history_scene(scene: dict | None, height: int = 600, big: bool = False, empty: str = "") -> bool:
    if not scene:
        if empty:
            st.caption(empty)
        return False
    components.html(history_html(scene, height=height, big=big), height=height + 10)
    return True


def render_timeline(plan: dict, height: int = 560, big: bool = False) -> None:
    render_history_scene(timeline_scene(plan), height, big, "No dated events in this lesson.")
    periods = plan.get("periods", [])
    if periods:  # the table students copy for exam answers (like the textbook's exercise chart)
        st.markdown("**Periods**")
        st.dataframe(
            [
                {"Name": p.get("name", ""), "Years": f"{p.get('start')}–{p.get('end')}", "Main focus": p.get("focus", ""),
                 "Textbook page": ", ".join(map(str, p.get("pages", [])))}
                for p in periods
            ],
            hide_index=True,
            width="stretch",
        )  # fmt: skip


@st.cache_data(max_entries=16, show_spinner="Placing the lesson's places on the map…")
def _map_scene(places_json: str) -> dict | None:
    return map_scene({"places": json.loads(places_json)})


def render_map(plan: dict, height: int = 620, big: bool = False) -> list[dict]:
    """Map of the lesson's places; returns the places that could not be placed (with reasons)."""
    scene = _map_scene(json.dumps(plan.get("places", []), ensure_ascii=False))
    render_history_scene(scene, height, big, "No places in this lesson.")
    return scene["unplaced"] if scene else []


def render_cause_effect(plan: dict, height: int = 520, big: bool = False) -> None:
    scenes = flow_scenes(plan)
    if not scenes:
        st.caption("No cause-and-effect items in this lesson.")
    for scene in scenes:
        render_history_scene(scene, height, big)


def lesson_figures(document_id: int | None, plan: dict, engine) -> list:
    """Captioned pictures from the lesson's textbook pages (the teacher's own PDF)."""
    if not document_id:
        return []
    from sqlmodel import Session

    from app.core.config import PROJECT_ROOT
    from app.db.models import Document

    with Session(engine) as s:
        document = s.get(Document, document_id)
    if document is None or document.kind != "pdf":
        return []
    pages = {src.get("page") for src in plan.get("sources", [])}
    return figures_for(PROJECT_ROOT / document.rel_path, pages or None)


def render_people(plan: dict, figures: list, big: bool = False) -> None:
    people = plan.get("people", [])
    if not people:
        st.caption("No people in this lesson.")
        return
    columns = st.columns(3)
    for index, person in enumerate(people):
        with columns[index % 3]:
            portrait = portrait_of(person.get("name", ""), figures)
            if portrait:
                st.image(portrait.png, width=150, caption="Picture from your textbook")
            size = "1.35rem" if big else "1.05rem"
            st.markdown(
                f"<div style='font-size:{size}'><b>{person.get('name', '')}</b></div>", unsafe_allow_html=True
            )
            st.markdown(person.get("role", ""))
            if person.get("pages"):
                st.caption("📖 Textbook page " + ", ".join(map(str, person["pages"])))


def render_figures(figures: list) -> None:
    if not figures:
        st.caption("No captioned pictures on this lesson's textbook pages.")
        return
    columns = st.columns(min(3, len(figures)))
    for index, figure in enumerate(figures):
        with columns[index % len(columns)]:
            st.image(
                figure.png,
                caption=f"{figure.caption} — textbook page {figure.page_no}",
                width="stretch",
            )


def render_simulation(lesson, height: int = 640) -> None:
    problems = json.loads(lesson.simulation_problems or "[]")
    if lesson.simulation_status == "generating":
        st.info("The simulation is being written… (progress on Lesson Studio)")
        return
    if not lesson.simulation_js:
        st.caption("No simulation yet.")
        return
    stopping = blocking(problems)
    if stopping:
        st.warning("This simulation did not pass all checks: " + "; ".join(stopping))
        return
    if problems:  # only notes from the automatic picture review: show the simulation, let the teacher judge
        st.info(
            "The automatic picture review noted (please check while previewing): "
            + "; ".join(p.removeprefix(VISUAL_PREFIX) for p in problems)
        )
    try:
        components.html(simulation_html(lesson.simulation_js), height=height, scrolling=True)
    except VendorFileError as err:
        st.error(str(err))
