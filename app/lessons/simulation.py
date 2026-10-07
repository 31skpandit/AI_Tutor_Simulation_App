"""AI-written interactive simulations (p5.js sketches) with automatic checks.

The model writes ONLY a `SIM` object that plugs into our hand-written lab kit (assets/labkit.js), which owns
the layout (labels cannot overlap), the controls and ready-made, correctly drawn apparatus (beaker, test tube,
burner …). We wrap it in a page whose security policy blocks all network access (viewers.py).
Before a sketch is accepted it must pass, in this order:
  1. safety rules — no network, storage, eval or access to the surrounding app;
  2. lab-kit rules — SIM with drawApparatus/panel, no own setup/draw/canvas, no direct text() (labels only
     through labLabel), controls through labButton/labSelect/labSlider/labCheckbox and animated with labStart;
  3. syntax — `node --check` (Node.js is installed) must accept it;
  4. run-time — the page is opened in a hidden Edge/Chrome and every control is used (browser_check.py):
     no errors, and every control must visibly change the picture;
  5. visual review — pictures of each state are checked by a vision model against the textbook facts
     (apparatus drawn correctly, colours and results right, labels sensible).
If a check fails, the problems are sent back to the model to fix (up to 3 times). The teacher then
previews the simulation in Lesson Studio before approving the lesson.
"""

import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import PROJECT_ROOT
from app.lessons.browser_check import check_in_browser
from app.lessons.viewers import simulation_html, uses_labkit
from app.llm.router import AllModelsFailed, LLMRouter

SIM_TASK = "simulation_code"
REVIEW_TASK = "simulation_review"
MAX_FIX_ROUNDS = 3
MAX_CHARS = 30_000
VISUAL_PREFIX = "Visual review: "  # such problems are shown to the teacher but do not hide the simulation
EXAMPLE = (PROJECT_ROOT / "assets" / "labkit_example.js").read_text(encoding="utf-8")

FORBIDDEN = {
    r"\bfetch\s*\(": "network access (fetch)",
    r"XMLHttpRequest": "network access (XMLHttpRequest)",
    r"\bWebSocket\b": "network access (WebSocket)",
    r"\bEventSource\b": "network access (EventSource)",
    r"\bimport\s*\(|^\s*import\s": "loading other code (import)",
    r"\beval\s*\(|new\s+Function\s*\(": "running generated code (eval / Function)",
    r"localStorage|sessionStorage|indexedDB|document\.cookie": "browser storage",
    r"window\.(parent|top|opener|frameElement)|(?<![\w.$])(parent|top|opener)\.(document|location|postMessage|window)": "access to the surrounding app",
    r"https?://": "web addresses",
    r"\bloadImage\b|\bloadFont\b|\bloadJSON\b|\bloadStrings\b|\bloadSound\b|\bloadModel\b": "loading files",
    r"\bpreload\s*\(": "preload() (not available in p5.js 2)",
    r"\brequire\s*\(|\bprocess\.|\bchild_process\b": "Node.js-only features (require/process)",
}

