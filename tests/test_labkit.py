"""Lab kit: layout guarantees (run in Node.js) and the rules AI-written simulations must follow."""

import json
import shutil
import subprocess

import pytest

from app.core.config import PROJECT_ROOT
from app.lessons import simulation
from app.lessons.viewers import simulation_html, uses_labkit
from tests.test_lessons import GOOD_SIM, GOOD_SKETCH

LABKIT = PROJECT_ROOT / "assets" / "labkit.js"
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="Node.js not installed")


def run_node(script: str) -> dict:
    code = f"const kit = require({json.dumps(str(LABKIT))});\n{script}"
    done = subprocess.run([NODE, "-e", code], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@needs_node
def test_labkit_is_valid_javascript():
    assert simulation.node_syntax_error(LABKIT.read_text(encoding="utf-8")) is None


@needs_node
def test_labels_at_the_same_spot_never_overlap_and_stay_inside_the_area():
    """The exact problem from the owner's screenshot: several labels wanted the same place."""
    result = run_node(
        """
        const area = kit.LAB.apparatus, placed = [];
        for (let i = 0; i < 12; i++) placed.push(kit.labPlace({x: 400, y: 150, w: 140, h: 20}, placed, area));
        let overlaps = 0, outside = 0;
        for (let i = 0; i < placed.length; i++) {
          for (let j = i + 1; j < placed.length; j++) if (kit.labOverlaps(placed[i], placed[j])) overlaps++;
          const r = placed[i];
          if (r.x < area.x || r.y < area.y || r.x + r.w > area.x + area.w || r.y + r.h > area.y + area.h) outside++;
        }
        console.log(JSON.stringify({overlaps, outside, first: placed[0]}));
        """
    )
    assert result == {"overlaps": 0, "outside": 0, "first": {"x": 400, "y": 150, "w": 140, "h": 20}}


@needs_node
def test_label_near_the_edge_is_kept_inside():
    result = run_node(
        "const a = kit.LAB.apparatus;"
        "console.log(JSON.stringify(kit.labPlace({x: a.x + a.w - 20, y: a.y - 30, w: 100, h: 20}, [], a)));"
    )
    assert result["x"] + result["w"] <= 16 + 560 and result["y"] >= 58


@needs_node
def test_text_wrapping():
    result = run_node(
        "console.log(JSON.stringify(kit.labWrap('one two three four five six', 10, s => s.length)));"
    )
    assert result == ["one two", "three four", "five six"]


@needs_node
def test_indicator_colours_follow_the_school_chart():
    result = run_node(
        "console.log(JSON.stringify([1, 7, 13, -5, 99, 6.6].map(kit.labIndicatorColor)"
        ".concat([kit.labMixHex('#000000', '#ffffff', 0.5)])));"
    )
    red, green, violet, low, high, rounded, grey = result
    assert red.startswith("#e") and green == "#2fa84f" and violet == "#6a1f8a"
    assert low == kit_colour(0) and high == kit_colour(14) and rounded == green  # clamped / rounded
    assert grey == "#808080"


def kit_colour(ph: int) -> str:
    return run_node(f"console.log(JSON.stringify(kit.labIndicatorColor({ph})));")


@needs_node
def test_chainable_wrapper_returns_the_element_but_keeps_getter_values():
    """p5.js 2 setters return undefined → chained calls crashed; getters must still return their value."""
    result = run_node(
        """
        const el = { opts: [], v: 'a',
          option(x) { this.opts.push(x); },             // p5.js 2 style: returns nothing
          value(x) { if (x === undefined) return this.v; this.v = x; } };
        kit.labMakeChainable(el).option('one').option('two');
        console.log(JSON.stringify({ opts: el.opts, value: el.value(), chained: el.value('b') === el, now: el.value() }));
        """
    )
    assert result == {"opts": ["one", "two"], "value": "a", "chained": True, "now": "b"}


def test_controls_must_use_the_lab_helpers():
    raw = GOOD_SIM.replace("labButton('Stir', () => labStart('stir', 2000));", "createButton('Stir');")
    problems = simulation.check_sketch(raw, require_labkit=True)
    assert any("labButton / labSelect" in p for p in problems), problems


def test_lab_kit_sketch_passes_and_pages_include_the_kit_only_when_needed():
    assert simulation.check_sketch(GOOD_SIM, require_labkit=True) == []
    assert uses_labkit(GOOD_SIM) and not uses_labkit(GOOD_SKETCH)
    assert "function labLabel" in simulation_html(GOOD_SIM)
    assert "function labLabel" not in simulation_html(GOOD_SKETCH)  # older lessons still work unchanged
    assert simulation.check_sketch(GOOD_SKETCH) == []  # and still pass their original checks


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (lambda c: c.replace("labLabel('Beaker'", "text('Beaker'"), "direct text()"),
        (
            lambda c: c.replace("labStart('drop', 1200);", "").replace("labStart('stir', 2000)", "0"),
            "visible animations",
        ),
        (lambda c: c + "\nfunction draw() {}", "do not define setup() or draw()"),
        (lambda c: c + "\ncreateCanvas(10, 10);", "createCanvas"),
        (lambda c: c.replace("panel()", "readings()"), "panel()"),
    ],
)
def test_lab_kit_rules_reject_layout_and_animation_problems(change, expected):
    problems = simulation.check_sketch(change(GOOD_SIM), require_labkit=True)
    assert any(expected in p for p in problems), problems


def test_new_generations_must_use_the_lab_kit():
    problems = simulation.check_sketch(GOOD_SKETCH, require_labkit=True)
    assert any("const SIM" in p for p in problems)


def test_textsize_and_textwidth_are_not_mistaken_for_text():
    code = GOOD_SIM.replace(
        "fill(180, 210, 255);", "fill(180, 210, 255); textSize(14); const w = textWidth('x');"
    )
    assert simulation.check_sketch(code, require_labkit=True) == []
