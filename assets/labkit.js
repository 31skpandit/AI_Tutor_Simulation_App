/* AI Teaching Studio — Lab kit for classroom simulations (p5.js global mode).
 *
 * Written by hand (not by AI). It owns the layout so AI-written experiments cannot overlap text:
 *   ┌ title band ─────────────────────────────────────────────────────────┐
 *   │ apparatus area (the experiment, clipped)  │ readings panel (stacked) │
 *   └ "Observe" band ─────────────────────────────────────────────────────┘
 * The AI-written part defines one object `SIM` (see app/lessons/simulation.py for the contract):
 *   SIM.title, SIM.observe, SIM.setup(), SIM.controls(), SIM.drawApparatus(area), SIM.panel()
 * Labels drawn with labLabel() never overlap each other: a label that would collide is moved and
 * connected to its point with a thin leader line. Actions are animated with labStart()/labProgress().
 *
 * Version 2 (2026-10-06), after the teacher found a crashing simulation and wrongly drawn glassware:
 *  - p5.js 2 compatibility: some element methods (e.g. select.option()) return nothing in p5.js 2, so the
 *    common chained style createSelect().option('a').option('b') crashed. The kit makes them chainable again.
 *  - Control helpers labButton / labSelect / labSlider / labCheckbox (errors are caught and shown).
 *  - Hand-drawn apparatus parts (beaker, test tube, burner, tripod, dish, dropper, glass rod, electrodes,
 *    battery, wires, bubbles, pH strip, thermometer) so the AI places correct glassware instead of drawing
 *    it line by line (liquid outside the beaker, an upside-down tripod … were seen in screenshots).
 */
const LAB = {
  W: 900,
  H: 560,
  title: { x: 20, y: 10, w: 860, h: 44 },
  apparatus: { x: 16, y: 58, w: 560, h: 420 },
  panel: { x: 590, y: 58, w: 294, h: 420 },
  observe: { x: 0, y: 486, w: 900, h: 74 },
  placed: [],
  timers: {},
  error: null,
};

/* ---------- pure helpers (also unit-tested with Node, no p5 needed) ---------- */

function labOverlaps(a, b) {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}

function labClampRect(r, bounds) {
  if (!bounds) return r;
  return {
    x: Math.min(Math.max(r.x, bounds.x), bounds.x + bounds.w - r.w),
    y: Math.min(Math.max(r.y, bounds.y), bounds.y + bounds.h - r.h),
    w: r.w,
    h: r.h,
  };
}

/* Find the nearest free position for `rect` (moving down/up, then right/left) inside `bounds`. */
function labPlace(rect, placed, bounds) {
  const free = (r) => !placed.some((p) => labOverlaps(r, p));
  const start = labClampRect(rect, bounds);
  if (free(start)) return start;
  const step = 4;
  for (let i = 1; i <= 120; i++) {
    const d = i * step;
    const candidates = [
      { ...rect, y: rect.y + d },
      { ...rect, y: rect.y - d },
      { ...rect, x: rect.x + d },
      { ...rect, x: rect.x - d },
    ];
    for (const c of candidates) {
      const r = labClampRect(c, bounds);
      if (free(r)) return r;
    }
  }
  return start; // extremely crowded: give up moving (still clamped inside the area)
}

/* Split text into lines that fit `maxWidth`, using a width function (p5's textWidth in the browser). */
function labWrap(str, maxWidth, widthOf) {
  const words = String(str).split(/\s+/).filter(Boolean);
  const lines = [];
  let line = "";
  for (const word of words) {
    const tryLine = line ? line + " " + word : word;
    if (widthOf(tryLine) <= maxWidth || !line) {
      line = tryLine;
    } else {
      lines.push(line);
      line = word;
    }
  }
  if (line) lines.push(line);
  return lines.length ? lines : [""];
}

/* ---------- animation timers ---------- */

function labStart(name, durationMs) {
  LAB.timers[name] = { start: millis(), duration: Math.max(1, durationMs || 1500) };
}

/* 0 → 1 while the action runs; 1 after it finished; 0 if it never started. */
function labProgress(name) {
  const t = LAB.timers[name];
  if (!t) return 0;
  return Math.min(1, (millis() - t.start) / t.duration);
}

function labActive(name) {
  const t = LAB.timers[name];
  return !!t && millis() - t.start < t.duration;
}

function labEase(t) {
  return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
}

/* ---------- drawing helpers ---------- */

/* A label that never overlaps another label. (x, y) is the point the label belongs to.
 * opts: { size: 14, align: 'center'|'left'|'right', color: '#1f2937', bold: false, background: true } */