SYSTEM_PROMPT = (
    """You write ONE interactive science experiment for a school classroom. It runs inside our "lab kit" for
p5.js 2 (global mode). The kit already provides setup() and draw(), the canvas, the layout, a title band, a readings
panel on the right and an "Observe" band at the bottom.
Output ONLY JavaScript that defines one object named SIM — no HTML, no Markdown fences, no setup() or draw(), no createCanvas().

const SIM = {
  title: "short title",
  observe: "one sentence telling students what to watch (without the word Observe)",
  state: { /* every value the experiment needs */ },
  setup() { /* optional: initialise this.state */ },
  controls() { /* labButton / labSelect / labSlider / labCheckbox only */ },
  drawApparatus(area) { /* draw the experiment inside area = {x, y, w, h} (560 x 420 px); drawing outside is cut off */ },
  panel() { return ["pH: 6.0", {text: "Solution: acidic", color: "#b91c1c", bold: true}]; },
};

CONTROLS (use these, never createButton/createSelect/… directly):
- labButton(label, () => {...})
- labSelect(label, ["choice 1", "choice 2"], (value) => {...}, initialChoice)
- labSlider(label, min, max, value, step, (value) => {...})
- labCheckbox(label, checked, (checked) => {...})

COMPLETE SETUPS — if the experiment is one of these, call the setup in drawApparatus and do NOT draw its parts
again (they are hand-drawn and checked). Add only the extra things the experiment needs, and the readings:
- labElectrolysis(area, {on, conducts, liquid, cathodeGas: "H₂", anodeGas: "O₂", ratio: 2}) — electrolysis of water:
  beaker, inverted tubes, electrodes, battery and wires; the gas collects by itself while on && conducts.
  labSetupReset() empties the tubes (e.g. on a "Reset" button).
- labHeating(area, {on, vessel: "dish" | "beaker", color, crystals, steam, label}) — heating on a tripod with a
  burner. Show changes ONLY through `color` (e.g. blue copper sulphate crystals: labMixHex("#2563eb", "#f8fafc", t)
  with t going 0 → 1 while heating). Leave out `amount` (it means how FULL the dish is; 0 = empty dish).
  Returns {x, top, bench} — put extra labels and the dropper relative to x and top.
- labConductivity(area, {on, conducts, liquid, label}) — does a liquid conduct? battery, bulb, electrodes in a beaker.
- labNeutralisation(area, {ph, indicator: "universal" | "phenolphthalein" | "litmus" | "none", drop: labProgress("drop"),
  stir: labProgress("stir"), strip: null | ph, acid: "Dilute HCl", base: "NaOH"}) — adding a base drop by drop to an
  acid: the kit colours the solution from the indicator chart and the pH paper from the pH (strip: null = not yet
  tested). You keep the pH in state (change it gradually after each drop) and the readings.
- Every setup already labels its own parts: do not add labels for them again, and put any new label right next to
  the thing it names (use the geometry the setup returns), never in empty space. Keep the picture simple: do not
  add instruments (thermometer, meter …) or decorations unless the textbook facts need them; formulas, names and
  states go in panel().

APPARATUS PARTS — for other experiments. ALWAYS use these parts instead of drawing glassware yourself.
x = horizontal centre; y = the line the part stands on (its bottom). Each returns its geometry for placing other parts.
- labBeaker(x, y, {w, h, level 0..1, liquid: "#hex", label, maxMl, swirl: labProgress("stir")}) → {x, left, right, top, bottom, surface, w, h}
- labTestTube(x, y, {w, h, level, liquid, label}) upright, y = round bottom;
  labTestTube(x, mouthY, {inverted: true, gas: 0..1, gasLabel: "H₂", liquid}) for collecting gas: place mouthY BELOW
  the liquid surface of the beaker so the tube stands in the liquid → {x, left, right, top, bottom, gasEnd}
- labBurner(x, y, {on, size}) Bunsen burner (flame flickers by itself) → {x, top, bottom}
- labTripod(x, y, {w, h}) → {top} (put a dish or beaker ON result.top; put the burner under it on the same y)
- labDish(x, y, {w, color, amount 0..1, crystals: true, label}) china dish resting on y
- labDropper(x, tipY, {color, drop: labProgress("drop"), dropTo: beaker.surface, label}) the drop falls while 0<drop<1
- labGlassRod(beaker, {stir: labProgress("stir"), label}) rod in the beaker; circles while 0<stir<1
- labElectrode(x, top, bottom, {sign: "+" | "-", label})
- labBattery(x, y, {on, label}) → {plus: {x, y}, minus: {x, y}}
- labWire([[x1, y1], [x2, y2], …], {current: true}) dots move from the first point to the last (electron flow:
  from the − terminal to the cathode, from the anode to the + terminal)
- labBubbles(x, fromY, toY, {rate 0..1, spread}) rising bubbles, animated by themselves
- labPHStrip(x, y, {ph: null | number, wet: 0..1, label}) universal-indicator paper (colour from pH by the kit)
- labThermometer(x, y, {value, min, max, label})
- labIndicatorColor(ph) → "#hex" universal-indicator colour; labMixHex("#a", "#b", t) mixes two colours

TEXT AND ANIMATION:
- labLabel(text, x, y, {size, align: 'center'|'left'|'right', color, bold}) — the ONLY way to write text in drawApparatus.
  If that space is taken the kit moves the label and draws a leader line, so labels never overlap. NEVER call text().
- labStart(name, ms) starts an animation; labProgress(name) gives 0→1 while it runs (1 afterwards, 0 before it ever
  started); labActive(name) is true while it runs; labEase(t) makes motion smooth.

RULES:
- EVERY control must start a VISIBLE animation of 1–3 seconds drawn in drawApparatus (e.g. stirring → labGlassRod with
  stir + labBeaker swirl; adding a drop → labDropper drop falls, then the colour changes gradually; heating → labBurner
  on and the substance changes colour gradually; current on → labBubbles at both electrodes and gas collects).
- The FIRST picture (before any control is used) must show the correct starting state (e.g. blue copper sulphate
  crystals are blue before heating). Remember labProgress(name) is 0 before the action ever started.
- Stack parts realistically: things stand on the bench or on a tripod, liquids stay inside their containers, inverted
  tubes stand in the liquid, electrodes dip into the liquid, wires connect real terminals. Nothing floats.
- Electrical parts (battery, switch, bulb, meter) are ALWAYS outside every container and liquid, joined by wires.
  An electrode inside an inverted gas tube enters from BELOW (through the base of the beaker or from under the
  mouth) and ends inside the tube — it must never pass through the closed top of a tube. Leave room below the beaker
  (as in the example) when the battery goes underneath.
- Place everything relative to area.x, area.y, area.w, area.h. Keep at least 12 px between parts.
  Labels: at most 4 words, only real names of things (no "Ticks", no "Scale"). Numbers, explanations and equations go in panel().
- panel(): at most 8 short lines.
- Use `this.state` (or SIM.state) for values; inside arrow functions in controls() refer to SIM.state.
- The science must match the textbook facts given by the user exactly (formulas, colours, ratios, values). Do not
  invent facts. Write formulas with Unicode subscripts (H₂O, H₂SO₄) and charges with superscripts (Na⁺, OH⁻).
- At most about 220 lines. No external files, images, fonts or sounds; no fetch/network, no localStorage, no eval,
  no access to window.parent/top, no preload(), no load* functions. Short comments in simple English.

EXAMPLE of a correct experiment (follow its style):
"""
    + EXAMPLE
)

