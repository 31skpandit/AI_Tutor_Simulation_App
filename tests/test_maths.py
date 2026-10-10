"""Maths lessons: computed answers, equation steps, scenes, the hand-written maths kit (Node + browser), the photo
finder (mocked Wikimedia, offline) and the maths path through the planner and the lesson service."""

import io
import json
import shutil
import subprocess

import httpx
import pytest
from PIL import Image

from app.core.config import PROJECT_ROOT
from app.lessons import maths
from app.lessons.browser_check import _inject, _run, find_browser
from app.lessons.service import LessonService, photo_queries
from app.lessons.viewers import CSP, math_html
from app.llm.backend import BackendResult
from app.media.finder import MediaError, MediaFinder, licence_ok
from tests.test_ingestion import env, make_text_pdf  # noqa: F401

# ---------------------------------------------------------------- computing (checked against the Class 7 textbook)


def test_number_facts():
    assert maths.prime_factors(546) == [2, 3, 7, 13]
    assert maths.hcf([195, 312, 546]) == 39
    assert maths.lcm([16, 24, 18]) == 144
    steps = maths.euclid_steps(144, 252)
    assert steps[0]["dividend"] == 252 and steps[-1]["remainder"] == 0 and steps[-1]["divisor"] == 36
    assert [n for n in range(1, 20) if maths.is_prime(n)] == [2, 3, 5, 7, 11, 13, 17, 19]
    tree = maths.factor_tree(24)
    assert tree["n"] == 24 and tree["children"][0] == {"n": 2, "prime": True}


@pytest.mark.parametrize(
    ("equation", "var", "value"),
    [
        ("a + 15 + 2a = 90", "a", 25),
        ("70 + x = 90", "x", 20),
        ("(a+30) + 2a = 180", "a", 50),
        ("135 + p = 180", "p", 45),
        ("x - 5 = 3", "x", 8),
        ("3y = 2y + 7", "y", 7),
    ],
)
def test_textbook_equations_are_solved_step_by_step(equation, var, value):
    solved = maths.solve_linear(equation)
    assert solved is not None
    got_var, got_value, steps, reasons = solved
    assert (got_var, got_value) == (var, value)
    assert steps[-1].replace(" ", "") == f"{var}={value}"
    assert len(steps) == len(reasons) and all(reasons)
    assert len({s.replace(" ", "").replace("−", "-") for s in steps}) == len(steps)  # no repeated step


def test_reasons_say_what_is_done_to_both_sides():
    _, _, _, reasons = maths.solve_linear("a + 15 + 2a = 90")
    assert any("Take away 15" in r for r in reasons) and any("Divide" in r for r in reasons)
    _, _, _, reasons = maths.solve_linear("x - 5 = 3")
    assert any("Add 5" in r for r in reasons)


def test_unsupported_equations_are_not_guessed():
    assert maths.solve_linear("2(a+3) = 10") is None  # brackets with a factor: not solved, not invented
    assert maths.solve_linear("x*x = 4") is None
    assert maths.solve_linear("hello") is None


def test_verify_corrects_wrong_ai_answers_and_keeps_good_ones():
    plan = {
        "concepts": [
            {"name": "HCF", "kind": "hcf", "examples": [{"text": "HCF of 195, 312, 546", "numbers": [195, 312, 546], "answer": "140"}],
             "real_life": [{"title": "Tiles", "story": "…", "image_query": "floor tiles"}, "junk"]},
            {"name": "LCM", "kind": "lcm", "examples": [{"numbers": [16, 24, 18], "answer": "144"}]},
            {"name": "Complement", "kind": "complementary_angles", "examples": [{"angles": [70], "answer": "20°"}]},
            {"name": "Odd idea", "kind": "made_up_kind", "examples": [{"text": "?"}]},
            {"kind": "hcf"},  # no name: dropped
        ]
    }  # fmt: skip
    warnings = maths.verify(plan)
    assert len(warnings) == 1 and "140" in warnings[0] and "39" in warnings[0]
    hcf_example = plan["concepts"][0]["examples"][0]
    assert hcf_example["answer"] == "39" and hcf_example["computed"] == "39" and hcf_example["ok"] is False
    assert plan["concepts"][1]["examples"][0]["ok"] is True
    assert (
        plan["concepts"][2]["examples"][0]["computed"] == "20°" and plan["concepts"][2]["examples"][0]["ok"]
    )
    assert plan["concepts"][3]["kind"] == "other"
    assert len(plan["concepts"]) == 4 and plan["concepts"][0]["real_life"] == [
        plan["concepts"][0]["real_life"][0]
    ]


