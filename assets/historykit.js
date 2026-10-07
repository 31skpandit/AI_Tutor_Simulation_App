/* AI Teaching Studio — history player (written by hand, not by AI).
 *
 * Draws scenes built by app/lessons/history.py as SVG and lets the teacher step through them:
 *   timeline — events revealed oldest → newest, periods (e.g. five-year plans) as coloured bars;
 *   map      — places of the lesson appear one by one on a map of India (labels never overlap);
 *   flow     — an event, then its causes, then its effects, one at a time.
 * Every fact shown comes from the checked lesson data; this file only lays it out. No libraries, no network.
 */
const HK = (() => {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";
  const COLORS = ["#2563eb", "#16a34a", "#d97706", "#9333ea", "#dc2626", "#0891b2", "#4d7c0f", "#c026d3", "#475569", "#b45309"];

  /* ---------- pure helpers (unit-tested in Node) ---------- */

  /* Split text into lines of at most `max` characters (words are not broken). */
  function wrap(text, max) {
    const words = String(text || "").split(/\s+/).filter(Boolean);
    const lines = [];
    let line = "";
    for (const w of words) {
      if (line && (line + " " + w).length > max) {
        lines.push(line);
        line = w;
      } else line = line ? line + " " + w : w;
    }
    if (line) lines.push(line);
    return lines.length ? lines : [""];
  }

  const overlaps = (a, b) => a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;

  /* Year → x with long empty stretches squeezed: a gap of more than `maxGap` years between two marked years gets a
   * small fixed width (drawn as a ≈ break). Measured on the owner's chapter: one 1882 event pushed 1950–2002 into a
   * third of the width. Returns {x(year), breaks: [{x0, x1}], spans}. */
  function yearScale(years, left, right, maxGap) {
    const marks = [...new Set(years)].sort((a, b) => a - b);
    const spans = [];
    for (let i = 0; i + 1 < marks.length; i++) {
      const d = marks[i + 1] - marks[i];
      spans.push({ a: marks[i], b: marks[i + 1], w: d > maxGap ? 4 : d, cut: d > maxGap });
    }
    const total = spans.reduce((s, sp) => s + sp.w, 0) || 1;
    let pos = left;
    for (const sp of spans) {
      sp.x0 = pos;
      sp.x1 = pos + ((right - left) * sp.w) / total;
      pos = sp.x1;
    }
    const x = (year) => {
      if (!spans.length) return (left + right) / 2;
      if (year <= spans[0].a) return spans[0].x0;
      for (const sp of spans) if (year <= sp.b) return sp.x0 + ((year - sp.a) / Math.max(1, sp.b - sp.a)) * (sp.x1 - sp.x0);
      return spans[spans.length - 1].x1;
    };
    return { x, spans, breaks: spans.filter((s) => s.cut) };
  }

  /* Put each period bar in the first lane where it does not overlap an earlier bar. */
  function lanes(periods) {
    const ends = [];
    return periods.map((p) => {
      let lane = ends.findIndex((end) => end <= p.start);
      if (lane < 0) {
        lane = ends.length;
        ends.push(p.end);
      } else ends[lane] = p.end;
      return lane;
    });
  }

  /* Place label boxes next to their points without overlapping each other or other points.
   * items: [{x, y, w, h}] → [{x, y}] top-left corners. Tries right, left, above, below, then further out. */
  function placeLabels(items, bounds) {
    const placed = [];
    const dots = items.map((it) => ({ x: it.x - 6, y: it.y - 6, w: 12, h: 12 }));
    return items.map((it) => {
      const tries = [];
      for (const d of [10, 26, 44, 64, 90]) {
        tries.push({ x: it.x + d, y: it.y - it.h / 2 }, { x: it.x - d - it.w, y: it.y - it.h / 2 },
                   { x: it.x - it.w / 2, y: it.y - d - it.h }, { x: it.x - it.w / 2, y: it.y + d },
                   { x: it.x + d, y: it.y - d - it.h / 2 }, { x: it.x - d - it.w, y: it.y + d - it.h / 2 });
      }
      let best = tries[0];
      for (const t of tries) {
        const r = { x: t.x, y: t.y, w: it.w, h: it.h };
        const inside = !bounds || (r.x >= bounds.x && r.y >= bounds.y && r.x + r.w <= bounds.x + bounds.w && r.y + r.h <= bounds.y + bounds.h);
        if (inside && !placed.some((p) => overlaps(p, r)) && !dots.some((p) => overlaps(p, r))) {
          best = t;
          break;
        }
      }
      placed.push({ x: best.x, y: best.y, w: it.w, h: it.h });
      return best;
    });
  }

  /* ---------- SVG helpers ---------- */

  function el(name, attrs, parent, text) {
    const node = document.createElementNS(NS, name);
    for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, v);
    if (text !== undefined) node.textContent = text;
    if (parent) parent.appendChild(node);
    return node;
  }

  function multiline(parent, lines, x, y, size, attrs) {
    const t = el("text", Object.assign({ x: x, y: y, "font-size": size }, attrs || {}), parent);
    lines.forEach((line, i) => el("tspan", { x: x, dy: i ? size * 1.25 : 0 }, t, line));
    return t;
  }

  /* ---------- scenes ---------- */

  function timeline(svg, scene) {
    const W = 1000, H = 520, left = 40, right = 960;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    const [y0, y1] = scene.range;
    const lo = Math.floor((y0 - 1) / 5) * 5, hi = Math.ceil((y1 + 1) / 5) * 5;
    const marked = [lo, hi].concat(scene.events.map((e) => e.year), scene.periods.flatMap((p) => [p.start, p.end]));
    const scale = yearScale(marked, left, right, 25);
    const X = scale.x;
    const lane = lanes(scene.periods);
    const legendBottom = 18 + Math.ceil(scene.periods.length / 2) * 24;
    const laneCount = scene.periods.length ? Math.max(...lane) + 1 : 0;
    const axisY = Math.max(scene.periods.length ? 0 : 120, legendBottom + 40 + laneCount * 30); // legend, bars, axis
    const g = el("g", {}, svg);
    el("line", { x1: left, y1: axisY, x2: right, y2: axisY, stroke: "#334155", "stroke-width": 3 }, g);
    const shown = scale.spans.filter((s) => !s.cut).reduce((n, s) => n + (s.b - s.a), 0);
    const step = shown > 60 ? 10 : 5;
    const inBreak = (y) => scale.breaks.some((b) => y > b.a && y < b.b);
    let lastTick = -1e9;
    for (let y = lo; y <= hi; y += step) {
      if (inBreak(y) || X(y) - lastTick < 34) continue; // no ticks inside a squeezed gap, no crowded labels
      lastTick = X(y);
      el("line", { x1: X(y), y1: axisY - 6, x2: X(y), y2: axisY + 6, stroke: "#334155", "stroke-width": 2 }, g);
      el("text", { x: X(y), y: axisY + 24, "font-size": 13, "text-anchor": "middle", fill: "#475569" }, g, String(y));
    }
    for (const b of scale.breaks) { // ≈ mark where years are skipped
      const mid = (b.x0 + b.x1) / 2;
      el("rect", { x: mid - 9, y: axisY - 10, width: 18, height: 20, fill: "#fff" }, g);
      el("text", { x: mid, y: axisY + 6, "font-size": 20, "text-anchor": "middle", fill: "#334155", "font-weight": 700 }, g, "≈");
      el("title", {}, g, `${b.a}–${b.b}: years without events in this lesson are squeezed`);
    }
    const bars = scene.periods.map((p, i) => {
      const y = axisY - 40 - lane[i] * 30;
      const bar = el("g", { class: "period" }, g);
      el("rect", { x: X(p.start), y: y, width: Math.max(4, X(p.end) - X(p.start)), height: 22, rx: 5,
                   fill: COLORS[i % COLORS.length], opacity: 0.85 }, bar);
      el("text", { x: (X(p.start) + X(p.end)) / 2, y: y + 15, "font-size": 12, fill: "#fff", "font-weight": 700,
                   "text-anchor": "middle" }, bar, String(i + 1));
      el("title", {}, bar, `${p.name} (${p.start}–${p.end}): ${p.text}`);
      // legend at the top: every period with its number, colour and years (bars are often too short for names)
      const col = i % 2, row = Math.floor(i / 2);
      const lx = left + col * 470, ly = 18 + row * 24;
      const item = el("g", { class: "period" }, g);
      el("rect", { x: lx, y: ly, width: 22, height: 18, rx: 4, fill: COLORS[i % COLORS.length] }, item);
      el("text", { x: lx + 11, y: ly + 13.5, "font-size": 12, fill: "#fff", "font-weight": 700, "text-anchor": "middle" }, item, String(i + 1));
      el("text", { x: lx + 30, y: ly + 14, "font-size": 14, fill: "#1f2937" }, item, `${p.name} (${p.start}–${p.end})`);
      return { node: bar, legend: item, p: p };
    });
    // event labels below the axis, in rows so that they never overlap
    const rows = [];
    const cards = scene.events.map((e, i) => {
      const x = X(e.year);
      const text = e.label;
      const w = Math.max(54, text.length * 7.2 + 14);
      const cx = Math.min(W - 6 - w / 2, Math.max(6 + w / 2, x)); // keep the card inside the picture
      let row = rows.findIndex((r) => r <= cx - w / 2 - 6);
      if (row < 0) { row = rows.length; rows.push(0); }
      rows[row] = cx + w / 2;
      const y = axisY + 44 + row * 34;
      const gr = el("g", { class: "event" }, g);
      el("line", { x1: x, y1: axisY, x2: cx, y2: y, stroke: "#94a3b8", "stroke-dasharray": "3 3" }, gr);
      el("circle", { cx: x, cy: axisY, r: 7, fill: "#1e3a8a", stroke: "#fff", "stroke-width": 2 }, gr);
      el("rect", { x: cx - w / 2, y: y, width: w, height: 24, rx: 6, fill: "#fff", stroke: "#1e3a8a" }, gr);
      el("text", { x: cx, y: y + 16, "font-size": 12.5, "text-anchor": "middle", fill: "#1e293b", "font-weight": 600 }, gr, text);
      el("title", {}, gr, `${e.label}: ${e.text}`);
      return gr;
    });
    svg.setAttribute("viewBox", `0 0 ${W} ${Math.max(240, axisY + 44 + rows.length * 34 + 20)}`); // no empty space
    const steps = scene.events.map((e) => ({ name: e.label, caption: e.text, pages: e.pages }));
    if (!steps.length) steps.push(...scene.periods.map((p) => ({ name: `${p.name} (${p.start}–${p.end})`, caption: p.text, pages: p.pages })));
    function show(k) {
      cards.forEach((c, i) => {
        c.setAttribute("opacity", i < k ? 0.55 : i === k ? 1 : 0.12);
        c.querySelector("rect").setAttribute("stroke-width", i === k ? 3 : 1);
        c.querySelector("circle").setAttribute("r", i === k ? 10 : 7);
      });
      const year = scene.events[k] ? scene.events[k].year : null;
      bars.forEach(({ node, legend, p }, i) => {
        const on = year === null ? i === k : p.start <= year && year <= p.end;
        node.setAttribute("opacity", on ? 1 : 0.35);
        legend.setAttribute("opacity", on ? 1 : 0.45);
      });
    }
    return { steps, show };
  }

  function map(svg, scene) {
    const [W, H] = scene.size;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    const g = el("g", {}, svg);
    el("rect", { x: 0, y: 0, width: W, height: H, fill: "#e0f2fe" }, g);
    for (const [code, c] of Object.entries(scene.outlines)) {
      el("path", { d: c.path, fill: code === "IND" ? "#fef9c3" : "#f1f5f9", stroke: code === "IND" ? "#a16207" : "#cbd5e1",
                   "stroke-width": code === "IND" ? 1.6 : 1, "stroke-linejoin": "round" }, g);
    }
    el("text", { x: W - 12, y: H - 12, "font-size": 13, "text-anchor": "end", fill: "#64748b" }, g, "N ↑");
    // big labels: the tall map of India is shrunk to fit the frame (seen in a screenshot: 16 px was too small)
    const items = scene.places.map((p) => ({ x: p.x, y: p.y, w: p.name.length * 18 + 24, h: 44 }));
    const spots = placeLabels(items, { x: 0, y: 0, w: W, h: H });
    const marks = scene.places.map((p, i) => {
      const gr = el("g", { class: "place" }, g);
      const s = spots[i], it = items[i];
      const ex = Math.max(s.x, Math.min(p.x, s.x + it.w)), ey = Math.max(s.y, Math.min(p.y, s.y + it.h));
      el("line", { x1: p.x, y1: p.y, x2: ex, y2: ey, stroke: "#7f1d1d", "stroke-width": 2.5 }, gr); // label → its dot
      el("circle", { cx: p.x, cy: p.y, r: 22, fill: "none", stroke: "#dc2626", "stroke-width": 5, class: "ring" }, gr);
      el("circle", { cx: p.x, cy: p.y, r: 10, fill: "#dc2626", stroke: "#fff", "stroke-width": 3 }, gr);
      el("rect", { x: s.x, y: s.y, width: it.w, height: it.h, rx: 8, fill: "#fff", stroke: "#7f1d1d", "stroke-width": 2, opacity: 0.95 }, gr);
      el("text", { x: s.x + 12, y: s.y + 31, "font-size": 30, fill: "#111827", "font-weight": 700 }, gr, p.name);
      el("title", {}, gr, `${p.name}${p.state ? " (" + p.state + ")" : ""}: ${p.text}`);
      return gr;
    });
    const steps = scene.places.map((p) => ({
      name: p.name + (p.state ? ` (${p.state})` : ""),
      caption: p.text + (p.how ? ` — map: ${p.how}` : ""),
      pages: p.pages,
    }));
    function show(k) {
      marks.forEach((m, i) => {
        m.setAttribute("opacity", i <= k ? 1 : 0);
        m.querySelector(".ring").setAttribute("opacity", i === k ? 1 : 0);
      });
    }
    return { steps, show };
  }

  function flow(svg, scene) {
    const W = 1000, colW = 290, lineMax = 34;
    const box = (lines) => 22 + lines.length * 20;
    const causes = scene.causes.map((c) => wrap(c, lineMax));
    const effects = scene.effects.map((c) => wrap(c, lineMax));
    const event = wrap(scene.event, 30);
    const colH = (list) => list.reduce((s, l) => s + box(l) + 16, -16);
    const H = Math.max(260, colH(causes), colH(effects), box(event)) + 80;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    const defs = el("defs", {}, svg);
    const marker = el("marker", { id: "arr", viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 8, markerHeight: 8, orient: "auto" }, defs);
    el("path", { d: "M0,0 L10,5 L0,10 z", fill: "#475569" }, marker);
    const g = el("g", {}, svg);
    el("text", { x: 20 + colW / 2, y: 28, "font-size": 18, "text-anchor": "middle", fill: "#b45309", "font-weight": 700 }, g, "Causes");
    el("text", { x: W - 20 - colW / 2, y: 28, "font-size": 18, "text-anchor": "middle", fill: "#15803d", "font-weight": 700 }, g, "Effects");
    const ev = { x: W / 2 - 170, w: 340, h: box(event) };
    ev.y = (H + 30) / 2 - ev.h / 2;
    const evG = el("g", {}, g);
    el("rect", { x: ev.x, y: ev.y, width: ev.w, height: ev.h, rx: 12, fill: "#1e3a8a" }, evG);
    multiline(evG, event, W / 2, ev.y + 28, 17, { "text-anchor": "middle", fill: "#fff", "font-weight": 700 });
    function column(list, x, colour, fill, toEvent) {
      let y = (H + 30) / 2 - colH(list) / 2;
      return list.map((lines) => {
        const h = box(lines);
        const gr = el("g", {}, g);
        el("rect", { x: x, y: y, width: colW, height: h, rx: 10, fill: fill, stroke: colour, "stroke-width": 2 }, gr);
        multiline(gr, lines, x + 12, y + 25, 15, { fill: "#1f2937" });
        const cy = y + h / 2;
        if (toEvent) el("line", { x1: x + colW, y1: cy, x2: ev.x - 4, y2: ev.y + ev.h / 2, stroke: "#475569", "stroke-width": 2, "marker-end": "url(#arr)" }, gr);
        else el("line", { x1: ev.x + ev.w, y1: ev.y + ev.h / 2, x2: x - 4, y2: cy, stroke: "#475569", "stroke-width": 2, "marker-end": "url(#arr)" }, gr);
        y += h + 16;
        return gr;
      });
    }
    const cG = column(causes, 20, "#d97706", "#fff7ed", true);
    const eG = column(effects, W - 20 - colW, "#16a34a", "#f0fdf4", false);
    const steps = [{ name: scene.event, caption: "What happened? First, the event itself.", pages: scene.pages }]
      .concat(scene.causes.map((c, i) => ({ name: `Cause ${i + 1}`, caption: c, pages: scene.pages })))
      .concat(scene.effects.map((c, i) => ({ name: `Effect ${i + 1}`, caption: c, pages: scene.pages })));
    function show(k) {
      cG.forEach((n, i) => n.setAttribute("opacity", k >= 1 + i ? 1 : 0.06));
      eG.forEach((n, i) => n.setAttribute("opacity", k >= 1 + cG.length + i ? 1 : 0.06));
    }
    return { steps, show };
  }

  /* ---------- player ---------- */

  function player(scene, start) {
    const svg = document.getElementById("hk");
    const view = { timeline, map, flow }[scene.kind](svg, scene);
    const steps = view.steps;
    let k = Math.min(start || 0, steps.length - 1), playing = false, timer = null;
    const $ = (id) => document.getElementById(id);
    function render() {
      view.show(k);
      const s = steps[k] || { name: "", caption: "", pages: [] };
      $("stepname").textContent = `Step ${k + 1} of ${steps.length} — ${s.name}: `;
      $("steptext").textContent = s.caption + (s.pages && s.pages.length ? `  (textbook page ${s.pages.join(", ")})` : "");
      $("back").disabled = k === 0;
      $("next").disabled = k >= steps.length - 1;
      $("play").textContent = playing ? "⏸ Pause" : "▶ Play";
      window.hk.current = k;
    }
    function go(i) { k = Math.max(0, Math.min(steps.length - 1, i)); render(); }
    function tick() {
      if (!playing) return;
      if (k >= steps.length - 1) { playing = false; render(); return; }
      go(k + 1);
      timer = setTimeout(tick, Math.max(2500, (steps[k].caption || "").length * 45) / Number($("speed").value || 1));
    }
    $("next").onclick = () => { playing = false; go(k + 1); };
    $("back").onclick = () => { playing = false; go(k - 1); };
    $("restart").onclick = () => { playing = false; go(0); };
    $("all").onclick = () => { playing = false; go(steps.length - 1); };
    $("play").onclick = () => {
      playing = !playing;
      clearTimeout(timer);
      if (playing && k >= steps.length - 1) k = -1;
      if (playing) tick(); else render();
    };
    document.addEventListener("keydown", (ev) => {
      if (ev.key === "ArrowRight") $("next").click();
      if (ev.key === "ArrowLeft") $("back").click();
      if (ev.key === " ") { ev.preventDefault(); $("play").click(); }
    });
    $("title").textContent = scene.title || "";
    window.hk = { steps: steps.length, current: k, go: go };
    render();
  }

  return { wrap, lanes, placeLabels, overlaps, yearScale, player };
})();

if (typeof module !== "undefined") {
  module.exports = HK;
} else if (typeof window !== "undefined" && window.HK_SCENE) {
  try {
    HK.player(window.HK_SCENE, window.HK_START || 0);
  } catch (e) {
    document.body.insertAdjacentHTML("beforeend", "<p style='color:#b91c1c'>History view error: " + String(e.message) + "</p>");
    throw e;
  }
}
