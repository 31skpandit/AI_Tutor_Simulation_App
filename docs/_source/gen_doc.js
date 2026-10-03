// Builds docs/AI_Teaching_Studio_Project_Blueprint_v1.2.docx
const fs = require('fs');
const path = require('path');
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, Table, TableRow, TableCell,
  WidthType, ShadingType, BorderStyle, ImageRun, PageBreak, PageOrientation, Header, Footer,
  PageNumber, TableOfContents, LevelFormat,
} = require('docx');

const ROOT = process.argv[2];
const DIAG = path.join(ROOT, 'docs', 'diagrams');
const OUTFILE = path.join(ROOT, 'docs', 'AI_Teaching_Studio_Project_Blueprint_v1.2.docx');

const BLUE = '1F3A93', INK = '1F2937', MUTE = '4B5563';
const PORTRAIT_W = 9026, LANDSCAPE_W = 14678;

// ---------- helpers ----------
function runs(text, base = {}) {
  // **bold** and `code` inline markup
  const out = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), ...base }));
    const t = m[0];
    if (t.startsWith('**')) out.push(new TextRun({ text: t.slice(2, -2), bold: true, ...base }));
    else out.push(new TextRun({ text: t.slice(1, -1), font: 'Consolas', size: 19, color: '7A1F5C', ...base }));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), ...base }));
  return out;
}
const P = (text, o = {}) => new Paragraph({ children: runs(text, o.run || {}), spacing: { after: 120, line: 276 }, alignment: o.align, ...(o.p || {}) });
const H1 = t => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)], pageBreakBefore: false });
const H2 = t => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] });
const H3 = t => new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(t)] });
const bullets = (items, level = 0) => items.map(t => new Paragraph({ numbering: { reference: 'bul', level }, children: runs(t), spacing: { after: 60, line: 276 } }));
let numCount = 0;
const numberedRefs = [];
function numbered(items) {
  const ref = 'num' + (++numCount);
  numberedRefs.push(ref);
  return items.map(t => new Paragraph({ numbering: { reference: ref, level: 0 }, children: runs(t), spacing: { after: 60, line: 276 } }));
}
function code(lines) {
  return lines.map((l, i) => new Paragraph({
    children: [new TextRun({ text: l === '' ? ' ' : l, font: 'Consolas', size: 18, color: '1F2937' })],
    shading: { type: ShadingType.CLEAR, color: 'auto', fill: 'F3F4F6' },
    spacing: { after: 0, before: i === 0 ? 60 : 0, line: 240 }, keepNext: i < lines.length - 1, keepLines: true,
    indent: { left: 200, right: 200 },
  })).concat([new Paragraph({ spacing: { after: 120 }, children: [] })]);
}
function note(text, fill = 'FFF4E0', border = 'C77700') {
  return new Paragraph({
    children: runs(text),
    shading: { type: ShadingType.CLEAR, color: 'auto', fill },
    border: { left: { style: BorderStyle.SINGLE, size: 18, color: border, space: 8 } },
    spacing: { before: 80, after: 160, line: 276 },
    indent: { left: 160, right: 160 },
  });
}
const cellBorder = { style: BorderStyle.SINGLE, size: 4, color: 'BFC7D5' };
function table(headers, rows, ratios, total = PORTRAIT_W) {
  const sum = ratios.reduce((a, b) => a + b, 0);
  const widths = ratios.map(r => Math.floor(total * r / sum));
  widths[widths.length - 1] += total - widths.reduce((a, b) => a + b, 0);
  const mk = (txt, w, head, zebra) => new TableCell({
    width: { size: w, type: WidthType.DXA },
    shading: { type: ShadingType.CLEAR, color: 'auto', fill: head ? 'DCE5F7' : (zebra ? 'F8FAFC' : 'FFFFFF') },
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    borders: { top: cellBorder, bottom: cellBorder, left: cellBorder, right: cellBorder },
    children: String(txt).split('\n').map(line => new Paragraph({ children: runs(line, head ? { bold: true, color: BLUE, size: 20 } : { size: 20 }), spacing: { after: 30 } })),
  });
  return [new Table({
    width: { size: total, type: WidthType.DXA },
    columnWidths: widths,
    rows: [
      new TableRow({ tableHeader: true, children: headers.map((h, i) => mk(h, widths[i], true)) }),
      ...rows.map((r, ri) => new TableRow({ cantSplit: true, children: r.map((c, i) => mk(c, widths[i], false, ri % 2 === 1)) })),
    ],
  }), new Paragraph({ spacing: { after: 160 }, children: [] })];
}
function pngSize(file) { const b = fs.readFileSync(file); return [b.readUInt32BE(16), b.readUInt32BE(20)]; }
function figure(name, maxW, maxH, caption) {
  const file = path.join(DIAG, name + '.png');
  const [w, h] = pngSize(file);
  let dw = maxW, dh = Math.round(maxW * h / w);
  if (dh > maxH) { dh = maxH; dw = Math.round(maxH * w / h); }
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60, after: 60 }, children: [new ImageRun({ type: 'png', data: fs.readFileSync(file), transformation: { width: dw, height: dh }, altText: { title: caption, description: caption, name } })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 160 }, children: [new TextRun({ text: caption, italics: true, size: 18, color: MUTE })] }),
  ];
}
const pb = () => new Paragraph({ children: [new PageBreak()] });

const header = () => ({ default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun({ text: 'AI Teaching Studio — Project Blueprint v1.2', size: 16, color: MUTE })] })] }) });
const footer = () => ({ default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: 'Page ', size: 16, color: MUTE }), new TextRun({ children: [PageNumber.CURRENT], size: 16, color: MUTE })] })] }) });
const portrait = children => ({ properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 } } }, headers: header(), footers: footer(), children });
const landscape = children => ({ properties: { page: { size: { width: 11906, height: 16838, orientation: PageOrientation.LANDSCAPE }, margin: { top: 1080, bottom: 1080, left: 1080, right: 1080 } } }, headers: header(), footers: footer(), children });

// ---------- content ----------
const sections = [];

