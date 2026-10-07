"""Run a simulation in a real browser before the teacher sees it.

`node --check` only proves the code can be *read*; it cannot see mistakes that appear when the code *runs*
(found by the teacher: `createSelect().option('a').option('b')` passes the syntax check but crashes in p5.js 2,
because option() no longer returns the element). This module opens the exact sealed page the app shows in a
hidden (headless) Microsoft Edge or Google Chrome — both are normal Windows programs, nothing is installed —
then presses every button, picks every choice in every list, moves every slider and ticks every box, and reports:
  - errors when the simulation starts or after any control;
  - controls that change nothing on screen (every control must start a visible animation).
It can also save a screenshot (used for the visual checks in tests and the docs).

The page keeps its no-network security policy; the browser runs with a throw-away profile folder.
"""

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import get_settings

_CANDIDATES = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)
RESULT_ID = "__ats_check_result"

# Presses every control and watches the canvas. Runs inside the sealed page (inline script, no network).
EXERCISE_JS = r"""
(async () => {
  const R = { ready: false, start_error: null, errors: [], controls: [], shots: [] };
  const snap = (label) => {
    const c = document.querySelector('canvas');
    // at most 13 pictures: the start + DURING and AFTER for up to 6 controls
    if (c && R.shots.length < 13) {
      try { R.shots.push({ label, png: c.toDataURL('image/png') }); } catch (e) {}
    }
  };
  window.addEventListener('error', (e) => R.errors.push(String(e.message || e)));
  window.addEventListener('unhandledrejection', (e) => R.errors.push(String((e.reason && e.reason.message) || e.reason)));
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const labError = () => (typeof LAB !== 'undefined' && LAB.error) ? String(LAB.error.message || LAB.error) : null;
  // A hidden browser draws NO frames by itself (measured: 0 per second), so frames are drawn here at the speed of a
  // real screen (~60 per second); otherwise changes made a little on every frame would look frozen.
  const frame = async () => {
    try { if (typeof redraw === 'function') await redraw(); } catch (e) { R.errors.push(String(e.message || e)); }
    await wait(16);
  };
  const play = async (ms) => {
    const end = performance.now() + ms;
    while (performance.now() < end) await frame();
  };
  const signature = () => {
    const c = document.querySelector('canvas');
    if (!c) return 'none';
    try {
      const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
      let h = 0;
      for (let i = 0; i < d.length; i += 41) h = (h * 31 + d[i]) | 0;
      return h;
    } catch (e) { return 'unreadable'; }
  };
  const press = (el) => {
    for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup']) {
      el.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }));
    }
    el.click();
  };
  const fire = (el) => { el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); };
  try {
    for (let i = 0; i < 100 && !document.querySelector('canvas'); i++) await wait(50);
    R.ready = !!document.querySelector('canvas');
    await play(500);
    R.start_error = labError();
    snap('at the start');
    const actions = [];
    for (const el of document.querySelectorAll('button, select, input')) {
      if (el.tagName === 'BUTTON') {
        actions.push({ name: 'button "' + el.textContent.trim() + '"', run: () => press(el) });
      } else if (el.tagName === 'SELECT') {
        const values = [...el.options].map((o) => o.value);
        for (const v of values.slice(1).concat(values.slice(0, 1))) {
          actions.push({ name: 'list choice "' + v + '"', run: () => { el.value = v; fire(el); } });
        }
      } else if (el.type === 'range') {
        const lo = Number(el.min || 0), hi = Number(el.max || 100);
        actions.push({ name: 'slider (to maximum)', run: () => { el.value = String(hi); fire(el); } });
        actions.push({ name: 'slider (to minimum)', run: () => { el.value = String(lo); fire(el); } });
      } else if (el.type === 'checkbox' || el.type === 'radio') {
        const text = (el.closest('label') || el.parentElement || el).textContent.trim();
        actions.push({ name: el.type + ' "' + text + '"', run: () => el.click() });
      }
    }
    for (const action of actions.slice(0, 24)) {
      await frame();
      const before = signature();
      const known = labError();
      let changed = false;
      try { action.run(); } catch (e) { R.errors.push(String(e.message || e)); }
      for (let k = 0; k < 13; k++) {  // 3.25 s: animations last 1–3 s
        await play(250);
        if (signature() !== before) changed = true;
        if (k === 2) snap('DURING the ' + action.name + ' (0.75 s after it was used, animation running)');
      }
      snap('AFTER the ' + action.name + ' (3 s later, animation finished)');
      const now = labError();
      R.controls.push({ control: action.name, changed, error: now && now !== known ? now : null });
    }
  } catch (e) {
    R.errors.push('checker: ' + String(e.message || e));
  }
  const out = document.createElement('pre');
  out.id = '__RESULT_ID__';
  out.textContent = JSON.stringify(R);
  document.body.appendChild(out);
})();
""".replace("__RESULT_ID__", RESULT_ID)


