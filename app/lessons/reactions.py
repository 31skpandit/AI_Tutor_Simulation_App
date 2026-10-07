"""3D chemistry scenes: how atoms give, take and share electrons, and how atoms rearrange in a reaction.

Three kinds of scene, each a short sequence of steps that the teacher plays or steps through:
  - ionic bonding    (e.g. NaCl, MgO, CaCl₂): the metal atom gives its outer electron(s) to the non-metal atom;
                      the atoms become ions with complete outer shells and attract each other;
  - covalent bonding (e.g. H₂O, NH₃, CO₂, O₂): atoms come close and share pairs of electrons (one from each atom);
  - reaction         (a balanced equation of table species, e.g. HCl + NaOH → NaCl + H₂O): old bonds break and the
                      atoms move to new partners; the atom count stays the same.

Everything in a scene is COMPUTED here from checked data — electron shells from the atomic number (Class 9 rule
2, 8, 8, 2), bonds from the hand-reviewed molecule table (RDKit), atoms from the balanced equation — and only drawn
by the hand-written assets/chem3d.js. No AI is involved, so a scene cannot invent electrons, bonds or atoms; an
unsupported case raises SceneError with a plain reason instead of guessing. Electrons keep the colour of the atom
they came from, so students can follow a donated or shared electron.
"""

import math
import re
from collections import Counter
from functools import lru_cache

from rdkit import Chem
from rdkit.Chem import AllChem

from app.lessons import chemistry
from app.lessons.molecules import ELEMENT_NAMES, charge_text, embed_3d, resolve

# ---------------------------------------------------------------- element data (Z ≤ 20, Class 9 scope)

ATOMIC_NUMBER = {
    "H": 1, "He": 2, "Li": 3, "Be": 4, "B": 5, "C": 6, "N": 7, "O": 8, "F": 9, "Ne": 10,
    "Na": 11, "Mg": 12, "Al": 13, "Si": 14, "P": 15, "S": 16, "Cl": 17, "Ar": 18, "K": 19, "Ca": 20,
}  # fmt: skip
METALS = {"Li", "Be", "Na", "Mg", "Al", "K", "Ca"}
ANION_FORMERS = {"N", "O", "F", "P", "S", "Cl"}  # non-metals that form simple negative ions
COVALENT_ELEMENTS = {"H", "C", "N", "O", "F", "P", "S", "Cl"}
NOBLE_GAS = {(2,): "helium (He)", (2, 8): "neon (Ne)", (2, 8, 8): "argon (Ar)"}
ANION_NAMES = {
    "Cl": "chloride",
    "O": "oxide",
    "S": "sulphide",
    "N": "nitride",
    "F": "fluoride",
    "P": "phosphide",
}

# Nucleus colours (usual school / CPK colours) and electron colours (one per element; the same element bonded
# to itself gets a second shade so students can still see which atom each electron came from).
NUCLEUS = {
    "H": "#e5e7eb", "C": "#4b5563", "N": "#2563eb", "O": "#dc2626", "F": "#65a30d", "Na": "#7c3aed",
    "Mg": "#15803d", "Al": "#94a3b8", "P": "#ea580c", "S": "#ca8a04", "Cl": "#16a34a", "K": "#6d28d9",
    "Ca": "#166534", "Li": "#a855f7", "Be": "#4d7c0f", "Cu": "#b45309", "Zn": "#64748b", "Fe": "#c2410c",
}  # fmt: skip
ELECTRON = {
    "H": ["#0284c7", "#f97316"], "C": ["#111827", "#6b7280"], "N": ["#1d4ed8", "#60a5fa"],
    "O": ["#b91c1c", "#f87171"], "Cl": ["#15803d", "#4ade80"], "F": ["#4d7c0f", "#a3e635"],
    "S": ["#a16207", "#facc15"], "P": ["#c2410c", "#fb923c"],
}  # fmt: skip
METAL_ELECTRON = "#f59e0b"  # amber: easy to follow when it jumps to the non-metal
FREE_ELECTRON = "#f59e0b"

SHELL_RADIUS = [0.0, 0.62, 1.05, 1.45, 1.85]  # drawing radius of shell 1 (K), 2 (L), 3 (M), 4 (N)
HYDRATE = re.compile(r"[·•∙*.](\d*)H2O$")
_SUB = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


class SceneError(ValueError):
    """The scene cannot be built; the message says why in plain words."""


# ---------------------------------------------------------------- small helpers


def shells(z: int) -> list[int]:
    """Electron distribution by the Class 9 rule (2, 8, 8, 2), valid for Z ≤ 20: Na (11) → [2, 8, 1]."""
    out, left = [], z
    for capacity in (2, 8, 8, 2):
        if left <= 0:
            break
        out.append(min(capacity, left))
        left -= out[-1]
    return out


def full_shell(symbol: str) -> int:
    """Electrons in a complete outer shell: 2 for H (like helium), else 8."""
    return 2 if symbol in {"H", "He", "Li", "Be"} else 8


def valency(symbol: str) -> int:
    outer = shells(ATOMIC_NUMBER[symbol])[-1]
    if outer == full_shell(symbol):
        return 0
    return outer if outer <= 4 and symbol != "H" else full_shell(symbol) - outer


def pretty(text: str) -> str:
    """'CuSO4·5H2O' → 'CuSO₄·5H₂O', 'Ca^2+' → 'Ca²⁺', '2H2O(l)' → '2H₂O', 'e^-' → 'e⁻'."""
    text = chemistry._STATE.sub("", chemistry.normalise(text)).strip()
    match = re.match(r"^(\d*)\s*(.*)$", text)
    coefficient, body = match.group(1), match.group(2)
    if body in {"e", "e-", "e^-"}:
        return f"{coefficient}e⁻"
    body, charge = chemistry._split_charge(body)
    body = re.sub(r"(?<=[A-Za-z)\]])(\d+)", lambda m: m.group(1).translate(_SUB), body)
    return coefficient + body + charge_text(charge)


