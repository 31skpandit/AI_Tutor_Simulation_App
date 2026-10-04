// Generates the project diagrams as SVG + high-res PNG.
const fs = require('fs');
const path = require('path');
const { Resvg } = require('@resvg/resvg-js');

const OUT = process.argv[2];
fs.mkdirSync(OUT, { recursive: true });

const FONT = "Segoe UI, Arial, sans-serif";
const C = {
  ink: '#1F2937', mute: '#4B5563', line: '#475569',
  blue: ['#E8F0FE', '#2F5FD0'], green: ['#E7F6EC', '#1E8E4E'], amber: ['#FFF4E0', '#C77700'],
  purple: ['#F1EAFD', '#6D3FC0'], teal: ['#E3F5F5', '#137C80'], rose: ['#FDECEF', '#BE2D4B'],
  gray: ['#F3F4F6', '#6B7280'],
};
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

function text(x, y, lines, { size = 15, bold1 = true, color = C.ink, anchor = 'middle', lh = 1.32 } = {}) {
  const arr = Array.isArray(lines) ? lines : [lines];
  const total = (arr.length - 1) * size * lh;
  let y0 = y - total / 2 + size * 0.35;
  return arr.map((l, i) => {
    const b = bold1 && i === 0 && arr.length > 1;
    const sz = b ? size + 1 : size;
    return `<text x="${x}" y="${y0 + i * size * lh}" font-family="${FONT}" font-size="${sz}" font-weight="${b ? 700 : 400}" fill="${b ? color : (arr.length > 1 ? C.mute : color)}" text-anchor="${anchor}">${esc(l)}</text>`;
  }).join('');
}
function box(x, y, w, h, lines, pal = C.blue, o = {}) {
  const dash = o.dashed ? ' stroke-dasharray="7 5"' : '';
  const rx = o.pill ? h / 2 : (o.rx ?? 10);
  return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${rx}" fill="${pal[0]}" stroke="${pal[1]}" stroke-width="2"${dash}/>` +
    text(x + w / 2, y + h / 2, lines, { size: o.size || 15, bold1: o.bold1 ?? true, color: o.single ? pal[1] : C.ink });
}
function diamond(cx, cy, hw, hh, lines, pal = C.amber) {
  return `<polygon points="${cx},${cy - hh} ${cx + hw},${cy} ${cx},${cy + hh} ${cx - hw},${cy}" fill="${pal[0]}" stroke="${pal[1]}" stroke-width="2"/>` +
    text(cx, cy, lines, { size: 15, bold1: false });
}
function arrow(pts, label, o = {}) {
  const d = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0]},${p[1]}`).join(' ');
  const both = o.both ? ' marker-start="url(#arrs)"' : '';
  let s = `<path d="${d}" fill="none" stroke="${o.color || C.line}" stroke-width="2.2"${o.dashed ? ' stroke-dasharray="6 5"' : ''} marker-end="url(#arr)"${both}/>`;
  if (label) {
    const [lx, ly] = o.at || [(pts[0][0] + pts[1][0]) / 2, (pts[0][1] + pts[1][1]) / 2];
    const lines = Array.isArray(label) ? label : [label];
    const w = Math.max(...lines.map(l => l.length)) * 7.4 + 14, h = lines.length * 18 + 6;
    s += `<rect x="${lx - w / 2}" y="${ly - h / 2}" width="${w}" height="${h}" rx="5" fill="#FFFFFF" stroke="#CBD5E1"/>` +
      text(lx, ly, lines, { size: 13, bold1: false, color: C.ink });
  }
  return s;
}
function svg(w, h, title, body) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
<defs>
<marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="${C.line}"/></marker>
<marker id="arrs" viewBox="0 0 10 10" refX="1" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M10,0 L0,5 L10,10 z" fill="${C.line}"/></marker>
</defs>
<rect width="100%" height="100%" fill="#FFFFFF"/>
<text x="${w / 2}" y="38" font-family="${FONT}" font-size="24" font-weight="700" fill="${C.ink}" text-anchor="middle">${esc(title)}</text>
${body}
</svg>`;
}
function save(name, s) {
  fs.writeFileSync(path.join(OUT, name + '.svg'), s);
  const png = new Resvg(s, { fitTo: { mode: 'zoom', value: 2 }, font: { loadSystemFonts: true, defaultFontFamily: 'Segoe UI' } }).render().asPng();
  fs.writeFileSync(path.join(OUT, name + '.png'), png);
  console.log('wrote', name);
}