function labLabel(str, x, y, opts = {}) {
  const size = opts.size || 14;
  push();
  textSize(size);
  textStyle(opts.bold ? BOLD : NORMAL);
  const pad = 4;
  const w = textWidth(String(str)) + pad * 2;
  const h = size * 1.35;
  const align = opts.align || "center";
  const left = align === "left" ? x : align === "right" ? x - w : x - w / 2;
  const wanted = { x: left, y: y - h / 2, w: w, h: h };
  const r = labPlace(wanted, LAB.placed, opts.bounds || LAB.apparatus);
  if (Math.abs(r.x - wanted.x) > 2 || Math.abs(r.y - wanted.y) > 2) {
    stroke(120);
    strokeWeight(1);
    line(x, y, r.x + r.w / 2, r.y + r.h / 2); // leader line to the original point
  }
  if (opts.background !== false) {
    noStroke();
    fill(255, 255, 255, 225);
    rect(r.x, r.y, r.w, r.h, 4);
  }
  noStroke();
  fill(opts.color || "#1f2937");
  textAlign(LEFT, CENTER);
  text(String(str), r.x + pad, r.y + r.h / 2);
  pop();
  LAB.placed.push(r);
  return r;
}

function labTitle(str) {
  push();
  noStroke();
  fill("#1f2937");
  textSize(24);
  textStyle(BOLD);
  textAlign(LEFT, CENTER);
  text(String(str || ""), LAB.title.x, LAB.title.y + LAB.title.h / 2);
  pop();
}

/* Readings panel: a list of strings or {text, color, bold}; lines are stacked, wrapped and shrunk to fit. */
function labPanel(lines, heading) {
  const p = LAB.panel;
  push();
  stroke(210);
  fill(255);
  rect(p.x, p.y, p.w, p.h, 8);
  noStroke();
  fill("#1f2937");
  textAlign(LEFT, TOP);
  textSize(17);
  textStyle(BOLD);
  text(heading || "Readings", p.x + 12, p.y + 10);
  const items = (lines || []).map((l) => (typeof l === "string" ? { text: l } : l));
  let size = 10; // smallest allowed; replaced by the largest size (15 → 10) that fits
  let wrapped = [];
  for (let s = 15; s >= 10; s--) {
    textSize(s);
    const attempt = items.map((it) => ({ ...it, rows: labWrap(it.text, p.w - 24, (t) => textWidth(t)) }));
    const height = attempt.reduce((sum, it) => sum + it.rows.length * s * 1.35 + 6, 0);
    size = s;
    wrapped = attempt;
    if (height <= p.h - 48) break;
  }
  let y = p.y + 40;
  textSize(size);
  for (const it of wrapped) {
    fill(it.color || "#374151");
    textStyle(it.bold ? BOLD : NORMAL);
    for (const row of it.rows) {
      text(row, p.x + 12, y);
      y += size * 1.35;
    }
    y += 6;
  }
  pop();
}

function labObserve(str) {
  const o = LAB.observe;
  push();
  noStroke();
  fill("#111827");
  rect(o.x, o.y, o.w, o.h);
  fill(255);
  textSize(16);
  textAlign(LEFT, TOP);
  const rows = labWrap("Observe: " + String(str || ""), o.w - 32, (s) => textWidth(s));
  rows.slice(0, 3).forEach((row, i) => text(row, o.x + 16, o.y + 10 + i * 21));
  pop();
}

/* ---------- p5.js 2 compatibility + controls ---------- */

const LAB_CHAINABLE = [
  "option", "selected", "disable", "mousePressed", "mouseReleased", "changed", "input",
  "style", "position", "parent", "class", "id", "attribute", "size", "html", "show", "hide", "value",
];

/* Methods that return nothing in p5.js 2 return the element again, so chained calls keep working.
 * Getters (e.g. value() or selected() without arguments) still return their value. */
function labMakeChainable(el) {
  if (!el || el.__labChainable) return el;
  for (const name of LAB_CHAINABLE) {
    const method = el[name];
    if (typeof method !== "function") continue;
    el[name] = function (...args) {
      const result = method.apply(el, args);
      return result === undefined ? el : result;
    };
  }
  el.__labChainable = true;
  return el;
}

function labInstallCompat() {
  const g = typeof window !== "undefined" ? window : globalThis;
  for (const name of ["createButton", "createSelect", "createSlider", "createCheckbox", "createRadio",
                      "createInput", "createSpan", "createDiv", "createP"]) {
    const original = g[name];
    if (typeof original !== "function" || original.__lab) continue;
    const wrapped = function (...args) {
      return labMakeChainable(original.apply(this, args));
    };
    wrapped.__lab = true;
    try {
      /* p5.js 2 defines its globals read-only (writable: false) but configurable, so a plain assignment is
       * silently ignored — measured in Edge. defineProperty replaces it. */
      const d = Object.getOwnPropertyDescriptor(g, name) || { enumerable: true };
      Object.defineProperty(g, name, { value: wrapped, writable: false, configurable: true, enumerable: !!d.enumerable });
    } catch (e) {
      /* cannot replace in this build: the lab helpers below still work */
    }
  }
}