def pretty_equation(equation: str) -> str:
    left, right = chemistry._ARROW.split(chemistry.normalise(equation), maxsplit=1)

    def side(text: str) -> str:
        return " + ".join(pretty(p) for p in re.split(r"\s\+\s", text.strip()) if p.strip())

    return f"{side(left)} → {side(right)}"


def _name(symbol: str) -> str:
    return ELEMENT_NAMES.get(symbol, symbol)


def _lower(symbol: str) -> str:
    """Element name inside a sentence: 'sodium'."""
    return _name(symbol).lower()


def _signed(n: int) -> str:
    """Charge in words-friendly form: 1 → '+1', -2 → '−2'."""
    return f"+{n}" if n > 0 else f"−{-n}"


def _bond_name(a: str, b: str, order: int = 1) -> str:
    """'C–O', 'O–H', 'H–Cl', 'C=O', 'N≡N' (carbon first, hydrogen last except in hydrogen halides)."""
    if "H" in (a, b) and ({a, b} & {"F", "Cl"}):
        first, second = "H", (b if a == "H" else a)
    else:
        first, second = sorted((a, b), key=lambda e: (e == "H", e != "C", e))
    return f"{first}{'–=≡'[order - 1]}{second}"


def _config(counts: list[int]) -> str:
    return ", ".join(map(str, counts))


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _r(values) -> list[float]:
    return [round(float(v), 3) for v in values]


def _angle(a, b) -> float:
    """Direction from point a to point b in the picture plane, in degrees."""
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 360


