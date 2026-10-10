"""Builds docs/AI_Teaching_Studio_Code_Workflow.drawio — ONE page, for learning the codebase:
  • the technology stack (every tool and library, with version and purpose);
  • the end-to-end workflow, lane by lane, where every box is  file → function() → what it does.

Open with draw.io (app.diagrams.net → File → Open from → Device). Rebuild after code changes:
    uv run python docs/_source/gen_code_workflow.py
"""

from html import escape
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "AI_Teaching_Studio_Code_Workflow.drawio"

BASE = "whiteSpace=wrap;html=1;fontSize=11;align=left;spacingLeft=6;spacingRight=4;verticalAlign=top;spacingTop=4;"
KIND = {
    "ui": BASE + "rounded=1;fillColor=#dae8fc;strokeColor=#6c8ebf;",
    "svc": BASE + "rounded=1;fillColor=#d5e8d4;strokeColor=#82b366;",
    "ai": BASE + "rounded=1;fillColor=#e1d5e7;strokeColor=#9673a6;",
    "check": BASE + "rounded=1;fillColor=#fff2cc;strokeColor=#d6b656;",
    "db": BASE + "rounded=1;fillColor=#f5f5f5;strokeColor=#666666;",
    "js": BASE + "rounded=1;fillColor=#ffe6cc;strokeColor=#d79b00;",
    "ext": BASE + "rounded=1;dashed=1;fillColor=#ffffff;strokeColor=#666666;",
    "start": BASE + "rounded=1;fillColor=#60a917;fontColor=#ffffff;strokeColor=#2D7600;",
}
EDGE = "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=block;endFill=1;fontSize=10;"

cells: list[str] = []
counter = [0]


def box(key, label, x, y, w, h, style):
    cells.append(
        f'<mxCell id="{key}" value="{escape(label, quote=True)}" style="{style}" vertex="1" parent="1">'
        f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>'
    )


def arrow(a, b, label="", dashed=False):
    counter[0] += 1
    style = EDGE + ("dashed=1;strokeColor=#9673a6;" if dashed else "")
    cells.append(
        f'<mxCell id="a{counter[0]}" value="{escape(label, quote=True)}" style="{style}" edge="1" parent="1" '
        f'source="{a}" target="{b}"><mxGeometry relative="1" as="geometry"/></mxCell>'
    )


# ================================================================ heading + how to read
box("title", "<b>AI Teaching Studio — code workflow: file → function → what it does, and the technology stack</b>",
    0, 0, 3000, 50, "text;html=1;fontSize=30;align=left;verticalAlign=top;")  # fmt: skip
box(
    "guide",
    "<b>How to read:</b> Part A (top) lists every technology used and why. Part B follows the app from the start "
    "command to the classroom: each coloured lane is one stage; inside a lane read the boxes <b>left → right</b> "
    "(a lane continues on its next row). Every box shows <b>file</b> → <b>function()</b> and, in grey, what it does. "
    "Purple dashed arrows = an AI call through the router (lane 5).<br>"
    "<b>Colours:</b> blue = screen (ui/) · green = Python app code (app/) · purple = AI model / router · "
    "yellow = check or security · grey = database · orange = JavaScript in the browser (assets/) · white dashed = "
    "outside tool. Generated from the code by docs/_source/gen_code_workflow.py (07-Oct-2026).",
    0, 55, 3000, 80,
    "shape=note;whiteSpace=wrap;html=1;size=14;fillColor=#fffce8;strokeColor=#b3a34a;fontSize=14;align=left;"
    "spacingLeft=8;verticalAlign=top;",
)  # fmt: skip

