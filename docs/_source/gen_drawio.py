"""Builds docs/AI_Teaching_Studio_Architecture.drawio — architecture and flowcharts of the whole codebase.

Open the file with draw.io (desktop app, or app.diagrams.net → File → Open from → Device). Everything is on ONE
page (owner's wish): 8 framed sections laid out in a grid — zoom out to see the whole map, zoom in to read a
section. Re-run after code changes:   uv run python docs/_source/gen_drawio.py
"""

from html import escape
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "AI_Teaching_Studio_Architecture.drawio"

# ---------------------------------------------------------------- styles (one colour per kind of thing)
BASE = "whiteSpace=wrap;html=1;fontSize=12;"
S = {
    "ui": BASE + "rounded=1;fillColor=#dae8fc;strokeColor=#6c8ebf;",
    "svc": BASE + "rounded=1;fillColor=#d5e8d4;strokeColor=#82b366;",
    "ai": BASE + "rounded=1;fillColor=#e1d5e7;strokeColor=#9673a6;",
    "check": BASE + "rounded=1;fillColor=#fff2cc;strokeColor=#d6b656;",
    "store": BASE
    + "shape=cylinder3;boundedLbl=1;backgroundOutline=1;size=10;fillColor=#f5f5f5;strokeColor=#666666;",
    "ext": BASE + "rounded=1;dashed=1;fillColor=#ffffff;strokeColor=#666666;",
    "start": BASE + "ellipse;fillColor=#60a917;fontColor=#ffffff;strokeColor=#2D7600;fontStyle=1;",
    "end": BASE + "ellipse;fillColor=#1ba1e2;fontColor=#ffffff;strokeColor=#006EAF;fontStyle=1;",
    "stop": BASE + "ellipse;fillColor=#f8cecc;strokeColor=#b85450;",
    "dec": BASE + "rhombus;fillColor=#ffe6cc;strokeColor=#d79b00;fontSize=11;",
    "proc": BASE + "rounded=1;fillColor=#ffffff;strokeColor=#333333;",
    "person": "shape=umlActor;verticalLabelPosition=bottom;verticalAlign=top;html=1;outlineConnect=0;fontSize=12;",
    "group": "rounded=1;whiteSpace=wrap;html=1;fillColor=none;dashed=1;strokeColor=#999999;verticalAlign=top;"
    "align=left;spacingLeft=8;fontStyle=1;fontSize=13;container=0;",
    "title": "text;html=1;fontSize=20;fontStyle=1;align=left;verticalAlign=top;",
    "note": "shape=note;whiteSpace=wrap;html=1;size=14;fillColor=#fffce8;strokeColor=#b3a34a;fontSize=11;align=left;"
    "spacingLeft=6;verticalAlign=top;",
}
EDGE = "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=block;endFill=1;fontSize=11;"
DASHED = EDGE + "dashed=1;"


SECTION_W, SECTION_H, TOP = 1800, 1120, 260  # grid cell of one section on the single page
_count = 0


