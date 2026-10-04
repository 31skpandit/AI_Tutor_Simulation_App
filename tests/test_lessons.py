"""Phase 2: molecules, viewers, simulation checks, planner and lesson service (fake models, offline)."""

import json

import pytest

from app.lessons import planner, simulation
from app.lessons.molecules import build
from app.lessons.service import LessonService
from app.lessons.viewers import CSP, molecule_html, simulation_html, vendor_status
from app.llm.backend import BackendResult
from tests.conftest import FakeBackend
from tests.test_ingestion import TEXT_PAGE, env, make_text_pdf  # noqa: F401

GOOD_SKETCH = """// neutralisation demo
let drops = 0;
function setup() { createCanvas(860, 500); createButton('Add drop').mousePressed(() => drops++); }
function draw() { background(255); textSize(16); text('Drops: ' + drops, 20, 30); text('Observe: pH rises', 20, 480); }
"""

PLAN = {
    "title": "Neutralisation",
    "objectives": ["Explain neutralisation"],
    "sections": [{"heading": "What happens", "content": "Acid + base → salt + water [1].", "cites": [1]}],
    "key_points": ["Salt and water form"],
    "equations": [{"equation": "HCl + NaOH → NaCl + H₂O", "meaning": "neutralisation"}],
    "molecules": [{"name": "water", "formula": "H₂O"}],
    "simulation": {"title": "Titration", "brief": "Add NaOH drop by drop to HCl and watch the pH."},
    "vocabulary": [],
}


# ---------------------------------------------------------------- molecules & viewers


def test_pilot_molecules_have_2d_and_3d():
    for formula in ["H₂O", "H₂", "O₂", "HCl", "NaOH", "NaCl", "CuSO₄"]:
        molecule = build(formula=formula)
        assert molecule and molecule.svg.startswith("<?xml") and molecule.molblock, formula


def test_every_molecule_used_by_the_pilot_lessons_is_available():
    for name, formula in [
        ("ferrous sulphate", "FeSO₄·7H₂O"),
        ("washing soda", "Na₂CO₃·10H₂O"),
        ("alum", "KAl(SO₄)₂·12H₂O"),
        ("hydrogen ion", "H⁺"),
        ("hydroxide ion", "OH⁻"),
        ("carbon dioxide", "CO₂"),
        ("green vitriol", ""),
    ]:
        assert build(name, formula) is not None, (name, formula)


def test_hydrate_label_mentions_water_not_drawn_and_unknown_is_not_guessed():
    assert "water molecule(s) of crystallisation are not drawn" in build(formula="CuSO₄·5H₂O").name
    assert build(formula="Fe₂O₃") is None


def test_vendor_files_verified_and_pages_block_network():
    assert vendor_status() == {"p5.min.js": "ok", "3Dmol-min.js": "ok"}
    page = simulation_html(GOOD_SKETCH)
    assert "default-src 'none'" in page and "connect-src 'none'" in page and CSP in page
    assert "3Dmol" in molecule_html(build(formula="H₂O").molblock, "Water")


def test_tampered_vendor_file_is_refused(tmp_path, monkeypatch):
    from app.lessons import viewers

    (tmp_path / "p5.min.js").write_text("evil()")
    (tmp_path / "manifest.json").write_text(json.dumps({"sha256": {"p5.min.js": "0" * 64}}))
    monkeypatch.setattr(viewers, "VENDOR", tmp_path)
    viewers.vendor_js.cache_clear()
    with pytest.raises(viewers.VendorFileError, match="modified"):
        viewers.vendor_js("p5.min.js")
    viewers.vendor_js.cache_clear()


# ---------------------------------------------------------------- simulation checks


def test_good_sketch_passes_all_checks():
    assert simulation.check_sketch(GOOD_SKETCH) == []


@pytest.mark.parametrize(
    ("snippet", "reason"),
    [
        ("fetch('http://x')", "network"),
        ("localStorage.setItem('a', 1)", "storage"),
        ("window.parent.postMessage('x')", "surrounding app"),
        ("eval('1+1')", "eval"),
        ("loadImage('cat.png')", "loading files"),
    ],
)
def test_unsafe_code_is_rejected(snippet, reason):
    problems = simulation.check_sketch(GOOD_SKETCH + "\n" + snippet + ";")
    assert any(reason in p for p in problems), problems


def test_harmless_lookalikes_are_not_rejected():
    code = GOOD_SKETCH + "\nlet box = {top: 5}; let y = box.top + 1; let topValue = 3;"
    assert simulation.check_sketch(code) == []


def test_syntax_errors_are_caught_by_node():
    if simulation.node_syntax_error("let a = 1;") is not None:
        pytest.skip("node not usable")
    problems = simulation.check_sketch(GOOD_SKETCH + "\nfunction broken( {")
    assert any("syntax error" in p for p in problems)