function labSafe(fn) {
  try {
    fn();
  } catch (e) {
    LAB.error = e;
  }
}

function labButton(label, onPress) {
  const b = labMakeChainable(createButton(String(label)));
  b.mousePressed(() => labSafe(() => onPress(b)));
  return b;
}

function labSelect(label, options, onChange, initial) {
  if (label) createSpan(String(label) + ": ");
  const s = labMakeChainable(createSelect());
  for (const o of options) s.option(String(o));
  if (initial !== undefined && initial !== null) s.selected(String(initial));
  s.changed(() => labSafe(() => onChange(s.value(), s)));
  return s;
}

function labSlider(label, min, max, value, step, onInput) {
  if (label) createSpan(String(label) + ": ");
  const s = labMakeChainable(createSlider(min, max, value, step || 0));
  s.input(() => labSafe(() => onInput(Number(s.value()), s)));
  return s;
}

function labCheckbox(label, checked, onChange) {
  const c = labMakeChainable(createCheckbox(String(label), !!checked));
  c.changed(() => labSafe(() => onChange(!!c.checked(), c)));
  return c;
}

/* ---------- colours (pure, unit-tested) ---------- */

/* Universal indicator colour for a pH value (common school chart: red 1 → green 7 → violet 14). */
const LAB_INDICATOR = [
  "#d7191c", "#e8301c", "#f0531c", "#f57f20", "#f9a51b", "#fbd319", "#c5d92d",
  "#2fa84f", "#1c9a7e", "#1f78b4", "#2b55a5", "#3f3b97", "#5a2d91", "#6a1f8a", "#5b136e",
];

function labIndicatorColor(ph) {
  const i = Math.round(Math.min(14, Math.max(0, Number(ph) || 0)));
  return LAB_INDICATOR[i];
}

function labMixHex(a, b, t) {
  const pa = parseInt(a.slice(1), 16), pb = parseInt(b.slice(1), 16);
  const k = Math.min(1, Math.max(0, t));
  const ch = (p, s) => (p >> s) & 255;
  const out = [16, 8, 0].map((s) => Math.round(ch(pa, s) + (ch(pb, s) - ch(pa, s)) * k));
  return "#" + out.map((v) => v.toString(16).padStart(2, "0")).join("");
}

/* ---------- apparatus parts (hand-drawn; positions: x = centre, y = the bench / bottom line) ---------- */

function labGlassStroke() {
  stroke(90, 110, 130);
  strokeWeight(2.5);
  noFill();
}

/* Beaker standing on y. opts: {w, h, level 0..1, liquid colour, label, maxMl (scale marks), swirl 0..1}
 * Returns geometry {left, right, top, bottom, surface, w, h, x} for placing a rod, dropper, electrodes. */
function labBeaker(x, y, opts = {}) {
  const w = opts.w || 150, h = opts.h || 170;
  const left = x - w / 2, right = x + w / 2, top = y - h;
  const level = Math.min(1, Math.max(0, opts.level === undefined ? 0.6 : opts.level));
  const surface = y - 4 - (h - 14) * level;
  push();
  if (level > 0) {
    noStroke();
    fill(opts.liquid || "#bfdbfe");
    rect(left + 3, surface, w - 6, y - 3 - surface, 0, 0, 10, 10);
    if (opts.swirl && opts.swirl > 0 && opts.swirl < 1) {
      noFill();
      stroke(255, 255, 255, 170);
      strokeWeight(2);
      const t = opts.swirl * TWO_PI * 3;
      for (let i = 0; i < 3; i++) {
        const rx = (w * 0.32) * (1 - i * 0.25), ry = Math.max(6, (y - surface) * 0.18);
        arc(x, (surface + y) / 2 + i * 8, rx * 2, ry * 2, t + i, t + i + PI * 1.2);
      }
    }
  }
  labGlassStroke();
  line(left, top, left, y - 10);
  line(right, top, right, y - 10);
  arc(left + 10, y - 10, 20, 20, HALF_PI, PI);
  arc(right - 10, y - 10, 20, 20, 0, HALF_PI);
  line(left + 10, y, right - 10, y);
  line(left - 6, top - 4, left, top); /* lip */
  stroke(255, 255, 255, 160);
  strokeWeight(3);
  line(left + 8, top + 12, left + 8, y - 22); /* glass shine */
  if (opts.maxMl) {
    stroke(90, 110, 130);
    strokeWeight(1);
    for (let i = 1; i <= 4; i++) {
      const yy = y - 4 - (h - 14) * (i / 5);
      line(right, yy, right - 10, yy);
      labLabel(Math.round((opts.maxMl * i) / 5) + " ml", right + 6, yy, { size: 10, align: "left", color: "#475569" });
    }
  }
  pop();
  if (opts.label) labLabel(opts.label, x, y + 14, { size: 13 });
  return { x, left, right, top, bottom: y, surface, w, h };
}

