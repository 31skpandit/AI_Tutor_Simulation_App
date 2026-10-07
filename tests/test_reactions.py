"""3D chemistry scenes: the chemistry is computed (never invented) — electrons, charges, bonds and atoms are
checked here against the rules students learn, and the hand-written player is checked in Node and a browser."""

import json
import shutil
import subprocess
from collections import Counter

import pytest
from rdkit import Chem

from app.core.config import PROJECT_ROOT
from app.lessons import reactions
from app.lessons.browser_check import _inject, _run, find_browser
from app.lessons.chemistry import parse_species
from app.lessons.molecules import KNOWN, build
from app.lessons.reactions import EXAMPLES, METAL_ELECTRON, SceneError, build_scene, shells, valency
from app.lessons.viewers import CSP, chem3d_html

ALL_EXAMPLES = [x for items in EXAMPLES.values() for x in items]


# ---------------------------------------------------------------- data


def test_molecule_table_formulas_match_their_structures():
    """Every reviewed entry: the SMILES has exactly the atoms and charge of its formula and builds in 3D."""
    for formula, (_, smiles, ions) in KNOWN.items():
        mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
        atoms = Counter(a.GetSymbol() for a in mol.GetAtoms())
        charge = sum(a.GetFormalCharge() for a in mol.GetAtoms())
        species = parse_species(formula)
        assert atoms == species.atoms and charge == species.charge, formula
        if ions:
            assert len(ions) == len(Chem.GetMolFrags(Chem.MolFromSmiles(smiles))), formula
        assert build(formula=formula).molblock, formula


def test_electron_shells_and_valency_follow_the_class_9_rules():
    assert shells(11) == [2, 8, 1] and shells(17) == [2, 8, 7] and shells(19) == [2, 8, 8, 1]
    assert shells(20) == [2, 8, 8, 2] and shells(1) == [1] and shells(10) == [2, 8]
    assert {s: valency(s) for s in ["H", "Na", "Mg", "Al", "C", "N", "O", "Cl", "Ne"]} == {
        "H": 1, "Na": 1, "Mg": 2, "Al": 3, "C": 4, "N": 3, "O": 2, "Cl": 1, "Ne": 0,
    }  # fmt: skip
    assert reactions.pretty("CuSO4·5H2O") == "CuSO₄·5H₂O" and reactions.pretty("Ca^2+") == "Ca²⁺"
    assert reactions.pretty("2H2O(l)") == "2H₂O" and reactions.pretty("4e^-") == "4e⁻"


# ---------------------------------------------------------------- every example: consistent scene


@pytest.mark.parametrize("source", ALL_EXAMPLES)
def test_every_example_builds_a_consistent_scene(source):
    scene = build_scene(source)
    assert len(scene["steps"]) == 4
    for step in scene["steps"]:
        assert len(step["atoms"]) == len(scene["atoms"])
        assert len(step["electrons"]) == len(scene["electrons"])
        assert step["caption"].strip() and step["name"]
        for placement in step["electrons"]:
            assert "p" in placement or ("a" in placement and placement["s"] >= 1)
        for bond in step.get("bonds", []):
            assert 0 <= bond["a"] < len(scene["atoms"]) and 0 <= bond["b"] < len(scene["atoms"])
    json.dumps(scene)  # sent to the browser as JSON


def _electrons_per_atom(scene, step: int) -> Counter:
    return Counter(p["a"] for p in scene["steps"][step]["electrons"] if "a" in p)


# ---------------------------------------------------------------- ionic: electron transfer


@pytest.mark.parametrize(
    ("formula", "ions"),
    [
        ("NaCl", {"Na⁺": "2, 8", "Cl⁻": "2, 8, 8"}),
        ("MgO", {"Mg²⁺": "2, 8", "O²⁻": "2, 8"}),
        ("CaCl₂", {"Ca²⁺": "2, 8, 8", "Cl⁻": "2, 8, 8"}),
        ("Al₂O₃", {"Al³⁺": "2, 8", "O²⁻": "2, 8"}),
        ("Li₃N", {"Li⁺": "2", "N³⁻": "2, 8"}),
    ],
)
def test_ionic_scene_moves_the_right_electrons(formula, ions):
    scene = build_scene(formula)
    assert scene["kind"] == "ionic"
    atoms = scene["atoms"]
    total = sum(reactions.ATOMIC_NUMBER[a["el"]] for a in atoms)
    assert len(scene["electrons"]) == total  # every electron of every atom is drawn, none invented
    before, after = _electrons_per_atom(scene, 0), _electrons_per_atom(scene, 3)
    final = scene["steps"][3]["atoms"]
    for i, atom in enumerate(atoms):
        z = reactions.ATOMIC_NUMBER[atom["el"]]
        assert before[i] == z  # neutral atoms first
        label = final[i]["label"]
        assert ions[label] == final[i]["sub"]
        charge = z - after[i]  # protons − electrons
        assert label.endswith(reactions.charge_text(charge))  # the label shows the real charge
    # Electrons that moved are the metal's (amber) and land in the outer shell of a non-metal.
    moved = [
        (j, a, b)
        for j, (a, b) in enumerate(
            zip(scene["steps"][0]["electrons"], scene["steps"][1]["electrons"], strict=True)
        )
        if a["a"] != b["a"]
    ]
    assert moved and all(scene["electrons"][j]["color"] == METAL_ELECTRON for j, _, _ in moved)
    for _, a, b in moved:
        assert atoms[a["a"]]["el"] in reactions.METALS and atoms[b["a"]]["el"] in reactions.ANION_FORMERS
        assert b["s"] == len(shells(reactions.ATOMIC_NUMBER[atoms[b["a"]]["el"]])) and b.get("jump")
    assert scene["steps"][3]["links"]  # attraction drawn in the last step