def test_scenes_are_built_only_from_computed_values():
    hcf_scenes = maths.visuals_for({"kind": "hcf", "examples": [{"numbers": [144, 252]}]})
    venn = next(s for s in hcf_scenes if s["type"] == "venn")
    assert venn["hcf"] == 36 and venn["lcm"] == 1008
    product = lambda xs: eval("*".join(map(str, xs)) or "1")  # noqa: E731,S307 — numbers only, built here
    assert product(venn["common"]) == 36 and product(venn["only_a"] + venn["common"]) == 144
    assert {s["type"] for s in hcf_scenes} == {"venn", "factor_tree", "division"}
    runners = maths.visuals_for({"kind": "lcm", "examples": [{"numbers": [16, 24, 18]}]})
    assert next(s for s in runners if s["type"] == "runners")["lcm"] == 144
    angles = maths.visuals_for(
        {"kind": "complementary_angles", "examples": [{"angles": [35], "equation": "70 + x = 90"}]}
    )
    assert [s["type"] for s in angles] == ["angle", "angle3d", "balance"]
    assert angles[1]["dim"] == "3d" and angles[1]["object"] == "ramp" and angles[0]["angle"] == 35
    assert angles[2]["steps"][-1].replace(" ", "") == "x=20"
    sieve = maths.visuals_for({"kind": "twin_primes", "examples": [{"numbers": [3, 5]}]})[0]
    assert sieve["top"] == 50 and [3, 5] in sieve["twins"] and len(sieve["primes"]) == 15
    assert maths.visuals_for({"kind": "other", "examples": []}) == []


def test_subject_profiles():
    from app.lessons.planner import lesson_profile

    assert lesson_profile("Maths") == "maths" and lesson_profile("Mathematics") == "maths"
    assert lesson_profile("History") == "history" and lesson_profile("Science") == "science"


# ---------------------------------------------------------------- the maths kit (hand-written player)

NODE = shutil.which("node")
KIT = PROJECT_ROOT / "assets" / "mathkit.js"


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_kit_helpers_in_node():
    script = (
        f"const K = require({json.dumps(str(KIT))});"
        "const tree = {n: 24, children: [{n: 2}, {n: 12, children: [{n: 2}, {n: 6, children: [{n: 2}, {n: 3}]}]}]};"
        "console.log(JSON.stringify({depth: K.treeDepth(tree), start: K.runnerAngles([16, 24], 0),"
        " lcm: K.runnerAngles([16, 24, 18], 144), right: K.pointerAngle(0, 0, 10, 0), up: K.pointerAngle(0, 0, 0, -10),"
        " product: K.product([2, 2, 3, 3]),"
        " right_angle: K.angleAt({x: 0, y: 0}, {x: 5, y: 0}, {x: 0, y: -7}), straight: K.angleAt({x: 0, y: 0}, {x: 5, y: 0}, {x: -3, y: 0})}));"
    )
    done = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    result = json.loads(done.stdout)
    assert result["depth"] == 3 and result["product"] == 36
    assert all(
        abs(a + 1.5707963) < 1e-6 for a in result["start"] + result["lcm"]
    )  # everyone at START at the LCM
    assert result["right"] == 0 and result["up"] == 90  # screen y grows downwards
    assert abs(result["right_angle"] - 90) < 1e-9 and abs(result["straight"] - 180) < 1e-9