// Title page + document control + TOC
sections.push(portrait([
  new Paragraph({ spacing: { before: 2400 }, children: [] }),
  new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: 'AI Teaching Studio', bold: true, size: 64, color: BLUE })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 200, after: 600 }, children: [new TextRun({ text: 'Project Blueprint: Requirements, Architecture, Workflows & Execution Plan', size: 30, color: INK })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: 'Version 1.2 — Approved; Phase 0 complete', size: 24, color: MUTE })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: '3 October 2026', size: 24, color: MUTE })] }),
  new Paragraph({ spacing: { before: 1600 }, children: [] }),
  ...table(['Item', 'Detail'], [
    ['Project', 'AI Teaching Studio — AI-assisted teaching with simulations, animations and an AI tutor'],
    ['Owner / teacher', 'Santosh'],
    ['Prepared by', 'Claude Code (AI engineering assistant), with the owner'],
    ['Codebase location', 'D:\\Santosh\\Data Science\\Entrepreneur journey\\Tuition study app'],
    ['Status', 'Approved by owner (03-Oct-2026). Phase 0 complete — live OpenAI test pending the owner’s API key'],
  ], [1, 3]),
  pb(),
  H1('Document Control'),
  ...table(['Version', 'Date', 'Change', 'Status'], [
    ['1.0', '03-Oct-2026', 'First complete blueprint: requirements from owner answers, architecture, model strategy, workflows, phased plan', 'Superseded'],
    ['1.1', '03-Oct-2026', 'Owner security guidelines after the March 2026 LiteLLM supply-chain incident: new Section 14 (pinning, hash-locked installs, API-key isolation, egress control); updates to stack, setup steps, NFR-06, Phase 0, risks and decisions D10–D11', 'Superseded'],
    ['1.2', '03-Oct-2026', 'Owner approved the plan. Phase 0 built and verified: exact installed versions (§5.1); local text model changed to qwen3:4b-instruct (§7.2); OpenAI models and prices fixed after cross-checking two sources (§7.3); real setup steps (§6.2) and configuration (§7.5); actual folder structure (§11); progress tracker (§12.2); LiteLLM hardening details (§14.6); decisions D12–D14', 'Current'],
  ], [1, 1.4, 5, 1.6]),
  P('How to use this document: it is the single reference for **what** we are building, **why**, and **how**. When a decision changes, update the Decision Log (Section 16), bump the version and keep the old file for history. Diagrams are also saved as high-resolution PNG and editable SVG in `docs/diagrams/`.'),
  new TableOfContents('Contents', { hyperlink: true, headingStyleRange: '1-2' }),
  P('(If the contents list is empty, right-click it in Word and choose “Update Field”.)', { run: { italics: true, color: MUTE, size: 18 } }),
]));

// 1-4
sections.push(portrait([
  H1('1. Project Overview'),
  H2('1.1 Vision'),
  P('Build an AI-powered **teaching studio** that runs on the owner’s laptop and turns textbook chapters into ready-to-teach lessons: clear explanations, accurate chemistry visuals, interactive experiment simulations, narrated animated videos, quizzes, and an AI tutor that answers students’ doubts from the textbook itself.'),
  H2('1.2 Users and context'),
  ...bullets([
    '**Now (Phases 0–4):** the owner teaches students at home, presenting from the laptop on a screen or projector.',
    '**Later (Phase 5):** students may use the app directly (web/mobile). Cloud hosting will be decided after Phase 4.',
  ]),
  H2('1.3 Scope'),
  ...bullets([
    '**Board-agnostic:** the app does not hard-code any syllabus. All content comes from the syllabus and textbook pages the owner uploads (currently State Board).',
    '**Subject-agnostic, chemistry-strong:** chemistry gets dedicated tools (equations, molecules, reactions); physics, biology and maths are covered through simulations, animations and the tutor.',
    '**Languages:** English by default; Hindi and Marathi only when explicitly requested.',
    '**Out of scope for now:** student accounts, payments, cloud deployment, mobile apps (Phase 5 or later).',
  ]),

  H1('2. Requirements'),
  H2('2.1 Functional requirements'),
  P('Priority: **Must** = required for the phase to be complete; **Should** = planned, can slip; **Could** = optional.'),
  ...table(['ID', 'Requirement', 'Priority', 'Phase'], [
    ['FR-01', 'Upload syllabus and chapter content as PDFs or photos / snapshots of textbook pages', 'Must', '1'],
    ['FR-02', 'Extract text from photos (OCR); owner reviews and corrects the text before it is used', 'Must', '1'],
    ['FR-03', 'Organise content by Class → Subject → Chapter → Topic, keeping page numbers', 'Must', '1'],
    ['FR-04', 'AI tutor answers doubts grounded in the uploaded textbook (RAG) and cites chapter + page', 'Must', '1'],
    ['FR-05', 'Generate a lesson for a topic: explanation, key points, examples, slides', 'Must', '2'],
    ['FR-06', 'Chemistry visualizer: balanced equations, 2D structures, rotatable 3D molecules', 'Must', '2'],
    ['FR-07', 'Interactive simulations of experiments (sliders, buttons), usable offline once generated', 'Must', '2'],
    ['FR-08', 'Teach Mode: full-screen, presenter-friendly view for the projector', 'Must', '2'],
    ['FR-09', 'Owner previews, edits and approves every lesson before it is saved or presented', 'Must', '2'],
    ['FR-10', 'Animated explainer videos (Manim) with narration', 'Should', '3'],
    ['FR-11', 'English by default; Hindi / Marathi narration, labels or answers only on explicit request', 'Must', '1 (chat), 3 (narration)'],
    ['FR-12', 'AI-generated illustrations, off by default and cost-gated', 'Could', '3'],
    ['FR-13', 'Quiz generation (MCQ + short answer) with answer key', 'Should', '4'],
    ['FR-14', 'Lesson library: reuse, search, versions', 'Should', '4'],
    ['FR-15', 'Export notes and quizzes as PDF', 'Could', '4'],
    ['FR-16', 'Choose AI provider / model per task through configuration, without code changes', 'Must', '0'],
    ['FR-17', 'Cost dashboard: tokens and cost per call, monthly totals, budget status', 'Must', '0–1'],
    ['FR-18', 'Student logins and progress tracking', 'Could', '5'],
  ], [0.8, 5.2, 0.9, 1.1]),
  H2('2.2 Non-functional requirements'),
  ...table(['ID', 'Quality', 'Requirement'], [
    ['NFR-01', 'Low cost', 'Local / free models first. Hard monthly cap on paid API spend (configurable; proposed default USD 5). An identical request is never paid for twice (cache + lesson library).'],
    ['NFR-02', 'Accuracy', 'Science visuals are drawn by code (Manim, RDKit, JS), not by image/video-generating AI. Equations are checked by chempy. Tutor answers cite textbook pages. Owner approves before use.'],
    ['NFR-03', 'Runs on this laptop', 'Windows 11, Intel Core 5 210H, 32 GB RAM, NVIDIA RTX 3050 (4 GB VRAM). No Docker or Redis needed for Phases 0–4.'],
    ['NFR-04', 'Offline-tolerant', 'Saved lessons, simulations (JS libraries stored locally) and local models work without internet. Internet is needed only for cloud models and PubChem/PhET lookups.'],
    ['NFR-05', 'Responsiveness (targets)', 'Tutor answer starts within ~5 s on local model; lesson text within ~1 min; video renders 1–3 min in the background with a progress bar.'],
    ['NFR-06', 'Security & privacy', 'API keys never in code or `.env`: stored in Windows Credential Manager (Section 14.4). All dependencies pinned and hash-verified via `uv.lock`; LiteLLM pinned to a clean version ≥ 1.83.0. Model calls only to allow-listed provider hosts. AI-generated code runs sandboxed (browser iframe or separate process with timeout). App listens on localhost only. No student personal data sent to free-tier providers.'],
    ['NFR-07', 'Maintainability', 'Python 3.12, type hints, configuration-driven, automated tests for core services, dependencies pinned in `uv.lock`.'],
    ['NFR-08', 'Future-ready', 'Layered design so a FastAPI backend and cloud deployment can be added in Phase 5 without rewriting services.'],
  ], [0.9, 1.5, 5.6]),

  H1('3. Guiding Design Principles'),
  ...numbered([
    '**Accuracy first — the AI writes code, Python draws.** Models generate Manim scripts, simulation code and chemistry data; deterministic libraries render them. Image/video-generating AI often draws wrong bonds, labels and reactions, so it is used only for decorative illustrations.',
    '**Cost first — local → cheap cloud → premium.** Every task has a default model and a fallback chain. Paid calls are logged, capped and cached.',
    '**Teacher in control.** Nothing is shown to students until the owner has previewed and approved it.',
    '**Textbook-grounded.** The tutor and lesson generator use the uploaded chapters as their source and show citations, so content matches what students study.',
    '**Configuration over code.** Models, budgets, languages and voices live in `config/*.yaml` and `.env` — never secrets, which go to Windows Credential Manager.',
    '**Thin vertical slices.** Every phase ends with something usable in a real class.',
  ]),
]));