def test_ionic_valency_is_explained_in_the_first_caption():
    caption = build_scene("MgCl₂")["steps"][0]["caption"]
    assert (
        "2, 8, 2" in caption
        and "valency is 2" in caption
        and "2, 8, 7" in caption
        and "valency is 1" in caption
    )
    assert "charge +2" in build_scene("MgCl₂")["steps"][2]["caption"]


# ---------------------------------------------------------------- covalent: sharing


@pytest.mark.parametrize(
    ("formula", "pairs"), [("H₂", 1), ("H₂O", 2), ("NH₃", 3), ("CH₄", 4), ("O₂", 2), ("N₂", 3), ("CO₂", 4)]
)
def test_covalent_scene_shares_one_electron_from_each_atom_per_pair(formula, pairs):
    scene = build_scene(formula)
    assert scene["kind"] == "covalent"
    assert len(scene["electrons"]) == sum(reactions.ATOMIC_NUMBER[a["el"]] for a in scene["atoms"])
    shared = [j for j, p in enumerate(scene["steps"][2]["electrons"]) if "p" in p]
    assert len(shared) == 2 * pairs
    # each shared electron started on its own atom's OUTER shell
    for j in shared:
        start = scene["steps"][0]["electrons"][j]
        el = scene["atoms"][start["a"]]["el"]
        assert start["s"] == len(shells(reactions.ATOMIC_NUMBER[el]))
    for atom in scene["steps"][3]["atoms"]:
        expected = 2 if atom["label"] == "H" else 8
        assert atom["sub"] == f"{expected} in outer shell"


def test_same_element_bonded_to_itself_gets_two_electron_colours():
    scene = build_scene("Cl₂")
    owners = {scene["steps"][0]["electrons"][j]["a"]: e["color"] for j, e in enumerate(scene["electrons"])}
    assert owners[0] != owners[1] and len(scene["legend"]) == 2


# ---------------------------------------------------------------- reactions: atoms rearrange


def test_neutralisation_keeps_the_hydroxide_bond_and_breaks_h_cl():
    scene = build_scene("HCl + NaOH → NaCl + H₂O")
    els = [a["el"] for a in scene["atoms"]]
    first, last = scene["steps"][0], scene["steps"][3]
    assert Counter(els) == Counter({"H": 2, "Cl": 1, "Na": 1, "O": 1})

    def bonds(step):
        return {tuple(sorted((els[b["a"]], els[b["b"]]))) + (b["style"],) for b in step["bonds"]}

    assert ("Cl", "H", "solid") in bonds(first) and ("Cl", "H", "solid") not in bonds(last)
    kept = scene["steps"][2]["bonds"]  # bonds that survive the whole reaction: the O–H of OH⁻
    assert [tuple(sorted((els[b["a"]], els[b["b"]]))) for b in kept] == [("H", "O")]
    assert "Old bonds break (dashed): H–Cl" in scene["steps"][1]["caption"]
    assert "Total charge: 0 on both sides" in last["caption"]
    assert {a["label"] for a in last["atoms"]} == {"Na⁺", "Cl⁻", "O", "H"}


def test_water_of_crystallisation_leaves_the_crystal_unchanged_in_number():
    scene = build_scene("CuSO₄·5H₂O → CuSO₄ + 5H₂O")
    assert Counter(a["el"] for a in scene["atoms"]) == Counter({"H": 10, "O": 9, "Cu": 1, "S": 1})
    assert scene["steps"][0]["tags"][0]["text"] == "CuSO₄·5H₂O"
    assert not [b for b in scene["steps"][1]["bonds"] if b["style"] == "dashed"]  # no covalent bond breaks