/* Test tube. Upright: y is the round bottom. inverted:true → y is the open mouth at the bottom (gas collection);
 * opts.gas 0..1 is the part filled with gas at the closed top. opts: {w, h, level, liquid, label, gasLabel} */
function labTestTube(x, y, opts = {}) {
  const w = opts.w || 34, h = opts.h || 150, r = w / 2;
  const left = x - r, right = x + r;
  push();
  if (opts.inverted) {
    const top = y - h;
    const gas = Math.min(1, Math.max(0, opts.gas || 0));
    const gasEnd = top + r + (h - r) * gas;
    noStroke();
    fill(opts.liquid || "#bfdbfe");
    rect(left + 2, Math.max(gasEnd, top + 2), w - 4, y - Math.max(gasEnd, top + 2));
    if (gas > 0) {
      fill(255, 255, 255, 235);
      arc(x, top + r, w - 4, w - 4, PI, TWO_PI);
      rect(left + 2, top + r, w - 4, gasEnd - top - r);
    }
    labGlassStroke();
    line(left, top + r, left, y);
    line(right, top + r, right, y);
    arc(x, top + r, w, w, PI, TWO_PI);
    pop();
    if (opts.gasLabel && gas > 0.04) labLabel(opts.gasLabel, x, top + r + (gasEnd - top - r) / 2, { size: 12, bold: true });
    if (opts.label) labLabel(opts.label, x, top - 12, { size: 12 });
    return { x, left, right, top, bottom: y, gasEnd, w, h };
  }
  const top = y - h;
  const level = Math.min(1, Math.max(0, opts.level || 0));
  const surface = y - r - (h - r - 6) * level;
  if (level > 0) {
    noStroke();
    fill(opts.liquid || "#bfdbfe");
    arc(x, y - r, w - 4, w - 4, 0, PI);
    rect(left + 2, surface, w - 4, y - r - surface);
  }
  labGlassStroke();
  line(left, top, left, y - r);
  line(right, top, right, y - r);
  arc(x, y - r, w, w, 0, PI);
  pop();
  if (opts.label) labLabel(opts.label, x, top - 12, { size: 12 });
  return { x, left, right, top, bottom: y, surface, w, h };
}

/* Bunsen burner standing on y. opts: {on, size 0..1} — the flame flickers by itself while on. */
function labBurner(x, y, opts = {}) {
  push();
  noStroke();
  fill(70, 80, 95);
  rect(x - 28, y - 10, 56, 10, 3);
  fill(110, 120, 135);
  rect(x - 7, y - 70, 14, 62, 2);
  if (opts.on) {
    const s = 0.7 + 0.3 * (opts.size === undefined ? 1 : opts.size);
    const flick = 1 + 0.08 * Math.sin(frameCount * 0.6) + 0.05 * Math.sin(frameCount * 1.7);
    fill(255, 150, 40, 200);
    ellipse(x, y - 70 - 26 * s * flick, 26 * s, 56 * s * flick);
    fill(70, 130, 255, 220);
    ellipse(x, y - 70 - 14 * s, 12 * s, 28 * s);
  }
  pop();
  return { x, top: y - 70, bottom: y };
}

/* Tripod stand with wire gauze: feet on y, flat top at y - h (put a dish or beaker on result.top). */
function labTripod(x, y, opts = {}) {
  const w = opts.w || 130, h = opts.h || 120;
  const top = y - h;
  push();
  stroke(80, 85, 95);
  strokeWeight(4);
  line(x - w / 2 + 8, top, x - w / 2 - 6, y);
  line(x + w / 2 - 8, top, x + w / 2 + 6, y);
  line(x - w / 2 - 6, top, x + w / 2 + 6, top);
  stroke(150);
  strokeWeight(2);
  for (let i = -3; i <= 3; i++) line(x + i * (w / 8) - 3, top - 2, x + i * (w / 8) + 3, top + 2); /* gauze */
  pop();
  return { x, top, bottom: y, w, h };
}

/* China dish resting on y. opts: {w, color of the contents, amount 0..1, crystals: true → small crystals} */
function labDish(x, y, opts = {}) {
  const w = opts.w || 120, depth = w * 0.24;
  push();
  noStroke();
  const amount = opts.amount === undefined ? 0.6 : opts.amount;
  if (amount > 0) {
    fill(opts.color || "#3b82f6");
    if (opts.crystals) {
      for (let i = 0; i < 9; i++) {
        const cx = x - w * 0.3 + (i % 5) * w * 0.15 + (i > 4 ? w * 0.07 : 0);
        const cy = y - depth * 0.35 - (i > 4 ? 9 : 0) - depth * 0.3 * amount;
        quad(cx, cy - 6, cx + 7, cy, cx, cy + 6, cx - 7, cy);
      }
    } else {
      ellipse(x, y - depth * 0.45, w * 0.8 * Math.max(0.3, amount), depth * 0.5);
    }
  }
  stroke(120, 125, 135);
  strokeWeight(2.5);
  noFill();
  arc(x, y - depth, w, depth * 2, 0, PI);
  line(x - w / 2 - 4, y - depth, x + w / 2 + 4, y - depth);
  pop();
  if (opts.label) labLabel(opts.label, x, y + 14, { size: 12 });
  return { x, top: y - depth, bottom: y, w };
}