// 4. Architecture (landscape figure)
sections.push(landscape([
  H1('4. System Architecture'),
  P('The Integrated Architecture Diagram (IAD) below shows all six layers. Each layer talks only to the layer below it, which keeps the design simple now and lets us replace the Streamlit UI with a FastAPI + web front end later without touching the services.'),
  ...figure('01_integrated_architecture_diagram', 790, 560, 'Figure 1 — Integrated Architecture Diagram (IAD)'),
]));
sections.push(portrait([
  H2('4.1 Components and responsibilities'),
  ...table(['Layer', 'Component', 'Responsibility'], [
    ['Presentation', 'Teach Mode', 'Full-screen presentation of an approved lesson: slides, simulations, 3D molecules, videos'],
    ['Presentation', 'Lesson Studio', 'Generate, preview, edit, regenerate sections, approve'],
    ['Presentation', 'Syllabus Library', 'Upload PDFs/photos, review OCR text, browse chapters and topics'],
    ['Presentation', 'AI Tutor Chat', 'Doubt solving grounded in the textbook, with citations and language on request'],
    ['Presentation', 'Settings & Cost', 'Model selection per task, budget cap, cost dashboard, voices'],
    ['Application', 'Lesson Orchestrator', 'Plans a lesson (JSON), calls generators, runs validator, assembles the lesson package'],
    ['Application', 'RAG Service', 'Retrieves the most relevant textbook chunks for a question or topic'],
    ['Application', 'Ingestion Service', 'PDF split, OCR, review queue, chunking, tagging, embedding, indexing'],
    ['Application', 'Generators', 'Simulation, chemistry, animation, narration, image, quiz — one module each, same interface'],
    ['Application', 'Job Runner', 'Runs slow work (video renders, bulk OCR) in the background with progress and timeouts'],
    ['Application', 'Cost & Budget Guard', 'Logs every model call, enforces the monthly cap, serves cached responses'],
    ['AI Gateway', 'LiteLLM', 'One Python API over Ollama, OpenAI, Hugging Face, Gemini, Groq, OpenRouter; retries and fallbacks'],
    ['Engines', 'Manim, RDKit, py3Dmol, chempy, HTML/JS sandbox, TTS, PyMuPDF', 'Deterministic rendering and processing on the laptop'],
    ['Data', 'SQLite, ChromaDB, file storage, cache', 'All data stays in the project’s `data/` folder on the laptop'],
  ], [1.3, 2.1, 4.6]),

  H1('5. Technology Stack and Versions'),
  P('**Version policy:** this table fixes the major choices and minimum versions. The exact versions of every package are resolved during Phase 0, checked on this Windows laptop, and pinned in `uv.lock`, which becomes the source of truth.'),
  ...table(['Area', 'Choice', 'Why this choice', 'Cost'], [
    ['Language', '**Python 3.12.x** (latest patch), installed and managed by uv', 'Most mature Windows wheels for RDKit, Manim, ChromaDB, PyMuPDF; security support until Oct 2028. 3.13 works for most packages but some scientific/audio libraries lag; 3.14 is too new.', 'Free'],
    ['Environment & packages', '**uv** (already installed: 0.12.11)', 'Fast installs, lockfile, installs Python itself — no conflict with other Pythons', 'Free'],
    ['User interface', '**Streamlit** (≥ 1.40)', 'Pure-Python UI, wide/full-screen layout, embeds HTML simulations, 3D viewers and video', 'Free'],
    ['AI gateway', '**LiteLLM Python SDK**, exact-pinned to a clean release **≥ 1.83.0** (never 1.82.7 / 1.82.8), hash-locked; used in-process only — the LiteLLM Proxy Server is **not** used', 'Single API for all providers, cost tracking, fallbacks; change models in YAML. Hidden behind our own `LLMRouter` / `Backend` interface so it can be replaced (Section 14)', 'Free'],
    ['Secrets', '**keyring** → Windows Credential Manager', 'API keys encrypted per Windows user; never stored in files', 'Free'],
    ['Supply-chain checks', '**pip-audit** (run via `uvx`)', 'Checks locked dependencies against known-vulnerability databases before each upgrade and phase sign-off', 'Free'],
    ['Local AI runtime', '**Ollama** (installed: 0.34.4)', 'Runs local models on the RTX 3050 / CPU; already has OCR and embedding models', 'Free'],
    ['Cloud AI', '**OpenAI** (owner has keys) + optional Hugging Face, Gemini, Groq, OpenRouter', 'Higher-quality code generation, translation and vision when local models are not enough', 'Pay-per-use / free tiers'],
    ['Vector store', '**ChromaDB** (embedded, persistent)', 'No server; stores vectors and metadata on disk', 'Free'],
    ['Database', '**SQLite + SQLModel** (Pydantic v2)', 'Zero setup, single file; upgrade path to PostgreSQL in Phase 5', 'Free'],
    ['Configuration', '**pydantic-settings**, YAML, `.env`', 'Typed, validated settings; secrets kept out of code', 'Free'],
    ['PDF & images', '**PyMuPDF**, **Pillow**', 'Fast text extraction and page rendering; photo cleanup before OCR. Note: PyMuPDF is AGPL — fine for personal use; review before selling the app (Phase 5).', 'Free'],
    ['Chemistry', '**RDKit**, **py3Dmol**, **chempy**, **PubChemPy**', 'Structures, interactive 3D molecules, equation balancing, name → structure lookup (PubChem needs internet)', 'Free'],
    ['Animation', '**Manim Community Edition** (≥ 0.19)', 'Precise, programmable science/maths animations rendered to MP4', 'Free'],
    ['Video/audio tools', '**FFmpeg** (system install)', 'Merge narration with video, convert formats', 'Free'],
    ['Typesetting', '**MiKTeX**', 'Formulas in Manim (MathTex, chemistry via mhchem)', 'Free'],
    ['Text-to-speech', '**edge-tts** (primary), OpenAI TTS (fallback)', 'Natural English, Hindi and Marathi voices at no cost; paid fallback if the free service changes', 'Free / paid fallback'],
    ['Simulations', '**p5.js**, **three.js** (stored locally), **PhET** HTML5 sims (embedded)', 'AI-written interactive experiments; ready-made PhET sims for standard experiments (CC-BY, online)', 'Free'],
    ['Background jobs', 'Python thread/process pool + SQLite jobs table', 'Avoids Redis/Celery, which are awkward on Windows', 'Free'],
    ['Quality', '**pytest**, **ruff**, **loguru**', 'Tests, linting/formatting, readable logs', 'Free'],
    ['Version control', '**Git** (installed: 2.51) + optional private GitHub repo', 'History, safe experiments, backup', 'Free'],
  ], [1.4, 2.2, 3.6, 1.0]),
  H2('5.1 Pinned versions (installed and verified on 3 Oct 2026)'),
  P('Direct Python dependencies are pinned with `==` in `pyproject.toml`; all 110 packages (including transitive ones) are pinned with SHA-256 hashes in `uv.lock`. Release cooldown: nothing published after **26 Sep 2026** is allowed (`exclude-newer`). Vulnerability audit (`pip-audit`): **no known vulnerabilities**. Packages for later phases (ChromaDB, RDKit, Manim, edge-tts…) are added only when their phase starts, to keep the installed surface small.'),
  ...table(['Component', 'Version', 'Notes'], [
    ['Python', '3.12.14', 'Installed and managed by uv'],
    ['litellm', '1.102.1', 'SDK only; ≥ 1.83.0 clean line. Pulls in boto3, uvicorn, tokenizers etc. as dependencies — all hash-locked'],
    ['streamlit', '1.64.0', 'UI; bound to 127.0.0.1, usage statistics off'],
    ['sqlmodel / pydantic-settings', '0.0.47 / 2.15.0', 'Database models (timezone-aware UTC timestamps) / typed settings'],
    ['keyring', '25.7.0', 'Backend: Windows Credential Manager (WinVaultKeyring)'],
    ['httpx · pyyaml · loguru', '0.28.1 · 6.0.3 · 0.7.3', 'Health checks · config · logging'],
    ['pytest · ruff · pip-audit (dev)', '9.1.1 · 0.16.9 · 2.10.1', 'Tests · lint/format · vulnerability audit'],
    ['Ollama', '0.34.4', 'Local model runtime'],
    ['FFmpeg', '9.0.2 (Gyan full build)', 'Installed via winget; installer hash verified'],
    ['MiKTeX', '25.12', 'Installed via winget (per-user); installer hash verified'],
    ['uv / Git', '0.12.11 / 2.51', 'Already present'],
  ], [2.2, 2, 3.8]),

  H1('6. Local Environment Setup (Phase 0)'),
  H2('6.1 Laptop profile (checked on 3 Oct 2026)'),
  ...table(['Item', 'Status'], [
    ['Operating system', 'Windows 11 Home Single Language'],
    ['CPU / RAM', 'Intel Core 5 210H / 32 GB'],
    ['GPU', 'NVIDIA GeForce RTX 3050 Laptop, 4 GB VRAM (+ Intel integrated graphics)'],
    ['Free disk space on D:', '≈ 117 GB (project needs ~15–25 GB incl. models and videos)'],
    ['Installed (Phase 0)', 'Python 3.12.14 (uv) · FFmpeg 9.0.2 · MiKTeX 25.12 · uv 0.12.11 · Git 2.51 · Ollama 0.34.4 · Node.js 24.16 (not required)'],
    ['Ollama models', 'qwen3:4b-instruct (used) · qwen3-vl:4b · qwen3-vl:2b · qwen3-embedding:0.6b · qwen3:4b (Thinking, not used) · deepseek-r1:1.5b (not used)'],
  ], [2, 6]),
  H2('6.2 Setup steps (also in README.md)'),
  P('Steps 1–3 were done in Phase 0. On a new laptop, repeat all of them from the project folder:'),
  ...numbered([
    'Tools: `uv python install 3.12` · `winget install --id Gyan.FFmpeg -e` · `winget install --id MiKTeX.MiKTeX -e --scope user`',
    'Local models: `ollama pull qwen3:4b-instruct` · `ollama pull qwen3-vl:4b` · `ollama pull qwen3-embedding:0.6b`',
    'Packages, only from the lockfile (checks every SHA-256 hash): `uv sync --locked`',
    'Settings (no secrets): `copy .env.example .env`',
    'In the OpenAI dashboard, create a Project “ai-teaching-studio” with its own restricted key and a monthly budget limit.',
    'Store the key in Windows Credential Manager (input hidden): `uv run python -m app.core.secrets set openai` — or use the Settings & Cost page.',
    'Security checks: `uv run python -m app.core.startup_checks` (all lines OK) · Models & prices: `uv run python -m app.tools.verify_models`',
    'Start: `uv run streamlit run ui/Home.py` → http://localhost:8501',
  ]),
]));