# ================================================================ PART A — technology stack
STACK = [
    ("Runtime & packaging", "#d5e8d4", [
        ("Python 3.12.14", "the language of all app code"),
        ("uv 0.12", "installs packages only from uv.lock (SHA-256 hashes); `uv run …`"),
        ("Windows 11 + RTX 3050 4 GB", "everything runs on the teacher's laptop"),
        ("Node.js 24", "syntax check of simulations; builds the Word docs"),
    ]),
    ("User interface", "#dae8fc", [
        ("Streamlit 1.64.0", "web pages at localhost:8501 (ui/)"),
        ("streamlit components", "sealed iframes for simulations & 3D"),
        ("Microsoft Edge (headless)", "hidden browser that tests simulations"),
    ]),
    ("AI models", "#e1d5e7", [
        ("LiteLLM 1.102.1 (SDK)", "one interface to Ollama and OpenAI"),
        ("Ollama 0.34", "runs local models free on the GPU"),
        ("qwen3:4b-instruct", "local text: tutor, page summaries"),
        ("qwen3-vl:2b-instruct", "local vision: OCR of page images; checks lesson photos"),
        ("qwen3-embedding:0.6b", "local embeddings for search"),
        ("OpenAI gpt-5-nano / 5.4-mini / 5.2", "cloud: cheap answers, lessons, simulations, picture review, premium"),
    ]),
    ("Data & settings", "#f5f5f5", [
        ("SQLite (WAL)", "one file data/app.db for everything"),
        ("SQLModel 0.0.47", "tables as Python classes (app/db/models.py)"),
        ("NumPy 2.5.3", "vector search (cosine similarity)"),
        ("pydantic-settings 2.15.0", "settings from .env (ATS_*)"),
        ("PyYAML 6.0.3", "reads config/models.yaml"),
    ]),
    ("Documents & chemistry", "#fff2cc", [
        ("PyMuPDF 1.28.2", "PDF text and page images"),
        ("python-docx 1.2.0", "Word files"),
        ("Pillow 12.3.0", "photos / page images"),
        ("RDKit 2026.3.6", "molecule structures, 2D/3D coordinates, bonds"),
        ("in-house chemistry.py", "equation balancing checker"),
        ("Natural Earth (India view)", "offline map outlines, India's official boundaries"),
        ("GeoNames India", "563 000 places for the history maps (CC BY 4.0)"),
        ("Wikimedia Commons · Wikidata · Openverse", "free-licence real-life photos (CC0 / PD / CC BY / BY-SA)"),
    ]),
    ("Browser libraries (offline)", "#ffe6cc", [
        ("p5.js 2.3.3", "drawing engine of simulations"),
        ("3Dmol.js 2.5.5", "rotatable 3D molecule models"),
        ("labkit.js (hand-written)", "layout, labels, controls, apparatus"),
        ("chem3d.js (hand-written)", "3D electron / reaction player"),
        ("historykit.js (hand-written)", "timeline, map, cause → effect player"),
        ("mathkit.js (hand-written)", "factor tree, Venn, angles, 3D ramp/door/clock"),
    ]),
    ("Security & quality", "#f8cecc", [
        ("keyring 25.7.0", "API keys in Windows Credential Manager"),
        ("loguru 0.7.3", "logs (keys redacted)"),
        ("httpx 0.28.1", "model health checks; photo search (allow-listed hosts)"),
        ("pip-audit 2.10.1", "vulnerability audit (scripts/audit.ps1)"),
        ("pytest 9.1.1", "330 automated tests"),
        ("ruff 0.16.9", "lint and format"),
    ]),
    ("Documentation", "#f5f5f5", [
        ("docx 9.8.1 (npm)", "builds the blueprint & learning log .docx"),
        ("@resvg/resvg-js 2.6.2", "turns diagrams into images"),
        ("draw.io", "these architecture maps"),
        ("Git + GitHub", "version history (you commit & push yourself)"),
    ]),
]  # fmt: skip
AY = 160
box("partA", "<b>PART A — Technology stack (what is used, version, and why)</b>", 0, AY, 3000, 36,
    "text;html=1;fontSize=20;align=left;verticalAlign=top;")  # fmt: skip
