"""Maths lessons: concepts with the textbook's worked examples, re-computed by the app, and the data for the
maths visual kit (assets/mathkit.js).

The AI only EXTRACTS concepts and the numbers of the textbook's examples, and suggests real-life examples.
Every answer that can be computed is computed here (HCF, LCM, prime factors, angle pairs, one-variable linear
equations); a wrong AI answer is corrected and reported. The visuals are drawn by hand-written code from these
computed values, so a factor tree, a Venn diagram or an angle can never be mathematically wrong.
"""

import math
import re
from fractions import Fraction
from functools import reduce

MATHS_SUBJECTS = {"maths", "math", "mathematics", "algebra", "geometry"}

# Concept kinds the visual kit can draw (anything else gets text, real-life examples and photos only).
KINDS = {
    "prime_numbers": "Prime and composite numbers",
    "co_primes": "Co-prime numbers",
    "twin_primes": "Twin primes",
    "prime_factorisation": "Prime factorisation",
    "hcf": "HCF / GCD",
    "lcm": "LCM",
    "angle_parts": "Angle, vertex, arms, interior and exterior",
    "adjacent_angles": "Adjacent angles",
    "complementary_angles": "Complementary angles",
    "supplementary_angles": "Supplementary angles",
    "opposite_rays": "Opposite rays",
    "linear_pair": "Linear pair",
    "vertically_opposite_angles": "Vertically opposite angles",
    "linear_equation": "Equations in one variable",
    "triangle_angle_sum": "Sum of the angles of a triangle",
    "exterior_angle": "Exterior angle of a triangle",
    "polygon_angle_sum": "Sum of the interior angles of a polygon",
}

SYSTEM_PROMPT = """You are an experienced {audience} teacher preparing a lesson for your own class.
Build the lesson ONLY from the numbered textbook extracts (except 'real_life', see below).
Return ONE JSON object with exactly these keys:
{{
 "title": "short lesson title",
 "objectives": ["what students will be able to do (3 to 4 items)"],
 "sections": [ {{"heading": "...", "content": "teaching text in simple English; cite extracts like [1]", "cites": [1]}} ],
 "key_points": ["one-line takeaways (5 to 7)"],
 "vocabulary": [ {{"term": "...", "meaning": "..."}} ],
 "concepts": [ {{
    "name": "the concept's heading in the textbook, in words (e.g. 'Twin prime numbers')",
    "kind": "one of: {kinds} or 'other'",
    "explain": "2-4 simple sentences a Class student understands",
    "cites": [1],
    "examples": [ {{"text": "the worked example or question as written in the extract",
                    "numbers": [24, 32], "angles": [40, 50], "equation": "a + 15 + 2a = 90", "answer": "8"}} ],
    "real_life": [ {{"title": "short title", "story": "2-3 sentences: where and why this is used in daily life in India",
                     "image_query": "a concrete thing to photograph (see rules)"}} ]
 }} ]
}}
Rules: concepts in the order the textbook teaches them; use 'numbers' for HCF/LCM/primes examples, 'angles' (degrees)
for angle examples, 'equation' for equations — copy them exactly from the extracts and leave out keys that do not
apply. 'answer' = the textbook's answer if it is given. real_life: 2 or 3 per concept, from everyday Indian life
(market, school, railway, cricket, kitchen, buildings, clocks, roads); they may go beyond the extracts but must be
mathematically correct. image_query: 2-4 words naming ONE concrete thing a camera can photograph, as a Wikimedia Commons file would be titled (good: 'railway level crossing', 'wall clock', 'floor tiles pattern', 'cricket pitch', 'tailor cutting cloth'; bad: abstract ideas like 'number chart', 'timetable', 'math puzzle', 'sharing'); use \"\" when nothing concrete fits.
3 to 6 sections. Output the JSON object only."""


def profile_is_maths(subject: str) -> bool:
    key = (subject or "").strip().lower()
    return key in MATHS_SUBJECTS or key.startswith("math")


# ---------------------------------------------------------------- computing


def prime_factors(n: int) -> list[int]:
    """24 → [2, 2, 2, 3]."""
    factors, d = [], 2
    while d * d <= n:
        while n % d == 0:
            factors.append(d)
            n //= d
        d += 1
    if n > 1:
        factors.append(n)
    return factors


def is_prime(n: int) -> bool:
    return n > 1 and prime_factors(n) == [n]


def hcf(numbers: list[int]) -> int:
    return reduce(math.gcd, numbers)