// 7. AI model strategy
sections.push(portrait([
  H1('7. AI Model Strategy and Cost Control'),
  P('The app never hard-codes a model. Each **task** (tutor chat, OCR, Manim code, translation…) is mapped in `config/models.yaml` to a primary model and a fallback chain. The LiteLLM gateway applies the mapping, enforces the budget and logs cost.'),
  H2('7.1 Providers and their constraints'),
  ...table(['Provider', 'Cost', 'Strengths', 'Constraints'], [
    ['Ollama (local)', 'Free', 'Private, offline, no per-token cost; good for OCR, embeddings, simple Q&A', '4 GB VRAM ⇒ ~4B-parameter models run fully on GPU; 7–8B models spill to RAM and run several times slower; one model loaded at a time (switching takes seconds); weaker at long code and Marathi'],
    ['OpenAI', 'Pay per token', 'Strong code generation, reasoning, vision, TTS, images', 'Costs money; needs internet; prices and model names change — verified in Phase 0 and kept in config'],
    ['Hugging Face', 'Free hub; small monthly free inference credit, then pay-as-you-go', '(a) Source of open models to run in Ollama; (b) hosted inference for larger open models', 'Credits are limited; model availability varies by provider'],
    ['Free cloud tiers (Gemini API, Groq, OpenRouter “:free”)', 'Free with rate limits', 'Fast, capable models at zero cost', 'Per-minute/day limits; terms can change; prompts may be used for training ⇒ send textbook content only, never student personal data'],
  ], [1.6, 1.3, 2.4, 3.2]),
  H2('7.2 What fits on this laptop'),
  ...table(['Local model', 'Disk', 'Fits 4 GB GPU?', 'Use in this project'], [
    ['qwen3:4b-instruct (installed)', '≈ 2.5 GB', 'Yes', '**Used.** Qwen3-4B-Instruct-2507: tutor chat, summaries, quiz drafts. Measured: ~22 tokens/s; direct answers'],
    ['qwen3:4b (installed)', '≈ 2.5 GB', 'Yes', '**Not used.** This tag is Qwen3-4B-Thinking-2507: it always reasons first (≈ 190 tokens and 15–25 s for a one-line answer) and ignores the “thinking off” switch'],
    ['qwen3-vl:4b (installed)', '3.3 GB', 'Yes (tight)', 'OCR of textbook photos, describing diagrams'],
    ['qwen3-vl:2b (installed)', '1.9 GB', 'Yes', 'Faster OCR for clean, printed pages'],
    ['qwen3-embedding:0.6b (installed)', '0.6 GB', 'Yes', 'Embeddings for RAG (multilingual)'],
    ['deepseek-r1:1.5b (installed)', '1.1 GB', 'Yes', 'Not used — too small for reliable teaching answers'],
    ['7–8B models (optional, e.g. qwen3:8b)', '≈ 5 GB', 'Partly (CPU offload)', 'Better offline quality when speed is not critical'],
  ], [2.4, 1, 1.4, 3.2]),
  H2('7.3 Default task → model routing (as configured in Phase 0)'),
  P('OpenAI tiers chosen: **cheapest** = `gpt-5-nano` (USD 0.05 in / 0.40 out per 1M tokens) · **mini** = `gpt-5.4-mini` (0.75 / 4.50) · **premium** = `gpt-5.2` (1.75 / 14.00, only with your approval). These names and prices were confirmed in two independent sources on 3 Oct 2026: the OpenAI pricing page and LiteLLM’s bundled price list.'),
  ...table(['Task', 'Primary', 'Fallback', 'Reason'], [
    ['OCR of photos', 'ollama/qwen3-vl:4b', 'openai/gpt-5-nano (vision)', 'Free for most pages; cloud only for hard pages'],
    ['Embeddings', 'ollama/qwen3-embedding:0.6b', '—', 'Free and multilingual. The same model must be used for the whole index (changing it means re-indexing).'],
    ['Tutor chat', 'ollama/qwen3:4b-instruct + RAG', 'openai/gpt-5-nano', 'Grounded answers are short and simple'],
    ['Lesson plan & explanations', 'openai/gpt-5.4-mini', 'ollama/qwen3:4b-instruct', 'Quality matters; generated once, then cached'],
    ['Manim & simulation code', 'openai/gpt-5.4-mini', 'openai/gpt-5.2 (asks first)', 'Small local models often produce broken code'],
    ['Quiz generation', 'openai/gpt-5-nano', 'ollama/qwen3:4b-instruct', 'Structured output, low token count'],
    ['Hindi / Marathi translation', 'openai/gpt-5.4-mini', '— (Gemini free tier optional)', 'Small local models are weak in Marathi'],
    ['Narration (TTS)', 'edge-tts', 'OpenAI TTS', 'Free en-IN, hi-IN, mr-IN voices (Phase 3)'],
    ['Images', 'Off by default', '—', 'Expensive relative to text; rarely needed (Phase 3)'],
    ['Science validation', 'chempy rules + openai/gpt-5-nano', 'ollama/qwen3:4b-instruct', 'Rules catch most errors at zero cost'],
  ], [1.8, 2.1, 2, 2.5]),
  note('**Model names are configuration, not code.** Run `uv run python -m app.tools.verify_models` (or *Verify models* on the Settings page) to confirm every configured model is installed (Ollama) or available to your OpenAI key, and that prices still match. If a model is retired or a cheaper one appears, only `config/models.yaml` changes.'),
  note('**GPT-5 family note:** these are reasoning models — hidden reasoning tokens are billed as output and count inside `max_tokens`. Tasks therefore set `reasoning_effort` (`minimal` for chat, `low` for generation) and generous `max_tokens`. For Ollama, the same setting switches Qwen3 “thinking” off.', 'E8F0FE', '2F5FD0'),
  H2('7.4 Cost-control mechanisms'),
  ...bullets([
    '**Monthly hard cap** (`ATS_MONTHLY_BUDGET_USD` in `.env`, default USD 5): when reached, paid calls are downgraded to local/free models or require your approval.',
    '**Response cache** keyed by task + model + prompt: an identical request costs nothing the second time.',
    '**Lesson library:** a topic is generated once and reused across batches and years.',
    '**Small prompts:** only the top few textbook chunks are sent, and every task has a `max_tokens` limit.',
    '**Premium needs approval:** the most expensive tier is never used silently.',
    '**Cost dashboard:** per-call tokens, cost, model and latency; monthly totals.',
    '**Expected pattern:** day-to-day use (tutor chat, OCR, embeddings) runs locally for free; paid calls happen mainly once per new lesson.',
  ]),
]));
sections.push(portrait([
  ...figure('04_model_routing_cost_control', 470, 470, 'Figure 4 — AI model routing and cost control'),
  H2('7.5 Configuration file (excerpt of config/models.yaml)'),
  ...code([
    'budget:',
    '  monthly_usd_cap: 5.00              # ATS_MONTHLY_BUDGET_USD in .env overrides',
    '  premium_requires_approval: true',
    'allowed_hosts: ["127.0.0.1:11434", "api.openai.com"]   # egress allow-list',
    'providers:',
    '  ollama:',
    '    litellm_prefix: ollama_chat',
    '    api_base: http://127.0.0.1:11434',
    '    paid: false',
    '  openai:',
    '    litellm_prefix: openai',
    '    api_base: https://api.openai.com/v1',
    '    secret: openai                     # key from Credential Manager',
    '    paid: true',
    'premium_models: [openai/gpt-5.2]',
    'prices:                                # USD per 1M tokens (input / output)',
    '  openai/gpt-5-nano:   { input_per_million: 0.05, output_per_million: 0.40 }',
    '  openai/gpt-5.4-mini: { input_per_million: 0.75, output_per_million: 4.50 }',
    '  openai/gpt-5.2:      { input_per_million: 1.75, output_per_million: 14.00 }',
    'tasks:',
    '  tutor_chat:',
    '    primary: ollama/qwen3:4b-instruct',
    '    fallbacks: [openai/gpt-5-nano]',
    '    max_tokens: 800',
    '    reasoning_effort: minimal',
    '  manim_code:',
    '    primary: openai/gpt-5.4-mini',
    '    fallbacks: [openai/gpt-5.2]        # premium: asks before use',
    '    max_tokens: 6000',
    '    reasoning_effort: low',
  ]),
]));

