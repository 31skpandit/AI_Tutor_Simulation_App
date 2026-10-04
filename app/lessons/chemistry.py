"""Chemical formulas and equations: parse, count atoms and charge, check that an equation is balanced.

Written in-house (≈150 lines, fully tested) instead of adding `chempy`, which would pull in SciPy, SymPy and
Matplotlib only to check equations (blueprint D24). Handles: brackets Ca(OH)₂, hydrates CuSO₄·5H₂O, ions
Ca²⁺ / OH⁻ / SO₄²⁻, electrons e⁻ in half-reactions, state symbols (s)(l)(g)(aq), Unicode sub/superscripts.
"""

import re
from collections import Counter
from dataclasses import dataclass, field

_SUB = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
_SUP_DIGITS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
_ARROW = re.compile(r"\s*(?:→|⟶|->|=>|⇌|<=>|=)\s*")
_STATE = re.compile(r"\((?:s|l|g|aq)\)", re.I)
_ELEMENT = re.compile(r"([A-Z][a-z]?)(\d*)")
_HYDRATE_DOT = re.compile(r"[·•∙*]|\.(?=\d*[A-Z(])")

ELEMENTS = set(
    "H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y "
    "Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re "
    "Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U".split()
)


class FormulaError(ValueError):
    pass


@dataclass
class Species:
    text: str
    coefficient: int
    atoms: Counter
    charge: int


@dataclass
class EquationCheck:
    equation: str
    balanced: bool
    message: str
    left: Counter = field(default_factory=Counter)
    right: Counter = field(default_factory=Counter)


def normalise(text: str) -> str:
    """Unicode sub/superscripts → ASCII with explicit charge marks: 'Ca²⁺' → 'Ca^2+', 'H₂O' → 'H2O'."""
    text = text.translate(_SUB)
    text = re.sub(
        r"([⁰¹²³⁴⁵⁶⁷⁸⁹]*)([⁺⁻])",
        lambda m: "^" + m.group(1).translate(_SUP_DIGITS) + ("+" if m.group(2) == "⁺" else "-"),
        text,
    )
    return text.replace("−", "-").replace("–", "-")


def _split_charge(formula: str) -> tuple[str, int]:
    """Charges must be written 'Ca²⁺' / 'Ca^2+' (any size) or as a bare sign 'OH-' / 'Na+' (size 1).

    'Fe3+' in plain ASCII is ambiguous (charge 3+ or 3 Fe atoms?) and is reported as unreadable instead of
    guessed; the lesson planner is told to use Unicode superscripts.
    """
    match = re.search(r"\^(\d*)([+-])$", formula)
    if match:
        size = int(match.group(1) or 1)
        return formula[: match.start()], size if match.group(2) == "+" else -size
    match = re.search(r"(?<=[A-Za-z)\]])([+-])$", formula)
    if match:
        return formula[: match.start()], 1 if match.group(1) == "+" else -1
    return formula, 0


def _count(formula: str) -> Counter:
    """Atoms in a formula without coefficient/charge, e.g. 'Ca(OH)2' → {Ca:1, O:2, H:2}."""
    stack: list[Counter] = [Counter()]
    index = 0
    while index < len(formula):
        char = formula[index]
        if char in "([":
            stack.append(Counter())
            index += 1
        elif char in ")]":
            if len(stack) == 1:
                raise FormulaError(f"unmatched bracket in '{formula}'")
            group = stack.pop()
            number = re.match(r"\d+", formula[index + 1 :])
            times = int(number.group()) if number else 1
            index += 1 + (len(number.group()) if number else 0)
            for element, n in group.items():
                stack[-1][element] += n * times
        else:
            match = _ELEMENT.match(formula, index)
            if not match:
                raise FormulaError(f"cannot read '{formula[index:]}' in '{formula}'")
            element, number = match.group(1), match.group(2)
            if element not in ELEMENTS:
                raise FormulaError(f"unknown element '{element}' in '{formula}'")
            stack[-1][element] += int(number) if number else 1
            index = match.end()
    if len(stack) != 1:
        raise FormulaError(f"unclosed bracket in '{formula}'")
    return stack[0]


def parse_species(text: str) -> Species:
    raw = normalise(text).strip()
    cleaned = _STATE.sub("", raw).replace(" ", "")
    match = re.match(r"^(\d+)(?=[A-Z(\[]|e)", cleaned)
    coefficient = int(match.group(1)) if match else 1
    body = cleaned[match.end() :] if match else cleaned
    if body in {"e", "e-", "e^-"}:  # electron
        return Species(raw, coefficient, Counter(), -1)
    body, charge = _split_charge(body)
    atoms: Counter = Counter()
    for part_index, part in enumerate(_HYDRATE_DOT.split(body)):
        if not part:
            continue
        hydrate = re.match(r"^(\d+)(?=[A-Z(])", part) if part_index else None
        times = int(hydrate.group(1)) if hydrate else 1
        for element, n in _count(part[hydrate.end() :] if hydrate else part).items():
            atoms[element] += n * times
    if not atoms:
        raise FormulaError(f"no atoms in '{text}'")
    return Species(raw, coefficient, atoms, charge)


def _side(text: str) -> list[Species]:
    # Species are separated by ' + ' (with spaces) so that ion charges like 'Na^+' are not split.
    parts = [p for p in re.split(r"\s\+\s", normalise(text).strip()) if p.strip()]
    return [parse_species(p) for p in parts]


def check_equation(equation: str) -> EquationCheck:
    """Is the equation balanced in atoms and in charge? Never raises — problems are reported in the result."""
    text = normalise(equation)
    sides = _ARROW.split(text, maxsplit=1)
    if len(sides) != 2:
        return EquationCheck(equation, False, "No reaction arrow found (use → or ->).")
    try:
        left, right = _side(sides[0]), _side(sides[1])
    except FormulaError as exc:
        return EquationCheck(equation, False, f"Could not read a formula: {exc}")
    if not left or not right:
        return EquationCheck(equation, False, "A side of the equation is empty.")

    def total(species: list[Species]) -> tuple[Counter, int]:
        atoms: Counter = Counter()
        charge = 0
        for s in species:
            for element, n in s.atoms.items():
                atoms[element] += n * s.coefficient
            charge += s.charge * s.coefficient
        return atoms, charge

    (left_atoms, left_charge), (right_atoms, right_charge) = total(left), total(right)
    problems = []
    for element in sorted(set(left_atoms) | set(right_atoms)):
        if left_atoms[element] != right_atoms[element]:
            problems.append(
                f"{element}: {left_atoms[element]} on the left, {right_atoms[element]} on the right"
            )
    if left_charge != right_charge:
        problems.append(f"charge: {left_charge:+d} on the left, {right_charge:+d} on the right")
    if problems:
        return EquationCheck(
            equation, False, "Not balanced — " + "; ".join(problems), left_atoms, right_atoms
        )
    return EquationCheck(equation, True, "Balanced (atoms and charge).", left_atoms, right_atoms)