COLW = 370
for i, (group, colour, items) in enumerate(STACK):
    x = i * (COLW + 6)
    h = 40 + 52 * len(items)
    box(f"st{i}", f"<b>{group}</b>", x, AY + 40, COLW, max(h, 360),
        f"rounded=1;html=1;fillColor={colour};strokeColor=#999999;verticalAlign=top;align=left;spacingLeft=8;fontSize=14;")  # fmt: skip
    for j, (name, why) in enumerate(items):
        box(f"st{i}_{j}", f"<b>{name}</b><br><font color='#555555'>{why}</font>", x + 10, AY + 75 + j * 52,
            COLW - 20, 46, BASE + "rounded=1;fillColor=#ffffff;strokeColor=#bbbbbb;")  # fmt: skip

# ================================================================ PART B — workflow lanes
# Each step: (file, function, what it does, kind)
LANES = [
    ("0 · Start the app", "#e8f5e9", [
        ("terminal", "uv run streamlit run ui/Home.py", "starts the web app on localhost:8501", "start"),
        ("ui/Home.py", "page()", "status page: checks, models, totals", "ui"),
        ("ui/common.py", "get_router()", "builds the AI router once (cached)", "ui"),
        ("app/llm/service.py", "build_router()", "assembles everything below", "svc"),
        ("app/core/config.py", "get_settings()", "reads .env (ATS_*), creates data/ folders", "svc"),
        ("app/core/logging.py", "setup_logging()", "log files; redact() hides keys", "check"),
        ("app/core/startup_checks.py", "assert_safe_to_start() → run_all()", "LiteLLM version, .pth files, no keys in .env, Ollama local, Streamlit local, keyring", "check"),
        ("app/llm/config.py", "load_models_config()", "config/models.yaml → ModelsConfig (tasks, prices, hosts)", "svc"),
        ("app/llm/litellm_backend.py", "LiteLLMBackend()", "the ONLY place LiteLLM is imported", "ai"),
        ("app/db/session.py", "make_engine()", "SQLite, WAL mode; migrations.apply()", "db"),
        ("app/llm/router.py", "LLMRouter(...)", "router ready (lane 5)", "ai"),
        ("ui/common.py", "get_ingestion() · get_worker()", "IngestionService + background Worker.start()", "ui"),
        ("app/jobs/runner.py", "Worker._loop → recover_stale() · claim_next() · run_job()", "runs queued jobs one by one", "svc"),
    ]),
    ("1 · Add a chapter", "#e3f2fd", [
        ("ui/pages/3_Syllabus_Library.py", "upload / live_status()", "add files, watch progress", "ui"),
        ("app/ingestion/service.py", "scan_source() · save_upload() · add_file()", "register new files", "svc"),
        ("app/ingestion/files.py", "file_kind() · sha256_file() · guess_metadata()", "type, fingerprint, class/subject/chapter from name", "svc"),
        ("app/db/models.py", "Document", "one row per unique file (duplicate SHA-256 skipped)", "db"),
        ("app/ingestion/service.py", "enqueue('extract')", "creates a Job row", "svc"),
        ("app/jobs/runner.py", "claim_next() → run_job()", "worker picks it up", "svc"),
        ("app/ingestion/service.py", "extract_document()", "page by page; resumable", "svc"),
        ("app/ingestion/extract.py", "iter_pages() → _pdf_pages / _image_pages / _read_text", "text layer if ≥ 25 words, else page image", "svc"),
        ("app/ingestion/service.py", "_reusable_ocr()", "same page image seen before → reuse", "svc"),
        ("app/ingestion/ocr.py", "ocr_page() → ocr_page_once()", "router task 'ocr' (qwen3-vl)", "ai"),
        ("app/ingestion/ocr.py", "looks_degenerate() · collapse_repeats()", "loop detected → task 'ocr_retry'", "check"),
        ("app/ingestion/ocr.py", "clean_ocr_text() · normalize_markdown_tables()", "tidy text, repair tables", "check"),
        ("app/db/models.py", "Page", "saved: 📝 needs review", "db"),
    ]),
    ("1b · Autopilot (automatic check → lesson)", "#e8f5e9", [
        ("app/ingestion/service.py", "extract_document() → autopilot_check()", "runs after every extraction", "svc"),
        ("app/ingestion/quality.py", "assess()", "clean / check with reasons (little text, odd characters, OCR tables …)", "check"),
        ("app/db/models.py", "Page.quality · quality_notes · auto_reviewed", "result stored per page", "db"),
        ("app/ingestion/service.py", "_guess_chapter_title() → guess_chapter_title()", "title from page 1", "svc"),
        ("app/ingestion/service.py", "enqueue('index')", "clean pages become searchable (lane 3)", "svc"),
        ("app/jobs/runner.py", "run_job('index') → auto_create_for_document()", "one draft lesson per chapter", "svc"),
        ("app/ingestion/quality.py", "find_chapters()", "a file with several chapters → page ranges (one lesson each)", "check"),
        ("app/lessons/service.py", "chapter_topic() · page_range() · generate_plan(whole_chapter)", "the whole chapter (its own pages) goes to the planner (lane 6)", "svc"),
        ("app/lessons/service.py", "pages_added_after()", "pages reviewed later → Rebuild notice", "check"),
        ("ui/pages/3_Syllabus_Library.py", "autopilot panel", "⚠️ pages with reasons, cloud re-read on click", "ui"),
    ]),
    ("2 · Review the text", "#e3f2fd", [
        ("ui/pages/4_Review_Text.py", "preview()", "image beside text, edit / preview tabs", "ui"),
        ("app/ingestion/extract.py", "render_page_preview()", "the page image you compare with", "svc"),
        ("app/ingestion/service.py", "update_page() · retry_page()", "save corrections / redo OCR", "svc"),
        ("app/ingestion/service.py", "reread_pages_cloud()", "optional: task 'ocr_cloud' (gpt-5.4-mini)", "ai"),
        ("app/ingestion/service.py", "mark_all_reviewed()", "reviewed pages may be indexed", "svc"),
    ]),
    ("3 · Make searchable", "#e3f2fd", [
        ("app/ingestion/service.py", "index_document() → _index_page()", "job 'index'", "svc"),
        ("app/ingestion/chunking.py", "chunk_text() · text_hash()", "≈ 1500-char passages, 200 overlap", "svc"),
        ("app/rag/store.py", "VectorStore.has_text()", "same passage stored before → skip", "check"),
        ("app/llm/router.py", "LLMRouter.embed('embed')", "qwen3-embedding vectors (no fallbacks)", "ai"),
        ("app/ingestion/enrich.py", "enrich_page() → parse_enrichment()", "task 'enrich': page summary, table/figure descriptions (search aids)", "ai"),
        ("app/rag/store.py", "VectorStore.add() → _bump_generation()", "Chunk rows + IndexState counter", "db"),
    ]),
    ("4 · AI Tutor", "#ede7f6", [
        ("ui/pages/5_AI_Tutor.py", "chat box / general_answer()", "question + filters + language + model switch", "ui"),
        ("app/rag/tutor.py", "answer()", "the whole answer flow", "svc"),
        ("app/rag/tutor.py", "embed_question()", "router.embed()", "ai"),
        ("app/rag/answer_cache.py", "lookup() · scope_key() · contrast_conflict()", "≥ 0.97 similar, same scope → ♻️ reuse", "check"),
        ("app/rag/tutor.py", "retrieve()", "relevant passages, threshold 0.50", "svc"),
        ("app/rag/store.py", "VectorStore.search(SearchFilters)", "NumPy cosine similarity over vectors", "db"),
        ("app/rag/tutor.py", "original_passages() · build_messages()", "only original reviewed text goes to the model", "check"),
        ("app/llm/router.py", "complete('tutor_answer' | '_cloud' | '_indic')", "local qwen3 or gpt-5-nano; HI/MR gpt-5.4-mini", "ai"),
        ("app/rag/tutor.py", "clean_answer() → TutorAnswer", "answer + citations [1] Ch. 5, p. 2", "svc"),
        ("app/rag/answer_cache.py", "save()", "remember for similar questions", "db"),
    ]),
    ("5 · Every AI call (router)", "#f3e5f5", [
        ("any module", "router.complete(task, messages)", "e.g. 'ocr', 'lesson_plan'", "ai"),
        ("app/llm/router.py", "_task()", "task from models.yaml: primary + fallbacks", "ai"),
        ("app/llm/router.py", "_cache_key() · _cache_get()", "same request → CacheEntry, $0", "db"),
        ("app/llm/router.py", "_preflight()", "host_of() allow-list · month_spend_usd() cap · premium approval", "check"),
        ("app/core/secrets.py", "get_secret('openai')", "key from Windows Credential Manager", "check"),
        ("app/llm/router.py", "_try_chat()", "one model; on failure next fallback", "ai"),
        ("app/llm/litellm_backend.py", "LiteLLMBackend.complete()", "litellm.completion → Ollama / OpenAI", "ai"),
        ("app/llm/router.py", "_log_call() · _cache_put()", "LLMCall row: tokens, cost, time", "db"),
        ("app/llm/router.py", "LLMResult / AllModelsFailed", "text back, or a clear failure", "ai"),
    ]),
    ("6 · Create a lesson", "#e8f5e9", [
        ("ui/pages/2_Lesson_Studio.py", "New lesson / live()", "chapter + topic, live job progress", "ui"),
        ("app/lessons/service.py", "LessonService.create()", "Lesson row + job 'lesson_plan'", "svc"),
        ("app/jobs/runner.py", "run_job()", "→ LessonService.generate_plan()", "svc"),
        ("app/lessons/planner.py", "plan_lesson() → gather_evidence()", "textbook passages, relevance ≥ 0.45", "svc"),
        ("app/llm/router.py", "complete('lesson_plan')", "gpt-5.4-mini writes the plan JSON", "ai"),
        ("app/lessons/planner.py", "parse_plan() · check_equations()", "sections ↔ pages, equations checked", "svc"),
        ("app/lessons/chemistry.py", "check_equation() → parse_species() · _count()", "atoms and charge balanced?", "check"),
        ("app/lessons/service.py", "_update(status='draft') → enqueue('simulation')", "saved, simulation queued", "db"),
    ]),
    ("7 · Write & check a simulation", "#fff8e1", [
        ("app/lessons/service.py", "generate_simulation()", "job 'simulation'", "svc"),
        ("app/lessons/planner.py", "simulation_facts()", "textbook facts for the experiment", "svc"),
        ("app/lessons/simulation.py", "generate_simulation()", "up to 3 fix rounds", "svc"),
        ("app/llm/router.py", "complete('simulation_code')", "gpt-5.4-mini writes const SIM (lab-kit prompt + example)", "ai"),
        ("app/lessons/simulation.py", "strip_fences() · check_sketch()", "① safety (FORBIDDEN) ② _labkit_rules()", "check"),
        ("app/lessons/simulation.py", "node_syntax_error()", "③ node --check", "check"),
        ("app/lessons/viewers.py", "simulation_html() · vendor_js()", "p5 + labkit.js + SIM in a no-network page (SHA-256 checked)", "svc"),
        ("app/lessons/browser_check.py", "check_in_browser() → _run() · _problems()", "④ hidden Edge presses every control, 60 frames/s", "check"),
        ("app/lessons/simulation.py", "review_visually()", "⑤ task 'simulation_review' looks at the pictures", "ai"),
        ("app/lessons/simulation.py", "blocking() → SimulationResult", "problems back to the AI, or saved", "svc"),
    ]),
    ("8 · Show & teach", "#e3f2fd", [
        ("ui/pages/2_Lesson_Studio.py · 1_Teach_Mode.py", "tabs / slides", "preview, edit, approve; present", "ui"),
        ("ui/lesson_views.py", "render_equations()", "✅ / ⚠️ equations", "ui"),
        ("ui/lesson_views.py", "render_molecules() → _molecule()", "3D models with labels", "ui"),
        ("app/lessons/molecules.py", "build() → resolve() · embed_3d() · _model_3d()", "table → RDKit 3D, ions apart, charge_text()", "svc"),
        ("app/lessons/viewers.py", "molecule_html()", "3Dmol.js viewer page", "js"),
        ("ui/lesson_views.py", "render_scene() → scene_or_reason()", "3D bonding / reaction scene", "ui"),
        ("app/lessons/reactions.py", "build_scene() → ionic_scene() · covalent_scene() · reaction_scene()", "computed electrons, bonds, atoms", "svc"),
        ("app/lessons/viewers.py", "chem3d_html()", "scene JSON + chem3d.js player", "js"),
        ("ui/lesson_views.py", "render_simulation()", "simulation_html → labkit.js + p5.js in the browser", "js"),
        ("app/lessons/service.py", "approve()", "lesson ready for Teach Mode", "db"),
    ]),
    ("8b · History lessons", "#fdf2e9", [
        ("app/ingestion/extract.py", "reading_order_text()", "two-column pages read left column, then right (line level)", "svc"),
        ("app/lessons/history.py", "profile(subject)", "History / Civics / Economics → 'history' lesson design", "svc"),
        ("app/rag/store.py", "document_text_hits()", "whole chapter in page order (not just a topic search)", "db"),
        ("app/lessons/history.py", "without_exercises()", "exercise pages (blanks, wrong pairs) never become facts", "check"),
        ("app/llm/router.py", "complete('lesson_plan')", "history prompt: timeline, periods, people, places, causes-effects", "ai"),
        ("app/lessons/history.py", "verify() → date_in_text() · event_near_date() · name_in_text()", "unproven dates, names, places removed and listed", "check"),
        ("app/lessons/geo.py", "geocode() → _candidates() · _similar() · _dominant()", "offline place list; placed only when unambiguous", "check"),
        ("app/lessons/history.py", "timeline_scene() · map_scene() · flow_scenes()", "scene data for the player", "svc"),
        ("app/lessons/viewers.py", "history_html()", "assets/historykit.js player (no network)", "js"),
        ("app/lessons/figures.py", "extract_figures() · portrait_of()", "textbook's own captioned pictures for slides / people", "svc"),
        ("ui/lesson_views.py", "render_timeline · render_map · render_cause_effect · render_people", "Lesson Studio tabs and Teach Mode slides", "ui"),
    ]),
    ("8c · Maths lessons & real-life photos", "#eef7ee", [
        ("app/lessons/planner.py", "lesson_profile(subject)", "Maths / Mathematics → 'maths' lesson design", "svc"),
        ("app/llm/router.py", "complete('lesson_plan')", "maths prompt: concepts, textbook examples, real-life stories + photo phrases", "ai"),
        ("app/lessons/maths.py", "verify() → check_example() · solve_linear() · hcf() · lcm()", "every answer re-computed; wrong AI answers replaced and listed", "check"),
        ("app/lessons/service.py", "generate_plan() → enqueue('media')", "photo search queued after the plan", "db"),
        ("app/jobs/runner.py", "run_job('media') → find_photos()", "one search per real-life example", "svc"),
        ("app/media/finder.py", "find() → wikidata_image() · search_commons() · search_openverse()", "allow-listed hosts; free licences only; no SVG/HTML", "ext"),
        ("app/media/finder.py", "_download() · check()", "thumbnail ≤ 1.5 MB; local qwen3-vl caption must match the wanted subject", "ai"),
        ("app/db/models.py", "MediaAsset", "photo file + credit: title, author, licence, link", "db"),
        ("app/lessons/maths.py", "visuals_for(concept)", "factor tree, Venn, division, runners, sieve, balance, angles, 3D objects", "svc"),
        ("app/lessons/viewers.py", "math_html()", "assets/mathkit.js player (no network)", "js"),
        ("ui/lesson_views.py", "render_concept()", "Visualise: 🌍 Real life · 🖼️ Photos · 📐 2D · 🧊 3D", "ui"),
        ("app/lessons/service.py", "add_real_life()", "'More real-life examples' button (≈ 0.2 ¢) → photos", "ai"),
        ("app/lessons/service.py", "reject_photo()", "teacher's 'Wrong photo' — never chosen again", "db"),
    ]),
    ("9 · 3D Lab · Settings · quality", "#f5f5f5", [
        ("ui/pages/7_Chemistry_3D_Lab.py", "examples / typed input", "any formula or equation → render_scene()", "ui"),
        ("ui/pages/6_Settings_and_Cost.py", "keys · budget · call log", "secrets.set_secret(), LLMCall table, find_browser()", "ui"),
        ("app/tools/verify_models.py", "verify() → health.ollama_models() · openai_models()", "are configured models available?", "check"),
        ("app/ingestion/__main__.py", "main()", "command line: scan / status / index / ask", "svc"),
        ("tests/ (pytest)", "330 tests", "chemistry rules, router, ingestion, browser runs, every page", "check"),
        ("scripts/audit.ps1", "pip-audit", "known vulnerabilities in the locked packages", "check"),
        ("docs/_source", "gen_doc.js · gen_interactions.js · gen_drawio.py · gen_code_workflow.py", "blueprint, learning log, these maps", "ext"),
    ]),
]  # fmt: skip

