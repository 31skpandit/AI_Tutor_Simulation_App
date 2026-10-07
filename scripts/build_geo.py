"""Build the offline map data in assets/geo/ from two free, downloaded sources (run once; the app never downloads).

Sources (download, then pass the folder):
  • Natural Earth 1:10m Admin-0 countries, India point of view (public domain):
      https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_0_countries_ind.geojson
    India's boundaries as India officially depicts them (Natural Earth "point-of-view" edition).
  • GeoNames India gazetteer IN.zip (unzipped IN.txt) + admin1CodesASCII.txt (CC BY 4.0, credit "GeoNames"):
      https://download.geonames.org/export/dump/IN.zip
      https://download.geonames.org/export/dump/admin1CodesASCII.txt

Usage:   uv run python scripts/build_geo.py <folder with the three files>
Writes:  assets/geo/south_asia.json (simplified outlines), assets/geo/in_places.tsv.gz (places),
         assets/geo/manifest.json (sources, licences, SHA-256 of inputs and outputs).
"""

import gzip
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "geo"
COUNTRIES = {"IND", "PAK", "CHN", "NPL", "BTN", "BGD", "MMR", "LKA", "AFG"}  # India + neighbours for context
BBOX = (60.0, 4.0, 100.0, 39.0)  # lon_min, lat_min, lon_max, lat_max
TOLERANCE = 0.03  # degrees (~3 km): plenty for a classroom map of India
KEEP_S = {"DAM", "PRT", "MNMT", "FT", "RUIN", "HSTS", "CSTL", "PAL", "TMPL", "MSQE", "CH", "UNIV", "MFG"}
KEEP_OTHER = {("L", "AREA"), ("H", "RSV"), ("H", "LK"), ("T", "PASS"), ("T", "PK"), ("T", "MT")}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def simplify(points: list[list[float]], tol: float) -> list[list[float]]:
    """Douglas–Peucker line simplification (iterative)."""
    if len(points) < 4:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        (x1, y1), (x2, y2) = points[a], points[b]
        dx, dy = x2 - x1, y2 - y1
        norm = (dx * dx + dy * dy) ** 0.5 or 1e-12
        best, index = 0.0, -1
        for i in range(a + 1, b):
            x0, y0 = points[i]
            d = abs(dy * x0 - dx * y0 + x2 * y1 - y2 * x1) / norm
            if d > best:
                best, index = d, i
        if best > tol and index > 0:
            keep[index] = True
            stack += [(a, index), (index, b)]
    return [p for p, k in zip(points, keep, strict=True) if k]


def build_outlines(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, list] = {}
    for feature in data["features"]:
        code = feature["properties"].get("ADM0_A3") or feature["properties"].get("ISO_A3")
        if code not in COUNTRIES:
            continue
        geometry = feature["geometry"]
        polygons = (
            geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
        )
        rings = []
        for polygon in polygons:
            ring = polygon[0]  # outer ring only (no holes needed at this scale)
            xs, ys = [p[0] for p in ring], [p[1] for p in ring]
            if max(xs) < BBOX[0] or min(xs) > BBOX[2] or max(ys) < BBOX[1] or min(ys) > BBOX[3]:
                continue
            # A ring starts and ends at the same point, which makes Douglas–Peucker keep nothing (measured: 0 points).
            # Split it at the point farthest from the start and simplify both halves.
            pts = [[round(x, 4), round(y, 4)] for x, y in ring]
            far = max(
                range(len(pts)), key=lambda i: (pts[i][0] - pts[0][0]) ** 2 + (pts[i][1] - pts[0][1]) ** 2
            )
            small = simplify(pts[: far + 1], TOLERANCE)[:-1] + simplify(pts[far:], TOLERANCE)
            if len(small) >= 4:
                rings.append(small)
        out[code] = {
            "name": feature["properties"].get("NAME_EN") or feature["properties"].get("NAME"),
            "rings": rings,
        }
    return out


def build_places(path: Path) -> list[str]:
    rows = []
    for line in path.open(encoding="utf-8"):
        f = line.rstrip("\n").split("\t")
        cls, code, population = f[6], f[7], int(f[14] or 0)
        keep = (cls == "P" and code != "PPLQ") or (cls == "S" and code in KEEP_S) or (cls, code) in KEEP_OTHER
        if not keep:
            continue
        important = population > 0 or code.startswith(("PPLA", "PPLC", "PPLX")) or cls != "P"
        alternates = ""
        if important:  # Latin-script alternate spellings only (Vishakhapatnam, Bombay …)
            seen = {f[1].lower(), f[2].lower()}
            alts = []
            for alt in f[3].split(","):
                if alt and alt.isascii() and alt.lower() not in seen and len(alt) <= 40:
                    seen.add(alt.lower())
                    alts.append(alt)
            alternates = ";".join(alts[:40])  # 12 was too few: 'Madras' and 'Plassey' were cut off (measured)
        name = f[2] if f[2] else f[1]
        if f[1] != name and f[1].lower() not in alternates.lower():
            alternates = ";".join(x for x in [f[1], alternates] if x)
        lat, lon = f"{float(f[4]):.4f}", f"{float(f[5]):.4f}"  # 4 decimals ≈ 11 m
        rows.append("\t".join([name, alternates, lat, lon, f"{cls}.{code}", f[10], str(population)]))
    return rows


def main(folder: str) -> None:
    src = Path(folder)
    ne, places_txt, admin1 = (
        src / "ne_10m_admin_0_countries_ind.geojson",
        src / "IN.txt",
        src / "admin1CodesASCII.txt",
    )
    OUT.mkdir(parents=True, exist_ok=True)
    outlines = build_outlines(ne)
    states = {}
    for line in admin1.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if parts[0].startswith("IN."):
            states[parts[0][3:]] = parts[1]
    (OUT / "south_asia.json").write_text(
        json.dumps({"countries": outlines, "states": states}, separators=(",", ":")), encoding="utf-8"
    )
    rows = build_places(places_txt)
    with gzip.open(OUT / "in_places.tsv.gz", "wt", encoding="utf-8", compresslevel=9) as handle:
        handle.write("name\talternates\tlat\tlon\tcode\tadmin1\tpopulation\n")
        handle.write("\n".join(rows) + "\n")
    manifest = {
        "built": date.today().isoformat(),
        "sources": {
            "south_asia.json": {
                "from": "Natural Earth 1:10m Admin-0 countries, India point of view (ne_10m_admin_0_countries_ind)",
                "url": "https://www.naturalearthdata.com/ (GitHub nvkelso/natural-earth-vector)",
                "licence": "Public domain",
                "input_sha256": sha256(ne),
            },
            "in_places.tsv.gz": {
                "from": "GeoNames India gazetteer (IN.zip) + admin1 codes",
                "url": "https://download.geonames.org/export/dump/",
                "licence": "CC BY 4.0 — credit: GeoNames (www.geonames.org)",
                "input_sha256": sha256(places_txt),
                "rows": len(rows),
            },
        },
        "sha256": {name: sha256(OUT / name) for name in ("south_asia.json", "in_places.tsv.gz")},
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(
        json.dumps({k: (OUT / k).stat().st_size for k in ("south_asia.json", "in_places.tsv.gz")}),
        len(rows),
        "places",
    )
    print({c: (v["name"], len(v["rings"]), sum(len(r) for r in v["rings"])) for c, v in outlines.items()})


if __name__ == "__main__":
    main(sys.argv[1])
