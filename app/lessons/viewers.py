"""Self-contained HTML for the 3D molecule viewer and the simulations (shown in a sandboxed frame).

Security:
- The browser libraries are local copies whose SHA-256 must match assets/vendor/manifest.json.
- Every page carries a Content-Security-Policy that forbids ALL network access (no fetch, no external
  scripts, images or fonts): an AI-written simulation can draw and animate, nothing else.
"""

import hashlib
import json
import re
from functools import lru_cache

from app.core.config import PROJECT_ROOT

VENDOR = PROJECT_ROOT / "assets" / "vendor"
CSP = (
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
    "img-src data: blob:; font-src data:; connect-src 'none'; worker-src blob:"
)


class VendorFileError(RuntimeError):
    pass


@lru_cache(maxsize=4)
def vendor_js(filename: str) -> str:
    """Return a vendored library after checking its SHA-256 against the manifest."""
    manifest = json.loads((VENDOR / "manifest.json").read_text(encoding="utf-8"))
    expected = manifest["sha256"].get(filename)
    path = VENDOR / filename
    if not expected or not path.is_file():
        raise VendorFileError(f"{filename} is missing from assets/vendor")
    data = path.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise VendorFileError(f"{filename} has been modified (SHA-256 mismatch) — refusing to use it")
    return data.decode("utf-8")


def _page(body: str, scripts: list[str], extra_head: str = "") -> str:
    inline = "\n".join(f"<script>{s}</script>" for s in scripts)
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<meta http-equiv='Content-Security-Policy' content=\"{CSP}\">"
        "<style>body{margin:0;font-family:Segoe UI,Arial,sans-serif;background:#fff;color:#1f2937}"
        "button,select,input{font-size:15px;margin:4px 6px 4px 0;padding:4px 10px}</style>"
        f"{extra_head}</head><body>{body}{inline}</body></html>"
    )


def molecule_html(
    molblock: str, atom_labels=(), ion_labels=(), height: int = 360, show_atom_labels: bool = True
) -> str:
    """Rotatable 3D model. Atom labels: symbol + charge on each atom (e.g. 'Cu²⁺', 'O⁻');
    ion labels: formula + charge above each separate ion (e.g. 'SO₄²⁻'). The caption is shown by the page,
    outside this frame, so it can never be cut off."""
    atoms = [{"t": a.text, "x": a.x, "y": a.y, "z": a.z} for a in atom_labels] if show_atom_labels else []
    ions = [{"t": a.text, "x": a.x, "y": a.y, "z": a.z} for a in ion_labels]
    viewer = (
        "const el=document.getElementById('mol');"
        "const v=$3Dmol.createViewer(el,{backgroundColor:'white'});"
        f"v.addModel({json.dumps(molblock)},'sdf');"
        "v.setStyle({},{stick:{radius:0.16},sphere:{scale:0.3}});"
        f"for(const a of {json.dumps(atoms, ensure_ascii=False)}){{v.addLabel(a.t,{{position:{{x:a.x,y:a.y,z:a.z}},"
        "fontSize:15,fontColor:'#111827',backgroundColor:'#ffffff',backgroundOpacity:0.8,borderThickness:0,"
        "inFront:true,alignment:'center'});}"
        f"for(const a of {json.dumps(ions, ensure_ascii=False)}){{v.addLabel(a.t,{{position:{{x:a.x,y:a.y,z:a.z}},"
        "fontSize:20,fontColor:'#1e3a8a',backgroundColor:'#dbeafe',backgroundOpacity:0.95,borderThickness:1,"
        "borderColor:'#1e3a8a',inFront:true,alignment:'center'});}"
        "v.zoomTo();v.zoom(0.9);v.render();"
    )
    body = f"<div id='mol' style='width:100%;height:{height}px;position:relative'></div>"
    return _page(body, [vendor_js("3Dmol-min.js"), viewer])


LABKIT = PROJECT_ROOT / "assets" / "labkit.js"


def uses_labkit(sketch_js: str) -> bool:
    return bool(re.search(r"\b(const|let|var)\s+SIM\s*=", sketch_js))


def simulation_html(sketch_js: str) -> str:
    """Wrap a sketch into a sealed page.

    New sketches define `SIM` and run inside the lab kit (fixed layout, labels that never overlap,
    animation timers). Older sketches with their own setup()/draw() still run as before.
    """
    scripts = [vendor_js("p5.min.js")]
    if uses_labkit(sketch_js):
        scripts.append(LABKIT.read_text(encoding="utf-8"))
    scripts.append(sketch_js)
    return _page("<main id='sim'></main>", scripts)


CHEM3D = PROJECT_ROOT / "assets" / "chem3d.js"

