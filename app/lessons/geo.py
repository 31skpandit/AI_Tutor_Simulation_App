"""Places on a map of India — offline, from checked data, never guessed.

Data (assets/geo/, built by scripts/build_geo.py, SHA-256 in manifest.json):
  • south_asia.json — outlines of India and its neighbours from Natural Earth 1:10m, India point-of-view edition
    (public domain), i.e. India's boundaries as India officially depicts them;
  • in_places.tsv.gz — 562 753 places in India from GeoNames (CC BY 4.0: credit "GeoNames").
On first use the places are copied into a small SQLite index (data/geo_places.db) so look-ups are instant.

A name is placed only when the choice is clear (measured on the owner's history chapter: India has many villages
called Durgapur and four places called Sindri):
  1. a hint ("Jharkhand", old names like "Bihar"/"Bombay", or a city such as "Chennai" for Perambur) narrows the
     candidates to that state / within 40 km of that city;
  2. otherwise the largest place wins only if it is clearly larger (10×) than any other place of that name;
  3. a name used by exactly one place is placed;
  4. 'Bhakra-Nangal' style names are tried part by part;
  5. anything else is NOT placed and the reason is shown, so the teacher can add a hint.
"""

import gzip
import hashlib
import json
import math
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.core.config import PROJECT_ROOT, get_settings

GEO = PROJECT_ROOT / "assets" / "geo"
CREDIT = "Map: Natural Earth (public domain, India's official boundaries) · Places: GeoNames (CC BY 4.0)"

# Old or alternative state names used in history textbooks → today's GeoNames admin1 codes.
STATE_ALIASES = {
    "bihar": ["34", "38"], "madhya pradesh": ["35", "37"], "uttar pradesh": ["36", "39"],
    "andhra pradesh": ["02", "40"], "bombay": ["16", "09"], "bombay state": ["16", "09"], "madras": ["25"],
    "madras state": ["25"], "orissa": ["21"], "mysore": ["19"], "punjab": ["23", "10", "11"], "east punjab": ["23", "10", "11"],
    "jammu and kashmir": ["12", "41"], "kashmir": ["12", "41"], "pondicherry": ["22"], "uttaranchal": ["39"],
    "travancore": ["13"], "hyderabad state": ["40", "02"], "assam": ["03", "18", "20", "31", "30"],
}  # fmt: skip
MAX_HINT_KM = 40


class GeoDataError(RuntimeError):
    pass


@dataclass(frozen=True)
class Place:
    name: str  # as written in the lesson
    found: str  # name in the gazetteer
    lat: float
    lon: float
    state: str
    how: str  # how the choice was made (shown to the teacher)