// 8. Workflows
sections.push(portrait([
  H1('8. Workflows'),
  H2('8.1 Teaching workflow (home tuition)'),
  ...figure('02_teacher_workflow', 520, 600, 'Figure 2 — Teaching workflow'),
  ...bullets([
    '**Once per chapter:** upload photos/PDFs, review the extracted text, confirm the topic tags.',
    '**Before class:** pick a topic; open it from the library or generate it, then preview, edit and approve.',
    '**In class:** present in Teach Mode; ask the AI tutor when a doubt comes up; finish with the quiz.',
  ]),
]));
sections.push(landscape([
  H2('8.2 Syllabus ingestion and RAG pipeline'),
  ...figure('03_syllabus_ingestion_rag', 940, 380, 'Figure 3 — Syllabus ingestion & RAG pipeline'),
  ...bullets([
    '**Photo tips for good OCR:** good light, page flat, one page per photo, phone held parallel to the page.',
    '**Your review step is mandatory:** OCR errors in formulas (e.g. subscripts in H₂SO₄) would otherwise flow into lessons.',
    '**Citations:** every chunk keeps its chapter and page number, so answers can say “Chapter 3, page 42”.',
  ]),
]));
sections.push(landscape([
  H2('8.3 Lesson generation pipeline'),
  ...figure('05_lesson_generation_pipeline', 900, 520, 'Figure 5 — Lesson generation pipeline'),
  P('The planner produces a structured **Lesson Plan** (JSON) so every generator gets precise instructions. The validator checks results; failures regenerate only the failing part. The Manim generator feeds render errors back to the model up to 3 times before asking you.'),
]));