// ---------- 1. Integrated Architecture Diagram ----------
(function () {
  const W = 1500, H = 1140; let b = '';
  const band = (y, h, pal, label) => {
    b += `<rect x="20" y="${y}" width="1460" height="${h}" rx="14" fill="${pal[0]}" fill-opacity="0.45" stroke="${pal[1]}" stroke-opacity="0.5" stroke-width="1.5"/>`;
    b += `<rect x="20" y="${y}" width="165" height="${h}" rx="14" fill="${pal[1]}"/>`;
    b += text(102, y + h / 2, label, { size: 15, bold1: true, color: '#FFFFFF' }).replace(/fill="#4B5563"/g, 'fill="#FFFFFF"');
  };
  const row = (y, h, n, items, pal, x0 = 205, x1 = 1460, gap = 26) => {
    const w = (x1 - x0 - gap * (n - 1)) / n;
    items.forEach((it, i) => { b += box(x0 + i * (w + gap), y, w, h, it.l || it, pal, it.o || {}); });
  };
  band(64, 106, C.gray, ['USERS']);
  b += box(430, 82, 320, 70, ['Teacher (you)', 'laptop + screen / projector'], C.gray);
  b += box(860, 82, 320, 70, ['Students — Phase 5 (later)', 'web / mobile access'], C.gray, { dashed: true });

  band(206, 112, C.blue, ['PRESENTATION', 'Streamlit UI', 'localhost:8501']);
  row(227, 70, 5, [['Teach Mode', 'present lessons'], ['Lesson Studio', 'create & edit'], ['Syllabus Library', 'upload & browse'], ['AI Tutor Chat', 'doubts, RAG-grounded'], ['Settings & Cost', 'models, budget']], C.blue);

  band(354, 212, C.green, ['APPLICATION', 'Python services']);
  row(372, 76, 5, [['Lesson Orchestrator', 'plan → generate → validate'], ['RAG Service', 'retrieve textbook context'], ['Ingestion Service', 'PDF / photo → text → chunks'], ['Job Runner', 'background renders'], ['Cost & Budget Guard', 'log · limits · cache']], C.green);
  row(470, 76, 6, [['Simulation', 'generator'], ['Chemistry', 'generator'], ['Animation', 'generator'], ['Narration', 'generator'], ['Image', 'generator'], ['Quiz', 'generator']], C.green);

  band(602, 196, C.purple, ['AI GATEWAY', 'LiteLLM router']);
  b += box(205, 620, 380, 124, ['LLM Router + LiteLLM 1.102.1 (SDK)', 'config/models.yaml: task → model', 'fallbacks · budget · cache · allow-list', 'keys from Credential Manager'], C.purple);
  b += box(625, 620, 265, 124, ['Ollama — local, free', 'qwen3:4b-instruct (text)', 'qwen3-vl:2b-instruct (OCR)', 'qwen3-embedding:0.6b'], C.purple);
  b += box(910, 620, 265, 124, ['OpenAI — paid, low-cost', 'mini / nano text tiers', 'vision · TTS · images', 'used only when needed'], C.purple);
  b += box(1195, 620, 265, 124, ['Optional free / cheap', 'Hugging Face Inference', 'Gemini free tier · Groq', 'OpenRouter free models'], C.purple, { dashed: true });
  b += `<path d="M395,744 L395,774 L1327,774" fill="none" stroke="${C.line}" stroke-width="2.2"/>`;
  [757, 1042, 1327].forEach(x => { b += `<path d="M${x},774 L${x},748" fill="none" stroke="${C.line}" stroke-width="2.2" marker-end="url(#arr)"/>`; });

  band(834, 112, C.amber, ['ENGINES', 'local tools']);
  row(855, 70, 5, [['Manim + FFmpeg', 'animated videos'], ['RDKit · py3Dmol · chempy', 'molecules & equations'], ['HTML/JS sandbox', 'p5.js · three.js · PhET'], ['edge-tts / OpenAI TTS', 'EN · HI · MR voices'], ['PyMuPDF · Pillow', 'PDF & image processing']], C.amber);

  band(982, 140, C.teal, ['DATA', 'on your laptop', '(data/ folder)']);
  row(1000, 104, 4, [['SQLite (SQLModel)', 'documents · pages · jobs', 'LLM cost log · cache'], ['Vector index', 'SQLite + NumPy search', 'passages with chapter/page'], ['File storage', 'uploads · videos · simulations', 'images · audio'], ['Response cache', 'same request → reuse result', 'cost = 0']], C.teal);

  const gaps = [[170, 206, 'browser (HTTP)'], [318, 354, 'Python calls'], [566, 602, 'LLM requests'], [798, 834, 'render / run'], [946, 982, 'read / write']];
  gaps.forEach(([a, z, l]) => { b += arrow([[1320, a + 2], [1320, z - 2]], null, { both: true }); b += `<text x="1334" y="${(a + z) / 2 + 5}" font-family="${FONT}" font-size="13" fill="${C.mute}">${l}</text>`; });
  save('01_integrated_architecture_diagram', svg(W, H, 'Integrated Architecture Diagram (IAD) — AI Teaching Studio', b));
})();