needs_browser = pytest.mark.skipif(find_browser() is None, reason="no Edge/Chrome on this computer")
SCENE_CONCEPTS = {
    "factor_tree": {"kind": "prime_factorisation", "examples": [{"numbers": [546]}]},
    "venn": {"kind": "hcf", "examples": [{"numbers": [144, 252]}]},
    "division": {"kind": "hcf", "examples": [{"numbers": [144, 252]}]},
    "runners": {"kind": "lcm", "examples": [{"numbers": [16, 24, 18]}]},
    "sieve": {"kind": "twin_primes", "examples": []},
    "balance": {"kind": "linear_equation", "examples": [{"equation": "a + 15 + 2a = 90"}]},
    "angle": {"kind": "vertically_opposite_angles", "examples": [{"angles": [50]}]},
    "angle3d": {"kind": "supplementary_angles", "examples": [{"angles": [135]}]},
    "triangle": {"kind": "exterior_angle", "examples": [{"angles": [70, 70]}]},
    "polygon": {"kind": "polygon_angle_sum", "examples": []},
}


@needs_browser
@pytest.mark.parametrize("kind", list(SCENE_CONCEPTS))
def test_every_scene_runs_in_a_real_browser(kind):
    scene = next(s for s in maths.visuals_for(SCENE_CONCEPTS[kind]) if s["type"] == kind)
    html = math_html(scene, 560)
    assert CSP in html
    probe = """
    window.addEventListener('error', e => (window.__err = String(e.message)));
    setTimeout(() => {
      document.getElementById('next').click();
      const out = {steps: window.mk.steps, current: window.mk.current, err: window.__err || null,
                   text: document.getElementById('steptext').textContent,
                   shapes: document.querySelectorAll('#mk *').length + (document.getElementById('mk3d') ? 100 : 0),
                   broken: document.body.innerText.includes('Maths view error')};
      const pre = document.createElement('pre'); pre.id = 'R'; pre.textContent = JSON.stringify(out); document.body.appendChild(pre);
    }, 800);
    """
    dom = _run(find_browser(), _inject(html, probe), ["--virtual-time-budget=3000", "--dump-dom"])
    start = dom.find('id="R">')
    assert start > 0, "page did not finish"
    result = json.loads(
        dom[start + 7 : dom.find("</pre>", start)].replace("&quot;", '"').replace("&amp;", "&")
    )
    assert result["err"] is None and not result["broken"]
    assert result["steps"] >= 2 and result["current"] == 1 and result["shapes"] > 5 and result["text"]


# ---------------------------------------------------------------- photo finder (mocked Wikimedia — no network)


def test_only_free_licences_are_accepted():
    for good in ["CC0", "Public domain", "CC BY 4.0", "CC BY-SA 3.0", "CC-BY-SA-4.0", "cc by 2.0"]:
        assert licence_ok(good), good
    for bad in ["CC BY-NC 2.0", "CC BY-ND 4.0", "CC BY-NC-SA 3.0", "All rights reserved", "", "GFDL"]:
        assert not licence_ok(bad), bad


def _png(colour="red") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), colour).save(buffer, "PNG")
    return buffer.getvalue()


def _commons_page(index, title, licence, mime="image/png", host="upload.wikimedia.org"):
    return {
        "index": index, "title": f"File:{title}.png",
        "imageinfo": [{"mime": mime, "thumburl": f"https://{host}/thumb/{index}.png",
                       "descriptionurl": f"https://commons.wikimedia.org/wiki/File:{title}.png",
                       "extmetadata": {"LicenseShortName": {"value": licence}, "Artist": {"value": "<a href='x'>Asha</a>"},
                                       "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0"}}}],
    }  # fmt: skip