def test_half_equation_electrons_are_drawn():
    scene = build_scene("2H₂O + 2e⁻ → H₂ + 2OH⁻")
    assert len(scene["electrons"]) == 2
    assert all(p.get("o") == 0.0 for p in scene["steps"][3]["electrons"])  # gained: they join the products
    assert "2 electrons (e⁻) are gained" in scene["steps"][1]["caption"]


@pytest.mark.parametrize(
    ("source", "reason"),
    [
        ("H₂O → H₂ + O₂", "not balanced"),
        ("H₂SO₄", "12 electrons"),
        ("NaCl₃", "charges do not balance"),
        ("XeF₂ + H₂ → Xe + 2HF", "not in the molecule table"),
        ("CuSO₄", "made of ions"),
        ("", "nothing to show"),
    ],
)
def test_unsupported_cases_give_a_reason_instead_of_a_picture(source, reason):
    with pytest.raises(SceneError, match=reason):
        build_scene(source)


def test_lesson_sources_come_from_molecules_balanced_equations_and_extras():
    plan = {
        "molecules": [{"formula": "H₂O"}, {"formula": "H₂O"}],
        "equations": [
            {"equation": "HCl + NaOH → NaCl + H₂O", "balanced": True},
            {"equation": "H₂ → H", "balanced": False},
        ],
        "scenes_3d": ["MgO"],
    }
    assert reactions.lesson_scene_sources(plan) == ["H₂O", "HCl + NaOH → NaCl + H₂O", "MgO"]


# ---------------------------------------------------------------- the player


NODE = shutil.which("node")
CHEM3D = PROJECT_ROOT / "assets" / "chem3d.js"


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_player_maths_in_node():
    scene = build_scene("NaCl")
    script = (
        f"const C = require({json.dumps(str(CHEM3D))}); const s = {json.dumps(scene, ensure_ascii=False)};"
        "const f0 = C.frame(s, 0, 1, 0, 0), f1 = C.frame(s, 0, 1, 1, 0), mid = C.frame(s, 0, 1, 0.5, 0);"
        "const j = s.steps[1].electrons.findIndex(p => p.jump);"
        "const onRing = C.placement({a: 0, s: 2, ang: 90}, [[1, 2, 0]], s.shellRadius, 0);"
        "console.log(JSON.stringify({start: f0.electrons[j].p, end: f1.electrons[j].p, lift: mid.electrons[j].p[2],"
        " onRing, fit: C.fitScale(s, 800, 400), ease: [C.ease(0), C.ease(0.5), C.ease(1)]}));"
    )
    done = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    r = json.loads(done.stdout)
    na_x, cl_x = scene["steps"][0]["atoms"][0]["p"][0], scene["steps"][0]["atoms"][1]["p"][0]
    assert abs(r["start"][0] - (na_x + scene["shellRadius"][3])) < 1e-6  # Na's outer shell, facing Cl
    assert abs(r["end"][0] - (cl_x - scene["shellRadius"][3])) < 1e-6  # Cl's outer shell, facing Na
    assert r["lift"] > 1.0  # the electron jumps over in an arc
    assert r["onRing"] == pytest.approx([1, 2 + scene["shellRadius"][2], 0])
    assert r["fit"] > 0 and r["ease"] == [0, 0.5, 1]


needs_browser = pytest.mark.skipif(find_browser() is None, reason="no Edge/Chrome on this computer")


@needs_browser
@pytest.mark.parametrize("source", ["NaCl", "H₂O", "HCl + NaOH → NaCl + H₂O", "2H₂O + 2e⁻ → H₂ + 2OH⁻"])
def test_player_runs_in_a_real_browser_and_steps_through(source):
    html = chem3d_html(build_scene(source), height=560)
    assert CSP in html  # same no-network policy as every other page
    probe = """
    window.addEventListener('error', e => (window.__err = String(e.message)));
    setTimeout(() => {
      const out = {frames: window.chem3d && window.chem3d.frames, steps: window.chem3d && window.chem3d.steps};
      document.getElementById('next').click(); document.getElementById('next').click();
      out.after = window.chem3d.current();
      out.caption = document.getElementById('steptext').textContent;
      out.err = window.__err || null;
      const pre = document.createElement('pre'); pre.id = 'R'; pre.textContent = JSON.stringify(out);
      document.body.appendChild(pre);
    }, 1500);
    """
    dom = _run(find_browser(), _inject(html, probe), ["--virtual-time-budget=4000", "--dump-dom"])
    start = dom.find('id="R">')
    assert start > 0, "page did not finish"
    result = json.loads(
        dom[start + 7 : dom.find("</pre>", start)].replace("&quot;", '"').replace("&amp;", "&")
    )
    assert result["err"] is None and result["frames"] >= 1 and result["steps"] == 4
    assert result["after"] == 2 and result["caption"] == build_scene(source)["steps"][2]["caption"]