// ---------- 2. Teacher workflow ----------
(function () {
  const W = 1220, H = 1360; let b = '';
  const M = 400, S = 860; // column centres
  b += box(M - 110, 60, 220, 50, ['Start'], C.gray, { pill: true });
  b += box(M - 210, 140, 420, 74, ['Upload syllabus & chapter snapshots', 'one-time per chapter: phone photos or PDFs'], C.blue);
  b += box(M - 210, 244, 420, 74, ['Ingestion pipeline (see Fig. 3)', 'OCR → you review text → chunk → embed'], C.green);
  b += box(M - 210, 348, 420, 60, ['Select Class → Subject → Chapter → Topic'], C.blue, { bold1: false });
  b += diamond(M, 490, 140, 56, ['Lesson already', 'in library?']);
  b += box(S - 160, 452, 320, 76, ['Generate lesson (Fig. 5)', 'orchestrator + textbook context'], C.purple);
  b += box(S - 160, 562, 320, 76, ['Preview & edit', 'in Lesson Studio'], C.blue);
  b += diamond(S, 712, 130, 52, ['You approve', 'the lesson?']);
  b += box(S - 160, 800, 320, 64, ['Save to Lesson Library'], C.teal, { bold1: false });
  b += box(M - 210, 794, 420, 76, ['Teach Mode — full screen', 'slides · simulations · 3D molecules · videos'], C.blue);
  b += diamond(M, 980, 140, 56, ['Student has', 'a doubt?']);
  b += box(S - 180, 942, 360, 76, ['Ask AI Tutor (RAG-grounded)', 'English; Hindi/Marathi only if asked'], C.purple);
  b += box(M - 210, 1076, 420, 70, ['End-of-lesson quiz', 'auto-generated; on screen or printed'], C.blue);
  b += box(M - 210, 1176, 420, 64, ['Mark topic as taught', 'notes & quiz saved for next class'], C.teal);
  b += box(M - 110, 1272, 220, 50, ['End'], C.gray, { pill: true });

  b += arrow([[M, 110], [M, 140]]); b += arrow([[M, 214], [M, 244]]); b += arrow([[M, 318], [M, 348]]); b += arrow([[M, 408], [M, 434]]);
  b += arrow([[M + 140, 490], [S - 160, 490]], 'No', { at: [610, 490] });
  b += arrow([[M, 546], [M, 794]], 'Yes', { at: [M, 670] });
  b += arrow([[S, 528], [S, 562]]); b += arrow([[S, 638], [S, 660]]);
  b += arrow([[S + 130, 712], [1115, 712], [1115, 490], [S + 160, 490]], ['No: give feedback,', 'regenerate a section'], { at: [1115, 600] });
  b += arrow([[S, 764], [S, 800]], 'Yes', { at: [S + 30, 782] });
  b += arrow([[S - 160, 832], [M + 210, 832]]);
  b += arrow([[M, 870], [M, 924]]);
  b += arrow([[M + 140, 980], [S - 180, 980]], 'Yes', { at: [610, 980] });
  b += arrow([[M, 1036], [M, 1076]], 'No', { at: [M + 26, 1056] });
  b += arrow([[S, 1018], [S, 1111], [M + 210, 1111]], 'continue teaching', { at: [S, 1070] });
  b += arrow([[M, 1146], [M, 1176]]); b += arrow([[M, 1240], [M, 1272]]);
  b += box(700, 1170, 380, 96, ['Language rule', 'English by default. Hindi / Marathi', 'narration or labels only on request.'], C.amber, { dashed: true });
  save('02_teacher_workflow', svg(W, H, 'Fig. 2 — Teaching Workflow (home tuition, laptop)', b));
})();