// 9-12
sections.push(portrait([
  H1('9. Multilingual Design (English, Hindi, Marathi)'),
  ...bullets([
    '**English is the source of truth.** All lessons are generated and stored in English first.',
    '**Hindi / Marathi only on explicit request:** a language selector on narration and labels (“English / हिंदी / मराठी”, default English) or a request in chat (“explain this in Marathi”).',
    '**Translations are cached per language,** so each one is paid for only once.',
    '**Scientific terms** keep the English term in brackets, e.g. “सोडियम (Sodium)”, so students still learn the textbook terminology.',
    '**Voices (edge-tts):** en-IN, hi-IN (e.g. SwaraNeural, MadhurNeural), mr-IN (e.g. AarohiNeural, ManoharNeural); OpenAI TTS as fallback.',
    '**Devanagari in videos:** Manim `Text` (Pango) with the Nirmala UI font, which ships with Windows; LaTeX is used only for formulas.',
  ]),

  H1('10. Data Model'),
  ...table(['Entity', 'Key fields', 'Purpose'], [
    ['Subject / Chapter / Topic', 'class_level, subject, chapter no. & title, topic title', 'The syllabus tree you teach from'],
    ['SourceDocument', 'file path, type (PDF/photo), page count, OCR status', 'Every uploaded file'],
    ['PageText', 'document, page no., text, reviewed (yes/no)', 'Extracted text after your review'],
    ['Chunk (ChromaDB)', 'text, vector, chapter, topic, page', 'Searchable pieces for RAG'],
    ['Lesson', 'topic, version, status (draft/approved), language', 'One lesson per topic, versioned'],
    ['LessonAsset', 'lesson, type (slide/simulation/molecule/video/audio/image/quiz), file path, model, cost', 'Everything a lesson contains'],
    ['Job', 'type, status, progress, error, timestamps', 'Background renders and bulk OCR'],
    ['LLMCall', 'task, provider, model, input/output tokens, cost (USD), cached, latency, time', 'Cost dashboard and budget guard'],
    ['CacheEntry', 'key (task + model + prompt hash), response, created', 'Never pay twice for the same request'],
  ], [2, 3.6, 2.4]),

  H1('11. Project Folder Structure'),
  P('Built in Phase 0 (folders marked “later” are added in their phase):', { p: { keepNext: true } }),
  ...code([
    'Tuition study app/',
    '├── app/',
    '│   ├── core/       config.py · secrets.py · logging.py · startup_checks.py',
    '│   ├── db/         models.py (LLMCall, CacheEntry) · session.py',
    '│   ├── llm/        router.py · config.py · backend.py · litellm_backend.py',
    '│   │               service.py · health.py',
    '│   ├── tools/      verify_models.py',
    '│   ├── ingestion/  rag/                    (later: Phase 1)',
    '│   └── lessons/    generators/  jobs/      (later: Phases 2–3)',
    '├── ui/             Home.py · common.py · pages/1_…5_*.py',
    '├── config/         models.yaml',
    '├── tests/          48 automated tests (offline, no cost)',
    '├── scripts/        audit.ps1 (vulnerability audit)',
    '├── docs/           blueprint .docx · diagrams/ · _source/ (doc generators)',
    '├── .streamlit/     config.toml (localhost only, no usage stats)',
    '├── data/           NOT in Git: app.db, logs/ (created at runtime)',
    '├── .env.example    non-secret settings only',
    '├── pyproject.toml  uv.lock  .python-version  .gitignore',
    '└── README.md       short setup & daily-use guide',
  ]),
  P('**Key rule:** only `app/llm/litellm_backend.py` imports LiteLLM. Everything else calls `LLMRouter.complete(task, messages)`.'),
]));

