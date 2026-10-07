"""Molecules for lessons: name/formula → structure (local table) → 2D drawing (SVG) and labelled 3D model.

Structures come from a reviewed local table (no internet needed in class). Ionic compounds are shown as their
separate ions, laid out side by side with a gap, each labelled with its formula and charge (e.g. Cu²⁺, SO₄²⁻);
every atom is labelled with its symbol and charge (e.g. O⁻). Anything not in the table is reported as
'not available' rather than guessed.
"""

import re
from dataclasses import dataclass, field

from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem
from rdkit.Chem.Draw import rdMolDraw2D
from rdkit.Geometry import Point3D

from app.lessons.chemistry import normalise

RDLogger.DisableLog("rdApp.*")  # keep RDKit's warnings out of the app log

GAP_ANGSTROM = 2.5  # empty space between separate ions in the 3D view

# formula (ASCII, as written after normalise()) → (display name, SMILES, ion labels in SMILES fragment order).
# Ion labels are written by hand (not computed) so they follow school notation. Reviewed by hand.
KNOWN: dict[str, tuple[str, str, list[str] | None]] = {
    "H2O": ("Water", "O", None),
    "H2": ("Hydrogen", "[H][H]", None),
    "O2": ("Oxygen", "O=O", None),
    "N2": ("Nitrogen", "N#N", None),
    "Cl2": ("Chlorine", "ClCl", None),
    "HCl": ("Hydrogen chloride", "Cl", None),
    "NaOH": ("Sodium hydroxide (Na⁺ and OH⁻ ions)", "[Na+].[OH-]", ["Na⁺", "OH⁻"]),
    "KOH": ("Potassium hydroxide (K⁺ and OH⁻ ions)", "[K+].[OH-]", ["K⁺", "OH⁻"]),
    "NaCl": ("Sodium chloride (Na⁺ and Cl⁻ ions)", "[Na+].[Cl-]", ["Na⁺", "Cl⁻"]),
    "H2SO4": ("Sulphuric acid", "OS(=O)(=O)O", None),
    "HNO3": ("Nitric acid", "O[N+](=O)[O-]", None),
    "H3PO4": ("Phosphoric acid", "OP(=O)(O)O", None),
    "H2CO3": ("Carbonic acid", "OC(=O)O", None),
    "CH3COOH": ("Acetic acid", "CC(=O)O", None),
    "NH3": ("Ammonia", "N", None),
    "CO2": ("Carbon dioxide", "O=C=O", None),
    "CH4": ("Methane", "C", None),
    "C2H5OH": ("Ethanol", "CCO", None),
    "Ca(OH)2": ("Calcium hydroxide (Ca²⁺ and 2 OH⁻ ions)", "[Ca+2].[OH-].[OH-]", ["Ca²⁺", "OH⁻", "OH⁻"]),
    "CaCO3": ("Calcium carbonate (Ca²⁺ and CO₃²⁻ ions)", "[Ca+2].[O-]C(=O)[O-]", ["Ca²⁺", "CO₃²⁻"]),
    "NaHCO3": ("Sodium bicarbonate (Na⁺ and HCO₃⁻ ions)", "[Na+].OC(=O)[O-]", ["Na⁺", "HCO₃⁻"]),
    "CuSO4": ("Copper sulphate (Cu²⁺ and SO₄²⁻ ions)", "[Cu+2].[O-]S(=O)(=O)[O-]", ["Cu²⁺", "SO₄²⁻"]),
    "FeSO4": ("Ferrous sulphate (Fe²⁺ and SO₄²⁻ ions)", "[Fe+2].[O-]S(=O)(=O)[O-]", ["Fe²⁺", "SO₄²⁻"]),
    "Na2CO3": (
        "Sodium carbonate / washing soda (2 Na⁺ and CO₃²⁻ ions)",
        "[Na+].[Na+].[O-]C(=O)[O-]",
        ["Na⁺", "Na⁺", "CO₃²⁻"],
    ),
    "KAl(SO4)2": (
        "Potash alum (K⁺, Al³⁺ and 2 SO₄²⁻ ions)",
        "[K+].[Al+3].[O-]S(=O)(=O)[O-].[O-]S(=O)(=O)[O-]",
        ["K⁺", "Al³⁺", "SO₄²⁻", "SO₄²⁻"],
    ),
    "H^+": ("Hydrogen ion", "[H+]", ["H⁺"]),
    "OH^-": ("Hydroxide ion", "[OH-]", ["OH⁻"]),
    "H3O^+": ("Hydronium ion", "[OH3+]", ["H₃O⁺"]),
    "Na^+": ("Sodium ion", "[Na+]", ["Na⁺"]),
    "Cl^-": ("Chloride ion", "[Cl-]", ["Cl⁻"]),
    # Added 2026-10-06 for the 3D chemistry lab (bonding and reaction scenes). Reviewed by hand.
    "K^+": ("Potassium ion", "[K+]", ["K⁺"]),
    "Mg^2+": ("Magnesium ion", "[Mg+2]", ["Mg²⁺"]),
    "Ca^2+": ("Calcium ion", "[Ca+2]", ["Ca²⁺"]),
    "Cu^2+": ("Copper ion", "[Cu+2]", ["Cu²⁺"]),
    "Zn^2+": ("Zinc ion", "[Zn+2]", ["Zn²⁺"]),
    "Fe^2+": ("Ferrous ion", "[Fe+2]", ["Fe²⁺"]),
    "O^2-": ("Oxide ion", "[O-2]", ["O²⁻"]),
    "SO4^2-": ("Sulphate ion", "[O-]S(=O)(=O)[O-]", ["SO₄²⁻"]),
    "CO3^2-": ("Carbonate ion", "[O-]C(=O)[O-]", ["CO₃²⁻"]),
    "NO3^-": ("Nitrate ion", "[O-][N+](=O)[O-]", ["NO₃⁻"]),
    "Na": ("Sodium (one atom shown)", "[Na]", None),
    "K": ("Potassium (one atom shown)", "[K]", None),
    "Mg": ("Magnesium (one atom shown)", "[Mg]", None),
    "Ca": ("Calcium (one atom shown)", "[Ca]", None),
    "Al": ("Aluminium (one atom shown)", "[Al]", None),
    "Zn": ("Zinc (one atom shown)", "[Zn]", None),
    "Fe": ("Iron (one atom shown)", "[Fe]", None),
    "Cu": ("Copper (one atom shown)", "[Cu]", None),
    "C": ("Carbon (one atom shown)", "[C]", None),
    "S": ("Sulphur (one atom shown)", "[S]", None),
    "F2": ("Fluorine", "FF", None),
    "HF": ("Hydrogen fluoride", "F", None),
    "H2S": ("Hydrogen sulphide", "S", None),
    "H2O2": ("Hydrogen peroxide", "OO", None),
    "CH3OH": ("Methanol", "CO", None),
    "CCl4": ("Carbon tetrachloride", "ClC(Cl)(Cl)Cl", None),
    "C2H4": ("Ethene", "C=C", None),
    "C2H2": ("Ethyne", "C#C", None),
    "SO2": ("Sulphur dioxide", "O=S=O", None),
    "MgO": ("Magnesium oxide (Mg²⁺ and O²⁻ ions)", "[Mg+2].[O-2]", ["Mg²⁺", "O²⁻"]),
    "CaO": ("Calcium oxide / quicklime (Ca²⁺ and O²⁻ ions)", "[Ca+2].[O-2]", ["Ca²⁺", "O²⁻"]),
    "CuO": ("Copper(II) oxide (Cu²⁺ and O²⁻ ions)", "[Cu+2].[O-2]", ["Cu²⁺", "O²⁻"]),
    "ZnO": ("Zinc oxide (Zn²⁺ and O²⁻ ions)", "[Zn+2].[O-2]", ["Zn²⁺", "O²⁻"]),
    "Na2O": ("Sodium oxide (2 Na⁺ and O²⁻ ions)", "[Na+].[Na+].[O-2]", ["Na⁺", "Na⁺", "O²⁻"]),
    "Al2O3": (
        "Aluminium oxide (2 Al³⁺ and 3 O²⁻ ions)",
        "[Al+3].[Al+3].[O-2].[O-2].[O-2]",
        ["Al³⁺", "Al³⁺", "O²⁻", "O²⁻", "O²⁻"],
    ),
    "KCl": ("Potassium chloride (K⁺ and Cl⁻ ions)", "[K+].[Cl-]", ["K⁺", "Cl⁻"]),
    "MgCl2": ("Magnesium chloride (Mg²⁺ and 2 Cl⁻ ions)", "[Mg+2].[Cl-].[Cl-]", ["Mg²⁺", "Cl⁻", "Cl⁻"]),
    "CaCl2": ("Calcium chloride (Ca²⁺ and 2 Cl⁻ ions)", "[Ca+2].[Cl-].[Cl-]", ["Ca²⁺", "Cl⁻", "Cl⁻"]),
    "ZnCl2": ("Zinc chloride (Zn²⁺ and 2 Cl⁻ ions)", "[Zn+2].[Cl-].[Cl-]", ["Zn²⁺", "Cl⁻", "Cl⁻"]),
    "ZnSO4": ("Zinc sulphate (Zn²⁺ and SO₄²⁻ ions)", "[Zn+2].[O-]S(=O)(=O)[O-]", ["Zn²⁺", "SO₄²⁻"]),
    "CaSO4": ("Calcium sulphate (Ca²⁺ and SO₄²⁻ ions)", "[Ca+2].[O-]S(=O)(=O)[O-]", ["Ca²⁺", "SO₄²⁻"]),
    "Na2SO4": (
        "Sodium sulphate (2 Na⁺ and SO₄²⁻ ions)",
        "[Na+].[Na+].[O-]S(=O)(=O)[O-]",
        ["Na⁺", "Na⁺", "SO₄²⁻"],
    ),
}
NAMES = {name.split(" (")[0].lower(): formula for formula, (name, _, _) in KNOWN.items()}
NAMES |= {
    "water": "H2O",
    "hydrochloric acid": "HCl",
    "sulfuric acid": "H2SO4",
    "copper sulfate": "CuSO4",
    "slaked lime": "Ca(OH)2",
    "lime water": "Ca(OH)2",
    "limewater": "Ca(OH)2",
    "baking soda": "NaHCO3",
    "common salt": "NaCl",
    "blue vitriol": "CuSO4",
    "ferrous sulfate": "FeSO4",
    "green vitriol": "FeSO4",
    "washing soda": "Na2CO3",
    "sodium carbonate": "Na2CO3",
    "alum": "KAl(SO4)2",
    "potash alum": "KAl(SO4)2",
    "quicklime": "CaO",
    "calcium oxide": "CaO",
    "magnesium oxide": "MgO",
    "zinc sulfate": "ZnSO4",
    "sodium sulfate": "Na2SO4",
    "calcium sulfate": "CaSO4",
    "sulfur dioxide": "SO2",
    "hydrogen sulfide": "H2S",
}