// ---------- 3. Ingestion / RAG pipeline ----------
(function () {
  const W = 1560, H = 620; let b = '';
  b += box(30, 120, 270, 110, ['Inputs (source/ or upload)', 'PDF · photos · DOCX · TXT', 'SHA-256: never twice'], C.gray);
  b += box(340, 120, 270, 110, ['Pre-process', 'PyMuPDF: split PDF pages', 'Pillow: rotate · crop · enhance'], C.blue);
  b += diamond(752, 175, 100, 64, ['Digital text', 'layer present?']);
  b += box(900, 52, 300, 84, ['Direct text extraction', 'PyMuPDF — free and exact'], C.green);
  b += box(900, 208, 300, 104, ['OCR with vision model', 'local: qwen3-vl:2b-instruct (free)', 'fallback: OpenAI vision (low cost)'], C.purple);
  b += box(1260, 120, 270, 110, ['Your review', 'fix OCR mistakes,', 'confirm chapter / topic tags'], C.amber);
  b += box(1260, 390, 270, 116, ['Structure & tag', 'Class · Subject · Chapter', 'Topic · page numbers'], C.blue);
  b += box(930, 390, 290, 116, ['Chunk', '~400–600 tokens, overlap', 'heading-aware splitting'], C.blue);
  b += box(600, 390, 290, 116, ['Embed', 'qwen3-embedding:0.6b', 'local, free, multilingual'], C.purple);
  b += box(270, 390, 290, 116, ['Store', 'SQLite: passages + vectors', 'duplicates stored once'], C.teal);
  b += box(30, 404, 200, 88, ['Ready for RAG', 'Tutor & Lesson Studio'], C.gray, { pill: true });
  b += arrow([[300, 175], [340, 175]]); b += arrow([[610, 175], [652, 175]]);
  b += arrow([[752, 111], [752, 94], [900, 94]], 'Yes', { at: [810, 94] });
  b += arrow([[752, 239], [752, 260], [900, 260]], 'No', { at: [810, 260] });
  b += arrow([[1200, 94], [1230, 94], [1230, 150], [1260, 150]]);
  b += arrow([[1200, 260], [1230, 260], [1230, 200], [1260, 200]]);
  b += arrow([[1395, 230], [1395, 390]]);
  b += arrow([[1260, 448], [1220, 448]]); b += arrow([[930, 448], [890, 448]]); b += arrow([[600, 448], [560, 448]]); b += arrow([[270, 448], [230, 448]]);
  b += `<text x="${W / 2}" y="575" font-family="${FONT}" font-size="15" fill="${C.mute}" text-anchor="middle">Rule: every tutor answer and lesson cites chapter + page, so you can verify against the textbook.</text>`;
  save('03_syllabus_ingestion_rag', svg(W, H, 'Fig. 3 — Syllabus Ingestion & RAG Pipeline', b));
})();

