"""History (and similar social-science) lessons: timeline, periods, people, places, causes & effects.

The AI only EXTRACTS these from the reviewed textbook passages. Every item is then checked against the passage text
before it is shown (this file): a date whose numbers and month are not in the cited pages is removed, a person or
place whose name is not in the pages is removed, places are put on the map only by the offline place list
(app/lessons/geo.py). Removed items are listed for the teacher, so nothing invented reaches the students.
"""

import re

from app.lessons import geo

HISTORY_SUBJECTS = {"history", "civics", "political science", "economics", "social science", "social studies"}
GEOGRAPHY_SUBJECTS = {"geography"}


def profile(subject: str) -> str:
    """Which lesson design a subject gets: 'history' or 'science' (default; Phase 2 design)."""
    key = (subject or "").strip().lower()
    if key in HISTORY_SUBJECTS or key.startswith("history"):
        return "history"
    return "science"


SYSTEM_PROMPT = """You are an experienced {audience} teacher preparing a lesson for your own class.
Build the lesson ONLY from the numbered textbook extracts. Do not add facts that are not in them.
Return ONE JSON object with exactly these keys:
{{
 "title": "short lesson title",
 "objectives": ["what students will be able to explain (3 to 4 items)"],
 "sections": [ {{"heading": "...", "content": "teaching text in simple English, short paragraphs or bullet points; cite extracts like [1] or [2]", "cites": [1, 2]}} ],
 "key_points": ["one-line takeaways (5 to 7 items)"],
 "vocabulary": [ {{"term": "...", "meaning": "..."}} ],
 "timeline": [ {{"date": "the date EXACTLY as written in the extract, e.g. '19th July 1969' or '1955'", "year": 1969, "event": "what happened, one line", "cite": 3}} ],
 "periods": [ {{"name": "e.g. First Five Year Plan", "start": 1951, "end": 1956, "focus": "main aims in a few words", "cite": 2}} ],
 "people": [ {{"name": "name as written in the extract", "role": "who they were and what they did in this chapter", "cite": 5}} ],
 "places": [ {{"name": "place as written in the extract", "near": "ALWAYS fill: for a part of a city or a small town, the big city it belongs to or is closest to (e.g. 'Kolkata' for Howrah, 'Pune' for Hadapsar); for a big city, its present-day state — used only to find it on the map", "what": "what happened or what was set up there", "cite": 2}} ],
 "cause_effect": [ {{"event": "an important event", "causes": ["cause 1", "..."], "effects": ["effect 1", "..."], "cites": [5, 6]}} ]
}}
Rules: every item cites the number of the extract it comes from. Dates, years and names must be written exactly as in
the extracts. timeline: every event with ONE date in the extracts (up to 25), oldest first; use the event the extract
gives for that date, word for word where possible. periods: things with a start and an end year (plans, reigns,
wars) — never put them in the timeline too. people: up to 12. places: only real towns, cities and dams that are
mentioned (not rivers or regions), up to 20. cause_effect: 2 to 4 important events with the causes and effects
given in the extracts.
3 to 5 sections. Output the JSON object only."""

MONTHS = ("january february march april may june july august september october november december").split()
TITLES = {"dr", "mr", "mrs", "smt", "shri", "pandit", "prime", "minister", "mahatma", "barrister", "sir", "lord",
          "president", "finance", "chief", "the", "of"}  # fmt: skip


def _numbers(text: str) -> list[str]:
    return re.findall(r"\d+", text)


def _in(text: str, number: str) -> bool:
    return re.search(rf"(?<!\d){re.escape(number)}(?!\d)", text) is not None


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text.lower())).strip()


def date_in_text(date: str, text: str) -> bool:
    """Every number and month name of the date appears in the text ('19th July 1969' → 19, July, 1969)."""
    low = text.lower()
    numbers = _numbers(date)
    months = [m for m in MONTHS if m in date.lower()]
    return bool(numbers) and all(_in(text, n) for n in numbers) and all(m in low for m in months)


STOP = set("that this with from were have been they their there which into about after before during also more "
           "than when what will would could should these those other such only very over under some many most "
           "made make each india indian".split())  # fmt: skip


def _stems(text: str) -> set[str]:
    """Significant words, cut to 5 letters so that 'nationalised' and 'nationalisation' match."""
    return {w[:5] for w in _norm(text).split() if len(w) >= 4 and w not in STOP and not w.isdigit()}