class Wikimedia:
    """Fake Commons: one non-free photo, one SVG, one good photo, one photo on a host outside the allow-list."""

    def __init__(self):
        self.requests: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(str(request.url))
        host = request.url.host
        if host == "commons.wikimedia.org":
            pages = {
                "1": _commons_page(1, "Non free gate", "CC BY-NC 2.0"),
                "2": _commons_page(2, "Gate drawing", "CC0", mime="image/svg+xml"),
                "3": _commons_page(3, "Railway level crossing gate", "CC BY-SA 4.0"),
                "4": _commons_page(4, "Elsewhere gate", "CC0", host="evil.example.com"),
            }
            return httpx.Response(200, json={"query": {"pages": pages}})
        if host == "upload.wikimedia.org":
            return httpx.Response(200, content=_png(), headers={"Content-Type": "image/png"})
        if host == "api.openverse.org":
            return httpx.Response(200, json={"results": []})
        return httpx.Response(200, content=b"<html>should never be fetched</html>")


@pytest.fixture
def finder_env(env):  # noqa: F811
    service, backend, _ = env
    router = service.router
    router.config.tasks["image_check"] = router.config.tasks["simulation_review"]  # local, JSON, no cache
    wikimedia = Wikimedia()
    client = httpx.Client(transport=httpx.MockTransport(wikimedia), follow_redirects=False)
    return MediaFinder(router, service.engine, service.settings, client=client), backend, wikimedia, service


def test_finder_keeps_only_free_raster_photos_that_the_vision_model_confirms(finder_env):
    finder, backend, wikimedia, service = finder_env
    backend.script = [
        BackendResult('{"fits": false, "caption": "a railway level crossing gate", "reason": "x"}', 1, 1)
    ]
    found = finder.find("railway level crossing gate", concept="Linear pair", lesson_id=7, keep=1)
    assert len(found) == 1
    asset = found[0]
    assert asset.license == "CC BY-SA 4.0" and asset.author == "Asha" and asset.fits and asset.lesson_id == 7
    assert (service.settings.data_dir / asset.local_path).is_file()
    assert not any(
        "evil.example.com" in url for url in wikimedia.requests
    )  # outside the allow-list: never fetched
    assert not any(
        "/thumb/1.png" in url or "/thumb/2.png" in url for url in wikimedia.requests
    )  # NC and SVG skipped
    calls = len(wikimedia.requests)
    assert finder.find("railway level crossing gate", keep=1)[0].id == asset.id  # cached: no new requests
    assert len(wikimedia.requests) == calls


def test_finder_rejects_a_photo_whose_caption_does_not_match(finder_env):
    finder, backend, _, _ = finder_env
    backend.script = [
        BackendResult('{"fits": true, "caption": "a bowl of rice on a table", "reason": "x"}', 1, 1)
    ]
    assert finder.find("railway level crossing gate", keep=1, max_checks=1) == []


def test_finder_never_leaves_the_allowed_hosts(finder_env):
    finder, *_ = finder_env
    with pytest.raises(MediaError):
        finder._get("https://evil.example.com/x.png")
    redirect = httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(302, headers={"Location": "https://evil.example.com/"})
        )
    )
    finder.client = redirect
    with pytest.raises(MediaError):
        finder._get("https://upload.wikimedia.org/a.png")


# ---------------------------------------------------------------- the maths path through planner and service

MATHS_TEXT = (
    "Highest Common Factor. The HCF of 195, 312 and 546 is found by prime factorisation. "
    "Complementary angles: if the sum of the measures of two angles is 90 degrees, the angles are complementary. "
    "Example: find a if a + 15 + 2a = 90. "
)
MATHS_PLAN = {
    "title": "HCF and angles",
    "objectives": ["Find the HCF"],
    "sections": [{"heading": "HCF", "content": "The HCF is the biggest common factor [1].", "cites": [1]}],
    "key_points": ["HCF divides every number"],
    "vocabulary": [],
    "equations": [{"equation": "H₂O → H₂ + O₂", "meaning": "should be dropped for maths"}],
    "simulation": {"title": "x", "brief": "should be dropped for maths"},
    "concepts": [
        {"name": "HCF", "kind": "hcf", "explain": "Biggest common factor.", "cites": [1],
         "examples": [{"text": "HCF of 195, 312, 546", "numbers": [195, 312, 546], "answer": "13"}],
         "real_life": [{"title": "Equal groups", "story": "Packing sweets into equal boxes.", "image_query": "sweet boxes"}]},
        {"name": "Complementary angles", "kind": "complementary_angles", "cites": [1],
         "examples": [{"text": "a + 15 + 2a = 90", "equation": "a + 15 + 2a = 90", "answer": "25"}],
         "real_life": [{"title": "Ramp", "story": "A ramp and a wall.", "image_query": "wheelchair ramp"}]},
    ],
}  # fmt: skip