CONTROL_PATTERN = r"\bcreate(Button|Slider|Select|Checkbox|Radio|Input)\s*\("
LAB_CONTROL_PATTERN = r"\blab(Button|Select|Slider|Checkbox)\s*\("

REVIEW_PROMPT = """You check an interactive school science experiment before a teacher shows it to Class 9 students.
You get pictures of its drawing area — at the start, then DURING and AFTER each control is used — and the textbook
facts. A movement such as stirring or a falling drop is only visible in the DURING picture; a lasting change (a
colour after heating, gas collected, a new pH) must be visible in the AFTER picture. Controls are used one after
another, so each picture continues from the one before. A colourless solution may be drawn pale blue, and a
solution with an indicator takes the indicator's colour.
Report ONLY definite, visible mistakes a teacher would notice:
- apparatus drawn wrongly: upside down, floating in the air, liquid outside its container, an inverted gas tube not
  standing in the liquid, electrodes not in the liquid, a burner not under what it heats, parts overlapping wrongly;
- a battery, switch, bulb or meter drawn inside a liquid or inside a container (it must be outside, joined by wires);
- a rod or electrode passing through the closed end of a test tube, or wires that do not reach a terminal;
- colours, states or results that contradict the textbook facts (e.g. a substance shown white when the facts say blue);
- labels that are meaningless, wrong, attached to the wrong part, or floating in empty space far from the part
  they name;
- a container that should hold something (crystals, liquid) but is empty in a picture;
- a part cut off at the edge of the picture, an instrument hanging in the air, or the same name written twice;
- a control whose effect cannot be seen.
Look at every part of every picture carefully before answering, as a strict science teacher would.
Do NOT report style, beauty, missing details or things that are only simplified.
Answer as JSON only: {"ok": true, "problems": []} or {"ok": false, "problems": ["short, specific fix instruction", ...]}"""