/* Dropper whose tip is at (x, tipY). opts: {color, drop 0..1 (a falling drop while 0 < drop < 1), dropTo y} */
function labDropper(x, tipY, opts = {}) {
  push();
  labGlassStroke();
  line(x - 6, tipY - 70, x - 6, tipY - 12);
  line(x + 6, tipY - 70, x + 6, tipY - 12);
  line(x - 6, tipY - 12, x - 2, tipY);
  line(x + 6, tipY - 12, x + 2, tipY);
  noStroke();
  fill(opts.color || "#bfdbfe");
  rect(x - 4, tipY - 40, 8, 28);
  fill(185, 60, 60);
  rect(x - 9, tipY - 92, 18, 24, 8); /* rubber bulb */
  const d = opts.drop || 0;
  if (d > 0 && d < 1) {
    const to = opts.dropTo === undefined ? tipY + 120 : opts.dropTo;
    fill(opts.color || "#bfdbfe");
    stroke(80, 120, 170);
    strokeWeight(1);
    const yy = tipY + 4 + (to - tipY - 4) * d * d;
    ellipse(x, yy, 8, 11);
  }
  pop();
  if (opts.label) labLabel(opts.label, x + 14, tipY - 80, { size: 12, align: "left" });
  return { x, tip: tipY };
}

/* Glass rod in a beaker (geometry from labBeaker). opts.stir 0..1: while 0 < stir < 1 the rod circles. */
function labGlassRod(beaker, opts = {}) {
  const s = opts.stir || 0;
  const moving = s > 0 && s < 1;
  const a = moving ? s * TWO_PI * 3 : 0;
  const tipX = beaker.x + Math.cos(a) * beaker.w * 0.25;
  const tipY = beaker.bottom - 14 + (moving ? Math.sin(a) * 6 : 0);
  const topX = beaker.x + beaker.w * 0.2 + (moving ? Math.cos(a) * 10 : 0);
  push();
  stroke(150, 170, 190, 230);
  strokeWeight(6);
  line(topX + 40, beaker.top - 40, tipX, tipY);
  stroke(255, 255, 255, 200);
  strokeWeight(2);
  line(topX + 40, beaker.top - 40, tipX, tipY);
  pop();
  if (opts.label) labLabel(opts.label, topX + 40, beaker.top - 50, { size: 12 });
  return { tipX, tipY };
}

/* Electrode rod from top to bottom. opts: {sign: '+' | '-', label} — the sign is drawn at the top. */
function labElectrode(x, top, bottom, opts = {}) {
  push();
  noStroke();
  fill(60, 60, 66);
  rect(x - 4, top, 8, bottom - top, 2);
  pop();
  if (opts.sign) labLabel(opts.sign === "+" ? "+" : "−", x, top - 10, { size: 15, bold: true, color: opts.sign === "+" ? "#b91c1c" : "#1d4ed8" });
  if (opts.label) labLabel(opts.label, x, bottom + 14, { size: 12 });
  return { x, top, bottom };
}

/* Battery (cell) centred at (x, y). opts: {on, label}. Returns terminals {plus: {x, y}, minus: {x, y}}. */
function labBattery(x, y, opts = {}) {
  push();
  stroke(60);
  strokeWeight(2);
  fill(opts.on ? "#fde68a" : "#e5e7eb");
  rect(x - 40, y - 16, 80, 32, 5);
  noStroke();
  fill(opts.on ? "#16a34a" : "#9ca3af");
  ellipse(x, y, 10, 10);
  pop();
  labLabel("+", x + 30, y, { size: 14, bold: true, color: "#b91c1c", background: false });
  labLabel("−", x - 30, y, { size: 14, bold: true, color: "#1d4ed8", background: false });
  if (opts.label) labLabel(opts.label, x, y - 28, { size: 12 });
  return { plus: { x: x + 40, y }, minus: { x: x - 40, y } };
}

/* Wire through points [[x, y], …]. opts.current: dots move along the wire (from first to last point). */
function labWire(points, opts = {}) {
  push();
  stroke(70);
  strokeWeight(2);
  noFill();
  beginShape();
  for (const p of points) vertex(p[0], p[1]);
  endShape();
  if (opts.current) {
    let total = 0;
    const seg = [];
    for (let i = 1; i < points.length; i++) {
      const l = Math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]);
      seg.push(l);
      total += l;
    }
    noStroke();
    fill(234, 179, 8);
    for (let k = 0; k < Math.max(2, total / 40); k++) {
      let d = (k * 40 + frameCount * 1.5) % total;
      for (let i = 0; i < seg.length; i++) {
        if (d <= seg[i]) {
          const t = d / seg[i];
          ellipse(points[i][0] + (points[i + 1][0] - points[i][0]) * t, points[i][1] + (points[i + 1][1] - points[i][1]) * t, 5, 5);
          break;
        }
        d -= seg[i];
      }
    }
  }
  pop();
}