@pytest.fixture
def maths_env(env):  # noqa: F811
    service, backend, source = env
    make_text_pdf(source / "Class 7 - Maths - 3rd Chapter.pdf", [MATHS_TEXT * 3])
    document = service.add_file(source / "Class 7 - Maths - 3rd Chapter.pdf", enqueue=False).document
    assert maths.profile_is_maths(document.subject)
    service.extract_document(document.id)
    service.mark_all_reviewed(document.id)
    service.index_document(document.id)
    router = service.router
    router.config.tasks["lesson_plan"] = router.config.tasks["local_only"]
    service.settings.media_search = True
    return LessonService(service.engine, router, 0.1, service.settings), backend, document, service


class FakeFinder:
    def __init__(self, assets):
        self.assets, self.queries = assets, []

    def find(self, query, **kwargs):
        self.queries.append(query)
        return self.assets.get(query, [])


def test_maths_lesson_is_checked_and_gets_photos(maths_env):
    from sqlmodel import Session, select

    from app.db.models import Job, MediaAsset

    lessons, backend, document, service = maths_env
    backend.script = [BackendResult(json.dumps(MATHS_PLAN), 500, 500)]
    lesson = lessons.create("HCF and complementary angles", document_id=document.id)
    lessons.generate_plan(lesson.id)
    stored = lessons.get(lesson.id)
    plan = lessons.plan(stored)
    assert plan["profile"] == "maths" and plan["equations"] == [] and plan["simulation"] == {}
    assert "prime_factorisation" in backend.calls[-1]["messages"][0]["content"]
    warnings = json.loads(stored.warnings)
    assert any("'13'" in w and "39" in w for w in warnings)  # wrong AI answer corrected
    assert plan["concepts"][0]["examples"][0]["answer"] == "39"
    assert plan["concepts"][1]["examples"][0]["computed"] == "a = 25"
    assert plan["concepts"][0]["pages"] == [1]
    with Session(service.engine) as s:
        assert s.exec(select(Job).where(Job.kind == "media", Job.lesson_id == lesson.id)).first() is not None

    photo_file = service.settings.data_dir / "media" / "abc.png"
    photo_file.parent.mkdir(parents=True, exist_ok=True)
    photo_file.write_bytes(_png())
    with Session(service.engine) as s:
        asset = MediaAsset(query="sweet boxes", page_url="https://commons.wikimedia.org/wiki/File:x.png", title="Boxes",
                           author="A", license="CC0", local_path="media/abc.png", fits=True)  # fmt: skip
        s.add(asset)
        s.commit()
        s.refresh(asset)
    finder = FakeFinder({"sweet boxes": [asset]})
    result = lessons.find_photos(lesson.id, finder=finder)
    assert result == {"examples": 2, "with_photos": 1}
    plan = lessons.plan(lessons.get(lesson.id))
    assert plan["concepts"][0]["real_life"][0]["photos"] == [asset.id]
    assert (
        plan["concepts"][1]["real_life"][0]["photos"] == []
    )  # searched, nothing fitting: not searched again
    assert photo_queries(plan) == []
    assert [a.id for a in lessons.photos([asset.id, 999])] == [asset.id]
    photo_file.unlink()
    assert lessons.photos([asset.id]) == []  # a deleted file is never shown