def lcm(numbers: list[int]) -> int:
    return reduce(lambda a, b: a * b // math.gcd(a, b), numbers)


def factor_tree(n: int) -> dict:
    """Split by the smallest prime each time: {'n': 24, 'children': [{'n': 2}, {'n': 12, 'children': [...]}]}"""
    if n < 4 or is_prime(n):
        return {"n": n, "prime": is_prime(n)}
    p = prime_factors(n)[0]
    return {"n": n, "prime": False, "children": [{"n": p, "prime": True}, factor_tree(n // p)]}


def euclid_steps(a: int, b: int) -> list[dict]:
    """Division method for HCF: 252, 144 → [{'dividend': 252, 'divisor': 144, 'quotient': 1, 'remainder': 108}, …]"""
    a, b = max(a, b), min(a, b)
    steps = []
    while b:
        steps.append({"dividend": a, "divisor": b, "quotient": a // b, "remainder": a % b})
        a, b = b, a % b
    return steps


def solve_linear(equation: str) -> tuple[str, Fraction, list[str], list[str]] | None:
    """Solve a one-variable linear equation: 'a + 15 + 2a = 90' → ('a', 25, steps, reasons). None if not linear."""
    text = equation.replace("−", "-").replace("×", "*").replace(" ", "")
    # brackets that are only added, e.g. '(a+30)+2a=180' (not '2(a+3)' or '-(a+3)', which are left unsolved)
    text = re.sub(r"(?:(?<=^)|(?<=[+=]))\(([^()]*)\)(?=[+=]|$)", r"\1", text)
    if "(" in text or ")" in text or text.count("=") != 1:
        return None
    variables = set(re.findall(r"[a-zA-Z]", text))
    if len(variables) != 1:
        return None
    var = variables.pop()

    def side(expr: str) -> tuple[Fraction, Fraction] | None:  # (coefficient of var, constant)
        if not expr:
            return None
        terms = re.findall(r"[+-]?[^+-]+", expr)
        coef, const = Fraction(0), Fraction(0)
        for term in terms:
            sign = -1 if term.startswith("-") else 1
            term = term.lstrip("+-").replace("*", "")
            if term.endswith(var):
                number = term[:-1] or "1"
                if not re.fullmatch(r"\d+(\.\d+)?", number):
                    return None
                coef += sign * Fraction(number)
            elif re.fullmatch(r"\d+(\.\d+)?", term):
                const += sign * Fraction(term)
            else:
                return None
        return coef, const

    left, right = text.split("=")
    a, b = side(left), side(right)
    if a is None or b is None:
        return None
    coef, const = a[0] - b[0], b[1] - a[1]
    if coef == 0:
        return None
    value = const / coef
    # the number beside the letter (left side) is removed from both sides; letters on the right are moved left
    moves = []
    if a[1]:
        moves.append(f"{'take away' if a[1] > 0 else 'add'} {_num(abs(a[1]))}")
    if b[0]:
        moves.append(f"{'take away' if b[0] > 0 else 'add'} {_expr((abs(b[0]), Fraction(0)), var)}")
    move_text = (" and ".join(moves) or "rearrange").capitalize()
    steps = [
        (equation.strip(), "The equation from the textbook — both pans of the balance weigh the same."),
        (f"{_expr(a, var)} = {_expr(b, var)}", f"Put the {var}-terms together and the numbers together."),
        (
            f"{_expr((coef, Fraction(0)), var)} = {_num(const)}",
            f"{move_text} on BOTH sides — the balance stays level.",
        ),
        (f"{var} = {_num(value)}", f"Divide BOTH sides by {_num(coef)} — so {var} = {_num(value)}."),
    ]
    unique: list[tuple[str, str]] = []
    for text, why in steps:
        same = lambda x: x.replace(" ", "").replace("−", "-")  # noqa: E731
        if not unique or same(unique[-1][0]) != same(text):
            unique.append((text, why))
    return var, value, [text for text, _ in unique], [why for _, why in unique]


def _expr(side: tuple[Fraction, Fraction], var: str) -> str:
    coef, const = side
    parts = []
    if coef:
        parts.append(var if coef == 1 else f"−{var}" if coef == -1 else f"{_num(coef)}{var}")
    if const or not parts:
        parts.append(_num(const) if not parts else (f"+ {_num(const)}" if const > 0 else f"− {_num(-const)}"))
    return " ".join(parts)


def _num(x: Fraction) -> str:
    return str(x.numerator) if x.denominator == 1 else f"{x.numerator}/{x.denominator}"


# ---------------------------------------------------------------- checking the plan


def _ints(values) -> list[int]:
    out = []
    for v in values or []:
        try:
            n = int(str(v).strip())
        except ValueError:
            continue
        if 0 < n < 10**7:
            out.append(n)
    return out


# Word problems and reverse questions: the listed numbers are NOT simply the numbers to combine (measured on the
# Class 7 book: "the product of two numbers is 1280 and their GCD is 4 — find the LCM" was 'checked' as LCM(1280, 4)
# and a correct answer 320 was 'corrected'). Such examples are shown as written and not computed.
_WORD_PROBLEM = re.compile(
    r"\b(product|sum|difference|remainders?|leaves?|left over|smallest number|greatest number|largest number|"
    r"least number|ratio|(?:hcf|gcd|lcm)\s*(?:=|is\s+\d)|times|more than|less than|each|how many|after)\b",
    re.I,
)


_NAMES_OPERATION = {
    "hcf": re.compile(r"\b(hcf|gcd|highest common|greatest common)", re.I),
    "lcm": re.compile(r"\b(lcm|lowest common|least common)", re.I),
}
_UNCHECKED = {"computed": "", "ok": None, "note": ""}


def check_example(kind: str, example: dict) -> dict:  # noqa: PLR0911, PLR0912
    """Compute the right answer for an example → {'computed', 'ok', 'note'}.

    'ok' is True/False only when the comparison is CERTAIN; otherwise None (the AI's answer is then never replaced).
    Measured on the Class 7 book: 'Reduce 209/247 to its simplest form' (answer 11/13) must not be 'corrected' to the
    HCF 19, and '(a + 15)° and 2a° are complementary — find each angle' (answer 40° and 50°) must not become 'a = 25'.
    """
    numbers = _ints(example.get("numbers"))
    stated = str(example.get("answer", "")).strip()
    text = str(example.get("text", ""))
    if _WORD_PROBLEM.search(text) and not example.get("equation"):
        return {
            "computed": "",
            "ok": None,
            "note": "word problem — shown as in the textbook, not re-computed",
        }
    stated_numbers = re.findall(r"\d+(?:\.\d+)?", stated)

    if example.get("equation"):
        solved = solve_linear(str(example["equation"]))
        if not solved:
            return dict(_UNCHECKED)
        var, value, _, _ = solved
        computed = f"{var} = {_num(value)}"
        said = re.search(rf"\b{re.escape(var)}\s*=\s*(-?\d+(?:\.\d+)?(?:/\d+)?)", stated)
        ok = (Fraction(said.group(1)) == value) if said else None  # only an answer 'a = …' can be compared
        return {"computed": computed, "ok": ok, "note": ""}

    if kind in _NAMES_OPERATION and len(numbers) >= 2:
        if text and not _NAMES_OPERATION[kind].search(text):
            return dict(_UNCHECKED)  # the question is about something else (e.g. simplest form of a fraction)
        computed = str(hcf(numbers) if kind == "hcf" else lcm(numbers))
        ok = (stated_numbers == [computed]) if len(stated_numbers) == 1 else None
        return {"computed": computed, "ok": ok, "note": ""}

    if kind == "prime_factorisation" and len(numbers) == 1:
        n = numbers[0]
        primes = prime_factors(n)
        computed = f"{n} = {' × '.join(map(str, primes))}"
        said = [int(float(x)) for x in stated_numbers]
        if said[:1] == [n]:
            said = said[1:]  # '24 = 2 × 2 × 2 × 3' or just '2 × 2 × 2 × 3'
        ok = (sorted(said) == primes) if said else None
        return {"computed": computed, "ok": ok, "note": ""}

    if kind in {"co_primes", "twin_primes"} and len(numbers) == 2:
        if kind == "co_primes":
            yes = hcf(numbers) == 1
            computed = "co-prime" if yes else f"not co-prime (common factor {hcf(numbers)})"
        else:
            yes = all(is_prime(n) for n in numbers) and abs(numbers[0] - numbers[1]) == 2
            computed = "twin primes" if yes else "not twin primes"
        # a yes/no answer ('Twin prime numbers', 'Their only common factor is 1', 'No, they are not'): by meaning
        said_no = bool(re.search(r"\b(not|no|isn.?t|aren.?t)\b", stated, re.I))
        return {"computed": computed, "ok": (said_no != yes) if stated else None, "note": ""}

    if kind in {"complementary_angles", "supplementary_angles", "linear_pair"} and example.get("angles"):
        total = 90 if kind == "complementary_angles" else 180
        angles = [float(a) for a in example["angles"] if str(a).replace(".", "", 1).isdigit()]
        if len(angles) == 2 and re.search(r"(complement|supplement)\s+of", text, re.I):
            angles = angles[:1]  # 'find the complement of 70°' — the second number was the answer
        if len(angles) == 1:
            other = Fraction(total) - Fraction(str(angles[0]))
            if other <= 0:
                return dict(_UNCHECKED)
            computed = f"{_num(other)}°"
            ok = (Fraction(stated_numbers[0]) == other) if len(stated_numbers) == 1 else None
            return {"computed": computed, "ok": ok, "note": f"{total}° − {angles[0]:g}°"}
        if len(angles) == 2:
            yes = abs(sum(angles) - total) < 1e-9
            computed = (
                f"yes: {angles[0]:g}° + {angles[1]:g}° = {total}°"
                if yes
                else f"no: the sum is {sum(angles):g}°"
            )
            return {"computed": computed, "ok": None, "note": ""}
    return dict(_UNCHECKED)


def verify(plan: dict) -> list[str]:
    """Annotate every concept example with the computed answer; report AI answers that were wrong."""
    warnings = []
    concepts = []
    for concept in plan.get("concepts", []) or []:
        if not isinstance(concept, dict) or not concept.get("name"):
            continue
        kind = concept.get("kind") if concept.get("kind") in KINDS else "other"
        concept["kind"] = kind
        name = str(concept["name"])
        if name in KINDS or "_" in name:  # the model wrote a code ('twin_prime_numbers') instead of a heading
            concept["name"] = KINDS.get(name) or KINDS.get(kind) or name.replace("_", " ").capitalize()
        for example in concept.get("examples", []) or []:
            result = check_example(kind, example)
            example.update(result)
            if result["ok"] is False:
                warnings.append(
                    f"{concept['name']}: the AI's answer '{example.get('answer')}' for '{example.get('text', '')[:60]}' "
                    f"is wrong — the app computed {result['computed']} (shown instead)."
                )
                example["answer"] = result["computed"]
        concept["real_life"] = [
            r for r in concept.get("real_life", []) or [] if isinstance(r, dict) and r.get("title")
        ]
        concepts.append(concept)
    plan["concepts"] = concepts
    return warnings


# ---------------------------------------------------------------- visual scenes (drawn by assets/mathkit.js)


def visuals_for(concept: dict) -> list[dict]:
    """The 2D/3D scenes the kit can draw for a concept, built only from computed values."""
    kind = concept.get("kind")
    examples = concept.get("examples", []) or []
    numbers = next((_ints(e.get("numbers")) for e in examples if len(_ints(e.get("numbers"))) >= 2), [])
    single = next((_ints(e.get("numbers"))[0] for e in examples if _ints(e.get("numbers"))), None)
    scenes: list[dict] = []
    if kind == "prime_factorisation":
        n = single or 24
        scenes.append({"type": "factor_tree", "dim": "2d", "title": f"Factor tree of {n}", "tree": factor_tree(n),
                       "result": f"{n} = {' × '.join(map(str, prime_factors(n)))}"})  # fmt: skip
    if kind in {"hcf", "lcm"}:
        nums = numbers[:2] if len(numbers) >= 2 else [24, 32]
        a, b = nums
        fa, fb = prime_factors(a), prime_factors(b)
        common = list((_counter(fa) & _counter(fb)).elements())
        only_a = list((_counter(fa) - _counter(fb)).elements())
        only_b = list((_counter(fb) - _counter(fa)).elements())
        scenes.append({"type": "venn", "dim": "2d", "title": f"Prime factors of {a} and {b}", "a": a, "b": b,
                       "only_a": only_a, "common": common, "only_b": only_b, "hcf": hcf(nums), "lcm": lcm(nums)})  # fmt: skip
        scenes.append({"type": "factor_tree", "dim": "2d", "title": f"Factor tree of {a}", "tree": factor_tree(a),
                       "result": f"{a} = {' × '.join(map(str, fa))}"})  # fmt: skip
        if kind == "hcf":
            scenes.append({"type": "division", "dim": "2d", "title": f"Division method: HCF of {max(nums)} and {min(nums)}",
                           "steps": euclid_steps(a, b), "hcf": hcf(nums)})  # fmt: skip
    if kind == "lcm":
        laps = next(
            (_ints(e.get("numbers")) for e in examples if 2 <= len(_ints(e.get("numbers"))) <= 4),
            [16, 24, 18],
        )
        if all(n <= 120 for n in laps):
            scenes.append({"type": "runners", "dim": "2d", "title": "When do they meet again at the start?",
                           "laps": laps, "lcm": lcm(laps)})  # fmt: skip
    if kind in {"complementary_angles", "supplementary_angles", "linear_pair", "adjacent_angles",
                "vertically_opposite_angles", "opposite_rays", "angle_parts"}:  # fmt: skip
        first = next((float(a) for e in examples for a in (e.get("angles") or []) if _is_num(a)), None)
        mode = {"complementary_angles": "complementary", "supplementary_angles": "supplementary",
                "linear_pair": "linear_pair", "adjacent_angles": "adjacent", "opposite_rays": "opposite_rays",
                "vertically_opposite_angles": "vertical", "angle_parts": "parts"}[kind]  # fmt: skip
        start = first if first and 0 < first < (90 if mode == "complementary" else 180) else 40
        scenes.append({"type": "angle", "dim": "2d", "title": KINDS[kind] + " — drag the ray", "mode": mode,
                       "angle": start})  # fmt: skip
        obj = {"complementary": "ramp", "supplementary": "door", "linear_pair": "laptop", "vertical": "scissors",
               "adjacent": "clock", "opposite_rays": "clock", "parts": "clock"}[mode]  # fmt: skip
        scenes.append({"type": "angle3d", "dim": "3d", "title": f"In real life: {obj}", "object": obj,
                       "mode": mode, "angle": start})  # fmt: skip
    for example in examples:
        if example.get("equation") and solve_linear(str(example["equation"])):
            var, value, steps, reasons = solve_linear(str(example["equation"]))
            scenes.append({"type": "balance", "dim": "2d", "title": f"Solve {example['equation']}",
                           "steps": steps, "reasons": reasons, "var": var, "value": _num(value)})  # fmt: skip
            break
    if kind in {"triangle_angle_sum", "exterior_angle"}:
        given = [float(a) for e in examples for a in (e.get("angles") or []) if _is_num(a)]
        pair = next(
            ([a, b] for a, b in zip(given, given[1:], strict=False) if a > 0 and b > 0 and a + b < 170),
            [60, 70],
        )
        scenes.append({"type": "triangle", "dim": "2d", "title": "Angles of a triangle — drag corner A",
                       "angles": pair})  # fmt: skip
    if kind == "polygon_angle_sum":
        scenes.append(
            {"type": "polygon", "dim": "2d", "title": "Angles of a polygon", "sides": [3, 4, 5, 6, 8]}
        )
    if kind == "co_primes":
        pair = next((p[:2] for p in pairs_in(examples) if len(p) >= 2 and hcf(p[:2]) == 1), [10, 21])
        a, b = pair
        scenes.append({"type": "venn", "dim": "2d", "title": f"{a} and {b} share no prime factor", "a": a, "b": b,
                       "only_a": prime_factors(a), "common": [], "only_b": prime_factors(b), "hcf": 1, "lcm": a * b})  # fmt: skip
        return scenes
    if kind in {"prime_numbers", "co_primes", "twin_primes"}:
        top = max([n for n in _ints(sum((e.get("numbers") or [] for e in examples), [])) if n <= 100] or [50])
        top = 50 if top <= 50 else 100
        primes = [n for n in range(2, top + 1) if is_prime(n)]
        twins = [[p, p + 2] for p in primes if is_prime(p + 2) and p + 2 <= top]
        scenes.append({"type": "sieve", "dim": "2d", "title": f"Prime numbers from 1 to {top}", "top": top,
                       "primes": primes, "twins": twins if kind == "twin_primes" else []})  # fmt: skip
    return scenes


def pairs_in(examples: list[dict]) -> list[list[int]]:
    """Numbers of each example: the 'numbers' list, else the numbers written in its text ('10 and 21')."""
    found = []
    for e in examples:
        numbers = _ints(e.get("numbers")) or _ints(re.findall(r"\d+", str(e.get("text", ""))))
        if numbers:
            found.append(numbers)
    return found


def _counter(values):
    from collections import Counter

    return Counter(values)


def _is_num(value) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False
