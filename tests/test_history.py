"""History lessons: two-column text order, fact checks against the textbook, offline map placement, textbook
pictures, scenes, the hand-written player (Node + browser) and the planner's history path."""

import io
import json
import shutil
import subprocess

import pymupdf
import pytest
from PIL import Image

from app.core.config import PROJECT_ROOT
from app.ingestion.extract import reading_order_text
from app.lessons import geo, history
from app.lessons.browser_check import _inject, _run, find_browser
from app.lessons.figures import extract_figures, portrait_of
from app.lessons.viewers import CSP, history_html

SOURCE = (
    "Prime Minister Indira Gandhi nationalised 14 banks on 19th July 1969. The first textile mill was started in "
    "Mumbai in 1854 by Kawasjee Dawar. Iron and steel industries at Durgapur, Bhilai and Rourkela. "
    "First Five Year Plan (1951-1956). Dr Datta Samant led the strike."
)


# ---------------------------------------------------------------- text order on two-column pages


def test_two_column_pages_are_read_left_column_first(tmp_path):
    """The owner's history page 18: plain PDF text put the right column first and split a sentence."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((60, 60), "4 Economic Development", fontsize=16)  # full-width title
    page.insert_textbox(pymupdf.Rect(320, 100, 560, 300), "RIGHT column text comes second.")  # written FIRST
    page.insert_textbox(pymupdf.Rect(40, 100, 280, 300), "LEFT column\ntext comes first,\nnot split.")
    page.insert_text((290, 820), "18", fontsize=9)  # page number in the bottom margin
    text = reading_order_text(page)
    assert text.index("Economic Development") < text.index("LEFT") < text.index("RIGHT")
    assert "LEFT column text comes first, not split." in text  # lines re-joined into a paragraph
    assert "18" not in text


# ---------------------------------------------------------------- fact checks


def test_dates_and_names_must_be_in_the_textbook_text():
    assert history.date_in_text("19th July 1969", SOURCE)
    assert not history.date_in_text("20th July 1969", SOURCE)  # wrong day
    assert not history.date_in_text("19th June 1969", SOURCE)  # wrong month
    assert history.name_in_text("Dr Datta Samant", SOURCE) and history.name_in_text("Indira Gandhi", SOURCE)
    assert not history.name_in_text("Morarji Desai", SOURCE)


def test_a_real_date_paired_with_the_wrong_event_is_removed():
    """Measured in the end-to-end test: '1991' (real) was paired with an event the textbook gives no year for."""
    assert history.event_near_date("Indira Gandhi nationalised 14 banks", "19th July 1969", SOURCE)
    assert not history.event_near_date("Indira Gandhi nationalised 14 banks", "1854", SOURCE)
    plan = {"timeline": [{"date": "1854", "year": 1854, "event": "First textile mill started in Mumbai", "cite": 1},
                         {"date": "1854", "year": 1854, "event": "Banks were nationalised by Indira Gandhi", "cite": 1},
                         {"date": "1951-1956", "year": 1951, "event": "First Five Year Plan", "cite": 1}]}  # fmt: skip
    warnings = history.verify(plan, {1: SOURCE})
    assert [e["event"] for e in plan["timeline"]] == ["First textile mill started in Mumbai"]
    assert any("not found together" in w for w in warnings)  # the range went to periods, not to warnings


def test_verify_removes_invented_items_and_fixes_wrong_citations():
    plan = {
        "timeline": [
            {
                "date": "19th July 1969",
                "year": 1969,
                "event": "Indira Gandhi nationalised banks",
                "cite": 2,
            },  # wrong cite
            {"date": "1947", "year": 1947, "event": "invented", "cite": 1},
        ],
        "periods": [
            {"name": "First Plan", "start": 1951, "end": 1956, "cite": 1},
            {"name": "Invented Plan", "start": 2003, "end": 2008, "cite": 1},
        ],  # fmt: skip
        "people": [{"name": "Dr Datta Samant", "cite": 1}, {"name": "Morarji Desai", "cite": 1}],
        "places": [{"name": "Bhilai", "cite": 1}, {"name": "Jamshedpur", "cite": 1}],
    }
    warnings = history.verify(plan, {1: SOURCE, 2: "Another page about mixed economy."})
    assert [e["event"] for e in plan["timeline"]] == ["Indira Gandhi nationalised banks"]
    assert plan["timeline"][0]["cite"] == 1
    assert [p["name"] for p in plan["periods"]] == ["First Plan"]
    assert [p["name"] for p in plan["people"]] == ["Dr Datta Samant"]
    assert [p["name"] for p in plan["places"]] == ["Bhilai"]
    assert len(warnings) == 4 and all("not found in the textbook" in w for w in warnings)


def test_the_same_event_told_twice_is_kept_once():
    text = "In order to stop this, the government nationalised the Imperial Bank in 1955 and it got converted into State Bank of India."
    plan = {"timeline": [{"date": "1955", "year": 1955, "event": "the government nationalised the Imperial Bank", "cite": 1},
                         {"date": "1955", "year": 1955, "event": "the government nationalised the Imperial Bank and it got converted into State Bank of India", "cite": 1}]}  # fmt: skip
    history.verify(plan, {1: text})
    assert [e["event"] for e in plan["timeline"]] == [
        "the government nationalised the Imperial Bank and it got converted into State Bank of India"
    ]


def test_exercise_passages_never_become_lesson_facts():
    """The exercise page has blanks and deliberately wrong pairs ('Kavasaji Davar – Iron and Steel factory')."""
    from app.rag.store import Hit

    def hit(chunk_id, page, text):
        return Hit(chunk_id, 1.0, text, page, 1, "f.pdf", "9", "History", 4, "")

    hits = [
        hit(1, 7, "In 1995, India became a member of the WTO."),
        hit(2, 8, "Projects to do at home."),  # before the exercises on the same page: kept
        hit(3, 8, "Exercises\n1. (A) Choose the correct option ... (1) On 19th July 1969 .......... banks"),
        hit(4, 8, "(B) Identify and write the wrong pair. (1) Kavasaji Davar – Iron and Steel factory"),
    ]
    assert [h.chunk_id for h in history.without_exercises(hits)] == [1, 2]


def test_subject_profiles():
    assert history.profile("History") == "history" and history.profile("Political Science") == "history"
    assert history.profile("Science") == "science" and history.profile("") == "science"


# ---------------------------------------------------------------- map placement (offline data)


@pytest.mark.parametrize(
    ("name", "hint", "expected_state"),
    [
        ("Bhilai", "", "Chhattisgarh"),  # largest of several Bhilais
        ("Rourkela", "", "Odisha"),
        ("Vishakhapattanam", "", "Andhra Pradesh"),  # textbook spelling
        ("Perambur (Chennai)", "", "Tamil Nadu"),  # city hint inside the name
        ("Sindri", "Dhanbad", "Jharkhand"),  # nearby-city hint
        ("Bhakra-Nangal", "", "Punjab"),  # tried part by part → Nangal
        ("Madras", "", "Tamil Nadu"),  # old name
    ],
)
def test_places_are_found_only_when_the_choice_is_clear(name, hint, expected_state):
    place, reason = geo.geocode(name, hint)
    assert place is not None, reason
    assert place.state == expected_state


def test_ambiguous_or_unknown_places_are_not_guessed():
    place, reason = geo.geocode("Sindri")
    assert place is None and "places in India have this name" in reason
    place, reason = geo.geocode("Xyzabad")
    assert place is None and "not found" in reason
    visakhapatnam, _ = geo.geocode(
        "Visakhapatnam"
    )  # also an alternate name of a bigger 'Rasapudipalem' entry
    assert visakhapatnam.found == "Visakhapatnam"


def test_map_data_is_verified_and_india_is_drawn():
    paths = geo.outline_paths()
    assert "IND" in paths and paths["IND"]["path"].count("M") >= 5  # mainland + islands
    x, y = geo.project(28.6, 77.2)  # Delhi lies inside the drawing
    width, height = geo.map_size()
    assert 0 < x < width and 0 < y < height


def test_map_scene_lists_unplaced_places_with_reasons():
    plan = {"places": [{"name": "Bhilai", "what": "steel"}, {"name": "Damodar", "what": "dam"},
                       {"name": "My village", "lat": 21.0, "lon": 79.0, "what": "entered by the teacher"}]}  # fmt: skip
    scene = history.map_scene(plan)
    assert [p["name"] for p in scene["places"]] == ["Bhilai", "My village"]
    assert scene["unplaced"][0]["name"] == "Damodar" and scene["unplaced"][0]["reason"]
    assert "GeoNames" in scene["credit"]


def test_timeline_and_flow_scenes():
    plan = {"title": "T", "timeline": [{"date": "1955", "year": 1955, "event": "SBI", "pages": [4]}],
            "periods": [{"name": "First Plan", "start": 1951, "end": 1956}],
            "cause_effect": [{"event": "Strike", "causes": ["bonus cut"], "effects": ["mills closed"], "pages": [5]}]}  # fmt: skip
    scene = history.timeline_scene(plan)
    assert scene["range"] == [1951, 1956] and scene["events"][0]["text"] == "SBI"
    flows = history.flow_scenes(plan)
    assert flows[0]["causes"] == ["bonus cut"] and flows[0]["pages"] == [5]
    assert history.timeline_scene({}) is None and history.flow_scenes({}) == []


# ---------------------------------------------------------------- textbook pictures


def _png(color: tuple[int, int, int], size=(200, 150)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def test_only_captioned_textbook_pictures_are_used(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(pymupdf.Rect(300, 100, 500, 250), stream=_png((200, 50, 50)))
    page.insert_text((330, 262), "P. V. Narasimha Rao", fontsize=10)  # caption just under the picture
    page.insert_image(pymupdf.Rect(40, 400, 240, 550), stream=_png((50, 50, 200)))  # no caption: decoration
    path = tmp_path / "book.pdf"
    doc.save(path)
    figures = list(extract_figures(str(path)))
    assert [f.caption for f in figures] == ["P. V. Narasimha Rao"] and figures[0].png.startswith(b"\x89PNG")
    assert portrait_of("P. V. Narasimha Rao", figures) and portrait_of("Indira Gandhi", figures) is None


# ---------------------------------------------------------------- the player


NODE = shutil.which("node")
KIT = PROJECT_ROOT / "assets" / "historykit.js"


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_player_helpers_in_node():
    script = (
        f"const K = require({json.dumps(str(KIT))});"
        "const items = Array.from({length: 8}, (_, i) => ({x: 500 + (i % 3) * 4, y: 400 + i * 3, w: 120, h: 30}));"
        "const spots = K.placeLabels(items, {x: 0, y: 0, w: 1000, h: 1000});"
        "let overlaps = 0; spots.forEach((a, i) => spots.forEach((b, j) => { if (i < j && K.overlaps("
        "{x: a.x, y: a.y, w: 120, h: 30}, {x: b.x, y: b.y, w: 120, h: 30})) overlaps++; }));"
        "console.log(JSON.stringify({overlaps, wrap: K.wrap('one two three four five', 9),"
        " lanes: K.lanes([{start: 1951, end: 1956}, {start: 1956, end: 1961}, {start: 1955, end: 1970}]),"
        " scale: (s => [s.x(1882), s.x(1950), s.x(2002), s.breaks.length])(K.yearScale([1880, 1882, 1950, 1969, 1982, 1995, 2005], 40, 960, 25))}));"
    )
    done = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    result = json.loads(done.stdout)
    assert result["overlaps"] == 0  # 8 crowded labels (like Sindri/Durgapur/Chittaranjan) never overlap
    assert result["wrap"] == ["one two", "three", "four five"]
    assert result["lanes"] == [0, 0, 1]  # touching plans share a lane, an overlapping one moves up
    x1882, x1950, x2002, breaks = result["scale"]
    assert breaks == 1 and x1950 - x1882 < 100 and x2002 - x1950 > 700  # the empty 68 years are squeezed


needs_browser = pytest.mark.skipif(find_browser() is None, reason="no Edge/Chrome on this computer")


@needs_browser
@pytest.mark.parametrize("kind", ["timeline", "map", "flow"])
def test_player_runs_in_a_real_browser(kind):
    plan = {"title": "Economic Development",
            "timeline": [{"date": "1955", "year": 1955, "event": "SBI formed"}, {"date": "19th July 1969", "year": 1969, "event": "14 banks"}],
            "periods": [{"name": "First Plan", "start": 1951, "end": 1956}],
            "places": [{"name": "Bhilai", "what": "steel plant"}, {"name": "Rourkela", "what": "steel plant"}],
            "cause_effect": [{"event": "Strike", "causes": ["bonus cut"], "effects": ["mills closed"]}]}  # fmt: skip
    scene = {"timeline": history.timeline_scene, "map": history.map_scene}.get(
        kind, lambda p: history.flow_scenes(p)[0]
    )(plan)
    html = history_html(scene, 560)
    assert CSP in html
    probe = """
    window.addEventListener('error', e => (window.__err = String(e.message)));
    setTimeout(() => {
      document.getElementById('next').click();
      const out = {steps: window.hk.steps, current: window.hk.current, err: window.__err || null,
                   text: document.getElementById('steptext').textContent, shapes: document.querySelectorAll('#hk *').length};
      const pre = document.createElement('pre'); pre.id = 'R'; pre.textContent = JSON.stringify(out); document.body.appendChild(pre);
    }, 800);
    """
    dom = _run(find_browser(), _inject(html, probe), ["--virtual-time-budget=3000", "--dump-dom"])
    start = dom.find('id="R">')
    assert start > 0, "page did not finish"
    result = json.loads(
        dom[start + 7 : dom.find("</pre>", start)].replace("&quot;", '"').replace("&amp;", "&")
    )
    assert result["err"] is None and result["steps"] >= 2 and result["current"] == 1 and result["shapes"] > 10
    assert result["text"]