def test_more_real_life_examples_are_added_and_photos_queued(maths_env):
    from sqlmodel import Session, select

    from app.db.models import Job

    lessons, backend, document, service = maths_env
    backend.script = [BackendResult(json.dumps(MATHS_PLAN), 500, 500)]
    lesson = lessons.create("HCF and complementary angles", document_id=document.id)
    lessons.generate_plan(lesson.id)
    lessons.find_photos(lesson.id, finder=FakeFinder({}))
    new = {"real_life": [{"title": "Cricket field", "story": "…", "image_query": "cricket field"},
                         {"title": "Equal groups", "story": "duplicate title", "image_query": "x"},
                         {"title": "Bus timetable", "story": "…", "image_query": "bus stand"}]}  # fmt: skip
    backend.script = [BackendResult(json.dumps(new), 50, 50)]
    assert lessons.add_real_life(lesson.id, "HCF") == {"added": 2}
    titles = [r["title"] for r in lessons.plan(lessons.get(lesson.id))["concepts"][0]["real_life"]]
    assert titles == ["Equal groups", "Cricket field", "Bus timetable"]
    with Session(service.engine) as s:
        assert s.exec(select(Job).where(Job.kind == "media", Job.status == "queued")).first() is not None
    with pytest.raises(ValueError):
        lessons.add_real_life(lesson.id, "Not a concept")


def test_word_problems_are_never_corrected():
    # Real case from the Class 7 book: a correct 320 was once 'corrected' to LCM(1280, 4) = 1280.
    reverse = {"text": "The product of two 2-digit numbers is 1280 and the GCD = 4. What is their LCM?",
               "numbers": [1280, 4], "answer": "320"}  # fmt: skip
    assert maths.check_example("lcm", reverse) == {
        "computed": "", "ok": None, "note": "word problem — shown as in the textbook, not re-computed"
    }  # fmt: skip
    plan = {"concepts": [{"name": "LCM", "kind": "lcm", "examples": [reverse]}]}
    assert maths.verify(plan) == [] and plan["concepts"][0]["examples"][0]["answer"] == "320"


def test_yes_no_answers_are_compared_by_meaning_and_names_are_readable():
    assert (
        maths.check_example("twin_primes", {"numbers": [3, 5], "answer": "Twin prime numbers"})["ok"] is True
    )
    assert (
        maths.check_example("twin_primes", {"numbers": [7, 11], "answer": "They are twin primes"})["ok"]
        is False
    )
    assert maths.check_example("co_primes", {"numbers": [10, 21], "answer": "Their only common factor is 1"})[
        "ok"
    ]
    assert maths.check_example("co_primes", {"numbers": [12, 18], "answer": "No, they are not co-prime"})[
        "ok"
    ]
    plan = {"concepts": [{"name": "twin_prime_numbers", "kind": "twin_primes"}, {"name": "prime_numbers", "kind": "prime_numbers"}]}  # fmt: skip
    maths.verify(plan)
    assert [c["name"] for c in plan["concepts"]] == ["Twin primes", "Prime and composite numbers"]


def test_slow_or_huge_downloads_are_cut_off(finder_env, monkeypatch):
    import app.media.finder as finder_module

    finder, *_ = finder_env
    candidate = finder_module.Candidate("commons", "https://commons.wikimedia.org/wiki/File:x.png",
                                        "https://upload.wikimedia.org/x.png", "x", "a", "CC0", "")  # fmt: skip
    monkeypatch.setattr(finder_module, "DOWNLOAD_SECONDS", -1.0)  # every download is 'too slow'
    with pytest.raises(MediaError, match="slower"):
        finder._download(candidate)
    monkeypatch.setattr(finder_module, "DOWNLOAD_SECONDS", 30.0)
    monkeypatch.setattr(finder_module, "MAX_BYTES", 10)
    with pytest.raises(MediaError, match="too large"):
        finder._download(candidate)