ELEMENT_NAMES = {
    "H": "Hydrogen",
    "He": "Helium",
    "Li": "Lithium",
    "Be": "Beryllium",
    "B": "Boron",
    "C": "Carbon",
    "N": "Nitrogen",
    "O": "Oxygen",
    "F": "Fluorine",
    "Ne": "Neon",
    "Na": "Sodium",
    "Mg": "Magnesium",
    "Al": "Aluminium",
    "Si": "Silicon",
    "P": "Phosphorus",
    "S": "Sulphur",
    "Cl": "Chlorine",
    "Ar": "Argon",
    "K": "Potassium",
    "Ca": "Calcium",
    "Fe": "Iron",
    "Cu": "Copper",
    "Zn": "Zinc",
}
_SUPERSCRIPT = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


def charge_text(charge: int) -> str:
    """0 → '', 1 → '⁺', -1 → '⁻', 2 → '²⁺', -2 → '²⁻'."""
    if charge == 0:
        return ""
    size = "" if abs(charge) == 1 else str(abs(charge)).translate(_SUPERSCRIPT)
    return size + ("⁺" if charge > 0 else "⁻")


@dataclass(frozen=True)
class Label3D:
    text: str
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class Molecule:
    formula: str
    name: str
    smiles: str
    svg: str  # 2D drawing
    molblock: str | None  # 3D coordinates for the viewer (None if 3D could not be built)
    atom_labels: list[Label3D] = field(default_factory=list)  # e.g. "Cu²⁺", "O⁻", "H"
    ion_labels: list[Label3D] = field(default_factory=list)  # e.g. "SO₄²⁻" above each ion
    elements: list[tuple[str, str]] = field(default_factory=list)  # [("Cu", "Copper"), ...] for the legend
    notes: list[str] = field(default_factory=list)  # teaching notes shown under the model