/* Bubbles rising from (x, fromY) to toY. opts: {rate 0..1 (0 = none), spread px, size} — animated by itself. */
function labBubbles(x, fromY, toY, opts = {}) {
  const rate = opts.rate === undefined ? 1 : opts.rate;
  if (rate <= 0) return;
  const n = Math.round(4 + 12 * Math.min(1, rate));
  const spread = opts.spread || 8;
  const travel = Math.max(1, fromY - toY);
  push();
  stroke(120, 150, 190);
  strokeWeight(1);
  fill(255, 255, 255, 220);
  for (let i = 0; i < n; i++) {
    const phase = ((frameCount * (1.2 + (i % 3) * 0.3) + i * 37) % travel) / travel;
    const bx = x + Math.sin(i * 12.9 + frameCount * 0.08) * spread;
    ellipse(bx, fromY - phase * travel, (opts.size || 5) + (i % 3), (opts.size || 5) + (i % 3));
  }
  pop();
}

/* pH (universal indicator) paper at (x, y). opts: {ph (null = not dipped yet), wet 0..1 colour change progress} */
function labPHStrip(x, y, opts = {}) {
  const dry = "#f5d77a";
  const target = opts.ph === null || opts.ph === undefined ? dry : labIndicatorColor(opts.ph);
  const wet = opts.wet === undefined ? 1 : opts.wet;
  push();
  stroke(120);
  strokeWeight(1);
  fill(labMixHex(dry, target, wet));
  rect(x - 34, y - 9, 68, 18, 3);
  pop();
  if (opts.label) labLabel(opts.label, x, y + 20, { size: 12 });
  return { x, y };
}

/* Thermometer with its bulb at (x, y). opts: {value, min, max, label} */
function labThermometer(x, y, opts = {}) {
  const min = opts.min === undefined ? 0 : opts.min, max = opts.max === undefined ? 100 : opts.max;
  const h = opts.h || 150;
  const t = Math.min(1, Math.max(0, ((opts.value || 0) - min) / (max - min)));
  push();
  stroke(120);
  strokeWeight(2);
  fill(255);
  rect(x - 6, y - h, 12, h, 6);
  noStroke();
  fill(220, 38, 38);
  ellipse(x, y, 18, 18);
  rect(x - 3, y - 8 - (h - 14) * t, 6, (h - 14) * t + 8);
  pop();
  if (opts.label) labLabel(opts.label, x + 14, y - h, { size: 12, align: "left" });
  return { x, top: y - h, bottom: y };
}

/* ---------- complete setups for common school experiments (hand-drawn and checked by eye) ----------
 * Each fills the apparatus area correctly; the AI only switches it on/off and writes the readings.
 * Gas collection is accumulated by the kit itself (it grows while the current flows). */

LAB.setup = { gas: 0, last: null };

function labSetupReset() {
  LAB.setup.gas = 0;
}

/* Electrolysis of water: beaker, two inverted tubes full of water, electrodes through the base, battery underneath.
 * opts: {on, conducts (enough ions?), liquid, cathodeGas "H₂", anodeGas "O₂", ratio 2 (cathode : anode volume)} */
function labElectrolysis(area, opts = {}) {
  const now = millis();
  const dt = LAB.setup.last === null ? 0 : Math.min(100, now - LAB.setup.last);
  LAB.setup.last = now;
  const flowing = !!opts.on && opts.conducts !== false;
  if (flowing) LAB.setup.gas = Math.min(1, LAB.setup.gas + dt / 15000);
  const ratio = opts.ratio || 2;
  const bottom = area.y + area.h - 95;
  const beaker = labBeaker(area.x + area.w * 0.42, bottom, { w: 260, h: 190, level: 0.75, liquid: opts.liquid || "#bfdbfe" });
  const cathodeX = beaker.x - 60, anodeX = beaker.x + 60;
  const mouth = beaker.surface + 30;
  const share = (k) => (LAB.setup.gas * 0.75 * k) / ratio; /* the cathode gets `ratio` times more gas */
  labTestTube(cathodeX, mouth, { inverted: true, h: 150, w: 40, gas: share(ratio), gasLabel: opts.cathodeGas || "H₂", liquid: opts.liquid });
  labTestTube(anodeX, mouth, { inverted: true, h: 150, w: 40, gas: share(1), gasLabel: opts.anodeGas || "O₂", liquid: opts.liquid });
  labElectrode(cathodeX, mouth - 20, beaker.bottom + 18, { sign: "-" });
  labElectrode(anodeX, mouth - 20, beaker.bottom + 18, { sign: "+" });
  if (flowing) {
    labBubbles(cathodeX, beaker.bottom - 10, mouth - 10, { rate: 1, spread: 6 });
    labBubbles(anodeX, beaker.bottom - 10, mouth - 10, { rate: 1 / ratio, spread: 6 });
  }
  const cell = labBattery(beaker.x, beaker.bottom + 58, { on: !!opts.on });
  labWire([[cell.minus.x, cell.minus.y], [cathodeX, cell.minus.y], [cathodeX, beaker.bottom + 18]], { current: flowing });
  labWire([[anodeX, beaker.bottom + 18], [anodeX, cell.plus.y], [cell.plus.x, cell.plus.y]], { current: flowing });
  labLabel("Cathode (−)", cathodeX - 28, beaker.bottom - 40, { size: 12, align: "right" });
  labLabel("Anode (+)", anodeX + 28, beaker.bottom - 40, { size: 12, align: "left" });
  labLabel("Battery", cell.plus.x + 10, cell.plus.y, { size: 12, align: "left" });
  return { beaker, cathodeX, anodeX, gas: LAB.setup.gas, flowing };
}

