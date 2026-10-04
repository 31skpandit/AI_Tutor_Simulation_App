"""Molecules for lessons: name/formula → structure (local table) → 2D drawing (SVG) and 3D coordinates.

Structures come from a reviewed local table (no internet needed in class). Ionic compounds are shown as
their separate ions. Anything not in the table is reported as 'not available' rather than guessed.
"""

import re
from dataclasses import dataclass

from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem
from rdkit.Chem.Draw import rdMolDraw2D

from app.lessons.chemistry import normalise

RDLogger.DisableLog("rdApp.*")  # keep RDKit's warnings out of the app log

# formula (ASCII, as written after normalise()) → (display name, SMILES). Reviewed by hand.
KNOWN: dict[str, tuple[str, str]] = {
    "H2O": ("Water", "O"),
    "H2": ("Hydrogen", "[H][H]"),
    "O2": ("Oxygen", "O=O"),
    "N2": ("Nitrogen", "N#N"),
    "Cl2": ("Chlorine", "ClCl"),
    "HCl": ("Hydrogen chloride", "Cl"),
    "NaOH": ("Sodium hydroxide (Na⁺ and OH⁻ ions)", "[Na+].[OH-]"),
    "KOH": ("Potassium hydroxide (K⁺ and OH⁻ ions)", "[K+].[OH-]"),
    "NaCl": ("Sodium chloride (Na⁺ and Cl⁻ ions)", "[Na+].[Cl-]"),
    "H2SO4": ("Sulphuric acid", "OS(=O)(=O)O"),
    "HNO3": ("Nitric acid", "O[N+](=O)[O-]"),
    "H3PO4": ("Phosphoric acid", "OP(=O)(O)O"),
    "H2CO3": ("Carbonic acid", "OC(=O)O"),
    "CH3COOH": ("Acetic acid", "CC(=O)O"),
    "NH3": ("Ammonia", "N"),
    "CO2": ("Carbon dioxide", "O=C=O"),
    "CH4": ("Methane", "C"),
    "C2H5OH": ("Ethanol", "CCO"),
    "Ca(OH)2": ("Calcium hydroxide (Ca²⁺ and 2 OH⁻ ions)", "[Ca+2].[OH-].[OH-]"),
    "CaCO3": ("Calcium carbonate (Ca²⁺ and CO₃²⁻ ions)", "[Ca+2].[O-]C(=O)[O-]"),
    "NaHCO3": ("Sodium bicarbonate (Na⁺ and HCO₃⁻ ions)", "[Na+].OC(=O)[O-]"),
    "CuSO4": ("Copper sulphate (Cu²⁺ and SO₄²⁻ ions)", "[Cu+2].[O-]S(=O)(=O)[O-]"),
    "FeSO4": ("Ferrous sulphate (Fe²⁺ and SO₄²⁻ ions)", "[Fe+2].[O-]S(=O)(=O)[O-]"),
    "Na2CO3": ("Sodium carbonate / washing soda (2 Na⁺ and CO₃²⁻ ions)", "[Na+].[Na+].[O-]C(=O)[O-]"),
    "KAl(SO4)2": (
        "Potash alum (K⁺, Al³⁺ and 2 SO₄²⁻ ions)",
        "[K+].[Al+3].[O-]S(=O)(=O)[O-].[O-]S(=O)(=O)[O-]",
    ),
    "H^+": ("Hydrogen ion", "[H+]"),
    "OH^-": ("Hydroxide ion", "[OH-]"),
    "H3O^+": ("Hydronium ion", "[OH3+]"),
    "Na^+": ("Sodium ion", "[Na+]"),
    "Cl^-": ("Chloride ion", "[Cl-]"),
}
NAMES = {name.split(" (")[0].lower(): formula for formula, (name, _) in KNOWN.items()}
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
}


@dataclass(frozen=True)
class Molecule:
    formula: str
    name: str
    smiles: str
    svg: str  # 2D drawing
    molblock: str | None  # 3D coordinates for the viewer (None if 3D could not be built)


def resolve(name: str = "", formula: str = "") -> tuple[str, str, str] | None:
    """(formula, display name, SMILES) from the local table, or None."""
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
    formula_key, display, smiles = found
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
    return Molecule(formula_key, display, smiles, drawer.GetDrawingText(), _molblock_3d(mol))


def _molblock_3d(mol: Chem.Mol) -> str | None:
    with_h = Chem.AddHs(mol)
    params = AllChem.ETKDGv3()
    params.randomSeed = 7  # same picture every time
    if AllChem.EmbedMolecule(with_h, params) != 0:
        return None
    try:
        AllChem.UFFOptimizeMolecule(with_h, maxIters=200)
    except Exception:  # noqa: BLE001 — some ions/metals have no force-field parameters; geometry is still usable
        pass
    return Chem.MolToMolBlock(with_h)