@dataclass
class SimulationResult:
    code: str
    ok: bool
    problems: list[str] = field(default_factory=list)
    rounds: int = 0
    model_ref: str | None = None
    cost_usd: float = 0.0


def strip_fences(text: str) -> str:
    match = re.search(r"```(?:javascript|js)?\s*\n(.*?)```", text, re.S)
    return (match.group(1) if match else text).strip()


def check_sketch(code: str, *, require_labkit: bool = False) -> list[str]:
    """All problems found in a sketch (empty list = accepted).

    Lab-kit sketches (define `SIM`) get the layout/animation rules; older stand-alone sketches keep the
    original rules so lessons made before the lab kit still work. New generations require the lab kit.
    """
    problems = []
    if len(code) > MAX_CHARS:
        problems.append(f"too long ({len(code)} characters; limit {MAX_CHARS})")
    for pattern, reason in FORBIDDEN.items():
        if re.search(pattern, code, re.M):
            problems.append(f"not allowed: {reason}")
    if uses_labkit(code):
        problems += _labkit_rules(code)
    elif require_labkit:
        problems.append("must define `const SIM = {...}` for the lab kit (no setup()/draw() of your own)")
    else:  # older stand-alone sketch
        if not re.search(r"function\s+setup\s*\(", code):
            problems.append("missing function setup()")
        if not re.search(r"function\s+draw\s*\(", code):
            problems.append("missing function draw()")
        if "createCanvas" not in code:
            problems.append("setup() must call createCanvas(860, 500)")
    syntax = node_syntax_error(code)
    if syntax:
        problems.append(f"JavaScript syntax error: {syntax}")
    return problems


def _labkit_rules(code: str) -> list[str]:
    problems = []
    if not re.search(r"\bdrawApparatus\s*\(", code):
        problems.append("SIM must have drawApparatus(area)")
    if not re.search(r"\bpanel\s*\(", code):
        problems.append("SIM must have panel() returning the readings")
    if re.search(r"^\s*function\s+(setup|draw)\s*\(", code, re.M):
        problems.append("do not define setup() or draw(): the lab kit provides them")
    if "createCanvas" in code:
        problems.append("do not call createCanvas(): the lab kit creates the canvas")
    direct_text = len(re.findall(r"(?<![\w.$])text\s*\(", code))
    if direct_text:
        problems.append(
            f"{direct_text} direct text() call(s): use labLabel(text, x, y) for every label so labels cannot overlap"
        )
    if re.search(CONTROL_PATTERN, code):
        problems.append(
            "create controls only with labButton / labSelect / labSlider / labCheckbox (not createButton, "
            "createSelect … — in p5.js 2 some of their methods cannot be chained)"
        )
    has_controls = re.search(CONTROL_PATTERN, code) or re.search(LAB_CONTROL_PATTERN, code)
    if has_controls and not ("labStart(" in code and ("labProgress(" in code or "labActive(" in code)):
        problems.append(
            "controls must start visible animations: call labStart(name, ms) in each control and draw the motion "
            "with labProgress(name) / labActive(name) in drawApparatus (a counter alone is not enough)"
        )
    return problems