def event_near_date(event: str, date: str, text: str) -> bool:
    """The date and the event are told together: some sentence with the date's numbers, with the sentence before
    and after it, contains at least two significant words of the event (measured: the AI once paired '1991' with
    'Dr Manmohan Singh signed the WTO agreement'; the textbook gives no year for that)."""
    sentences = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))  # line breaks are not sentence ends
    numbers = _numbers(date)
    wanted = _stems(event)
    need = min(2, len(wanted))
    if not numbers or not need:
        return False
    for i, sentence in enumerate(sentences):
        if all(_in(sentence, n) for n in numbers if len(n) == 4) and any(_in(sentence, n) for n in numbers):
            own = len(wanted & _stems(sentence))
            window = " ".join(sentences[max(0, i - 1) : i + 2])
            # the date's own sentence must share a word with the event; neighbours may complete it
            if own >= need or (own >= 1 and len(wanted & _stems(window)) >= need):
                return True
    return False


def name_in_text(name: str, text: str) -> bool:
    """The significant words of a name appear in the text ('Dr Datta Samant' → 'datta', 'samant')."""
    words = [w for w in _norm(re.sub(r"\(.*?\)", "", name)).split() if w not in TITLES and len(w) > 1]
    low = _norm(text)
    return bool(words) and all(re.search(rf"\b{re.escape(w)}\b", low) for w in words)


def verify(plan: dict, sources: dict[int, str]) -> list[str]:
    """Check timeline, periods, people and places against the cited extract text (number → text).
    Unsupported items are removed from the plan; returns the warnings for the teacher."""
    warnings: list[str] = []
    every = " \n".join(sources.values())

    def text_of(item: dict) -> str:
        cites = item.get("cites") or [item.get("cite")]
        return " \n".join(sources.get(c, "") for c in cites if isinstance(c, int)) or every

    def keep(key: str, test, label) -> None:
        kept = []
        for item in plan.get(key, []) or []:
            if not isinstance(item, dict):
                continue
            if test(item, text_of(item)):
                kept.append(item)
            elif test(item, every):  # right fact, wrong citation: fix the citation
                item["cite"] = next((n for n, t in sources.items() if test(item, t)), item.get("cite"))
                kept.append(item)
            else:
                warnings.append(f"Removed {label(item)} — not found in the textbook pages used.")
        plan[key] = kept

    # A range like '1951-1956' is a period, not a timeline event (the plans already appear as period bars).
    plan["timeline"] = [
        i for i in plan.get("timeline", []) or [] if len(re.findall(r"\d{4}", str(i.get("date", "")))) < 2
    ]
    keep("timeline", lambda i, t: date_in_text(str(i.get("date", "")), t) and _in(t, str(i.get("year", "")))
         and event_near_date(str(i.get("event", "")), str(i.get("date", "")), t),
         lambda i: f"timeline entry '{i.get('date')}: {i.get('event')}' (date and event not found together)")  # fmt: skip
    keep("periods", lambda i, t: _in(t, str(i.get("start", ""))) and _in(t, str(i.get("end", ""))),
         lambda i: f"period '{i.get('name')} ({i.get('start')}–{i.get('end')})'")  # fmt: skip
    keep(
        "people", lambda i, t: name_in_text(str(i.get("name", "")), t), lambda i: f"person '{i.get('name')}'"
    )
    keep("places", lambda i, t: name_in_text(str(i.get("name", "")), t), lambda i: f"place '{i.get('name')}'")
    # Citation marks belong to the sections, not to timeline/map texts ('... as its Chairman [4]' was seen).
    for key in ("timeline", "periods", "people", "places", "cause_effect"):
        for item in plan.get(key, []) or []:
            for field in ("event", "focus", "role", "what"):
                if isinstance(item.get(field), str):
                    item[field] = _strip_cites(item[field])
            for field in ("causes", "effects"):
                if isinstance(item.get(field), list):
                    item[field] = [_strip_cites(str(x)) for x in item[field]]
    # One card per person: 'Pandit Nehru' and 'Pandit Jawaharlal Nehru' are the same person.
    people = sorted(plan.get("people", []), key=lambda p: -len(str(p.get("name", ""))))
    merged: list[dict] = []
    for person in people:
        if not any(name_in_text(str(person.get("name", "")), str(other.get("name", ""))) for other in merged):
            merged.append(person)
    plan["people"] = [p for p in plan.get("people", []) if p in merged]
    for item in plan.get("timeline", []):
        try:
            item["year"] = int(item["year"])
        except (KeyError, TypeError, ValueError):
            item["year"] = int(_numbers(str(item.get("date", "")))[-1])
    plan["timeline"].sort(key=lambda i: i["year"])
    # The same event told twice ('1955: Imperial Bank nationalised' and '1955: … converted into State Bank of India'
    # were both returned in the end-to-end test): keep the fuller one.
    unique: list[dict] = []
    for item in sorted(plan["timeline"], key=lambda i: -len(str(i.get("event", "")))):
        words = _stems(str(item.get("event", "")))
        twin = any(
            o["date"] == item["date"] and words and len(words & _stems(str(o["event"]))) >= 0.6 * len(words)
            for o in unique
        )
        if not twin:
            unique.append(item)
    plan["timeline"] = sorted(unique, key=lambda i: i["year"])
    plan.setdefault("cause_effect", [])
    return warnings