@dataclass
class BrowserReport:
    checked: bool  # False = no browser available (nothing was tested)
    problems: list[str] = field(default_factory=list)
    controls: list[dict] = field(default_factory=list)
    note: str = ""
    # Pictures of the drawing area: [(what was happening, "data:image/png;base64,…")] for the visual review.
    shots: list[tuple[str, str]] = field(default_factory=list)


def find_browser() -> str | None:
    configured = get_settings().browser_path
    if configured and Path(configured).is_file():
        return str(configured)
    for path in _CANDIDATES:
        if Path(path).is_file():
            return path
    return shutil.which("msedge") or shutil.which("chrome")


def _inject(html: str, script: str) -> str:
    cut = html.rfind("</body>")  # the LAST one: library code may contain the text "</body>"
    return html[:cut] + f"<script>{script}</script>" + html[cut:]


def _run(browser: str, html: str, extra_args: list[str], timeout: int = 180) -> str:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        page = Path(tmp) / "page.html"
        page.write_text(html, encoding="utf-8")
        args = [
            browser,
            "--headless=new",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-sync",
            "--mute-audio",
            "--hide-scrollbars",
            "--use-angle=swiftshader",  # software 3D (WebGL) so the 3D viewers also render headless
            "--enable-unsafe-swiftshader",
            f"--user-data-dir={Path(tmp) / 'profile'}",
            *extra_args,
            page.as_uri(),
        ]
        done = subprocess.run(
            args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout
        )
        return done.stdout


def check_in_browser(html: str) -> BrowserReport:
    """Exercise every control of a simulation page; problems are written for the AI (and the teacher)."""
    if not get_settings().browser_check:
        return BrowserReport(False, note="browser check switched off (ATS_BROWSER_CHECK=false)")
    browser = find_browser()
    if browser is None:
        return BrowserReport(False, note="no Edge/Chrome found — run-time check skipped")
    try:
        dom = _run(browser, _inject(html, EXERCISE_JS), ["--virtual-time-budget=120000", "--dump-dom"])
    except (OSError, subprocess.TimeoutExpired) as exc:
        return BrowserReport(False, note=f"browser check could not run: {exc}")
    start = dom.find(f'id="{RESULT_ID}">')
    if start < 0:
        return BrowserReport(
            True, ["the simulation page did not finish loading (it may hang or loop forever)"]
        )
    raw = dom[start + len(RESULT_ID) + 6 : dom.find("</pre>", start)]
    raw = raw.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&amp;", "&")
    result = json.loads(raw)
    shots = [
        (s["label"], s["png"])
        for s in result.get("shots", [])
        if str(s.get("png", "")).startswith("data:image/png")
    ]
    return BrowserReport(True, _problems(result), result.get("controls", []), shots=shots)


def _problems(result: dict) -> list[str]:
    problems = []
    if not result.get("ready"):
        problems.append("the simulation did not start (no drawing area appeared)")
    if result.get("start_error"):
        problems.append(f"error when the simulation starts: {result['start_error']}")
    for error in dict.fromkeys(result.get("errors", [])):  # unique, in order
        problems.append(f"error while running: {error}")
    silent = []
    for item in result.get("controls", []):
        if item.get("error"):
            problems.append(f"using the {item['control']} caused an error: {item['error']}")
        elif not item.get("changed"):
            silent.append(item["control"])
    if silent:
        problems.append(
            "these controls changed nothing on screen: "
            + ", ".join(silent)
            + " — every control must start a visible animation and/or change the readings"
        )
    return problems


def screenshot(html: str, path: Path, width: int = 920, height: int = 640, wait_ms: int = 4000) -> bool:
    """Save a picture of the page after `wait_ms` (virtual time). True if the file was written."""
    browser = find_browser()
    if browser is None:
        return False
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        _run(
            browser,
            html,
            [f"--virtual-time-budget={wait_ms}", f"--window-size={width},{height}", f"--screenshot={path}"],
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return path.is_file()