BY = AY + 40 + max(40 + 52 * len(items) for _, _, items in STACK) + 60
box("partB", "<b>PART B — End-to-end workflow, file by file (read each lane left → right)</b>", 0, BY, 3000, 36,
    "text;html=1;fontSize=20;align=left;verticalAlign=top;")  # fmt: skip
STEP_W, STEP_H, GAP, PER_ROW, LANE_TITLE = 250, 92, 30, 9, 200
y = BY + 45
first_box = {}
for li, (name, colour, steps) in enumerate(LANES):
    rows = (len(steps) + PER_ROW - 1) // PER_ROW
    lane_h = rows * (STEP_H + 40) + 30
    box(f"lane{li}", f"<b>{name}</b>", 0, y, 3000, lane_h,
        f"rounded=1;html=1;fillColor={colour};strokeColor=#999999;align=left;verticalAlign=middle;spacingLeft=12;fontSize=16;")  # fmt: skip
    prev = None
    for si, (file, func, what, kind) in enumerate(steps):
        r, c = divmod(si, PER_ROW)
        key = f"L{li}_{si}"
        label = f"<b>{file}</b><br>{func}<br><font color='#555555'>{what}</font>"
        box(
            key,
            label,
            LANE_TITLE + c * (STEP_W + GAP),
            y + 20 + r * (STEP_H + 40),
            STEP_W,
            STEP_H,
            KIND[kind],
        )
        if prev:
            arrow(prev, key)
        prev = key
        first_box.setdefault(li, key)
    y += lane_h + 20