def check_runtime(code: str):
    """Open the sealed page in a hidden browser and use every control (see browser_check.py)."""
    return check_in_browser(simulation_html(code))


def review_visually(
    router: LLMRouter, shots: list[tuple[str, str]], brief: str, facts: str
) -> tuple[list[str], float]:
    """Vision-model review of the pictures against the facts. Returns (problems, cost). Never raises: if the
    review model is unavailable the simulation is not blocked (the teacher still previews it)."""
    if not shots:
        return [], 0.0
    content: list[dict] = [{"type": "text", "text": f"Experiment: {brief}\n\nTextbook facts:\n{facts}"}]
    for label, png in shots:
        content.append({"type": "text", "text": f"Picture — {label}:"})
        content.append({"type": "image_url", "image_url": {"url": png, "detail": "high"}})
    messages = [{"role": "system", "content": REVIEW_PROMPT}, {"role": "user", "content": content}]
    try:
        result = router.complete(REVIEW_TASK, messages)
    except AllModelsFailed:
        return [], 0.0
    try:
        verdict = json.loads(strip_fences(result.text))
    except json.JSONDecodeError:
        return [], result.cost_usd
    if not isinstance(verdict, dict) or verdict.get("ok") is True:
        return [], result.cost_usd
    problems = [str(p).strip() for p in verdict.get("problems", []) if str(p).strip()]
    return [VISUAL_PREFIX + p for p in problems[:6]], result.cost_usd


def blocking(problems: list[str]) -> list[str]:
    """Problems that stop a simulation from being shown (visual-review notes are only warnings)."""
    return [p for p in problems if not p.startswith(VISUAL_PREFIX)]


def node_syntax_error(code: str) -> str | None:
    """`node --check` on the sketch: parses it WITHOUT running it. None = fine (or Node not installed)."""
    node = shutil.which("node")
    if node is None:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "sketch.js"
        path.write_text(code, encoding="utf-8")
        try:
            done = subprocess.run([node, "--check", str(path)], capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            return "syntax check timed out"
    if done.returncode == 0:
        return None
    lines = [line for line in (done.stderr or "").splitlines() if line.strip()]
    detail = next((line for line in lines if "Error" in line), lines[-1] if lines else "unknown")
    location = next((line for line in lines if "sketch.js:" in line), "")
    return f"{detail.strip()} {location.split('sketch.js')[-1]}".strip()


def generate_simulation(router: LLMRouter, brief: str, facts: str, instruction: str = "") -> SimulationResult:
    """Ask the model for a sketch; send any problems back to it up to MAX_FIX_ROUNDS times."""
    user = f"Simulation to build:\n{brief}\n\nTextbook facts (the simulation must agree with these):\n{facts}"
    if instruction:
        user += f"\n\nTeacher's extra instruction: {instruction}"
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]
    total_cost, model_ref, code, problems = 0.0, None, "", []
    for round_no in range(MAX_FIX_ROUNDS + 1):
        result = router.complete(SIM_TASK, messages)
        total_cost += result.cost_usd
        model_ref = result.model_ref
        code = strip_fences(result.text)
        problems = check_sketch(code, require_labkit=True)
        if not problems:
            report = check_runtime(code)
            problems = report.problems
            if not problems:
                problems, cost = review_visually(router, report.shots, brief, facts)
                total_cost += cost
        if not problems:
            return SimulationResult(code, True, [], round_no, model_ref, total_cost)
        messages += [
            {"role": "assistant", "content": code},
            {
                "role": "user",
                "content": "The code was rejected:\n- "
                + "\n- ".join(problems)
                + "\nReturn the complete corrected JavaScript only.",
            },
        ]
    # Only visual-review notes left → the simulation works; it is shown with the notes for the teacher to judge.
    return SimulationResult(code, not blocking(problems), problems, MAX_FIX_ROUNDS, model_ref, total_cost)