def normalise(text: str) -> str:
    """'Vishākhapatnam ' → 'vishakhapatnam'; punctuation removed, 'the' dropped."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"[^a-z0-9\- ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"^the ", "", text)


def _check(name: str) -> Path:
    manifest = json.loads((GEO / "manifest.json").read_text(encoding="utf-8"))
    path = GEO / name
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != manifest["sha256"][name]:
        raise GeoDataError(
            f"assets/geo/{name} is missing or modified (SHA-256 mismatch) — run scripts/build_geo.py"
        )
    return path


@lru_cache(maxsize=1)
def outlines() -> dict:
    return json.loads(_check("south_asia.json").read_text(encoding="utf-8"))


def states() -> dict[str, str]:
    return outlines()["states"]


def _db_path() -> Path:
    return get_settings().data_dir / "geo_places.db"


@lru_cache(maxsize=1)
def _connection() -> sqlite3.Connection:
    """Open (and build on first use, ~20 s) the place index; rebuilt automatically if the data file changes."""
    source = _check("in_places.tsv.gz")
    version = json.loads((GEO / "manifest.json").read_text(encoding="utf-8"))["sha256"]["in_places.tsv.gz"]
    path = _db_path()
    if path.exists():
        con = sqlite3.connect(path, check_same_thread=False)
        try:
            if con.execute("SELECT value FROM meta WHERE key='version'").fetchone() == (version,):
                return con
        except sqlite3.DatabaseError:
            pass
        con.close()
        path.unlink()
    tmp = path.with_suffix(".building")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.executescript(
        "CREATE TABLE place(id INTEGER PRIMARY KEY, name TEXT, lat REAL, lon REAL, code TEXT, admin1 TEXT, pop INTEGER);"
        "CREATE TABLE alias(key TEXT, id INTEGER); CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);"
    )
    with gzip.open(source, "rt", encoding="utf-8") as handle:
        next(handle)  # header
        places, aliases = [], []
        for pid, line in enumerate(handle, start=1):
            name, alternates, lat, lon, code, admin1, pop = line.rstrip("\n").split("\t")
            places.append((pid, name, float(lat), float(lon), code, admin1, int(pop)))
            keys = {normalise(name)} | {normalise(a) for a in alternates.split(";") if a}
            aliases += [(k, pid) for k in keys if k]
    con.executemany("INSERT INTO place VALUES (?,?,?,?,?,?,?)", places)
    con.executemany("INSERT INTO alias VALUES (?,?)", aliases)
    con.execute("CREATE INDEX alias_key ON alias(key)")
    con.execute("INSERT INTO meta VALUES ('version', ?)", (version,))
    con.commit()
    con.close()
    tmp.replace(path)
    return sqlite3.connect(path, check_same_thread=False)


def _candidates(key: str) -> list[tuple]:
    """Places whose name (or alternate spelling) is `key`. Places whose MAIN name matches win over places that only
    list it as an alternate (measured: 'Visakhapatnam' is also an alternate of Rasapudipalem, which has a larger
    population; 'Dadar' is an alternate of Davrapada)."""
    rows = (
        _connection()
        .execute(
            "SELECT DISTINCT p.id, p.name, p.lat, p.lon, p.code, p.admin1, p.pop FROM alias a JOIN place p ON p.id = a.id "
            "WHERE a.key = ? AND p.code NOT IN ('H.STM')",
            (key,),
        )
        .fetchall()
    )
    main = [r for r in rows if normalise(r[1]) == key]
    return main or rows


def _similar(key: str) -> list[tuple]:
    """Spelling variants ('Vishakhapattanam' → 'Vishakhapatnam'): same first 3 letters, similar length, ≥ 0.8 alike."""
    from difflib import SequenceMatcher

    keys = (
        _connection()
        .execute(
            "SELECT DISTINCT key FROM alias WHERE key >= ? AND key < ? AND length(key) BETWEEN ? AND ?",
            (key[:3], key[:3] + "￿", len(key) - 3, len(key) + 3),
        )
        .fetchall()
    )
    close = [k for (k,) in keys if SequenceMatcher(None, key, k).ratio() >= 0.8]
    return [r for k in close for r in _candidates(k)]


def _km(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def _dominant(rows: list[tuple]) -> tuple | None:
    """The clearly most important place: a capital, or ≥ 10× the population of every other candidate."""
    capitals = [r for r in rows if r[4] in ("P.PPLC", "P.PPLA")]
    if len(capitals) == 1:
        return capitals[0]
    ranked = sorted(rows, key=lambda r: -r[6])
    if ranked and ranked[0][6] >= 5000 and (len(ranked) == 1 or ranked[0][6] >= 10 * max(ranked[1][6], 1)):
        return ranked[0]
    return None


def _important(row: tuple) -> bool:
    """A town, city, capital or landmark (dam, fort …) — not an unnamed-size village or a part of some city."""
    return row[6] >= 5000 or row[4] in ("P.PPLC", "P.PPLA", "P.PPLA2", "P.PPLA3") or row[4].startswith("S.")


def _state_codes(hint: str) -> list[str]:
    key = normalise(hint)
    if key in STATE_ALIASES:
        return STATE_ALIASES[key]
    return [code for code, name in states().items() if normalise(name) == key]


def geocode(name: str, hint: str = "") -> tuple[Place | None, str]:
    """(Place, '') or (None, reason). `hint` = state (also old names) or a city the place is in/near."""
    key = normalise(re.sub(r"\(.*?\)", "", name))
    inner = re.findall(r"\((.*?)\)", name)  # 'Perambur (Chennai)' → hint 'Chennai'
    hint = hint or (inner[0] if inner else "")
    if not key:
        return None, "empty name"
    how = ""
    state_only = False
    codes = _state_codes(hint) if hint else []
    centre = geocode(hint)[0] if hint and not codes else None

    def narrow(rows: list[tuple]) -> list[tuple]:
        if codes:
            return [r for r in rows if r[5] in codes]
        if hint:
            return [r for r in rows if centre and _km((r[2], r[3]), (centre.lat, centre.lon)) <= MAX_HINT_KM]
        return rows

    rows, fuzzy = narrow(_candidates(key)), False
    if not rows and len(key) >= 5:  # 'Paral' near Mumbai → Parel (other 'Paral' villages are far away)
        rows, fuzzy = narrow(_similar(key)), True
    if hint:
        how, state_only = (f"in {hint}", True) if codes else (f"near {hint}", False)
        if not rows and not _candidates(key) and not _similar(key):
            rows = []  # nothing anywhere: the name-part rule below may still help ('Bhakra-Nangal')
        elif not rows:
            return None, f"no place called '{name}' found {how} — check the spelling or the hint"
    chosen = rows[0] if len(rows) == 1 else _dominant(rows)
    if chosen is None and len(rows) > 1:
        # several entries close together are one place (a town and its railway station …)
        if max(_km((a[2], a[3]), (b[2], b[3])) for a in rows for b in rows) <= 15:
            chosen = max(rows, key=lambda r: (r[6], r[4].startswith("P.")))
    # Measured in the end-to-end test on the owner's chapter: with only a STATE as hint, 'Shivdi' (a Mumbai mill
    # area) was spelling-matched to Shirdi, and 'Paral'/'Damodar' went to unrelated villages of that name.
    if fuzzy and chosen is not None and (state_only or not hint) and chosen[6] < 100_000:
        chosen = (
            None  # a spelling guess is trusted only near a named city, or for a big city (Vishakhapattanam)
        )
    if state_only and chosen is not None and not _important(chosen):
        return None, (
            f"only small places called '{name}' in {hint} — if it is part of a city or near one, give that city "
            "as the hint (e.g. 'Mumbai')"
        )
    if chosen is not None and fuzzy:
        how = (how + "; " if how else "") + f"spelling matched '{chosen[1]}'"
    if chosen is not None:
        why = how or ("only place with this name" if len(rows) == 1 else "the main place with this name")
        state = states().get(chosen[5], "")
        return Place(name, chosen[1], chosen[2], chosen[3], state, why), ""
    if not rows:
        for part in re.split(r"\s*[-/,]\s*|\s+and\s+", name):
            if part and normalise(part) != key:
                place, _ = geocode(part, hint)
                if place:
                    return Place(
                        name, place.found, place.lat, place.lon, place.state, f"shown at {place.found}"
                    ), ""
        return None, "not found in the place list (it may be a river, region or building)"
    if fuzzy:
        return (
            None,
            "no exact match; several places have similar names — check the spelling or add a nearby city",
        )
    return None, f"{len(rows)} places in India have this name — add the state or nearby city as a hint"


# ---------------------------------------------------------------- drawing coordinates


INDIA_VIEW = (66.5, 5.5, 98.5, 37.5)  # lon/lat box shown for maps of India
REF_LAT = math.radians(22.0)


def project(lat: float, lon: float, view=INDIA_VIEW, width: float = 1000.0) -> tuple[float, float]:
    """Equirectangular projection centred on India (good enough for a classroom map)."""
    lon0, lat0, lon1, lat1 = view
    scale = width / ((lon1 - lon0) * math.cos(REF_LAT))
    return round((lon - lon0) * math.cos(REF_LAT) * scale, 1), round((lat1 - lat) * scale, 1)


def map_size(view=INDIA_VIEW, width: float = 1000.0) -> tuple[float, float]:
    lon0, lat0, lon1, lat1 = view
    scale = width / ((lon1 - lon0) * math.cos(REF_LAT))
    return width, round((lat1 - lat0) * scale, 1)


def outline_paths(view=INDIA_VIEW, width: float = 1000.0) -> dict[str, dict]:
    """SVG path strings for India and its neighbours within the view."""
    out = {}
    for code, country in outlines()["countries"].items():
        paths = []
        for ring in country["rings"]:
            pts = [project(lat, lon, view, width) for lon, lat in ring]
            paths.append("M" + "L".join(f"{x},{y}" for x, y in pts) + "Z")
        out[code] = {"name": country["name"], "path": " ".join(paths)}
    return out