// 12. Execution plan
sections.push(landscape([
  H1('12. Execution Plan'),
  P('Durations are indicative and assume regular working sessions together. Each phase starts with a short plan review and ends with a demo and your sign-off.'),
  ...figure('06_execution_roadmap', 940, 300, 'Figure 6 — Execution roadmap'),
]));
sections.push(portrait([
  H2('12.1 Phase deliverables and acceptance criteria'),
  ...table(['Phase', 'Deliverables', 'Done when…'], [
    ['0 — Setup\n~3–4 days', 'Tools installed; repo skeleton; hash-locked dependencies (`uv.lock`) with LiteLLM pinned ≥ 1.83.0; keyring secrets; startup security checks; host allow-list; settings & `models.yaml`; `LLMRouter` gateway with routing, cache, cost log and budget cap; Streamlit shell (localhost only) with the five pages; Git repository', 'App opens with `uv run streamlit run`; one test prompt each to Ollama and OpenAI is routed and logged with cost; budget cap blocks paid calls when exceeded (tested); `uv sync --locked` succeeds; no API key exists in any project file; a call to a non-allow-listed host is refused (tested); `pip-audit` clean'],
    ['1 — Syllabus & AI Tutor\n~1.5 weeks', 'Upload page; PDF + photo ingestion; OCR with review screen; chunk / embed / index; tutor chat with citations; Hindi/Marathi answers on request', 'One real chapter is uploaded from photos and corrected; the tutor answers 10 test questions with correct page citations and says clearly when something is not in the textbook'],
    ['2 — Lessons & Simulations\n~2 weeks', 'Lesson planner; explanation & slides; chemistry visualizer; simulation generator + PhET embedding; Teach Mode; preview/edit/approve; basic library', 'For 3 pilot topics, a lesson is generated, edited, approved and presented full-screen; simulations work offline; all equations verified balanced'],
    ['3 — Videos & Narration\n~2 weeks', 'Manim generator with auto-fix loop; narration (EN; HI/MR on request); audio-video merge; job runner with progress; optional images', 'A 60–90 s narrated video renders without manual code edits for at least 2 of 3 pilot topics; Marathi narration produced when requested'],
    ['4 — Quiz & Polish\n~1 week', 'Quiz generator; library search & versions; PDF export of notes/quiz; automated tests; user guide', 'A full class is run end-to-end with the app as a dry run'],
    ['5 — Students & Cloud\nlater', 'FastAPI backend; student logins & progress; PostgreSQL; cloud storage; deployment; licence review', 'Scope decided after Phase 4'],
  ], [1.6, 3.4, 3]),

  H2('12.2 Progress tracker'),
  ...table(['Phase', 'Status', 'Evidence / remaining'], [
    ['0 — Setup', '**Complete** (03-Oct-2026), 1 item waiting on owner', 'Done: tools installed; `uv sync --locked` OK (110 packages, SHA-256 verified); `pip-audit` clean; 6/6 security checks OK; 48/48 automated tests pass (router, budget, cache, fallback, premium approval, allow-list refusal, key redaction, no network on LiteLLM import, all pages render); local test prompt answered end-to-end and logged at $0, repeat served from cache; app listens on 127.0.0.1 only. **Remaining:** owner stores OpenAI key → `verify_models` + one test prompt with gpt-5-nano.'],
    ['1 — Syllabus & AI Tutor', 'Next', 'Needs: first class / subject / chapter photos or PDFs from the owner'],
    ['2 — Lessons & Simulations', 'Planned', 'Needs: 3 pilot topics'],
    ['3 — Videos & Narration', 'Planned', '—'],
    ['4 — Quiz & Polish', 'Planned', '—'],
    ['5 — Students & Cloud', 'Later', 'Decided after Phase 4'],
  ], [1.6, 1.8, 4.6]),

  H1('13. Risks and Mitigations'),
  ...table(['Risk', 'Impact', 'Mitigation'], [
    ['AI-generated code (Manim/JS) fails to run', 'Missing visuals', 'Error-feedback retry loop (max 3); tested templates; fall back to a simpler visual or a PhET sim'],
    ['Scientifically wrong content', 'Students learn errors', 'Code-drawn visuals; chempy checks; textbook grounding with citations; owner approval before use'],
    ['4 GB VRAM limits local models', 'Weaker local answers', 'Use local only for suitable tasks; cloud “mini” tier for code and translation; optional 8B model on CPU'],
    ['Poor OCR on photos', 'Wrong text in RAG', 'Photo tips; mandatory review screen; cloud vision fallback for hard pages'],
    ['Cloud cost overrun', 'Budget exceeded', 'Hard cap; cache; lesson reuse; dashboard; OpenAI dashboard limit'],
    ['edge-tts (unofficial service) stops working', 'No free narration', 'Automatic fallback to OpenAI TTS; narration cached once generated'],
    ['Weak Marathi quality', 'Confusing narration', 'Cloud model for translation; English term kept in brackets; owner review'],
    ['Slow video rendering on laptop', 'Waiting in class', 'Render in background before class; low-quality preview first; cache results'],
    ['Free-tier terms change or use data', 'Service loss / privacy', 'Optional only; never send student data; switch provider in config'],
    ['Textbook copyright', 'Legal issue when going public', 'Personal teaching use now; review licences before distributing to students (Phase 5)'],
    ['Compromised package on PyPI (as with LiteLLM, March 2026)', 'API keys and files stolen', 'Exact pins, hash-locked installs, 7-day cooldown, pip-audit, startup version check, keys outside files, scoped low-budget keys (Section 14)'],
  ], [2.4, 1.6, 4]),

  H1('14. Security: Dependencies, LiteLLM and API Keys'),
  H2('14.1 Why this section exists'),
  P('On **24 March 2026**, LiteLLM versions **1.82.7** and **1.82.8** were published to PyPI by an attacker who had stolen the maintainers’ publishing token through a compromised CI security scanner. They were live for about 40 minutes and contained a credential stealer targeting cloud keys, SSH keys and LLM API keys; 1.82.8 added a `.pth` file that runs whenever Python starts. Versions before 1.82.7 and **1.83.0 and later** are not affected. The owner’s rules (Decision D10) apply to LiteLLM, and this project applies the same discipline to **every** dependency.'),
  H2('14.2 How this project uses LiteLLM'),
  ...bullets([
    '**Python SDK only, in-process.** The LiteLLM Proxy Server (the standalone gateway the incident payload targeted in `proxy_server.py`) is **not** installed or run.',
    '**Behind our own interface.** The rest of the app calls `LLMRouter.complete(task, messages)` (app/llm/router.py), which talks to a small `Backend` interface; only `app/llm/litellm_backend.py` imports `litellm`. If LiteLLM ever becomes untrustworthy, it can be replaced by a thin client over the official `openai` SDK (Ollama, OpenAI, Hugging Face, Gemini, Groq and OpenRouter all offer OpenAI-compatible endpoints) without touching other code.',
    '**No third-party callbacks.** LiteLLM logging/telemetry callbacks stay disabled; cost logging is done by our own code into SQLite.',
  ]),
  H2('14.3 Dependency rules (all packages)'),
  ...table(['Rule', 'How it is enforced'], [
    ['Pin exactly', '`litellm==<clean version ≥ 1.83.0>` in `pyproject.toml` (exact version chosen in Phase 0 after checking advisories). All other packages pinned through `uv.lock`.'],
    ['Lockfile with SHA-256 hashes', '`uv.lock` stores the hash of every package file. Installs use `uv sync --locked`, which fails if the lock is stale or any hash does not match.'],
    ['Never install loosely', 'No `pip install <name>` into the project; packages are added only with `uv add <name>==<version>` and the lockfile change is reviewed and committed.'],
    ['Release cooldown', '`[tool.uv] exclude-newer` is set to a date at least 7 days in the past, so brand-new releases (when malicious uploads are usually caught) are never selected.'],
    ['Deliberate upgrades', 'One package at a time: read changelog and security advisories → `uv lock --upgrade-package <name>` → review `uv.lock` diff → `uvx pip-audit` → run tests → commit.'],
    ['Startup check', 'On launch the app verifies the installed LiteLLM version is the pinned one, refuses known-bad versions (1.82.7, 1.82.8) and flags unexpected `.pth` files such as `litellm_init.pth` in the environment.'],
  ], [1.8, 6.2]),
  H2('14.4 API-key isolation'),
  ...bullets([
    '**No keys in files:** not in code, not in `.env`, not in Git. Keys are stored in **Windows Credential Manager** via the `keyring` library (encrypted per Windows user) and read into memory only when a call is made. This is the local-laptop equivalent of a secrets manager; AWS Secrets Manager or HashiCorp Vault are considered for the cloud phase (Phase 5).',
    '**Scoped, low-limit keys:** a dedicated OpenAI Project for this app with a restricted key (only the endpoints we use) and a project budget limit, so a leaked key has limited value.',
    '**Rotation:** rotate keys every 90 days and immediately after any suspicion. (OpenAI keys for normal API use are long-lived; short-lived ephemeral tokens apply only to special APIs such as Realtime, so scoping + low budget + rotation is the practical substitute.)',
    '**Never logged:** keys are redacted from logs and error messages; LiteLLM verbose/debug logging stays off.',
    '**Local services need no keys:** Ollama binds to `127.0.0.1:11434` only (`OLLAMA_HOST` must not be set to `0.0.0.0`).',
  ]),
  H2('14.5 Network egress'),
  ...bullets([
    '**In-app allow-list:** the gateway sends model requests only to hosts listed in config — e.g. `api.openai.com`, `127.0.0.1:11434` (Ollama), `router.huggingface.co`, `generativelanguage.googleapis.com`, `api.groq.com`, `openrouter.ai`. Any other base URL is refused and logged.',
    '**Firewall rules:** because we do not run the Proxy Server, there is no separate gateway process to firewall. A Windows per-program rule on `python.exe` is not practical, since the same interpreter must also reach PubChem, PhET and the TTS service. When the app moves to the cloud (Phase 5), the gateway container’s outbound traffic will be restricted at the firewall / network-policy level to the official provider endpoints only.',
    '**Local-only UI:** Streamlit is bound to `127.0.0.1`, so other devices on the home Wi-Fi cannot open the app.',
  ]),
  H2('14.6 LiteLLM hardening as built (Phase 0)'),
  ...table(['Measure', 'Where / how verified'], [
    ['No downloads at start-up', 'LiteLLM normally fetches its price list and an Anthropic-headers file from GitHub when imported. `litellm_backend.py` sets `LITELLM_LOCAL_MODEL_COST_MAP=True` and `LITELLM_LOCAL_ANTHROPIC_BETA_HEADERS=True` before import, so bundled copies are used. Test `test_litellm_import_and_call_make_no_unexpected_network_connections` blocks all sockets and proves import + a mocked call make zero connections.'],
    ['No callbacks / telemetry', '`litellm.callbacks`, `success_callback`, `failure_callback` emptied; `telemetry=False`; debug info suppressed. Cost logging is our own (SQLite `LLMCall` table).'],
    ['Explicit endpoint and key per call', 'Every call passes `api_base` from `models.yaml` and the key from Credential Manager; LiteLLM never reads keys from environment variables (startup check warns if any are set).'],
    ['Security checks before import', '`startup_checks.py` inspects package metadata and files only (never imports LiteLLM): pinned version, blocked versions 1.82.7/1.82.8, `litellm_init.pth`, keys in `.env`, Ollama/Streamlit binding, keyring backend. Any error disables all AI features.'],
    ['Retries owned by our router', 'LiteLLM `num_retries=0`; the router retries once, then moves down the fallback chain, logging each failure with keys redacted.'],
    ['Ollama “thinking” off', 'Router passes `reasoning_effort` → LiteLLM maps it to Ollama `think=false`; any leftover reasoning text is stripped.'],
  ], [2, 6]),

  H1('15. Ways of Working'),
  ...bullets([
    'Work in phases; each feature is built as a thin, working slice and demoed to you.',
    'Every change is committed to Git with a clear message; nothing is pushed to the internet without your approval.',
    'API keys live only in Windows Credential Manager; `.env` holds non-secret settings; generated data stays in `data/` (excluded from Git).',
    'Dependencies change only through the controlled upgrade procedure in Section 14.3.',
    'This blueprint is updated at the end of each phase (version 1.1, 1.2, …).',
  ]),

  H1('16. Decision Log'),
  ...table(['#', 'Decision', 'Status', 'Date'], [
    ['D1', 'Board-agnostic: content comes from the syllabus and textbook pages the owner uploads (currently State Board)', 'Decided by owner', '03-Oct-2026'],
    ['D2', 'Primary user: the owner teaching at home from the laptop', 'Decided by owner', '03-Oct-2026'],
    ['D3', 'English by default; Hindi and Marathi only when explicitly requested', 'Decided by owner', '03-Oct-2026'],
    ['D4', 'Multi-provider AI via configuration: OpenAI (existing keys) + Ollama local + optional Hugging Face / free tiers; minimise cost', 'Decided by owner', '03-Oct-2026'],
    ['D5', 'Run locally on the laptop first; decide cloud after Phase 4', 'Decided by owner', '03-Oct-2026'],
    ['D6', 'Stack: Python 3.12 via uv, Streamlit, LiteLLM, SQLite + ChromaDB, Manim, RDKit/py3Dmol/chempy, edge-tts', 'Approved by owner', '03-Oct-2026'],
    ['D7', 'Accuracy-first: science visuals drawn by code; image/video-generating AI only for decoration', 'Approved by owner', '03-Oct-2026'],
    ['D8', 'Default monthly cap on paid API spend: USD 5 (adjustable any time)', 'Approved by owner', '03-Oct-2026'],
    ['D9', 'Phase plan 0–5 as in Section 12', 'Approved by owner', '03-Oct-2026'],
    ['D10', 'LiteLLM safety rules: exact pin to a clean version ≥ 1.83.0; SHA-256 hash-locked installs via uv; API keys isolated from files; network egress restricted to provider endpoints', 'Decided by owner', '03-Oct-2026'],
    ['D11', 'How D10 is implemented on the laptop: SDK in-process (no Proxy Server) behind our own `LLMRouter` / `Backend` interface; keys in Windows Credential Manager + scoped, budget-capped OpenAI project key; in-app host allow-list; 7-day release cooldown; vault/firewall egress rules in Phase 5', 'Approved by owner', '03-Oct-2026'],
    ['D12', 'Local text model is `qwen3:4b-instruct` (Qwen3-4B-Instruct-2507), not `qwen3:4b` (Thinking-2507, always reasons first — measured 15–25 s and ~190 tokens for a one-line answer)', 'Decided in Phase 0 (evidence-based)', '03-Oct-2026'],
    ['D13', 'OpenAI tiers: gpt-5-nano (cheapest), gpt-5.4-mini (mini), gpt-5.2 (premium, approval required); prices confirmed in two sources', 'Decided in Phase 0', '03-Oct-2026'],
    ['D14', 'Python packages for later phases are added only when that phase starts (smaller attack surface); each addition follows §14.3', 'Decided in Phase 0', '03-Oct-2026'],
  ], [0.5, 4.8, 1.6, 1.3]),

  H1('17. Open Items for the Owner'),
  ...numbered([
    'Create an OpenAI Project with a restricted key and a monthly limit; store the key with `uv run python -m app.core.secrets set openai`; then run `uv run python -m app.tools.verify_models` and send one test question with “OpenAI gpt-5-nano” on the AI Tutor page (closes Phase 0).',
    'Choose the first class, subject and chapter for Phase 1 and keep its photos/PDFs ready.',
    'Choose 3 pilot topics for Phase 2 (suggestion: one chemical reaction, one physical process, one concept-heavy topic).',
    'Optional: free ~3.6 GB by removing unused models: `ollama rm qwen3:4b` and `ollama rm deepseek-r1:1.5b`.',
  ]),

  H1('Appendix A — Glossary'),
  ...table(['Term', 'Meaning'], [
    ['LLM', 'Large Language Model — the AI that writes text and code (e.g. OpenAI models, Qwen)'],
    ['RAG', 'Retrieval-Augmented Generation — the AI first looks up relevant textbook passages, then answers using them'],
    ['OCR', 'Optical Character Recognition — reading text from photos of pages'],
    ['Embedding', 'A list of numbers that represents the meaning of a text, used to find similar passages'],
    ['Vector store', 'A database of embeddings (here: ChromaDB) for fast meaning-based search'],
    ['Token', 'A piece of a word; cloud AI providers charge per token'],
    ['Fallback chain', 'The ordered list of models to try if the first one fails or is unavailable'],
    ['Ollama', 'Software that runs open AI models locally on the laptop'],
    ['LiteLLM', 'A Python library that gives one common interface to many AI providers'],
    ['Manim', 'A Python library for precise mathematical/scientific animations'],
    ['Streamlit', 'A Python library for building web app interfaces quickly'],
    ['VRAM', 'Memory on the graphics card; limits which local models run fast'],
    ['Supply-chain attack', 'An attacker publishes a poisoned version of a trusted package, so installing or upgrading it runs their code'],
    ['Lockfile / hash', 'A file (`uv.lock`) recording the exact version and SHA-256 fingerprint of every package, so a tampered file is rejected'],
    ['Egress filtering', 'Allowing a program to connect only to approved internet addresses'],
  ], [1.6, 6.4]),
]));