_CHEM3D_STYLE = """<style>
#wrap{display:flex;flex-direction:column;gap:6px;padding:4px 6px}
#title{font-weight:700;font-size:18px}
#c3d{width:100%;border:1px solid #e5e7eb;border-radius:10px;background:radial-gradient(circle at 50% 40%,#ffffff,#eef2f7);
  cursor:grab;touch-action:none}
#caption{min-height:48px;line-height:1.45;background:#f8fafc;border-left:4px solid #2563eb;padding:6px 10px;border-radius:6px}
#stepname{color:#1e3a8a}
#bar{display:flex;flex-wrap:wrap;align-items:center;gap:4px}
#bar button,#bar select{font-size:14px;margin:0;padding:4px 10px;border-radius:6px;border:1px solid #cbd5e1;background:#fff;cursor:pointer}
#bar button:disabled{opacity:.45;cursor:default}
#bar label{font-size:14px;margin-left:6px}
#dots{display:inline-flex;gap:3px;margin-left:8px}
.dot{min-width:28px}.dot.on{background:#1e3a8a!important;color:#fff;border-color:#1e3a8a!important}
#legend{display:flex;flex-wrap:wrap;gap:14px;font-size:14px;color:#334155}
#legend i{display:inline-block;width:12px;height:12px;border-radius:50%;margin-right:5px;vertical-align:-1px;
  box-shadow:inset -2px -2px 3px rgba(0,0,0,.25)}
#legend i.ball{width:14px;height:14px}
#hint{font-size:12px;color:#64748b}
</style>"""


def chem3d_html(scene: dict, height: int = 560, start_step: int = 0, big: bool = False) -> str:
    """Self-contained 3D chemistry player for a scene from app/lessons/reactions.py (same no-network policy)."""
    canvas_h = max(260, height - 200)
    caption_size = 21 if big else 16
    body = (
        "<div id='wrap'><div id='title'></div>"
        f"<canvas id='c3d' style='height:{canvas_h}px'></canvas>"
        f"<div id='caption' style='font-size:{caption_size}px'><b id='stepname'></b><span id='steptext'></span></div>"
        "<div id='bar'><button id='restart' title='Back to the start'>⏮</button>"
        "<button id='back'>◀ Back</button><button id='play'>▶ Play</button><button id='next'>Next ▶</button>"
        "<select id='speed' title='Speed'><option value='0.5'>Slow</option><option value='1' selected>Normal</option>"
        "<option value='1.6'>Fast</option></select>"
        "<label><input type='checkbox' id='shells' checked> Shells</label>"
        "<label><input type='checkbox' id='turn'> Turn slowly</label>"
        "<button id='reset' title='Reset the view'>↺ View</button><span id='dots'></span></div>"
        "<div id='legend'></div><div id='hint'>Drag the picture to turn it · scroll to zoom · keys: ← → and Space</div>"
        "</div>"
    )
    data = json.dumps(scene, ensure_ascii=False).replace("</", "<\\/")
    setup = f"window.CHEM3D_SCENE={data};window.CHEM3D_START={int(start_step)};"
    return _page(body, [setup, CHEM3D.read_text(encoding="utf-8")], _CHEM3D_STYLE)


HISTORYKIT = PROJECT_ROOT / "assets" / "historykit.js"

_HISTORY_STYLE = """<style>
#wrap{display:flex;flex-direction:column;gap:6px;padding:4px 6px}
#title{font-weight:700;font-size:18px}
#hk{width:100%;border:1px solid #e5e7eb;border-radius:10px;background:#fff}
#hk .event,#hk .place,#hk .period,#hk g{transition:opacity .45s}
#caption{min-height:44px;line-height:1.45;background:#f8fafc;border-left:4px solid #b45309;padding:6px 10px;border-radius:6px}
#stepname{color:#7c2d12}
#bar{display:flex;flex-wrap:wrap;align-items:center;gap:4px}
#bar button,#bar select{font-size:14px;margin:0;padding:4px 10px;border-radius:6px;border:1px solid #cbd5e1;background:#fff;cursor:pointer}
#bar button:disabled{opacity:.45;cursor:default}
#note{font-size:12px;color:#64748b}
</style>"""


def history_html(scene: dict, height: int = 600, start_step: int = 0, big: bool = False) -> str:
    """Timeline / map / cause-and-effect player for a scene from app/lessons/history.py (no-network page)."""
    svg_h = max(240, height - 170)
    note = scene.get("credit", "")
    body = (
        "<div id='wrap'><div id='title'></div>"
        f"<svg id='hk' style='height:{svg_h}px' preserveAspectRatio='xMidYMid meet'></svg>"
        f"<div id='caption' style='font-size:{21 if big else 16}px'><b id='stepname'></b><span id='steptext'></span></div>"
        "<div id='bar'><button id='restart' title='Back to the start'>⏮</button><button id='back'>◀ Back</button>"
        "<button id='play'>▶ Play</button><button id='next'>Next ▶</button><button id='all' title='Show everything'>⏭ All</button>"
        "<select id='speed' title='Speed'><option value='0.6'>Slow</option><option value='1' selected>Normal</option>"
        "<option value='1.6'>Fast</option></select></div>"
        f"<div id='note'>{_escape(note)} · keys: ← → and Space</div></div>"
    )
    data = json.dumps(scene, ensure_ascii=False).replace("</", "<\\/")
    setup = f"window.HK_SCENE={data};window.HK_START={int(start_step)};"
    return _page(body, [setup, HISTORYKIT.read_text(encoding="utf-8")], _HISTORY_STYLE)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def vendor_status() -> dict[str, str]:
    """For the Home page / startup check: 'ok' or the problem, per vendored file."""
    result = {}
    for name in ("p5.min.js", "3Dmol-min.js"):
        try:
            vendor_js(name)
            result[name] = "ok"
        except (VendorFileError, OSError, KeyError, json.JSONDecodeError) as exc:
            result[name] = str(exc)
    return result