def resolve(name: str = "", formula: str = "") -> tuple[str, str, str, list[str] | None] | None:
    """(formula, display name, SMILES, ion labels) from the local table, or None."""
    key = normalise(formula).replace(" ", "")
    key = key.split("·")[0].split(".")[0] if key else key  # hydrate → the salt itself
    if key in KNOWN:
        return key, *KNOWN[key]
    by_name = NAMES.get(name.strip().lower())
    if by_name:
        return by_name, *KNOWN[by_name]
    return None


def build(name: str = "", formula: str = "") -> Molecule | None:
    found = resolve(name, formula)
    if found is None:
        return None
    formula_key, display, smiles, ions = found
    hydrate = re.search(r"[·•∙.](\d*)H2O", normalise(formula).replace(" ", ""))
    if hydrate:
        display += f" — the {hydrate.group(1) or 1} water molecule(s) of crystallisation are not drawn"
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    drawer = rdMolDraw2D.MolDraw2DSVG(320, 220)
    drawer.drawOptions().addAtomIndices = False
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    elements = sorted(
        {a.GetSymbol() for a in Chem.AddHs(mol).GetAtoms()}, key=lambda s: (s != "C", s != "H", s)
    )
    model = _model_3d(mol, ions)
    if model is None:
        return Molecule(
            formula_key,
            display,
            smiles,
            drawer.GetDrawingText(),
            None,
            elements=[(e, ELEMENT_NAMES.get(e, e)) for e in elements],
        )
    molblock, atom_labels, ion_labels = model
    return Molecule(
        formula_key,
        display,
        smiles,
        drawer.GetDrawingText(),
        molblock,
        atom_labels,
        ion_labels,
        [(e, ELEMENT_NAMES.get(e, e)) for e in elements],
        _charge_notes(mol, ions),
    )