/* Heating on a tripod: burner under a tripod with gauze; on it a china dish (default) or a beaker.
 * opts: {on, vessel: "dish" | "beaker", color (contents), amount 0..1, crystals, steam (show vapour), label} */
function labHeating(area, opts = {}) {
  const bench = area.y + area.h - 40;
  const x = area.x + area.w * 0.45;
  push();
  stroke(150);
  strokeWeight(2);
  line(area.x + 20, bench, area.x + area.w - 20, bench); /* bench */
  pop();
  const tripod = labTripod(x, bench, { w: 150, h: 125 });
  labBurner(x, bench, { on: !!opts.on, size: 1 });
  let top;
  if (opts.vessel === "beaker") {
    const b = labBeaker(x, tripod.top - 2, { w: 120, h: 110, level: opts.amount === undefined ? 0.6 : opts.amount, liquid: opts.color || "#bfdbfe" });
    top = b.top;
  } else {
    const d = labDish(x, tripod.top - 2, { w: 120, color: opts.color || "#3b82f6", amount: opts.amount === undefined ? 0.7 : opts.amount, crystals: opts.crystals !== false });
    top = d.top;
  }
  if (opts.on && opts.steam) {
    push();
    noFill();
    stroke(170, 180, 195, 170);
    strokeWeight(3);
    for (let i = 0; i < 4; i++) {
      const sx = x - 30 + i * 20;
      const rise = (frameCount * 0.8 + i * 15) % 60;
      bezier(sx, top - 6 - rise, sx - 8, top - 20 - rise, sx + 8, top - 30 - rise, sx, top - 44 - rise);
    }
    pop();
    labLabel("Water vapour", x + 60, top - 50, { size: 12, align: "left" });
  }
  if (opts.label) labLabel(opts.label, x - 90, tripod.top - 10, { size: 12, align: "right" });
  labLabel("Burner", x + 34, bench - 20, { size: 12, align: "left" });
  labLabel("Tripod", x - 80, bench - 60, { size: 12, align: "right" });
  return { x, top, bench, tripod };
}

/* Does a liquid conduct? Battery, bulb and two electrodes dipped in a beaker. opts: {on, conducts, liquid, label} */
function labConductivity(area, opts = {}) {
  const bottom = area.y + area.h - 40;
  const beaker = labBeaker(area.x + area.w * 0.35, bottom, { w: 200, h: 170, level: 0.7, liquid: opts.liquid || "#bfdbfe", label: opts.label });
  const leftX = beaker.x - 45, rightX = beaker.x + 45, topY = beaker.top - 40;
  labElectrode(leftX, topY, beaker.surface + 70, {});
  labElectrode(rightX, topY, beaker.surface + 70, {});
  const lit = !!opts.on && !!opts.conducts;
  /* one simple loop, no crossing wires: left electrode → bulb (on the top wire) → battery → right electrode */
  const yTop = area.y + 50;
  const bulbX = area.x + area.w * 0.5;
  const cell = { x: area.x + area.w * 0.78, y: topY - 50 };
  labWire([[leftX, topY], [leftX, yTop], [bulbX - 20, yTop]], { current: lit });
  labWire([[bulbX + 20, yTop], [cell.x + 70, yTop], [cell.x + 70, cell.y], [cell.x + 40, cell.y]], { current: lit });
  labWire([[cell.x - 40, cell.y], [rightX, cell.y], [rightX, topY]], { current: lit });
  push();
  if (lit) {
    noStroke();
    fill(253, 224, 71, 90);
    const glow = 84 + 6 * Math.sin(frameCount * 0.2);
    ellipse(bulbX, yTop - 4, glow, glow);
  }
  stroke(90);
  strokeWeight(2);
  fill(lit ? "#fde047" : "#f1f5f9");
  ellipse(bulbX, yTop - 8, 40, 40);
  fill(150);
  rect(bulbX - 20, yTop - 3, 40, 10, 3);
  pop();
  labBattery(cell.x, cell.y, { on: !!opts.on });
  labLabel(lit ? "Bulb glows" : "Bulb", bulbX + 30, yTop + 22, { size: 12, align: "left", bold: lit });
  labLabel("Battery", cell.x, cell.y + 30, { size: 12 });
  return { beaker, lit };
}