// ---------- document ----------
const doc = new Document({
  creator: 'Claude Code for Santosh',
  title: 'AI Teaching Studio — Project Blueprint v1.2',
  description: 'Requirements, architecture, workflows and execution plan',
  features: { updateFields: true },
  styles: {
    default: { document: { run: { font: 'Calibri', size: 22, color: INK } } },
    paragraphStyles: [
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { size: 34, bold: true, color: BLUE }, paragraph: { spacing: { before: 360, after: 160 }, outlineLevel: 0, keepNext: true } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { size: 27, bold: true, color: '2F5FD0' }, paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 1, keepNext: true } },
      { id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { size: 24, bold: true, color: INK }, paragraph: { spacing: { before: 200, after: 100 }, outlineLevel: 2, keepNext: true } },
    ],
  },
  numbering: {
    config: [
      { reference: 'bul', levels: [{ level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 270 } } } }, { level: 1, format: LevelFormat.BULLET, text: '◦', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 1080, hanging: 270 } } } }] },
      ...numberedRefs.map(ref => ({ reference: ref, levels: [{ level: 0, format: LevelFormat.DECIMAL, text: '%1.', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 360 } } } }] })),
    ],
  },
  sections,
});

Packer.toBuffer(doc).then(buf => { fs.writeFileSync(OUTFILE, buf); console.log('wrote', OUTFILE, buf.length, 'bytes'); });