class Page:
    """One framed section of the single page. Its coordinates are local; they are shifted into its grid cell."""

    def __init__(self, name: str, title: str):
        global _count
        self.index = _count
        _count += 1
        self.ox = (self.index % 2) * SECTION_W
        self.oy = TOP + (self.index // 2) * SECTION_H
        self.name, self.cells, self.n, self.prefix = name, [], 0, f"s{self.index}_"
        self.cells.append(  # frame around the section
            f'<mxCell id="{self.prefix}frame" value="" style="rounded=1;arcSize=2;fillColor=#fbfbfb;'
            f'strokeColor=#bbbbbb;strokeWidth=2;" vertex="1" parent="1"><mxGeometry x="{self.ox}" y="{self.oy}" '
            f'width="{SECTION_W - 60}" height="{SECTION_H - 60}" as="geometry"/></mxCell>'
        )
        self.node("title", title, 20, 10, 1600, 40, "title")

    def node(self, key, label, x, y, w=170, h=60, kind="proc"):
        self.cells.append(
            f'<mxCell id="{self.prefix}{key}" value="{escape(label, quote=True)}" style="{S[kind]}" vertex="1" '
            f'parent="1"><mxGeometry x="{x + self.ox + 20}" y="{y + self.oy + 10}" width="{w}" height="{h}" '
            'as="geometry"/></mxCell>'
        )
        return key

    def edge(self, src, tgt, label="", dashed=False, style=""):
        self.n += 1
        st = (DASHED if dashed else EDGE) + style
        self.cells.append(
            f'<mxCell id="{self.prefix}e{self.n}" value="{escape(label, quote=True)}" style="{st}" edge="1" '
            f'parent="1" source="{self.prefix}{src}" target="{self.prefix}{tgt}">'
            '<mxGeometry relative="1" as="geometry"/></mxCell>'
        )


def legend(p: Page, x: int, y: int) -> None:
    p.node("lg", "Legend", x, y, 230, 250, "group")
    items = [("ui", "Screen (Streamlit page)"), ("svc", "App code (Python)"), ("ai", "AI model call"),
             ("check", "Automatic check"), ("dec", "Decision"), ("store", "Stored data")]  # fmt: skip
    for k, (kind, text) in enumerate(items):
        h = 40 if kind in {"dec", "store"} else 28
        p.node(f"lg{k}", text, x + 15, y + 30 + k * 36, 200, h if kind != "dec" else 34, kind)


pages: list[Page] = []

# ================================================================ 1. system overview
p = Page(
    "1 · System overview",
    "1 · AI Teaching Studio — system architecture (everything runs on the teacher's laptop)",
)
p.node("teacher", "Teacher", 40, 120, 40, 70, "person")
p.node("students", "Students<br>(in class)", 40, 260, 40, 70, "person")

p.node("g_ui", "User interface — Streamlit, http://localhost:8501 only (ui/)", 140, 70, 1060, 190, "group")
ui = [("home", "Home<br><i>checks, models, totals</i>"), ("lib", "Syllabus Library<br><i>add files, progress</i>"),
      ("rev", "Review Text<br><i>check & correct pages</i>"), ("tutor", "AI Tutor<br><i>answers with page refs</i>"),
      ("studio", "Lesson Studio<br><i>create, edit, approve</i>"), ("teach", "Teach Mode<br><i>full-screen slides</i>"),
      ("lab3d", "3D Chemistry Lab<br><i>electrons & atoms</i>"), ("settings", "Settings & Cost<br><i>keys, budget, log</i>")]  # fmt: skip
for i, (k, t) in enumerate(ui):
    p.node(k, t, 160 + (i % 4) * 255, 105 + (i // 4) * 75, 235, 60, "ui")

p.node("g_app", "Application code (app/)", 140, 300, 1060, 300, "group")
p.node(
    "ingest",
    "<b>Ingestion</b> app/ingestion/<br>files → extract / OCR → review → chunk → embed → index",
    160,
    340,
    240,
    90,
    "svc",
)
p.node(
    "rag",
    "<b>Tutor (RAG)</b> app/rag/<br>vector search · answer from original passages · answer cache",
    420,
    340,
    240,
    90,
    "svc",
)
p.node(
    "lessons",
    "<b>Lessons</b> app/lessons/<br>planner · equation checker · molecules · simulations · 3D scenes",
    680,
    340,
    240,
    90,
    "svc",
)
p.node(
    "jobs",
    "<b>Background worker</b> app/jobs/runner.py<br>extract · index · reread_cloud · lesson_plan · simulation",
    940,
    340,
    240,
    90,
    "svc",
)
p.node(
    "router",
    "<b>LLM Router</b> app/llm/router.py<br>task → model, fallbacks, budget cap, cache, host allow-list, cost log",
    300,
    470,
    330,
    100,
    "ai",
)
p.node(
    "core",
    "<b>Core</b> app/core/<br>settings (.env) · startup security checks · secrets · logging",
    680,
    470,
    240,
    100,
    "svc",
)
p.node(
    "checks",
    "<b>Simulation checks</b><br>safety · lab-kit rules · node --check · hidden browser · picture review",
    940,
    470,
    240,
    100,
    "check",
)

p.node("g_ext", "AI models", 140, 640, 520, 150, "group")
p.node(
    "litellm", "LiteLLM 1.102.1 (SDK only)<br>imported only after security checks", 160, 680, 200, 90, "ext"
)
p.node(
    "ollama",
    "<b>Ollama (local, free)</b><br>qwen3:4b-instruct · qwen3-vl:2b-instruct · qwen3-embedding:0.6b",
    380,
    670,
    260,
    60,
    "ai",
)
p.node(
    "openai",
    "<b>OpenAI (paid, budget-capped)</b><br>gpt-5-nano · gpt-5.4-mini · gpt-5.2 (approval)",
    380,
    740,
    260,
    45,
    "ai",
)

p.node("g_store", "Data on this laptop", 700, 640, 500, 150, "group")
p.node(
    "db",
    "data/app.db (SQLite)<br>documents, pages, chunks+vectors, lessons, jobs, AI-call log, caches",
    715,
    675,
    220,
    100,
    "store",
)
p.node("src", "source/<br>your textbook files", 950, 675, 110, 100, "store")
p.node("keys", "Windows Credential Manager<br>API keys", 1075, 675, 115, 100, "store")

p.node("g_browser", "Shown in the browser (sealed frames, no internet)", 1230, 70, 300, 520, "group")
p.node(
    "vendor",
    "assets/vendor/<br>p5.js 2.3.3 · 3Dmol.js 2.5.5<br>(SHA-256 checked)",
    1250,
    110,
    260,
    70,
    "store",
)
p.node("labkit", "assets/labkit.js<br>layout, labels, controls, apparatus, setups", 1250, 200, 260, 70, "svc")
p.node("sim", "AI-written simulation (const SIM)", 1250, 290, 260, 50, "ai")
p.node("chem3d", "assets/chem3d.js<br>3D bonding & reaction player", 1250, 360, 260, 60, "svc")
p.node("mol3d", "3Dmol molecule viewer<br>atom & ion labels", 1250, 440, 260, 60, "svc")
p.node("edge", "Hidden Edge/Chrome<br>(only for automatic tests)", 1250, 520, 260, 50, "ext")

p.edge("teacher", "g_ui")
p.edge("students", "tutor", dashed=True, label="questions")
p.edge("lib", "ingest")
p.edge("rev", "ingest")
p.edge("tutor", "rag")
p.edge("studio", "lessons")
p.edge("lab3d", "lessons")
p.edge("ingest", "router")
p.edge("rag", "router")
p.edge("lessons", "router")
p.edge("jobs", "ingest", dashed=True, label="runs")
p.edge("jobs", "lessons", dashed=True, label="runs")
p.edge("lessons", "checks")
p.edge("router", "litellm")
p.edge("litellm", "ollama")
p.edge("litellm", "openai")
p.edge("router", "keys", dashed=True, label="key")
p.edge("ingest", "db", dashed=True)
p.edge("ingest", "src", dashed=True)
p.edge("router", "db", dashed=True, label="cost log")
p.edge("teach", "sim", dashed=True)
p.edge("checks", "edge", dashed=True)
p.node("n1", "Security: keys never in files · LiteLLM pinned & hash-locked · AI calls only to allowed hosts · "
       "localhost-only UI · every browser frame blocks network access", 140, 815, 1060, 40, "note")  # fmt: skip
legend(p, 1290, 610)
pages.append(p)

# ================================================================ 2. ingestion
p = Page(
    "2 · Textbook ingestion",
    "2 · Adding a textbook chapter (app/ingestion/service.py, extract.py, ocr.py, chunking.py, enrich.py)",
)
X = 60
p.node("s", "File added<br>source/ folder or upload", X, 70, 170, 60, "start")
p.node("hash", "SHA-256 of the file", X, 160, 170, 50)
p.node("d1", "Same file<br>already known?", X, 240, 170, 90, "dec")
p.node("skip", "Skip<br>(even if renamed)", X + 230, 255, 140, 60, "stop")
p.node("reg", "Register Document<br>class / subject / chapter guessed from name", X, 360, 170, 70, "svc")
p.node("job", "Queue job 'extract'<br>(resumable, background)", X, 460, 170, 60, "svc")
p.node("store1", "app.db", X + 230, 455, 100, 70, "store")

Y = 70
C2 = 520
p.node("page", "For each page", C2, Y, 170, 50, "proc")
p.node("d2", "PDF text layer<br>≥ 25 words?", C2, Y + 80, 170, 90, "dec")
p.node("txt", "Use the text layer<br>(instant, free)", C2 + 240, Y + 95, 160, 60, "svc")
p.node("img", "Render page image<br>(≤ 1600 px)", C2, Y + 200, 170, 60, "svc")
p.node("d3", "Same image<br>seen before?", C2, Y + 290, 170, 90, "dec")
p.node("reuse", "Reuse earlier OCR", C2 + 240, Y + 305, 160, 60, "svc")
p.node(
    "ocr",
    "OCR — task 'ocr'<br>qwen3-vl:2b-instruct (local)<br>fallback gpt-5-nano",
    C2,
    Y + 410,
    170,
    75,
    "ai",
)
p.node("d4", "Line repeated<br>in a loop?", C2, Y + 515, 170, 90, "dec")
p.node("retry", "Retry — task 'ocr_retry'<br>repeat_penalty 1.1", C2 + 240, Y + 530, 160, 60, "ai")
p.node("clean", "Clean up: remove repeats,<br>repair Markdown tables", C2, Y + 635, 170, 60, "check")
p.node("saved", "Page saved:<br>📝 needs review", C2, Y + 725, 170, 60, "store")

C3 = 1000
p.node("review", "Teacher: Review Text<br>compare image ↔ text, correct", C3, Y, 200, 60, "ui")
p.node("d5", "Table / diagram<br>read badly?", C3, Y + 90, 200, 90, "dec")
p.node(
    "cloud",
    "☁️ Re-read with cloud<br>task 'ocr_cloud' gpt-5.4-mini<br>≈ $0.005 / page",
    C3 + 250,
    Y + 100,
    190,
    75,
    "ai",
)
p.node("ok", "✅ Save & mark reviewed", C3, Y + 210, 200, 50, "ui")
p.node("idx", "Make searchable → job 'index'", C3, Y + 290, 200, 50, "svc")
p.node("chunk", "Split into passages<br>(≈ 1500 chars, 200 overlap)", C3, Y + 370, 200, 60, "svc")
p.node("d6", "Passage already<br>stored (hash)?", C3, Y + 460, 200, 90, "dec")
p.node("emb", "Embed — task 'embed'<br>qwen3-embedding:0.6b (local)", C3, Y + 580, 200, 60, "ai")
p.node(
    "enr",
    "Page summary + table/figure<br>descriptions — task 'enrich'<br>(search aids only)",
    C3 + 250,
    Y + 575,
    190,
    75,
    "ai",
)
p.node(
    "vec",
    "Chunks + vectors in app.db<br>IndexState.generation + 1<br>✅ searchable",
    C3,
    Y + 680,
    200,
    75,
    "end",
)

for a, b, lab in [("s", "hash", ""), ("hash", "d1", ""), ("d1", "skip", "Yes"), ("d1", "reg", "No"), ("reg", "job", ""),
                  ("job", "store1", ""), ("job", "page", ""), ("page", "d2", ""), ("d2", "txt", "Yes"), ("d2", "img", "No"),
                  ("img", "d3", ""), ("d3", "reuse", "Yes"), ("d3", "ocr", "No"), ("ocr", "d4", ""), ("d4", "retry", "Yes"),
                  ("d4", "clean", "No"), ("retry", "clean", ""), ("txt", "clean", ""), ("reuse", "clean", ""),
                  ("clean", "saved", ""), ("saved", "review", ""), ("review", "d5", ""), ("d5", "cloud", "Yes"),
                  ("cloud", "review", "review again"), ("d5", "ok", "No"), ("ok", "idx", ""), ("idx", "chunk", ""),
                  ("chunk", "d6", ""), ("d6", "emb", "No"), ("emb", "vec", ""), ("emb", "enr", ""), ("enr", "vec", "")]:  # fmt: skip
    p.edge(a, b, lab)
p.node("n2", "<b>3 levels of de-duplication:</b> whole file (SHA-256) · page image (hash → reuse OCR) · passage text "
       "(hash → stored once). Review is required before indexing (ATS_REQUIRE_REVIEW).", 40, 640, 380, 90, "note")  # fmt: skip
legend(p, 40, 760)
pages.append(p)

# ================================================================ 3. tutor
p = Page(
    "3 · AI Tutor (RAG)",
    "3 · Answering a question from the textbook (app/rag/tutor.py, store.py, answer_cache.py)",
)
X = 80
p.node("q", "Question typed<br>(filters: class / subject / chapter; language)", X, 70, 220, 70, "start")
p.node("emb", "Embed the question<br>qwen3-embedding:0.6b", X, 170, 220, 60, "ai")
p.node(
    "dc",
    "Similar question answered before?<br>similarity ≥ 0.97, same filters & language,<br>index unchanged, no contrast words",
    X - 20,
    260,
    260,
    130,
    "dec",
)
p.node("hit", "♻️ Show the saved answer<br>(instant, free)", X + 330, 290, 200, 70, "end")
p.node("srch", "Vector search (SQLite + NumPy)<br>top passages within the filters", X, 420, 220, 60, "svc")
p.node("dr", "Best match<br>≥ 0.50 relevance?", X, 510, 220, 100, "dec")
p.node(
    "nc",
    "“This is not covered in the uploaded<br>textbook pages.” (optional general<br>answer, clearly marked)",
    X + 330,
    525,
    240,
    75,
    "stop",
)
p.node(
    "orig",
    "Take the ORIGINAL reviewed passages<br>(summaries only helped to find them)",
    X,
    640,
    220,
    70,
    "check",
)
p.node("dl", "Language?", X, 740, 220, 80, "dec")
p.node(
    "en",
    "English: task 'tutor_answer'<br>local qwen3:4b-instruct<br>or 'tutor_answer_cloud' gpt-5-nano",
    X + 330,
    660,
    240,
    70,
    "ai",
)
p.node(
    "hm",
    "Hindi / Marathi: task<br>'tutor_answer_indic' gpt-5.4-mini<br>(terms kept in English)",
    X + 330,
    760,
    240,
    70,
    "ai",
)
p.node(
    "ans", "Answer with citations [1] Ch. 5, page 2<br>+ source passages shown", X + 680, 700, 240, 70, "end"
)
p.node(
    "save",
    "Save in answer cache<br>(question vector, scope, index generation)",
    X + 680,
    810,
    240,
    60,
    "store",
)
for a, b, lab in [("q", "emb", ""), ("emb", "dc", ""), ("dc", "hit", "Yes"), ("dc", "srch", "No"), ("srch", "dr", ""),
                  ("dr", "nc", "No"), ("dr", "orig", "Yes"), ("orig", "dl", ""), ("dl", "en", "English"),
                  ("dl", "hm", "HI / MR"), ("en", "ans", ""), ("hm", "ans", ""), ("ans", "save", "")]:  # fmt: skip
    p.edge(a, b, lab)
p.node("n3", "<b>Why these rules (measured):</b><br>• 0.50 threshold: in-chapter questions scored 0.70–0.84, unrelated "
       "0.22–0.34.<br>• Generated descriptions once swapped acidity/basicity → the tutor only sees original text.<br>"
       "• SQLite reuses row ids → a generation counter invalidates old cached answers.", 780, 80, 460, 120, "note")  # fmt: skip
legend(p, 1300, 80)
pages.append(p)

# ================================================================ 4. router
p = Page(
    "4 · LLM router", "4 · Every AI call goes through one router (app/llm/router.py + config/models.yaml)"
)
X = 80
p.node("boot", "App start", X, 70, 180, 50, "start")
p.node(
    "sc",
    "Startup security checks<br>LiteLLM version pinned & not 1.82.7/8 · no .pth hijack ·<br>no keys in .env · Ollama on localhost · Streamlit localhost",
    X - 40,
    150,
    260,
    90,
    "check",
)
p.node("dsc", "All OK?", X, 270, 180, 80, "dec")
p.node("refuse", "Refuse to start<br>(LiteLLM never imported)", X + 260, 280, 180, 60, "stop")
p.node("imp", "Import LiteLLM (SDK only, local price list,<br>no callbacks)", X, 380, 180, 70, "svc")

C = 560
p.node(
    "call",
    "complete(task, messages)<br>e.g. 'ocr', 'tutor_answer', 'simulation_code'",
    C,
    70,
    240,
    60,
    "start",
)
p.node(
    "spec",
    "Read the task from models.yaml<br>primary + fallbacks, max_tokens,<br>json_output, ollama_options",
    C,
    160,
    240,
    70,
    "svc",
)
p.node("dcache", "Same request<br>cached?", C, 260, 240, 80, "dec")
p.node("cached", "Return cached answer ($0)", C + 300, 270, 180, 60, "end")
p.node("next", "Next model in the list", C, 370, 240, 50, "proc")
p.node("dhost", "Host on the<br>allow-list?", C, 450, 240, 80, "dec")
p.node(
    "dpaid",
    "Paid model: key in Credential<br>Manager, under monthly cap ($5),<br>premium approved?",
    C - 10,
    560,
    260,
    110,
    "dec",
)
p.node("send", "Call the model via LiteLLM<br>(retry on short failures)", C, 700, 240, 60, "ai")
p.node("dok", "Success?", C, 790, 240, 70, "dec")
p.node("log", "Log LLMCall: tokens, cost, time<br>save in cache · return text", C + 300, 795, 220, 60, "end")
p.node("more", "More fallbacks?", C + 320, 450, 180, 80, "dec")
p.node("fail", "AllModelsFailed<br>(shown clearly to the teacher)", C + 560, 460, 180, 60, "stop")
for a, b, lab in [("boot", "sc", ""), ("sc", "dsc", ""), ("dsc", "refuse", "No"), ("dsc", "imp", "Yes"),
                  ("call", "spec", ""), ("spec", "dcache", ""), ("dcache", "cached", "Yes"), ("dcache", "next", "No"),
                  ("next", "dhost", ""), ("dhost", "more", "No"), ("dhost", "dpaid", "Yes"), ("dpaid", "send", "OK / local"),
                  ("dpaid", "more", "blocked"), ("send", "dok", ""), ("dok", "log", "Yes"), ("dok", "more", "No"),
                  ("more", "next", "Yes"), ("more", "fail", "No")]:  # fmt: skip
    p.edge(a, b, lab)
p.node("n4", "<b>Embedding calls</b> use embed() with NO fallbacks — vectors from different models cannot be mixed.<br>"
       "<b>Costs</b> appear on Settings & Cost; local models always cost $0.", 40, 500, 380, 90, "note")  # fmt: skip
legend(p, 1300, 600)
pages.append(p)

# ================================================================ 5. lessons + simulations
p = Page(
    "5 · Lessons & simulations",
    "5 · Lesson Studio → checked simulation → Teach Mode (app/lessons/*, app/jobs/runner.py)",
)
X = 60
p.node("new", "Teacher: New lesson<br>(chapter + topic)", X, 70, 190, 60, "start")
p.node("jp", "Job 'lesson_plan'", X, 160, 190, 45, "svc")
p.node("ev", "Find textbook passages<br>(relevance ≥ 0.45)", X, 235, 190, 60, "svc")
p.node("dev", "Enough passages?", X, 325, 190, 80, "dec")
p.node("pf", "Lesson ❌ failed<br>(reason shown)", X + 230, 335, 150, 60, "stop")
p.node(
    "plan",
    "Write plan JSON — task 'lesson_plan'<br>gpt-5.4-mini: sections + pages, equations,<br>molecules, simulation idea",
    X - 10,
    435,
    210,
    85,
    "ai",
)
p.node("eq", "Equation checker (in-house)<br>atoms and charge balanced?", X, 550, 190, 60, "check")
p.node("deq", "All balanced?", X, 640, 190, 70, "dec")
p.node("fix1", "One correction round<br>with the exact problem", X + 230, 645, 150, 60, "ai")
p.node("draft", "Save 📝 draft<br>queue job 'simulation'", X, 740, 190, 60, "store")

C = 470
p.node(
    "gen",
    "Write const SIM — task 'simulation_code'<br>gpt-5.4-mini + lab kit instructions,<br>apparatus, setups, hand-checked example",
    C,
    70,
    260,
    85,
    "ai",
)
p.node("c1", "① Safety: no internet, storage, eval,<br>access to the app", C, 185, 260, 55, "check")
p.node(
    "c2", "② Lab-kit rules: labLabel only, lab controls,<br>every control animated", C, 260, 260, 55, "check"
)
p.node("c3", "③ Syntax: node --check", C, 335, 260, 45, "check")
p.node(
    "c4",
    "④ Run in hidden Edge/Chrome: every button,<br>choice, slider used; 60 frames/s; errors?<br>controls that change nothing?",
    C,
    400,
    260,
    75,
    "check",
)
p.node(
    "c5",
    "⑤ Picture review — task 'simulation_review'<br>start + DURING/AFTER each control vs<br>textbook facts (vision, ≈ 1–2 ¢)",
    C,
    495,
    260,
    75,
    "ai",
)
p.node("dprob", "Problems?", C, 595, 260, 70, "dec")
p.node("dround", "Fix rounds<br>left (≤ 3)?", C + 320, 400, 170, 90, "dec")
p.node("back", "Send the problems back<br>to the AI", C + 320, 250, 170, 60, "ai")
p.node("ok", "Save simulation ✅<br>(picture notes shown as a blue box)", C, 700, 260, 60, "store")
p.node(
    "bad",
    "Only picture notes left → shown with notes;<br>other problems → warning, not shown",
    C + 320,
    600,
    230,
    70,
    "stop",
)

R = 1130
p.node(
    "prev",
    "Teacher previews in Lesson Studio:<br>Content · Equations & molecules ·<br>3D scenes · Simulation · Sources",
    R,
    70,
    260,
    80,
    "ui",
)
p.node("dgood", "Looks right?", R, 180, 260, 80, "dec")
p.node(
    "chg",
    "Edit text / Change request +<br>🔁 Regenerate (or edit code →<br>checks ①–④ again)",
    R + 20,
    290,
    220,
    75,
    "ui",
)
p.node("appr", "✅ Approve", R, 400, 260, 50, "ui")
p.node(
    "tm",
    "Teach Mode slides:<br>title → sections → equations → 3D molecules →<br>3D bonding/reaction scenes → simulation → key points",
    R - 20,
    480,
    300,
    85,
    "end",
)
for a, b, lab in [("new", "jp", ""), ("jp", "ev", ""), ("ev", "dev", ""), ("dev", "pf", "No"), ("dev", "plan", "Yes"),
                  ("plan", "eq", ""), ("eq", "deq", ""), ("deq", "fix1", "No"), ("fix1", "eq", ""), ("deq", "draft", "Yes"),
                  ("draft", "gen", ""), ("gen", "c1", ""), ("c1", "c2", ""), ("c2", "c3", ""), ("c3", "c4", ""),
                  ("c4", "c5", "passed"), ("c5", "dprob", ""), ("dprob", "ok", "No"), ("dprob", "dround", "Yes"),
                  ("dround", "back", "Yes"), ("back", "gen", ""), ("dround", "bad", "No"), ("ok", "prev", ""),
                  ("prev", "dgood", ""), ("dgood", "chg", "No"), ("chg", "prev", ""), ("dgood", "appr", "Yes"),
                  ("appr", "tm", "")]:  # fmt: skip
    p.edge(a, b, lab)
p.node("n5", "Failures at ①–④ skip the paid picture review (cheap checks first). The simulation runs in a sealed frame "
       "with a no-network policy; p5.js and the lab kit are local files.", R - 20, 610, 300, 90, "note")  # fmt: skip
legend(p, 1450, 720)
pages.append(p)

# ================================================================ 6. 3D chemistry
p = Page(
    "6 · 3D chemistry scenes",
    "6 · 3D bonding & reaction scenes — computed, no AI (app/lessons/reactions.py → assets/chem3d.js)",
)
X = 560
p.node(
    "in",
    "Formula or equation<br>(lesson molecules & equations,<br>teacher's extras, 3D Lab page)",
    X,
    60,
    240,
    75,
    "start",
)
p.node("darrow", "Has an arrow (→)?", X, 165, 240, 80, "dec")

L = 120
p.node("dbal", "Balanced in atoms<br>and charge?", L, 290, 200, 90, "dec")
p.node("dtab", "Every substance in the<br>checked molecule table<br>(72 entries)?", L, 410, 200, 100, "dec")
p.node(
    "lay",
    "Lay out each side in 3D (RDKit)<br>hydrate water round the salt,<br>e⁻ as free electrons",
    L,
    540,
    200,
    75,
    "svc",
)
p.node("map", "Match atoms: unchanged ions/molecules<br>first, then keep most bonds", L, 640, 200, 70, "svc")
p.node(
    "rs",
    "Reaction scene, 4 steps:<br>reactants → bonds break →<br>atoms rearrange → products",
    L,
    735,
    200,
    75,
    "end",
)

M = 560
p.node(
    "dion",
    "One metal (Li, Be, Na, Mg,<br>Al, K, Ca) + one non-metal<br>(N, O, F, P, S, Cl)?",
    M,
    290,
    240,
    110,
    "dec",
)
p.node("dch", "Charges balance?<br>(metal × given = non-metal × taken)", M, 430, 240, 90, "dec")
p.node(
    "shell",
    "Shells from atomic number<br>(2, 8, 8, 2); nearest anion<br>receives each electron",
    M,
    550,
    240,
    75,
    "svc",
)
p.node(
    "is",
    "Ionic scene, 4 steps:<br>atoms & valency → electron transfer →<br>ions formed → attraction",
    M,
    655,
    240,
    75,
    "end",
)

R = 1000
p.node("dcov", "In the table, one molecule,<br>non-metals, no charges?", R, 290, 220, 100, "dec")
p.node("doct", "Every atom ends with a full<br>shell (8, or 2 for H)?", R, 420, 220, 100, "dec")
p.node(
    "pairs",
    "Bonds from RDKit; shared pair =<br>one electron from each atom;<br>lone pairs away from bonds",
    R,
    550,
    220,
    75,
    "svc",
)
p.node(
    "cs",
    "Covalent scene, 4 steps:<br>atoms → shells overlap →<br>sharing → full shells",
    R,
    655,
    220,
    75,
    "end",
)

p.node(
    "err",
    "SceneError with a plain reason<br>(e.g. 'S would have 12 electrons')<br>— no guessed picture",
    1300,
    420,
    220,
    80,
    "stop",
)
p.node("html", "chem3d_html(): scene JSON + player<br>in a sealed page (no network)", M, 780, 240, 60, "svc")
p.node(
    "play",
    "assets/chem3d.js: perspective 3D, shells as rings,<br>electrons keep their atom's colour, Play / Back /<br>Next, drag to turn, zoom",
    M - 30,
    870,
    300,
    80,
    "ui",
)
for a, b, lab in [("in", "darrow", ""), ("darrow", "dbal", "Yes"), ("darrow", "dion", "No"), ("dbal", "dtab", "Yes"),
                  ("dbal", "err", "No"), ("dtab", "lay", "Yes"), ("dtab", "err", "No"), ("lay", "map", ""),
                  ("map", "rs", ""), ("dion", "dch", "Yes"), ("dion", "dcov", "No"), ("dch", "shell", "Yes"),
                  ("dch", "err", "No"), ("shell", "is", ""), ("dcov", "doct", "Yes"), ("dcov", "err", "No"),
                  ("doct", "pairs", "Yes"), ("doct", "err", "No"), ("pairs", "cs", ""), ("rs", "html", ""),
                  ("is", "html", ""), ("cs", "html", ""), ("html", "play", "")]:  # fmt: skip
    p.edge(a, b, lab)
legend(p, 1300, 620)
pages.append(p)

# ================================================================ 7. code map
p = Page("7 · Code map", "7 · Where everything lives in the codebase")
cols = [
    ("app/core", "svc", ["config.py — settings from .env (ATS_*)", "startup_checks.py — security checks", "secrets.py — Credential Manager", "logging.py — logs with key redaction"]),
    ("app/db", "svc", ["models.py — Document, Page, Chunk, Job, Lesson, LLMCall, caches", "session.py — SQLite (WAL)", "migrations.py — additive"]),
    ("app/llm", "ai", ["router.py — tasks, fallbacks, budget, cache", "config.py — reads models.yaml", "litellm_backend.py — the only LiteLLM import", "service.py — builds the router", "health.py — model checks"]),
    ("app/ingestion", "svc", ["service.py — the pipeline", "files.py — types & hashing", "extract.py — PDF/DOCX/images", "ocr.py — OCR + loop repair", "chunking.py — passages", "enrich.py — summaries", "__main__.py — command line"]),
    ("app/rag", "svc", ["store.py — vectors (SQLite + NumPy)", "tutor.py — answers with citations", "answer_cache.py — similar questions"]),
    ("app/lessons", "svc", ["service.py — lesson life cycle", "planner.py — plan from passages", "chemistry.py — equation checker", "molecules.py — table, 2D/3D", "simulation.py — writes & checks", "browser_check.py — hidden browser", "reactions.py — 3D scenes", "viewers.py — sealed pages"]),
    ("app/jobs · app/tools", "svc", ["runner.py — background worker", "verify_models.py — model check"]),
    ("ui", "ui", ["Home.py", "pages/1 Teach Mode", "pages/2 Lesson Studio", "pages/3 Syllabus Library", "pages/4 Review Text", "pages/5 AI Tutor", "pages/6 Settings & Cost", "pages/7 3D Chemistry Lab", "common.py · lesson_views.py"]),
    ("assets", "check", ["labkit.js — simulation kit", "labkit_example.js — example for the AI", "chem3d.js — 3D player", "vendor/ — p5.js, 3Dmol.js + SHA-256"]),
    ("config · docs · tests · scripts", "store", ["config/models.yaml — models & prices", "docs/ — blueprint, log, diagrams", "docs/_source — doc generators", "tests/ — 246 automated tests", "scripts/audit.ps1 — audit"]),
]  # fmt: skip
for i, (name, kind, files) in enumerate(cols):
    x = 40 + (i % 5) * 310
    y = 70 + (i // 5) * 430
    h = 50 + 34 * len(files)
    p.node(f"g{i}", name, x, y, 290, h, "group")
    for j, f in enumerate(files):
        p.node(f"f{i}_{j}", f, x + 12, y + 35 + j * 34, 266, 28, kind)
pages.append(p)

# ================================================================ 8. teacher workflow
p = Page("8 · Teacher workflow", "8 · How the teacher uses the app — from a new chapter to the class")
steps = [
    ("w1", "Start Ollama + app<br>uv run streamlit run ui/Home.py", "start"),
    ("w2", "Add chapter<br>(source/ folder or upload)", "ui"),
    ("w3", "Wait for extraction<br>(progress on Syllabus Library)", "svc"),
    ("w4", "Review Text: check every page,<br>fix formulas & tables, approve", "ui"),
    ("w5", "Make searchable", "svc"),
    ("w6", "Lesson Studio: create lesson<br>(topic from the chapter)", "ui"),
    ("w7", "Review content, equations, molecules,<br>3D scenes, simulation → Approve", "ui"),
    ("w8", "In class: Teach Mode slides,<br>3D Chemistry Lab, AI Tutor for doubts", "end"),
]  # fmt: skip
for i, (k, t, kind) in enumerate(steps):
    p.node(k, t, 60 + (i % 4) * 340, 120 + (i // 4) * 220, 260, 80, kind)
    if i:
        p.edge(steps[i - 1][0], k)
p.node("n8", "After class: note weak answers → correct those pages in Review Text → add the next chapter.<br>"
       "Costs: Settings & Cost (monthly cap $5; local models free).", 60, 560, 700, 60, "note")  # fmt: skip
pages.append(p)

# ================================================================ one page: heading + guide + all sections
head = [
    '<mxCell id="h_title" value="AI Teaching Studio — complete codebase architecture &amp; workflows" '
    'style="text;html=1;fontSize=34;fontStyle=1;align=left;verticalAlign=top;" vertex="1" parent="1">'
    '<mxGeometry x="0" y="0" width="1700" height="50" as="geometry"/></mxCell>',
]
guide = (
    "<b>How to read this map</b> (zoom out to see everything, zoom in to read a section; generated from the code by "
    "docs/_source/gen_drawio.py on 07-Oct-2026):<br>"
    "<b>1</b> System overview — the layers: screens → app code → AI router → models, data and browser parts. "
    "<b>2</b> Adding a textbook chapter — files to searchable passages. "
    "<b>3</b> AI Tutor — how a question is answered from the textbook.<br>"
    "<b>4</b> LLM router — what happens on every AI call (security, budget, fallbacks). "
    "<b>5</b> Lessons &amp; simulations — plan, checks ①–⑤, teacher approval, Teach Mode. "
    "<b>6</b> 3D chemistry scenes — how electron/atom animations are computed without AI.<br>"
    "<b>7</b> Code map — which folder/file does what. "
    "<b>8</b> Teacher workflow — the daily steps. "
    "Colours: blue = screen · green = app code · purple = AI model · yellow = automatic check · orange diamond = "
    "decision · grey cylinder = stored data · green circle = start · blue circle = result · red = stop / refused."
)
head.append(
    f'<mxCell id="h_guide" value="{escape(guide, quote=True)}" style="{S["note"]}fontSize=14;" vertex="1" '
    'parent="1"><mxGeometry x="0" y="60" width="3540" height="150" as="geometry"/></mxCell>'
)
body = (
    '<mxCell id="0"/><mxCell id="1" parent="0"/>'
    + "".join(head)
    + "".join(c for pg in pages for c in pg.cells)
)
xml = (
    '<mxfile host="app.diagrams.net" type="device"><diagram id="architecture" name="Complete architecture">'
    '<mxGraphModel dx="1400" dy="900" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" '
    f'fold="1" page="0" pageScale="1" math="0" shadow="0"><root>{body}</root></mxGraphModel></diagram></mxfile>'
)
OUT.write_text(xml, encoding="utf-8")
print(f"wrote {OUT} (1 page, {len(pages)} sections)")