def _strip_cites(text: str) -> str:
    return re.sub(r"\s*\[\d+\](?:\s*\[\d+\])*", "", text).strip()


EXERCISE_MARKS = re.compile(
    r"choose the correct option|wrong pair|complete the following|answer the following|write short notes|"
    r"explain the following|give reasons|fill in the blanks|match the following|\bexercises\b",
    re.I,
)


def is_exercise(text: str) -> bool:
    """Exercise passages contain blanks and deliberately WRONG pairs ('Kavasaji Davar – Iron and Steel factory' in
    the owner's chapter): never use them as lesson facts."""
    return len(EXERCISE_MARKS.findall(text)) >= 2 or "........." in text


def without_exercises(hits: list) -> list:
    """Drop exercise passages. An exercise section runs to the end of its page, so once a passage of a page is an
    exercise, the following passages of that page are too (measured: the owner's exercise page was split into 3
    passages and only the first said 'Exercises')."""
    start: dict[tuple[int, int], int] = {}
    for hit in hits:
        if is_exercise(hit.text):
            key = (hit.document_id, hit.page_no)
            start[key] = min(start.get(key, hit.chunk_id), hit.chunk_id)
    return [
        h
        for h in hits
        if (h.document_id, h.page_no) not in start or h.chunk_id < start[(h.document_id, h.page_no)]
    ]


def pages_of(item: dict, pages: dict[int, int]) -> list[int]:
    cites = item.get("cites") or [item.get("cite")]
    return sorted({pages[c] for c in cites if isinstance(c, int) and c in pages})


# ---------------------------------------------------------------- scenes for the browser (assets/historykit.js)


def timeline_scene(plan: dict) -> dict | None:
    events = [
        {
            "label": str(e["date"]),
            "year": int(e["year"]),
            "text": e.get("event", ""),
            "pages": e.get("pages", []),
        }
        for e in plan.get("timeline", [])
    ]
    periods = [
        {"name": p.get("name", ""), "start": int(p["start"]), "end": int(p["end"]), "text": p.get("focus", ""),
         "pages": p.get("pages", [])}
        for p in plan.get("periods", [])
        if str(p.get("start", "")).isdigit() and str(p.get("end", "")).isdigit()
    ]  # fmt: skip
    if not events and not periods:
        return None
    years = [e["year"] for e in events] + [p["start"] for p in periods] + [p["end"] for p in periods]
    return {"kind": "timeline", "title": plan.get("title", "Timeline"), "events": events, "periods": periods,
            "range": [min(years), max(years)]}  # fmt: skip


def flow_scenes(plan: dict) -> list[dict]:
    """One 'causes → event → effects' scene per cause-and-effect item of the plan."""
    scenes = []
    for item in plan.get("cause_effect", []):
        causes = [str(c) for c in item.get("causes", []) if str(c).strip()][:5]
        effects = [str(c) for c in item.get("effects", []) if str(c).strip()][:5]
        if item.get("event") and (causes or effects):
            scenes.append({"kind": "flow", "title": f"Why it happened and what followed: {item['event']}",
                           "event": item["event"], "causes": causes, "effects": effects,
                           "pages": item.get("pages", [])})  # fmt: skip
    return scenes


def map_scene(plan: dict) -> dict | None:
    """Places of the lesson on a map of India; places that cannot be placed are listed with the reason."""
    places = plan.get("places", [])
    if not places:
        return None
    width, height = geo.map_size()
    placed, unplaced = [], []
    for item in places:
        manual = item.get("lat") is not None and item.get("lon") is not None  # entered by the teacher
        if manual:
            found = geo.Place(
                item["name"], item["name"], float(item["lat"]), float(item["lon"]), "", "entered by you"
            )
            reason = ""
        else:
            found, reason = geo.geocode(item.get("name", ""), item.get("near", ""))
        if found is None:
            unplaced.append({"name": item.get("name", ""), "reason": reason, "what": item.get("what", "")})
            continue
        x, y = geo.project(found.lat, found.lon)
        if not (0 <= x <= width and 0 <= y <= height):
            unplaced.append(
                {
                    "name": item.get("name", ""),
                    "reason": "outside the map of India",
                    "what": item.get("what", ""),
                }
            )
            continue
        placed.append(
            {"name": item.get("name", ""), "found": found.found, "state": found.state, "how": found.how,
             "x": x, "y": y, "text": item.get("what", ""), "pages": item.get("pages", [])}
        )  # fmt: skip
    if not placed and not unplaced:
        return None
    return {"kind": "map", "title": "Places in this lesson", "size": [width, height], "outlines": geo.outline_paths(),
            "places": placed, "unplaced": unplaced, "credit": geo.CREDIT}  # fmt: skip
