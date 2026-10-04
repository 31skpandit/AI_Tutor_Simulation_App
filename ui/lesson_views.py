"""Shared display helpers for Lesson Studio and Teach Mode."""

import json

import streamlit as st
import streamlit.components.v1 as components

from app.lessons.molecules import build
from app.lessons.viewers import VendorFileError, molecule_html, simulation_html


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
    molecule = build(name, formula)
    if molecule is None:
        return None
    return molecule.name, molecule.formula, molecule.svg, molecule.molblock


def render_molecules(plan: dict, show_3d: bool = True, height: int = 360) -> None:
    molecules = plan.get("molecules", [])
    if not molecules:
        st.caption("No molecules in this lesson.")
        return
    columns = st.columns(min(len(molecules), 3))
    for index, item in enumerate(molecules):
        with columns[index % len(columns)]:
            found = _molecule(item.get("name", ""), item.get("formula", ""))
            st.markdown(f"**{item.get('name', '')}** ({item.get('formula', '')})")
            if found is None:
                st.caption("Structure not available in the local molecule table.")
                continue
            display, _, svg, molblock = found
            if show_3d and molblock:
                try:
                    components.html(molecule_html(molblock, display, height), height=height)
                except VendorFileError as err:
                    st.error(str(err))
            else:
                st.image(svg.encode("utf-8"), caption=display)


def render_simulation(lesson, height: int = 640) -> None:
    problems = json.loads(lesson.simulation_problems or "[]")
    if lesson.simulation_status == "generating":
        st.info("The simulation is being written… (progress on Lesson Studio)")
        return
    if not lesson.simulation_js:
        st.caption("No simulation yet.")
        return
    if problems:
        st.warning("This simulation did not pass all checks: " + "; ".join(problems))
        return
    try:
        components.html(simulation_html(lesson.simulation_js), height=height, scrolling=True)
    except VendorFileError as err:
        st.error(str(err))
