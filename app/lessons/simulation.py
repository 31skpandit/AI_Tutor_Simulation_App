"""AI-written interactive simulations (p5.js sketches) with automatic checks.

The model writes ONLY the sketch (JavaScript); we wrap it in a page whose security policy blocks all
network access (viewers.py). Before a sketch is accepted it must pass:
  1. safety rules — no network, storage, eval or access to the surrounding app;
  2. structure — defines setup() and draw(), creates a canvas, not too long;
  3. syntax — `node --check` (Node.js is installed) must accept it.
If a check fails, the problems are sent back to the model to fix (up to 2 times). The teacher then
previews the simulation in Lesson Studio before approving the lesson.
"""

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from app.llm.router import LLMRouter

SIM_TASK = "simulation_code"
MAX_FIX_ROUNDS = 2
MAX_CHARS = 30_000

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
}

SYSTEM_PROMPT = """You write small interactive science simulations for a school classroom, using p5.js version 2 in global mode.
Output ONLY JavaScript code — no HTML, no explanations, no Markdown fences.

Requirements:
- Define function setup() and function draw(). In setup() call createCanvas(860, 500).
- Add interactive controls with createButton / createSlider / createSelect / createCheckbox; they appear below the canvas.
  Every control must have a clear text label (e.g. createSpan('Drops of NaOH: ') before a slider).
- Draw clear labels on the canvas (textSize 15 or more) and show the important values (e.g. pH, volume, count of molecules).
- At the bottom of the canvas show one line "Observe: ..." telling students what to watch.
- The science must match the textbook facts given by the user exactly (formulas, colours, ratios, values). Do not invent facts.
- Write chemical formulas with Unicode subscripts (H₂O, H₂SO₄) and charges with superscripts (Na⁺, OH⁻).
- Keep it simple and smooth: at most about 250 lines, no external files, images, fonts or sounds,
  no fetch/network, no localStorage, no eval, no access to window.parent/top, no preload(), no load* functions.
- Use short comments in simple English so a teacher can follow the code."""


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


def check_sketch(code: str) -> list[str]:
    """All problems found in a sketch (empty list = accepted)."""
    problems = []
    if len(code) > MAX_CHARS:
        problems.append(f"too long ({len(code)} characters; limit {MAX_CHARS})")
    for pattern, reason in FORBIDDEN.items():
        if re.search(pattern, code, re.M):
            problems.append(f"not allowed: {reason}")
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
        problems = check_sketch(code)
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
    return SimulationResult(code, False, problems, MAX_FIX_ROUNDS, model_ref, total_cost)
