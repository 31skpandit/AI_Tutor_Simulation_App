"""Equation checker — every equation from the pilot topics plus tricky notation."""

import pytest

from app.lessons.chemistry import FormulaError, check_equation, parse_species


@pytest.mark.parametrize(
    ("formula", "atoms", "charge"),
    [
        ("H₂O", {"H": 2, "O": 1}, 0),
        ("Ca(OH)₂", {"Ca": 1, "O": 2, "H": 2}, 0),
        ("CuSO₄·5H₂O", {"Cu": 1, "S": 1, "O": 9, "H": 10}, 0),
        ("CuSO4.5H2O", {"Cu": 1, "S": 1, "O": 9, "H": 10}, 0),
        ("Ca²⁺", {"Ca": 1}, 2),
        ("SO₄²⁻", {"S": 1, "O": 4}, -2),
        ("OH⁻", {"O": 1, "H": 1}, -1),
        ("OH-", {"O": 1, "H": 1}, -1),
        ("Na^+", {"Na": 1}, 1),
        ("Fe₂O₃(s)", {"Fe": 2, "O": 3}, 0),
        ("CH₃COOH", {"C": 2, "H": 4, "O": 2}, 0),
    ],
)
def test_parse_species(formula, atoms, charge):
    species = parse_species(formula)
    assert dict(species.atoms) == atoms and species.charge == charge


@pytest.mark.parametrize(
    "equation",
    [
        "HCl + NaOH → NaCl + H₂O",  # neutralisation
        "HCl(aq) + NaOH(aq) → NaCl(aq) + H₂O(l)",
        "H⁺(aq) + OH⁻(aq) → H₂O(l)",  # ionic form
        "2H₂O → 2H₂ + O₂",  # electrolysis of water
        "2H₂O + 2e⁻ → H₂ + 2OH⁻",  # cathode half-reaction
        "2H₂O → O₂ + 4H⁺ + 4e⁻",  # anode half-reaction
        "CuSO₄·5H₂O → CuSO₄ + 5H₂O",  # water of crystallisation (heating)
        "CuSO₄ + 5H₂O → CuSO₄·5H₂O",
        "Fe₂O₃ + 6HCl → 2FeCl₃ + 3H₂O",  # from the owner's page 10
        "Ca(OH)₂ + CO₂ -> CaCO₃ + H₂O",  # limewater test
        "NaCl(s) → Na⁺(aq) + Cl⁻(aq)",
    ],
)
def test_balanced_equations(equation):
    result = check_equation(equation)
    assert result.balanced, result.message


@pytest.mark.parametrize(
    ("equation", "hint"),
    [
        ("H₂O → H₂ + O₂", "O: 1 on the left, 2 on the right"),
        ("Na + H₂O → NaOH + H₂", "H: 2 on the left, 3 on the right"),
        ("H⁺ + OH⁻ → H₂O⁺", "charge"),
        ("2H₂O + e⁻ → H₂ + 2OH⁻", "charge"),
    ],
)
def test_unbalanced_equations_are_explained(equation, hint):
    result = check_equation(equation)
    assert not result.balanced and hint in result.message


def test_unreadable_input_is_reported_not_crashing():
    assert "arrow" in check_equation("HCl and NaOH make salt").message
    assert not check_equation("Xx + H2 → XxH2").balanced  # unknown element
    with pytest.raises(FormulaError):
        parse_species("Fe3+")  # ambiguous ASCII charge is refused, not guessed
