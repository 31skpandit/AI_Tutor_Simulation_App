import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make ui/common.py importable

import common  # noqa: E402,F401
import streamlit as st  # noqa: E402
from common import page  # noqa: E402
from lesson_views import render_scene  # noqa: E402

from app.lessons.reactions import EXAMPLES  # noqa: E402

page("3D Chemistry Lab", "⚛️")
st.title("⚛️ 3D Chemistry Lab")
st.caption(
    "Watch atoms give, take and share electrons, and watch atoms change partners in a reaction — step by step, "
    "in 3D. Everything is calculated from the checked molecule table, electron shells (2, 8, 8, 2) and balanced "
    "equations: no AI, no internet, no cost. Electrons keep the colour of the atom they came from."
)

st.session_state.setdefault("lab3d", "NaCl")
for group, items in EXAMPLES.items():
    st.markdown(f"**{group}**")
    columns = st.columns(min(len(items), 5))
    for index, item in enumerate(items):
        if columns[index % len(columns)].button(item, key=f"ex_{item}", width="stretch"):
            st.session_state["lab3d"] = item

typed = st.text_input(
    "…or type a formula or an equation",
    key="lab3d_typed",
    placeholder="e.g. CaF₂, Li₃N, C₂H₂, 2Na + Cl₂ → 2NaCl   (plain text works too: H2O, 2H2 + O2 -> 2H2O)",
)
if typed.strip():
    st.session_state["lab3d"] = typed.strip()

render_scene(st.session_state["lab3d"], height=640, big=True)

with st.expander("What can be shown?"):
    st.markdown(
        "- **Electron transfer (ionic bond):** a compound of one metal (Li, Be, Na, Mg, Al, K, Ca) and one "
        "non-metal (N, O, F, P, S, Cl) whose charges balance — e.g. NaCl, MgO, CaCl₂, Al₂O₃, Li₃N.\n"
        "- **Electron sharing (covalent bond):** molecules from the checked table whose atoms all end with a full "
        "outer shell — e.g. H₂, O₂, N₂, Cl₂, HCl, H₂O, NH₃, CH₄, CO₂, C₂H₄, C₂H₂, CCl₄. Molecules such as H₂SO₄ "
        "or SO₂ (sulphur with more than 8 outer electrons) are shown as 3D models in lessons instead.\n"
        "- **Reactions:** any *balanced* equation whose substances are in the checked molecule table (about 70 "
        "molecules, ions and metals), including half-equations with electrons (e⁻) and hydrates such as "
        "CuSO₄·5H₂O.\n"
        "- Anything else gets a short, clear reason instead of a guessed picture."
    )