def _ang_dist(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


def _free_angles(taken: list[float], how_many: int) -> list[float]:
    """Directions (degrees) as far as possible from `taken` and from each other — used for lone pairs."""
    chosen: list[float] = []
    for _ in range(how_many):
        best = max(
            range(0, 360, 5),
            key=lambda a: (min((_ang_dist(a, t) for t in taken + chosen), default=180.0), -a),
        )
        chosen.append(float(best))
    return chosen


def _atom_spec(el: str, r: float) -> dict:
    return {"el": el, "color": NUCLEUS.get(el, "#64748b"), "r": r}


def _inner_electrons(atom: int, shell_counts: list[int]) -> list[dict]:
    """Electrons of the inner (complete) shells, spread evenly; they turn slowly in the picture."""
    out = []
    for shell_no, count in enumerate(shell_counts[:-1], start=1):
        for k in range(count):
            out.append(
                {"a": atom, "s": shell_no, "ang": round(360 * k / count + shell_no * 17, 1), "spin": True}
            )
    return out


# ---------------------------------------------------------------- ionic bonding


def _ionic_order(metal: str, nonmetal: str, counts: Counter) -> list[str]:
    """Order of atoms in the picture: Na Cl / Cl Mg Cl / Na O Na / O Al O Al O."""
    m, n = counts[metal], counts[nonmetal]
    if m == 1 and n == 1:
        return [metal, nonmetal]
    if m == 1 or n == 1:  # one centre atom with the others round it
        centre, outer = (metal, nonmetal) if m == 1 else (nonmetal, metal)
        return [outer, centre] + [outer] * (counts[outer] - 1)
    first, second = (metal, nonmetal) if m >= n else (nonmetal, metal)
    order, a, b = [], counts[first], counts[second]
    while a or b:
        if a:
            order.append(first)
            a -= 1
        if b:
            order.append(second)
            b -= 1
    return order


def _ionic_layout(order: list[str], radii: list[float], gap: float) -> list[tuple[float, float, float]]:
    """Positions: a centre atom with up to 4 neighbours (left, right, above, below), or a straight line."""
    count = Counter(order)
    if 2 < len(order) <= 5 and min(count.values()) == 1:
        centre = next(i for i, el in enumerate(order) if count[el] == 1)
        pos = [(0.0, 0.0, 0.0)] * len(order)
        for (dx, dy), i in zip(
            [(-1, 0), (1, 0), (0, 1), (0, -1)], [i for i in range(len(order)) if i != centre], strict=False
        ):
            d = radii[centre] + radii[i] + gap
            pos[i] = (dx * d, dy * d, 0.0)
        return pos
    xs, x = [], 0.0
    for i in range(len(order)):
        if i:
            x += radii[i - 1] + radii[i] + gap
        xs.append(x)
    middle = (xs[0] + xs[-1]) / 2
    return [(v - middle, 0.0, 0.0) for v in xs]


def ionic_scene(formula: str) -> dict:
    counts = chemistry._count(chemistry.normalise(formula).replace(" ", ""))
    metals = [e for e in counts if e in METALS]
    nonmetals = [e for e in counts if e in ANION_FORMERS]
    if len(counts) != 2 or len(metals) != 1 or len(nonmetals) != 1:
        raise SceneError(
            "electron transfer is shown for a compound of one metal (Li, Be, Na, Mg, Al, K, Ca) and one non-metal (N, O, F, P, S, Cl)"
        )
    metal, nonmetal = metals[0], nonmetals[0]
    metal_shells, nonmetal_shells = shells(ATOMIC_NUMBER[metal]), shells(ATOMIC_NUMBER[nonmetal])
    give, take = metal_shells[-1], 8 - nonmetal_shells[-1]
    if counts[metal] * give != counts[nonmetal] * take:
        raise SceneError(
            f"the charges do not balance in {pretty(formula)}: {counts[metal]} × {give}+ ≠ {counts[nonmetal]} × {take}−"
        )
    if counts[metal] + counts[nonmetal] > 6:
        raise SceneError("too many ions to show clearly (at most 6)")

    order = _ionic_order(metal, nonmetal, counts)
    ring_before = [SHELL_RADIUS[len(metal_shells if el == metal else nonmetal_shells)] for el in order]
    ring_after = [
        SHELL_RADIUS[len(metal_shells) - 1 if el == metal else len(nonmetal_shells)] for el in order
    ]
    start = _ionic_layout(order, ring_before, 1.6)
    close = _ionic_layout(order, ring_after, 0.55)
    metal_atoms = [i for i, el in enumerate(order) if el == metal]
    anion_atoms = [i for i, el in enumerate(order) if el == nonmetal]

    # Each metal electron goes to the nearest anion that still needs electrons.
    need = dict.fromkeys(anion_atoms, take)
    transfers: list[tuple[int, int]] = []  # (metal atom, anion atom), one entry per electron
    for m in metal_atoms:
        for _ in range(give):
            target = min(
                (i for i in anion_atoms if need[i] > 0), key=lambda i: (math.dist(start[m], start[i]), i)
            )
            need[target] -= 1
            transfers.append((m, target))

    # Final octet: 8 places 45° apart on each anion's outer shell; one points at its first donor.
    slots = {}
    for i in anion_atoms:
        donor = next(m for m, t in transfers if t == i)
        base = _angle(start[i], start[donor])
        slots[i] = [(base + 45 * k) % 360 for k in range(8)]

    electrons: list[dict] = []
    before: list[dict] = []
    after: list[dict] = []

    def add(colour: str, p_before: dict, p_after: dict) -> None:
        electrons.append({"color": colour})
        before.append(p_before)
        after.append(p_after)

    anion_colour = ELECTRON.get(nonmetal, ["#16a34a"])[0]
    for m in metal_atoms:
        for p in _inner_electrons(m, metal_shells):
            add(METAL_ELECTRON, p, dict(p))
        mine = [t for mm, t in transfers if mm == m]
        for k, target in enumerate(mine):
            same = mine.count(target)
            rank = mine[:k].count(target)
            spread = (rank - (same - 1) / 2) * 24
            slot = min(slots[target], key=lambda a: _ang_dist(a, _angle(start[target], start[m])))
            slots[target].remove(slot)
            add(
                METAL_ELECTRON,
                {
                    "a": m,
                    "s": len(metal_shells),
                    "ang": round((_angle(start[m], start[target]) + spread) % 360, 1),
                },
                {"a": target, "s": len(nonmetal_shells), "ang": round(slot, 1), "jump": True},
            )
    for i in anion_atoms:
        for p in _inner_electrons(i, nonmetal_shells):
            add(anion_colour, p, dict(p))
        for ang in slots[i]:  # the anion's own outer electrons fill the places not kept for incoming ones
            p = {"a": i, "s": len(nonmetal_shells), "ang": round(ang, 1)}
            add(anion_colour, p, dict(p))

    metal_ion, anion = metal + charge_text(give), nonmetal + charge_text(-take)
    ion_shells = {metal: metal_shells[:-1], nonmetal: nonmetal_shells[:-1] + [8]}
    atom_shells = {metal: metal_shells, nonmetal: nonmetal_shells}

    def atoms_at(positions, after_transfer: bool, ion_labels: bool) -> list[dict]:
        out = []
        for i, el in enumerate(order):
            now = ion_shells[el] if after_transfer else atom_shells[el]
            label = (metal_ion if el == metal else anion) if ion_labels else el
            out.append({"p": _r(positions[i]), "label": label, "sub": _config(now), "shells": len(now)})
        return out

    m_name, n_name = _lower(metal), _lower(nonmetal)
    zm, zn = ATOMIC_NUMBER[metal], ATOMIC_NUMBER[nonmetal]
    each_m = "Each" if counts[metal] > 1 else "The"
    each_n = "each" if counts[nonmetal] > 1 else "the"
    partners = {m: len({t for mm, t in transfers if mm == m}) for m in metal_atoms}
    its = _plural(give, "outer electron")
    if all(p == 1 for p in partners.values()):
        target = (
            f"the {n_name} atom next to it"
            if counts[nonmetal] == 1 or counts[metal] > 1
            else f"the {n_name} atom"
        )
        gives = f"{each_m} {m_name} atom gives (donates) its {its} to {target}."
    elif all(p == give for p in partners.values()):
        gives = f"{each_m} {m_name} atom gives (donates) its {its} — one to each neighbouring {n_name} atom."
    else:
        gives = f"{each_m} {m_name} atom gives (donates) its {its} to the {n_name} atoms next to it."
    gives += (
        f" {each_n.capitalize()} {n_name} atom takes {_plural(take, 'electron')}. "
        f"Electrons given = electrons taken = {counts[metal] * give}."
    )
    steps = [
        {
            "name": "The atoms",
            "caption": (
                f"{_name(metal)} ({metal}, atomic number {zm}) has electrons {_config(metal_shells)}: "
                f"{_plural(give, 'electron')} in its outer shell, so its valency is {give}. "
                f"{_name(nonmetal)} ({nonmetal}, atomic number {zn}) has {_config(nonmetal_shells)}: it needs {take} "
                f"more to complete its outer shell of 8, so its valency is {take}."
            ),
            "atoms": atoms_at(start, False, False),
            "electrons": before,
        },
        {
            "name": "Electron transfer",
            "caption": gives,
            "atoms": atoms_at(start, True, False),
            "electrons": after,
        },
        {
            "name": "Ions are formed",
            "caption": (
                f"{metal} becomes the {metal_ion} ion: {zm} protons, {zm - give} electrons → charge {_signed(give)}. "
                f"{nonmetal} becomes the {anion} ({ANION_NAMES[nonmetal]}) ion: {zn} protons, {zn + take} electrons "
                f"→ charge {_signed(-take)}. Both now have a complete outer shell, like "
                f"{NOBLE_GAS[tuple(ion_shells[metal])]} and {NOBLE_GAS[tuple(ion_shells[nonmetal])]}."
            ),
            "atoms": atoms_at(start, True, True),
            "electrons": after,
        },
        {
            "name": "Ionic bond",
            "caption": (
                f"Opposite charges attract. This strong force of attraction is the ionic (electrovalent) bond in "
                f"{pretty(formula)}. The charges balance: {counts[metal]} × ({_signed(give)}) + "
                f"{counts[nonmetal]} × ({_signed(-take)}) = 0."
            ),
            "atoms": atoms_at(close, True, True),
            "electrons": after,
            "links": [{"a": m, "b": t} for m, t in sorted(set(transfers))],
        },
    ]
    return {
        "kind": "ionic",
        "title": f"How {pretty(formula)} forms — electron transfer",
        "atoms": [_atom_spec(el, 0.42 if el == metal else 0.36) for el in order],
        "electrons": electrons,
        "legend": [
            {"color": METAL_ELECTRON, "text": f"electron from {m_name} ({metal})"},
            {"color": anion_colour, "text": f"electron of {n_name} ({nonmetal})"},
        ],
        "shellRadius": SHELL_RADIUS,
        "steps": steps,
    }


# ---------------------------------------------------------------- covalent bonding


def _covalent_mol(formula: str) -> Chem.Mol:
    found = resolve(formula=formula)
    if found is None:
        raise SceneError(f"{pretty(formula)} is not in the molecule table")
    mol = Chem.MolFromSmiles(found[2])
    if mol is None or len(Chem.GetMolFrags(mol)) != 1:
        raise SceneError(f"{pretty(formula)} is made of ions, not one molecule")
    mol = Chem.AddHs(mol)
    Chem.Kekulize(mol, clearAromaticFlags=True)
    if mol.GetNumAtoms() < 2:
        raise SceneError(f"{pretty(formula)} is a single atom: there is no bond to show")
    for atom in mol.GetAtoms():
        if atom.GetSymbol() not in COVALENT_ELEMENTS:
            raise SceneError(f"{atom.GetSymbol()} is not a non-metal")
        if atom.GetFormalCharge() or atom.GetNumRadicalElectrons():
            raise SceneError(f"{pretty(formula)} has charged atoms — shown as a 3D model only")
    return mol


def covalent_scene(formula: str) -> dict:
    mol = _covalent_mol(formula)
    n = mol.GetNumAtoms()
    symbols = [a.GetSymbol() for a in mol.GetAtoms()]
    shell_counts = [shells(ATOMIC_NUMBER[s]) for s in symbols]
    outer_r = [SHELL_RADIUS[len(c)] for c in shell_counts]
    bonds = [
        (b.GetBeginAtomIdx(), b.GetEndAtomIdx(), int(round(b.GetBondTypeAsDouble()))) for b in mol.GetBonds()
    ]
    bond_sum = [0] * n
    for a, b, order in bonds:
        bond_sum[a] += order
        bond_sum[b] += order
    lone = [shell_counts[i][-1] - bond_sum[i] for i in range(n)]
    for i in range(n):
        total = lone[i] + 2 * bond_sum[i]
        if lone[i] < 0 or total != full_shell(symbols[i]):
            raise SceneError(
                f"{symbols[i]} would have {total} electrons in its outer shell in {pretty(formula)} "
                "(not the usual full shell of 8) — shown as a 3D model only"
            )

    # Flat textbook layout: directions from RDKit's 2D drawing; each bond long enough for the outer shells to overlap.
    AllChem.Compute2DCoords(mol)
    flat = mol.GetConformer()
    xy = [(flat.GetAtomPosition(i).x, flat.GetAtomPosition(i).y) for i in range(n)]
    neighbours: dict[int, list[int]] = {i: [] for i in range(n)}
    for a, b, _ in bonds:
        neighbours[a].append(b)
        neighbours[b].append(a)
    root = max(range(n), key=lambda i: (len(neighbours[i]), -i))
    pos = {root: (0.0, 0.0, 0.0)}
    queue = [root]
    while queue:
        parent = queue.pop(0)
        for child in neighbours[parent]:
            if child in pos:
                continue
            dx, dy = xy[child][0] - xy[parent][0], xy[child][1] - xy[parent][1]
            length = math.hypot(dx, dy) or 1.0
            d = outer_r[parent] + outer_r[child] - 0.5 * min(outer_r[parent], outer_r[child])
            pos[child] = (pos[parent][0] + dx / length * d, pos[parent][1] + dy / length * d, 0.0)
            queue.append(child)
    cx, cy = sum(p[0] for p in pos.values()) / n, sum(p[1] for p in pos.values()) / n
    final = [(pos[i][0] - cx, pos[i][1] - cy, 0.0) for i in range(n)]
    # Before bonding: the same picture spread out until no two outer shells touch.
    spread = max(
        [1.0] + [(outer_r[a] + outer_r[b] + 0.35) / math.dist(final[a], final[b]) for a, b, _ in bonds]
    )
    apart = [(p[0] * spread, p[1] * spread, 0.0) for p in final]

    # Electron colours: one per element; atoms of one element bonded to each other get different shades.
    same_bonded = {symbols[a] for a, b, _ in bonds if symbols[a] == symbols[b]}
    shade: dict[int, int] = {}
    seen: Counter = Counter()
    for i, s in enumerate(symbols):
        shade[i] = seen[s] if s in same_bonded else 0
        seen[s] += 1
    colour = [
        ELECTRON.get(s, ["#334155"])[shade[i] % len(ELECTRON.get(s, ["#334155"]))]
        for i, s in enumerate(symbols)
    ]

    electrons: list[dict] = []
    p_apart: list[dict] = []
    p_shared: list[dict] = []

    def add(c: str, before: dict, after: dict) -> None:
        electrons.append({"color": c})
        p_apart.append(before)
        p_shared.append(after)

    bond_dirs: dict[int, list[float]] = {i: [] for i in range(n)}
    for a, b, _ in bonds:
        bond_dirs[a].append(_angle(final[a], final[b]))
        bond_dirs[b].append(_angle(final[b], final[a]))
    for i in range(n):
        for p in _inner_electrons(i, shell_counts[i]):
            add(colour[i], p, dict(p))
        outer = len(shell_counts[i])
        pairs, single = divmod(lone[i], 2)
        directions = _free_angles(bond_dirs[i], pairs + single)
        for ang in directions[:pairs]:
            for offset in (-11, 11):
                p = {"a": i, "s": outer, "ang": round((ang + offset) % 360, 1)}
                add(colour[i], p, dict(p))
        if single:
            p = {"a": i, "s": outer, "ang": round(directions[-1], 1)}
            add(colour[i], p, dict(p))
    # Shared pairs: one electron from each atom, side by side in the overlap of the two outer shells.
    for a, b, order in bonds:
        pa, pb = final[a], final[b]
        d = math.dist(pa, pb)
        ux, uy = (pb[0] - pa[0]) / d, (pb[1] - pa[1]) / d
        wx, wy = -uy, ux
        middle = (outer_r[a] + d - outer_r[b]) / 2
        for k in range(order):
            o = (k - (order - 1) / 2) * 0.3
            centre = (pa[0] + ux * middle + wx * o, pa[1] + uy * middle + wy * o)
            for atom, other, sign in ((a, b, -1), (b, a, 1)):
                fan = (k - (order - 1) / 2) * 16 * (1 if atom == a else -1)
                add(
                    colour[atom],
                    {
                        "a": atom,
                        "s": len(shell_counts[atom]),
                        "ang": round((_angle(final[atom], final[other]) + fan) % 360, 1),
                    },
                    {"p": _r((centre[0] + sign * ux * 0.09, centre[1] + sign * uy * 0.09, 0.0))},
                )

    def atoms_at(positions, done: bool) -> list[dict]:
        return [
            {
                "p": _r(positions[i]),
                "label": symbols[i],
                "sub": f"{lone[i] + 2 * bond_sum[i]} in outer shell" if done else _config(shell_counts[i]),
                "shells": len(shell_counts[i]),
            }
            for i in range(n)
        ]

    kinds = Counter(order for _, _, order in bonds)
    bond_text = ", ".join(
        _plural(kinds[k], w + " bond") for k, w in ((1, "single"), (2, "double"), (3, "triple")) if kinds[k]
    )
    pair_names = list(dict.fromkeys(_bond_name(symbols[a], symbols[b], order) for a, b, order in bonds))
    unique = list(dict.fromkeys(symbols))
    needs = " ".join(
        f"{_name(s)} ({s}) has {_config(shells(ATOMIC_NUMBER[s]))}: it needs "
        f"{_plural(full_shell(s) - shells(ATOMIC_NUMBER[s])[-1], 'more electron')} (valency {valency(s)})."
        for s in unique
    )
    done = "; ".join(
        ("each " if symbols.count(s) > 1 else "")
        + f"{s} has {lone[symbols.index(s)] + 2 * bond_sum[symbols.index(s)]}"
        for s in unique
    )
    steps = [
        {"name": "The atoms", "caption": needs, "atoms": atoms_at(apart, False), "electrons": p_apart},
        {
            "name": "Shells overlap",
            "caption": "The atoms come close together so that their outer shells overlap.",
            "atoms": atoms_at(final, False),
            "electrons": p_apart,
        },
        {
            "name": "Sharing electrons",
            "caption": (
                f"Each bond is a shared pair of electrons — one electron from each atom ({', '.join(pair_names)}). "
                f"{pretty(formula)} has {bond_text}. No electron is given away: they are shared."
            ),
            "atoms": atoms_at(final, False),
            "electrons": p_shared,
        },
        {
            "name": "Covalent bond",
            "caption": (
                f"Counting the shared electrons for both atoms, every atom now has a full outer shell: {done}. "
                "A bond made by sharing electrons is a covalent bond."
            ),
            "atoms": atoms_at(final, True),
            "electrons": p_shared,
            "bonds": [{"a": a, "b": b, "order": order, "style": "thin"} for a, b, order in bonds],
        },
    ]
    legend = []
    for i, s in enumerate(symbols):
        text = f"electron of {_name(s)} ({s})" + (f", atom {shade[i] + 1}" if s in same_bonded else "")
        if all(item["text"] != text for item in legend):
            legend.append({"color": colour[i], "text": text})
    return {
        "kind": "covalent",
        "title": f"How {pretty(formula)} forms — sharing electrons",
        "atoms": [_atom_spec(s, 0.24 if s == "H" else 0.34) for s in symbols],
        "electrons": electrons,
        "legend": legend,
        "shellRadius": SHELL_RADIUS,
        "steps": steps,
    }


# ---------------------------------------------------------------- reactions (atoms rearrange)


def _species_mol(body: str) -> Chem.Mol:
    """'CuSO4·5H2O' / 'Na^+' / 'H2O' → RDKit molecule with hydrogens and 3D coordinates (ions side by side,
    water of crystallisation round the salt)."""
    water = 0
    match = HYDRATE.search(body)
    if match:
        water = int(match.group(1) or 1)
        body = body[: match.start()]
    found = resolve(formula=body)
    if found is None or chemistry.parse_species(found[0]).atoms != chemistry.parse_species(body).atoms:
        raise SceneError(f"{pretty(body)} is not in the molecule table")
    mol = embed_3d(Chem.MolFromSmiles(found[2] + ".O" * water))
    if mol is None:
        raise SceneError(f"could not build a 3D model of {pretty(body)}")
    _arrange_fragments(mol, hydrate=water > 0)
    return mol


def _is_water(mol: Chem.Mol, atoms: tuple[int, ...]) -> bool:
    return sorted(mol.GetAtomWithIdx(i).GetSymbol() for i in atoms) == ["H", "H", "O"]


def _arrange_fragments(mol: Chem.Mol, hydrate: bool) -> None:
    conf = mol.GetConformer()

    def points(atoms):
        return [conf.GetAtomPosition(i) for i in atoms]

    def move(atoms, dx, dy):
        for i in atoms:
            p = conf.GetAtomPosition(i)
            conf.SetAtomPosition(i, (p.x + dx, p.y + dy, p.z))

    frags = Chem.GetMolFrags(mol)
    waters = [f for f in frags if hydrate and _is_water(mol, f)]
    salt = [f for f in frags if f not in waters]
    for k, atoms in enumerate(
        salt
    ):  # turn each ion so that its charged atom faces its neighbour (O⁻ of OH⁻ → Na⁺)
        charged = [i for i in atoms if mol.GetAtomWithIdx(i).GetFormalCharge()]
        if len(atoms) < 2 or not charged or len(salt) < 2:
            continue
        cx = sum(p.x for p in points(atoms)) / len(atoms)
        faces_left = conf.GetAtomPosition(charged[0]).x < cx
        if faces_left != (k > 0):
            for i in atoms:
                p = conf.GetAtomPosition(i)
                conf.SetAtomPosition(i, (2 * cx - p.x, p.y, p.z))
    cursor = 0.0
    for atoms in salt:  # ions side by side, centred on y = 0
        ps = points(atoms)
        move(atoms, cursor - min(p.x for p in ps), -sum(p.y for p in ps) / len(ps))
        cursor += max(p.x for p in ps) - min(p.x for p in ps) + 2.2
    for atoms in salt:
        move(atoms, -(cursor - 2.2) / 2, 0.0)
    radius = max(
        3.0, (cursor - 2.2) / 2 + 2.6
    )  # measured in a screenshot: +1.6 let waters touch the SO₄²⁻ ion
    for k, atoms in enumerate(waters):  # water of crystallisation round the salt
        a = 2 * math.pi * k / len(waters) + math.pi / 2
        ps = points(atoms)
        cx, cy = sum(p.x for p in ps) / len(ps), sum(p.y for p in ps) / len(ps)
        move(atoms, radius * math.cos(a) - cx, 0.85 * radius * math.sin(a) - cy)


def _side_layout(side: list[chemistry.Species]) -> tuple[list[dict], list[dict], list[dict], int]:
    """Atoms (positions, charges, neighbours), bonds and name tags for one side of an equation, plus the number of
    electrons (e⁻) written on that side. Species stand left → right; copies of one species (2H₂O) are stacked."""
    atoms: list[dict] = []
    bonds: list[dict] = []
    groups = []
    electrons = 0
    copy_no = 0
    for sp in side:
        if not sp.atoms:  # e⁻
            electrons += sp.coefficient
            continue
        body = re.sub(r"^\d+", "", chemistry._STATE.sub("", sp.text).replace(" ", ""))
        groups.append((sp, [_species_mol(body) for _ in range(sp.coefficient)]))
    x = 0.0
    spans = []
    for sp, copies in groups:
        boxes = []
        for mol in copies:
            ps = [mol.GetConformer().GetAtomPosition(i) for i in range(mol.GetNumAtoms())]
            boxes.append(
                (min(p.x for p in ps), max(p.x for p in ps), min(p.y for p in ps), max(p.y for p in ps))
            )
        width = max(b[1] - b[0] for b in boxes)
        top = (sum(b[3] - b[2] for b in boxes) + 1.4 * (len(copies) - 1)) / 2
        for mol, (x0, x1, y0, y1) in zip(copies, boxes, strict=True):
            conf = mol.GetConformer()
            offset = len(atoms)
            fragment = {}
            for f_no, frag in enumerate(Chem.GetMolFrags(mol)):
                fragment.update(dict.fromkeys(frag, (copy_no, f_no)))
            for atom in mol.GetAtoms():
                p = conf.GetAtomPosition(atom.GetIdx())
                atoms.append(
                    {
                        "el": atom.GetSymbol(),
                        "charge": atom.GetFormalCharge(),
                        "p": (x + (width - (x1 - x0)) / 2 + (p.x - x0), top - (y1 - p.y), p.z),
                        "frag": fragment[atom.GetIdx()],
                        "neighbours": [offset + nb.GetIdx() for nb in atom.GetNeighbors()],
                    }
                )
            for bond in mol.GetBonds():
                bonds.append(
                    {
                        "a": offset + bond.GetBeginAtomIdx(),
                        "b": offset + bond.GetEndAtomIdx(),
                        "order": int(round(bond.GetBondTypeAsDouble())),
                    }
                )
            charged = [
                f for f in Chem.GetMolFrags(mol) if sum(mol.GetAtomWithIdx(i).GetFormalCharge() for i in f)
            ]

            def charge_centre(
                frag, mol=mol
            ):  # the atom that carries the charge (O⁻ in OH⁻), else the first atom
                return next((i for i in frag if mol.GetAtomWithIdx(i).GetFormalCharge()), frag[0])

            for f1, f2 in zip(
                charged, charged[1:], strict=False
            ):  # ions of one formula unit attract (dotted)
                bonds.append(
                    {
                        "a": offset + charge_centre(f1),
                        "b": offset + charge_centre(f2),
                        "order": 1,
                        "style": "ionic",
                    }
                )
            top -= (y1 - y0) + 1.4
            copy_no += 1
        spans.append((x, x + width, sp))
        x += width + 2.6
    total = x - 2.6 if groups else 0.0
    for a in atoms:
        a["p"] = (a["p"][0] - total / 2, a["p"][1], a["p"][2])
    lowest = min((a["p"][1] for a in atoms), default=0.0)
    tags = []
    for k, (x0, x1, sp) in enumerate(spans):
        tags.append({"text": pretty(sp.text), "p": _r(((x0 + x1) / 2 - total / 2, lowest - 1.6, 0.0))})
        if k:
            tags.append({"text": "+", "p": _r((x0 - 1.3 - total / 2, 0.0, 0.0)), "plain": True})
    return atoms, bonds, tags, electrons


def _map_atoms(left: list[dict], right: list[dict]) -> dict[int, int]:
    """product atom → reactant atom. Unchanged molecules/ions (spectator ions, water of crystallisation …) are
    matched whole first; the other atoms are matched so that as many bonds as possible are kept."""
    mapping: dict[int, int] = {}
    used: set[int] = set()

    def members(atoms, frag):
        return [i for i, a in enumerate(atoms) if a["frag"] == frag]

    def signature(atoms, frag):
        return tuple(
            sorted(
                (atoms[i]["el"], atoms[i]["charge"], len(atoms[i]["neighbours"]))
                for i in members(atoms, frag)
            )
        )

    def kept(i: int, j: int) -> int:  # bonds of product atom i that would also exist for reactant atom j
        return sum(1 for nb in right[i]["neighbours"] if mapping.get(nb) in left[j]["neighbours"])

    free = {f: signature(left, f) for f in dict.fromkeys(a["frag"] for a in left)}
    for frag in dict.fromkeys(a["frag"] for a in right):
        match = next((f for f, sig in free.items() if sig == signature(right, frag)), None)
        if match is None:
            continue
        del free[match]
        remaining = members(left, match)
        for i in sorted(members(right, frag), key=lambda i: (right[i]["el"] == "H", i)):
            j = max((j for j in remaining if left[j]["el"] == right[i]["el"]), key=lambda j: (kept(i, j), -j))
            mapping[i] = j
            remaining.remove(j)
            used.add(j)
    todo = [i for i in range(len(right)) if i not in mapping]
    while todo:
        _, i, j = max(
            ((kept(i, j), right[i]["el"] != "H", len(right[i]["neighbours"]), -i, -j), i, j)
            for i in todo
            for j in range(len(left))
            if j not in used and left[j]["el"] == right[i]["el"]
        )
        mapping[i] = j
        used.add(j)
        todo.remove(i)
    return mapping


def reaction_scene(equation: str) -> dict:
    check = chemistry.check_equation(equation)
    if not check.balanced:
        raise SceneError(f"the equation is not balanced — {check.message}")
    left_text, right_text = chemistry._ARROW.split(chemistry.normalise(equation), maxsplit=1)
    left_species, right_species = chemistry._side(left_text), chemistry._side(right_text)
    left, left_bonds, left_tags, left_e = _side_layout(left_species)
    right, right_bonds, right_tags, right_e = _side_layout(right_species)
    if not left or len(left) > 60:
        raise SceneError("this reaction has too many atoms to show clearly (at most 60)")
    if Counter(a["el"] for a in left) != Counter(a["el"] for a in right):
        raise SceneError("the molecule table does not give the same atoms on both sides")
    to_left = _map_atoms(left, right)
    to_right = {j: i for i, j in to_left.items()}  # reactant atom → product atom

    def key(a: int, b: int) -> tuple[int, int]:
        return (min(a, b), max(a, b))

    before = {key(b["a"], b["b"]): b for b in left_bonds}
    after = {}
    for b in right_bonds:
        a, c = to_left[b["a"]], to_left[b["b"]]
        after[key(a, c)] = dict(b, a=a, b=c)
    covalent = lambda bonds: {k: b for k, b in bonds.items() if b.get("style") != "ionic"}  # noqa: E731
    broken = [k for k in covalent(before) if k not in after]
    formed = [k for k in covalent(after) if k not in before]
    kept = [b for k, b in covalent(before).items() if k in after]

    def label(atom: dict) -> str:
        return atom["el"] + charge_text(atom["charge"])

    def bond_list(items, style=None) -> list[dict]:
        return [
            {"a": b["a"], "b": b["b"], "order": b.get("order", 1), "style": style or b.get("style", "solid")}
            for b in items
        ]

    def names(keys) -> str:
        return ", ".join(dict.fromkeys(_bond_name(left[a]["el"], left[b]["el"]) for a, b in keys))

    n = len(left)
    centre = [sum(a["p"][k] for a in left) / n for k in range(3)]
    broken_atoms = {i for pair in broken for i in pair}
    start = [{"p": _r(a["p"]), "label": label(a)} for a in left]
    loosened = [
        {
            "p": _r(
                [centre[k] + (a["p"][k] - centre[k]) * (1.18 if i in broken_atoms else 1.0) for k in range(3)]
            ),
            "label": label(a),
        }
        for i, a in enumerate(left)
    ]
    end = [{"p": _r(right[to_right[i]]["p"]), "label": label(right[to_right[i]])} for i in range(n)]
    changed = list(
        dict.fromkeys(
            f"{label(left[i])} → {label(right[to_right[i]])}"
            for i in range(n)
            if label(left[i]) != label(right[to_right[i]])
        )
    )

    # Electrons written in a half-equation: gained ones fly in and join the products; released ones leave.
    electrons, e_steps = [], [[], [], [], []]
    xs = [a["p"][0] for a in left + right]
    left_edge, right_edge = min(xs) - 2.2, max(xs) + 2.2
    product_centre = [sum(a["p"][k] for a in right) / len(right) for k in range(3)]
    for k in range(min(left_e, 6)):
        electrons.append({"color": FREE_ELECTRON})
        p = _r((left_edge, 1.0 - 0.45 * k, 0.0))
        for step, place in enumerate(
            [{"p": p}, {"p": p}, {"p": _r(product_centre), "o": 0.0}, {"p": _r(product_centre), "o": 0.0}]
        ):
            e_steps[step].append(place)
    for k in range(min(right_e, 6)):
        electrons.append({"color": FREE_ELECTRON})
        p = _r((right_edge, 1.0 - 0.45 * k, 0.0))
        for step, place in enumerate([{"p": _r(centre), "o": 0.0}, {"p": _r(centre)}, {"p": p}, {"p": p}]):
            e_steps[step].append(place)

    counts = ", ".join(f"{el} {count}" for el, count in sorted(check.left.items()))
    charge = sum(s.charge * s.coefficient for s in left_species)
    charge_word = "0" if charge == 0 else f"{charge:+d}"
    electron_note = ""
    if left_e:
        electron_note = f" {_plural(left_e, 'electron')} (e⁻) are gained."
    if right_e:
        electron_note = f" {_plural(right_e, 'electron')} (e⁻) are given out."
    charge_note = (
        (" Charges change: " + ", ".join(changed) + " (electrons move between atoms).") if changed else ""
    )
    steps = [
        {
            "name": "Reactants",
            "caption": f"Reactants: {' + '.join(pretty(s.text) for s in left_species)}. Count the atoms: {counts}.",
            "atoms": start,
            "bonds": bond_list(left_bonds),
            "tags": left_tags
            + ([{"text": f"{left_e}e⁻", "p": _r((left_edge, -1.2, 0.0))}] if left_e else []),
            "electrons": e_steps[0],
        },
        {
            "name": "Bonds break",
            "caption": (
                f"Old bonds break (dashed): {names(broken)}."
                if broken
                else "No bonds inside the molecules or ions break here: the particles only move apart."
            )
            + electron_note,
            "atoms": loosened,
            "bonds": bond_list([b for k, b in before.items() if k not in broken])
            + bond_list([before[k] for k in broken], "dashed"),
            "electrons": e_steps[1],
        },
        {
            "name": "Atoms rearrange",
            "caption": (
                "The atoms move to new partners — no atom is created or destroyed."
                + (f" New bonds form: {names(formed)}." if formed else "")
                + charge_note
            ),
            "atoms": end,
            "bonds": bond_list(kept),
            "electrons": e_steps[2],
        },
        {
            "name": "Products",
            "caption": (
                f"Products: {' + '.join(pretty(s.text) for s in right_species)}. The same atoms are on both sides "
                f"({counts}), so the equation is balanced. Total charge: {charge_word} on both sides."
            ),
            "atoms": end,
            "bonds": bond_list(list(after.values())),
            "tags": right_tags
            + ([{"text": f"{right_e}e⁻", "p": _r((right_edge, -1.2, 0.0))}] if right_e else []),
            "electrons": e_steps[3],
        },
    ]
    elements = sorted({a["el"] for a in left}, key=lambda s: (s != "C", s != "H", s))
    return {
        "kind": "reaction",
        "title": pretty_equation(equation),
        "atoms": [
            _atom_spec(
                a["el"], 0.26 if a["el"] == "H" else 0.5 if a["el"] in METALS | {"Cu", "Zn", "Fe"} else 0.4
            )
            for a in left
        ],
        "electrons": electrons,
        "legend": [
            {"color": NUCLEUS.get(el, "#64748b"), "text": f"{_name(el)} ({el})", "ball": True}
            for el in elements
        ],
        "shellRadius": SHELL_RADIUS,
        "steps": steps,
    }


# ---------------------------------------------------------------- choosing scenes


@lru_cache(maxsize=128)
def build_scene(text: str) -> dict:
    """A formula → bonding scene (ionic or covalent); an equation → reaction scene. Raises SceneError.
    The returned dict is shared by the cache: do not modify it."""
    text = (text or "").strip()
    if not text:
        raise SceneError("nothing to show")
    if chemistry._ARROW.search(chemistry.normalise(text)):
        return reaction_scene(text)
    formula = HYDRATE.sub("", chemistry._STATE.sub("", chemistry.normalise(text)).replace(" ", ""))
    try:
        elements = set(chemistry._count(chemistry._split_charge(formula)[0]))
    except chemistry.FormulaError as exc:
        raise SceneError(str(exc)) from exc
    if elements & METALS and elements & ANION_FORMERS:
        return ionic_scene(formula)
    return covalent_scene(formula)


def lesson_scene_sources(plan: dict) -> list[str]:
    """Scenes offered for a lesson: its molecules (bonding), its balanced equations (reactions), the teacher's extras."""
    sources = [m.get("formula", "") for m in plan.get("molecules", [])]
    sources += [e.get("equation", "") for e in plan.get("equations", []) if e.get("balanced")]
    sources += list(plan.get("scenes_3d", []))
    return [s for s in dict.fromkeys(x.strip() for x in sources) if s]


EXAMPLES = {
    "Ionic bonds — electron transfer": ["NaCl", "MgO", "CaCl₂", "Na₂O", "MgCl₂", "KCl", "CaO", "Al₂O₃"],
    "Covalent bonds — sharing electrons": [
        "H₂",
        "Cl₂",
        "O₂",
        "N₂",
        "HCl",
        "H₂O",
        "NH₃",
        "CH₄",
        "CO₂",
        "C₂H₄",
    ],
    "Reactions — atoms rearrange": [
        "HCl + NaOH → NaCl + H₂O",
        "H⁺ + OH⁻ → H₂O",
        "2H₂ + O₂ → 2H₂O",
        "2H₂O → 2H₂ + O₂",
        "CuSO₄·5H₂O → CuSO₄ + 5H₂O",
        "Ca(OH)₂ + CO₂ → CaCO₃ + H₂O",
        "2Mg + O₂ → 2MgO",
        "Zn + CuSO₄ → ZnSO₄ + Cu",
        "CH₄ + 2O₂ → CO₂ + 2H₂O",
        "2H₂O + 2e⁻ → H₂ + 2OH⁻",
    ],
}