def test_generation_feeds_problems_back_and_fixes(make_router):
    backend = FakeBackend(
        [
            BackendResult("fetch('x'); function setup(){}", 100, 100),
            BackendResult("```javascript\n" + GOOD_SKETCH + "```", 100, 100),
        ]
    )
    router = make_router(backend)
    router.config.tasks["simulation_code"] = router.config.tasks["local_only"]
    result = simulation.generate_simulation(router, "brief", "facts")
    assert result.ok and result.rounds == 1 and result.code.startswith("// neutralisation")
    assert "was rejected" in backend.calls[1]["messages"][-1]["content"]


# ---------------------------------------------------------------- planner & service


@pytest.fixture
def lesson_env(env):  # noqa: F811
    service, backend, source = env
    make_text_pdf(source / "chapter.pdf", [(TEXT_PAGE + " ") * 3])
    document = service.add_file(source / "chapter.pdf", enqueue=False).document
    service.extract_document(document.id)
    service.mark_all_reviewed(document.id)
    service.index_document(document.id)
    router = service.router
    router.config.tasks["lesson_plan"] = router.config.tasks["local_only"]
    router.config.tasks["simulation_code"] = router.config.tasks["no_cache"]
    service.settings.lesson_min_relevance = 0.1  # fake word-count embeddings score lower than the real model
    return LessonService(service.engine, router, 0.1), backend, document


def test_plan_lesson_checks_equations_and_maps_pages(lesson_env):
    lessons, backend, document = lesson_env
    backend.script = [BackendResult(json.dumps(PLAN), 500, 500), BackendResult(GOOD_SKETCH, 100, 100)]
    lesson = lessons.create("neutralisation acid base salt water", document_id=document.id)
    lessons.generate_plan(lesson.id)
    plan = lessons.plan(lessons.get(lesson.id))
    assert plan["equations"][0]["balanced"] is True
    assert plan["sections"][0]["pages"] == [1]
    assert plan["sources"] and lessons.get(lesson.id).status == "draft"
    lessons.generate_simulation(lesson.id)
    assert lessons.get(lesson.id).simulation_status == "ok"


def test_unbalanced_equation_gets_one_correction_round(lesson_env):
    lessons, backend, document = lesson_env
    wrong = dict(PLAN, equations=[{"equation": "H₂O → H₂ + O₂", "meaning": "x"}])
    right = dict(PLAN, equations=[{"equation": "2H₂O → 2H₂ + O₂", "meaning": "x"}])
    backend.script = [BackendResult(json.dumps(wrong), 1, 1), BackendResult(json.dumps(right), 1, 1)]
    lesson = lessons.create("acid base salt water", document_id=document.id)
    lessons.generate_plan(lesson.id)
    assert lessons.plan(lessons.get(lesson.id))["equations"][0]["balanced"] is True
    assert "not balanced" in backend.calls[-1]["messages"][-1]["content"]


def test_planning_without_matching_pages_fails_clearly(lesson_env):
    lessons, backend, document = lesson_env
    lesson = lessons.create("history of the Mughal empire", document_id=document.id)
    with pytest.raises(planner.PlanningError):
        lessons.generate_plan(lesson.id)
    assert lessons.get(lesson.id).status == "failed"


def test_edit_save_recheck_and_approve(lesson_env):
    lessons, backend, document = lesson_env
    backend.script = [BackendResult(json.dumps(PLAN), 1, 1)]
    lesson = lessons.create("acid base salt water", document_id=document.id)
    lessons.generate_plan(lesson.id)
    plan = lessons.plan(lessons.get(lesson.id))
    plan["equations"][0]["equation"] = "HCl + NaOH → NaCl + H₂O₂"  # teacher typo
    saved = lessons.save_plan(lesson.id, plan)
    assert saved.version == 2 and lessons.plan(saved)["equations"][0]["balanced"] is False
    assert lessons.save_simulation_code(lesson.id, "eval('x')")  # problems reported
    assert lessons.approve(lesson.id).status == "approved"


def test_lesson_jobs_run_through_the_worker(lesson_env, env):  # noqa: F811
    from app.jobs.runner import run_until_empty

    lessons, backend, document = lesson_env
    backend.script = [BackendResult(json.dumps(PLAN), 1, 1), BackendResult(GOOD_SKETCH, 1, 1)]
    lesson = lessons.create("acid base salt water", document_id=document.id)
    assert run_until_empty(env[0]) == 2  # plan job, then the simulation job it queues
    stored = lessons.get(lesson.id)
    assert stored.status == "draft" and stored.simulation_status == "ok"