// ---------- 4. Model routing & cost control ----------
(function () {
  const W = 1140, H = 1130; let b = '';
  const M = 400, S = 905;
  b += box(M - 280, 60, 560, 70, ['Request from a feature', 'task: tutor_chat · ocr · manim_code · simulation · translate · quiz …'], C.gray, { size: 14 });
  b += diamond(M, 210, 140, 54, ['Same request', 'already cached?']);
  b += box(S - 150, 176, 300, 68, ['Return cached result', 'cost = 0'], C.teal);
  b += box(M - 280, 304, 560, 76, ['Look up task in config/models.yaml', 'primary model · fallback chain · max tokens'], C.blue);
  b += diamond(M, 460, 140, 54, ['Within monthly', 'budget?']);
  b += box(S - 150, 424, 300, 72, ['Downgrade to local / free model', 'or ask you to approve'], C.rose, { size: 14 });
  b += box(M - 280, 560, 560, 76, ['Call model via LiteLLM', 'Ollama · OpenAI · Hugging Face · free tiers'], C.purple);
  b += diamond(M, 730, 140, 54, ['Success and', 'output valid?']);
  b += box(S - 150, 696, 300, 68, ['Retry once, then next', 'model in fallback chain'], C.rose, { size: 14 });
  b += box(M - 280, 830, 560, 66, ['Log tokens · cost · latency', 'visible in Settings → Cost dashboard'], C.green);
  b += box(M - 280, 926, 560, 60, ['Save to cache + lesson library'], C.teal, { bold1: false });
  b += box(M - 130, 1020, 260, 56, ['Return result to feature'], C.gray, { pill: true, bold1: false });

  b += arrow([[M, 130], [M, 156]]);
  b += arrow([[M + 140, 210], [S - 150, 210]], 'Yes', { at: [620, 210] });
  b += arrow([[M, 264], [M, 304]], 'No', { at: [M + 26, 284] });
  b += arrow([[M, 380], [M, 406]]);
  b += arrow([[M + 140, 460], [S - 150, 460]], 'No', { at: [620, 460] });
  b += arrow([[M, 514], [M, 560]], 'Yes', { at: [M + 28, 537] });
  b += arrow([[S, 496], [S, 580], [M + 280, 580]]);
  b += arrow([[M, 636], [M, 676]]);
  b += arrow([[M + 140, 730], [S - 150, 730]], 'No', { at: [620, 730] });
  b += arrow([[S + 150, 730], [1085, 730], [1085, 615], [M + 280, 615]]);
  b += arrow([[M, 784], [M, 830]], 'Yes', { at: [M + 28, 807] });
  b += arrow([[M, 896], [M, 926]]); b += arrow([[M, 986], [M, 1020]]);
  b += arrow([[S + 150, 210], [1115, 210], [1115, 1048], [M + 130, 1048]]);
  b += box(720, 830, 340, 160, ['Cost rules', '• local first for simple tasks', '• cheap cloud tier for code & Marathi', '• hard monthly cap (in .env)', '• same topic never generated twice'], C.amber, { dashed: true, size: 14 });
  save('04_model_routing_cost_control', svg(W, H, 'Fig. 4 — AI Model Routing & Cost Control', b));
})();

// ---------- 5. Lesson generation pipeline ----------
(function () {
  const W = 1520, H = 880; let b = '';
  b += box(30, 378, 220, 104, ['Topic selected', '+ textbook context', '(from RAG)'], C.gray);
  b += box(290, 350, 260, 160, ['Lesson Planner (LLM)', 'Lesson Plan JSON:', 'objectives · sections', 'visuals · quiz spec', 'language'], C.purple);
  const gens = [
    ['Explanation & slides', 'simple language, examples'],
    ['Chemistry visuals', 'chempy: balance equation', 'RDKit / PubChem · py3Dmol 3D'],
    ['Interactive simulation', 'LLM writes HTML/JS (p5 / three)', 'or embed a matching PhET sim'],
    ['Animated video', 'LLM writes Manim → render MP4', 'errors fed back, max 3 retries'],
    ['Narration', 'edge-tts English voice', 'Hindi / Marathi only on request'],
    ['Quiz', 'MCQ + short answers + key'],
  ];
  const gx = 640, gw = 380, gh = 96, g0 = 70, gg = 24;
  gens.forEach((g, i) => { b += box(gx, g0 + i * (gh + gg), gw, gh, g, C.green, { size: 14 }); });
  const cys = gens.map((_, i) => g0 + i * (gh + gg) + gh / 2);
  b += arrow([[250, 430], [290, 430]]);
  b += `<path d="M550,430 L595,430 M595,${cys[0]} L595,${cys[5]}" stroke="${C.line}" stroke-width="2.2" fill="none"/>`;
  cys.forEach(y => { b += arrow([[595, y], [gx, y]]); });
  b += `<path d="M1055,${cys[0]} L1055,${cys[5]}" stroke="${C.line}" stroke-width="2.2" fill="none"/>`;
  cys.forEach(y => { b += `<path d="M${gx + gw},${y} L1055,${y}" stroke="${C.line}" stroke-width="2.2" fill="none"/>`; });
  b += box(1090, 320, 240, 190, ['Validator', '• equation balanced?', '• code renders cleanly?', '• facts match textbook?', '• labels / language OK?'], C.amber, { size: 14 });
  b += arrow([[1055, 415], [1090, 415]]);
  b += diamond(1210, 630, 110, 54, ['All checks', 'pass?']);
  b += arrow([[1210, 510], [1210, 576]]);
  b += box(1360, 360, 140, 110, ['Lesson', 'package →', 'your preview'], C.teal, { size: 14 });
  b += arrow([[1320, 630], [1430, 630], [1430, 470]], 'Yes', { at: [1375, 630] });
  b += arrow([[1210, 684], [1210, 820], [830, 820], [830, cys[5] + gh / 2]], 'No: regenerate only the failed part', { at: [1010, 820] });
  save('05_lesson_generation_pipeline', svg(W, H, 'Fig. 5 — Lesson Generation Pipeline', b));
})();

