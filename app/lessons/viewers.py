"""Self-contained HTML for the 3D molecule viewer and the simulations (shown in a sandboxed frame).

Security:
- The browser libraries are local copies whose SHA-256 must match assets/vendor/manifest.json.
- Every page carries a Content-Security-Policy that forbids ALL network access (no fetch, no external
  scripts, images or fonts): an AI-written simulation can draw and animate, nothing else.
"""

import hashlib
import json
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


def molecule_html(molblock: str, label: str, height: int = 360) -> str:
    viewer = (
        "const el=document.getElementById('mol');"
        "const v=$3Dmol.createViewer(el,{backgroundColor:'white'});"
        f"v.addModel({json.dumps(molblock)},'sdf');"
        "v.setStyle({},{stick:{radius:0.18},sphere:{scale:0.28}});"
        "v.zoomTo();v.render();v.spin('y',0.6);"
    )
    body = (
        f"<div id='mol' style='width:100%;height:{height - 30}px;position:relative'></div>"
        f"<div style='text-align:center;font-size:15px'>{_escape(label)} — drag to rotate, scroll to zoom</div>"
    )
    return _page(body, [vendor_js("3Dmol-min.js"), viewer])


def simulation_html(sketch_js: str) -> str:
    """Wrap a p5.js (global mode) sketch into a page; controls are placed under the canvas by the sketch."""
    return _page("<main id='sim'></main>", [vendor_js("p5.min.js"), sketch_js])


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