/* Colour of a solution containing an indicator at a given pH (school charts; pure, unit-tested).
 * universal: chart colour (a little lighter in solution); phenolphthalein: colourless below 8.2, pink from 8.2;
 * litmus: red in acid, purple at 7, blue in base; none: a colourless solution (drawn pale blue to be visible). */
function labIndicatorLiquid(ph, indicator) {
  if (indicator === "universal") return labMixHex(labIndicatorColor(ph), "#ffffff", 0.3);
  if (indicator === "phenolphthalein") return ph >= 8.2 ? "#f472b6" : "#eef2ff";
  if (indicator === "litmus") return ph < 6.5 ? "#f87171" : ph > 7.5 ? "#60a5fa" : "#a78bfa";
  return "#e0f2fe";
}

/* Acid–base neutralisation: a dropper of base over a beaker of acid (with an indicator), a glass rod, pH paper.
 * opts: {ph, indicator: "universal" | "phenolphthalein" | "litmus" | "none", drop 0..1, stir 0..1,
 *        strip: null (not tested yet) or the pH shown on the pH paper, acid: "Dilute HCl", base: "NaOH"} */
function labNeutralisation(area, opts = {}) {
  const bottom = area.y + area.h - 40;
  const liquid = labIndicatorLiquid(opts.ph === undefined ? 7 : opts.ph, opts.indicator || "none");
  const beaker = labBeaker(area.x + area.w * 0.36, bottom, { w: 210, h: 190, level: 0.55, liquid: liquid, swirl: opts.stir, maxMl: 250 });
  labGlassRod(beaker, { stir: opts.stir });
  const dropperX = beaker.x - 40;
  labDropper(dropperX, beaker.top - 25, { color: "#e0f2fe", drop: opts.drop, dropTo: beaker.surface });
  labLabel(opts.base || "NaOH", dropperX - 14, beaker.top - 95, { size: 12, align: "right" });
  labLabel((opts.acid || "Dilute HCl") + (opts.indicator && opts.indicator !== "none" ? " + " + opts.indicator + " indicator" : ""), beaker.x, beaker.bottom + 14, { size: 12 });
  const stripX = area.x + area.w * 0.8;
  labPHStrip(stripX, beaker.surface + 10, { ph: opts.strip === undefined ? null : opts.strip });
  labLabel("pH paper", stripX, beaker.surface + 34, { size: 12 });
  return { beaker, dropperX, stripX };
}

/* ---------- p5 entry points (the AI-written part must NOT define setup/draw) ---------- */

function setup() {
  createCanvas(LAB.W, LAB.H);
  textFont("Segoe UI, Arial, sans-serif");
  labInstallCompat();
  try {
    if (SIM.setup) SIM.setup();
    if (SIM.controls) SIM.controls();
  } catch (e) {
    LAB.error = e;
  }
}

function draw() {
  background(246);
  LAB.placed = [];
  labTitle(SIM.title);
  const a = LAB.apparatus;
  push();
  noFill();
  stroke(225);
  rect(a.x, a.y, a.w, a.h, 8);
  pop();
  if (!LAB.error) {
    push();
    drawingContext.save();
    drawingContext.beginPath();
    drawingContext.rect(a.x, a.y, a.w, a.h);
    drawingContext.clip(); // the experiment cannot draw over the panel or the bands
    try {
      SIM.drawApparatus(a);
    } catch (e) {
      LAB.error = e;
    }
    drawingContext.restore();
    pop();
  }
  let lines = [];
  try {
    lines = SIM.panel ? SIM.panel() : [];
  } catch (e) {
    LAB.error = LAB.error || e;
  }
  labPanel(lines);
  labObserve(SIM.observe);
  if (LAB.error) {
    push();
    fill(190, 30, 45);
    noStroke();
    textSize(15);
    textAlign(LEFT, TOP);
    text("Simulation error: " + LAB.error.message + " — use Regenerate in Lesson Studio.", a.x + 12, a.y + 12, a.w - 24);
    pop();
  }
}

if (typeof module !== "undefined") {
  module.exports = {
    labPlace, labOverlaps, labWrap, labClampRect, labIndicatorColor, labIndicatorLiquid, labMixHex, labMakeChainable, LAB,
  };
}