// ---------- 6. Roadmap ----------
(function () {
  const W = 1500, H = 430; let b = '';
  const P = [
    ['Phase 0 ✓', 'Setup', 'done 3 Oct 2026', ['Python 3.12 via uv', 'FFmpeg · MiKTeX · Ollama', 'secure, hash-locked deps', 'AI gateway + cost log'], C.gray],
    ['Phase 1 ▶', 'Syllabus & AI Tutor', 'built · testing', ['PDF / photo / DOCX upload', 'OCR + your review', 'RAG (SQLite + NumPy)', 'tutor with page citations'], C.blue],
    ['Phase 2', 'Lessons & Simulations', '~2 weeks', ['lesson planner', 'chemistry visualizer', 'interactive simulations', 'Teach Mode (projector)'], C.green],
    ['Phase 3', 'Videos & Narration', '~2 weeks', ['Manim animations', 'EN voice; HI / MR on request', 'images (optional)', 'background render jobs'], C.purple],
    ['Phase 4', 'Quiz & Polish', '~1 week', ['quiz generator', 'lesson library & search', 'export notes (PDF)', 'tests + user guide'], C.amber],
    ['Phase 5', 'Students & Cloud', 'later', ['FastAPI backend', 'student logins & progress', 'cloud deployment', 'decided after Phase 4'], C.teal],
  ];
  const w = 215, gap = 30, x0 = 30;
  P.forEach((p, i) => {
    const x = x0 + i * (w + gap), pal = p[4];
    b += `<rect x="${x}" y="70" width="${w}" height="320" rx="12" fill="${pal[0]}" stroke="${pal[1]}" stroke-width="2"${i === 5 ? ' stroke-dasharray="7 5"' : ''}/>`;
    b += `<rect x="${x}" y="70" width="${w}" height="44" rx="12" fill="${pal[1]}"/><rect x="${x}" y="100" width="${w}" height="14" fill="${pal[1]}"/>`;
    b += `<text x="${x + w / 2}" y="99" font-family="${FONT}" font-size="17" font-weight="700" fill="#FFFFFF" text-anchor="middle">${p[0]}</text>`;
    b += `<text x="${x + w / 2}" y="146" font-family="${FONT}" font-size="16" font-weight="700" fill="${C.ink}" text-anchor="middle">${esc(p[1])}</text>`;
    b += `<text x="${x + w / 2}" y="170" font-family="${FONT}" font-size="14" fill="${pal[1]}" font-weight="600" text-anchor="middle">${esc(p[2])}</text>`;
    p[3].forEach((l, j) => { b += `<text x="${x + 16}" y="${212 + j * 42}" font-family="${FONT}" font-size="14" fill="${C.mute}">• ${esc(l)}</text>`; });
    if (i < 5) b += arrow([[x + w + 3, 230], [x + w + gap - 3, 230]]);
  });
  save('06_execution_roadmap', svg(W, H, 'Fig. 6 — Execution Roadmap (indicative durations)', b));
})();