def _charge_notes(mol: Chem.Mol, ions: list[str] | None) -> list[str]:
    """For a charged ion made of several atoms (SO₄²⁻, CO₃²⁻, OH⁻ …) explain that the charge belongs to the
    whole ion — students otherwise ask why only some oxygens show O⁻."""
    notes = []
    labels = ions or []
    for index, atoms in enumerate(Chem.GetMolFrags(mol)):
        charge = sum(mol.GetAtomWithIdx(i).GetFormalCharge() for i in atoms)
        if len(atoms) > 1 and charge != 0:
            name = labels[index] if index < len(labels) else "this ion"
            note = (
                f"The {charge_text(charge)} charge belongs to the whole {name} ion; the marked atoms show "
                "one common way to draw it."
            )
            if note not in notes:
                notes.append(note)
    return notes


def embed_3d(mol: Chem.Mol) -> Chem.Mol | None:
    """Molecule with hydrogens and one 3D conformer (same picture every time), or None."""
    with_h = Chem.AddHs(mol)
    params = AllChem.ETKDGv3()
    params.randomSeed = 7  # same picture every time
    if AllChem.EmbedMolecule(with_h, params) != 0:
        return None
    try:
        AllChem.UFFOptimizeMolecule(with_h, maxIters=200)
    except Exception:  # noqa: BLE001 — some ions/metals have no force-field parameters; geometry is still usable
        pass
    return with_h


def _model_3d(mol: Chem.Mol, ions: list[str] | None):
    """3D coordinates with separate ions side by side, plus atom and ion labels."""
    with_h = embed_3d(mol)
    if with_h is None:
        return None
    conf = with_h.GetConformer()
    fragments = Chem.GetMolFrags(with_h)  # atom-index tuples, in SMILES order (heavy atoms come first)
    # Separate the fragments: RDKit places every fragment around the origin, so a lone ion (e.g. Cu²⁺)
    # ends up hidden inside another one (measured: Cu 0.04 Å from S). Lay them out left → right with a gap.
    cursor = 0.0
    centres = []
    for atoms in fragments:
        xs = [conf.GetAtomPosition(i).x for i in atoms]
        shift = cursor - min(xs)
        for i in atoms:
            p = conf.GetAtomPosition(i)
            conf.SetAtomPosition(i, Point3D(p.x + shift, p.y, p.z))
        width = max(xs) - min(xs)
        points = [conf.GetAtomPosition(i) for i in atoms]
        centre = (
            sum(p.x for p in points) / len(points),
            sum(p.y for p in points) / len(points),
            sum(p.z for p in points) / len(points),
        )
        top = max(p.y for p in points)
        centres.append((centre, top))
        cursor += width + GAP_ANGSTROM + 0.8  # 0.8 Å ≈ atom radius margin
    middle = (cursor - GAP_ANGSTROM - 0.8) / 2  # centre the whole picture on the origin
    for i in range(with_h.GetNumAtoms()):
        p = conf.GetAtomPosition(i)
        conf.SetAtomPosition(i, Point3D(p.x - middle, p.y, p.z))
    atom_labels = []
    for atom in with_h.GetAtoms():
        p = conf.GetAtomPosition(atom.GetIdx())
        atom_labels.append(Label3D(atom.GetSymbol() + charge_text(atom.GetFormalCharge()), p.x, p.y, p.z))
    ion_labels = []
    if ions and len(ions) == len(fragments) and len(fragments) > 1:
        for label, ((cx, _cy, cz), top) in zip(ions, centres, strict=True):
            ion_labels.append(Label3D(label, cx - middle, top + 1.4, cz))
    return Chem.MolToMolBlock(with_h), atom_labels, ion_labels