def test_the_teacher_can_reject_a_photo(maths_env):
    from sqlmodel import Session

    from app.db.models import MediaAsset

    lessons, backend, document, service = maths_env
    backend.script = [BackendResult(json.dumps(MATHS_PLAN), 500, 500)]
    lesson = lessons.create("HCF and complementary angles", document_id=document.id)
    lessons.generate_plan(lesson.id)
    with Session(service.engine) as s:
        asset = MediaAsset(query="sweet boxes", page_url="p", title="t", author="a", license="CC0", fits=True)
        s.add(asset)
        s.commit()
        s.refresh(asset)
    lessons.find_photos(lesson.id, finder=FakeFinder({"sweet boxes": [asset]}))
    lessons.reject_photo(lesson.id, asset.id)
    assert lessons.plan(lessons.get(lesson.id))["concepts"][0]["real_life"][0]["photos"] == []
    with Session(service.engine) as s:
        assert s.get(MediaAsset, asset.id).fits is False  # never chosen again for this phrase


@pytest.mark.parametrize(
    ("kind", "example", "ok"),
    [  # real cases from the Class 7 Maths book (end-to-end run, 09-Oct-2026)
        ("prime_factorisation", {"text": "24 = 2 × 2 × 2 × 3", "numbers": [24], "answer": "2 × 2 × 2 × 3"}, True),
        ("prime_factorisation", {"text": "Factorise 250", "numbers": [250], "answer": "250 = 2 × 5 × 5 × 3"}, False),
        ("hcf", {"text": "Reduce 247 to its simplest form.", "numbers": [209, 247], "answer": "11/13"}, None),
        ("hcf", {"text": "Find the HCF of 195, 312, 546.", "numbers": [195, 312, 546], "answer": "13"}, False),
        ("complementary_angles", {"text": "(a + 15)° and (2a)° are complementary. What is each angle?",
                                  "equation": "a + 15 + 2a = 90", "answer": "40° and 50°"}, None),
        ("complementary_angles", {"text": "Find the complement of an angle of 70°", "angles": [70, 20], "answer": "20°"}, True),
        ("supplementary_angles", {"text": "Find the supplement of 135°", "angles": [135], "answer": "55°"}, False),
        ("linear_equation", {"text": "Solve", "equation": "x - 5 = 3", "answer": "x = 7"}, False),
        ("lcm", {"text": "Find the LCM of 18, 30, 50.", "numbers": [18, 30, 50], "answer": "450"}, True),
    ],
)  # fmt: skip
def test_answers_are_only_judged_when_the_comparison_is_certain(kind, example, ok):
    assert maths.check_example(kind, example)["ok"] is ok


def test_logos_and_charts_are_never_used_as_photos(finder_env):
    from sqlmodel import Session

    from app.db.models import MediaAsset

    finder, backend, wikimedia, service = finder_env
    with Session(service.engine) as s:  # stored by an older version, before the title rule
        s.add(
            MediaAsset(query="open book", page_url="x", title="OBP logo", license="CC BY-SA 4.0", fits=True)
        )
        s.add(
            MediaAsset(query="open book", page_url="y", title="Open book on a desk", license="CC0", fits=True)
        )
        s.commit()
    assert [a.title for a in finder.find("open book", keep=1)] == ["Open book on a desk"]


def test_geometry_and_co_prime_scenes():
    tri = maths.visuals_for({"kind": "exterior_angle", "examples": [{"angles": [70, 70]}]})
    assert tri[0]["type"] == "triangle" and tri[0]["angles"] == [70.0, 70.0]
    assert maths.visuals_for({"kind": "triangle_angle_sum", "examples": []})[0]["angles"] == [60, 70]
    assert maths.visuals_for({"kind": "polygon_angle_sum", "examples": []})[0]["sides"][0] == 3
    venn = maths.visuals_for({"kind": "co_primes", "examples": [{"text": "10 and 21 are co-primes"}]})
    assert [s["type"] for s in venn] == ["venn"] and venn[0]["common"] == [] and venn[0]["lcm"] == 210
    assert {"triangle_angle_sum", "exterior_angle", "polygon_angle_sum"} <= set(maths.KINDS)