# Stage-to-stage links and the AI calls that go through lane 5 (router)
arrow("L0_12", "L1_5", "worker runs jobs", dashed=False)
arrow("L1_12", "L2_0", "")
arrow("L2_4", "L4_0", "clean pages")
arrow("L2_7", "L7_3", "whole chapter")
arrow("L3_4", "L4_0", "")
arrow("L4_5", "L5_5", "passages searched")
arrow("L7_7", "L8_0", "")
arrow("L8_9", "L9_0", "")
arrow("L7_3", "L10_1", "history subject")
arrow("L7_3", "L11_0", "maths subject")
for src in ["L1_9", "L4_3", "L4_4", "L5_7", "L7_4", "L8_3", "L8_8", "L10_4", "L11_1", "L11_6", "L11_11"]:
    arrow(src, "L6_0", "", dashed=True)

xml = (
    '<mxfile host="app.diagrams.net" type="device"><diagram id="code" name="Code workflow and stack">'
    '<mxGraphModel dx="1400" dy="900" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" '
    'fold="1" page="0" pageScale="1" math="0" shadow="0"><root><mxCell id="0"/><mxCell id="1" parent="0"/>'
    + "".join(cells)
    + "</root></mxGraphModel></diagram></mxfile>"
)
OUT.write_text(xml, encoding="utf-8")
print(
    f"wrote {OUT} (1 page, {len(STACK)} stack groups, {len(LANES)} lanes, {sum(len(s) for _, _, s in LANES)} steps)"
)
