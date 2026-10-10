/* AI Teaching Studio — maths visual kit (written by hand, not by AI).
 *
 * Draws scenes built by app/lessons/maths.py. Every number shown was COMPUTED by the app (prime factors, HCF, LCM,
 * angle sums, equation steps); this file only draws and animates them. Scenes:
 *   factor_tree · venn (HCF/LCM) · division (Euclid) · runners (LCM on a track) · sieve (primes)
 *   balance (one-variable equations) · angle (drag a ray: complementary, supplementary, linear pair, vertical …)
 *   angle3d (real objects in 3D: ramp, door, laptop, scissors, clock — drag to turn, slider for the angle)
 * Step through with Next / Back / Play (keys ← → Space). No libraries, no network.
 */
const MK = (() => {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";
  const C = { prime: "#16a34a", composite: "#2563eb", common: "#d97706", a: "#2563eb", b: "#db2777", ink: "#1f2937", soft: "#e5e7eb" };

  /* ---------- pure helpers (unit-tested in Node) ---------- */
  const deg = (r) => (r * 180) / Math.PI;
  const rad = (d) => (d * Math.PI) / 180;
  const product = (list) => list.reduce((p, x) => p * x, 1);
  function treeDepth(node) {
    return node.children ? 1 + Math.max(...node.children.map(treeDepth)) : 0;
  }
  /* Positions of runners after t minutes on a track of radius r: angle = 2π t / lap (start at the top). */
  function runnerAngles(laps, t) {
    return laps.map((lap) => -Math.PI / 2 + (2 * Math.PI * (t % lap)) / lap);
  }
  /* Angle (degrees, 0..360) of a point around a centre, measured anticlockwise from the right (screen y down). */
  function pointerAngle(cx, cy, x, y) {
    const a = deg(Math.atan2(cy - y, x - cx));
    return (a + 360) % 360;
  }

  /* ---------- SVG helpers ---------- */
  function el(name, attrs, parent, text) {
    const node = document.createElementNS(NS, name);
    for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, v);
    if (text !== undefined) node.textContent = text;
    if (parent) parent.appendChild(node);
    return node;
  }
  const txt = (parent, x, y, s, size, attrs) =>
    el("text", Object.assign({ x, y, "font-size": size || 18, "text-anchor": "middle", fill: C.ink, "font-weight": 600 }, attrs || {}), parent, s);
  function arcPath(cx, cy, r, a0, a1) {
    // angles in degrees, anticlockwise from the right; screen y is down
    const p = (a) => [cx + r * Math.cos(rad(a)), cy - r * Math.sin(rad(a))];
    const [x0, y0] = p(a0), [x1, y1] = p(a1);
    const large = ((a1 - a0 + 360) % 360) > 180 ? 1 : 0;
    return `M${cx},${cy} L${x0},${y0} A${r},${r} 0 ${large} 0 ${x1},${y1} Z`;
  }

  /* ---------- 2D scenes ---------- */

  function factorTree(svg, s) {
    const depth = treeDepth(s.tree);
    const W = 900, H = 150 + depth * 95, spread = Math.min(80, 520 / Math.max(1, depth));
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    const g = el("g", {}, svg);
    const nodes = [];
    function place(node, x, y, level) {
      const item = { node, x, y, level };
      nodes.push(item);
      if (node.children) {
        const [p, rest] = node.children;
        item.kids = [place(p, x - spread, y + 95, level + 1), place(rest, x + spread, y + 95, level + 1)];
      }
      return item;
    }
    place(s.tree, 300, 60, 0);
    const shapes = nodes.map((it) => {
      const gr = el("g", {}, g);
      if (it.kids) for (const k of it.kids) el("line", { x1: it.x, y1: it.y + 26, x2: k.x, y2: k.y - 26, stroke: "#94a3b8", "stroke-width": 3 }, gr);
      el("circle", { cx: it.x, cy: it.y, r: 28, fill: it.node.prime ? C.prime : C.composite }, gr);
      txt(gr, it.x, it.y + 7, String(it.node.n), 20, { fill: "#fff" });
      return { gr, level: it.level };
    });
    const result = txt(g, W / 2, H - 18, s.result, 28, { fill: C.prime });
    const steps = [];
    for (let level = 0; level <= depth; level++) {
      const here = nodes.filter((n) => n.level === level && n.kids);
      steps.push({ name: level === 0 ? `Start with ${s.tree.n}` : `Level ${level}`,
        caption: here.length ? `Split ${here.map((h) => h.node.n).join(", ")} = ${here.map((h) => h.node.children.map((c) => c.n).join(" × ")).join(", ")} (always try the smallest prime first).` : "All the ends are prime numbers (green) — they cannot be split any more." });
    }
    steps.push({ name: "Result", caption: `${s.result}. Green circles are prime factors.` });
    return { steps, show: (k) => {
      shapes.forEach((sh) => sh.gr.setAttribute("opacity", sh.level <= k + 1 ? 1 : 0.06));
      result.setAttribute("opacity", k >= steps.length - 1 ? 1 : 0);
    } };
  }

  function venn(svg, s) {
    const W = 900, H = 520;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    const g = el("g", {}, svg);
    el("circle", { cx: 340, cy: 250, r: 190, fill: C.a, "fill-opacity": 0.12, stroke: C.a, "stroke-width": 3 }, g);
    el("circle", { cx: 560, cy: 250, r: 190, fill: C.b, "fill-opacity": 0.12, stroke: C.b, "stroke-width": 3 }, g);
    txt(g, 230, 50, `Factors of ${s.a}`, 22, { fill: C.a });
    txt(g, 670, 50, `Factors of ${s.b}`, 22, { fill: C.b });
    const chips = (list, x, colour) => list.map((p, i) => {
      const y = 250 + (i - (list.length - 1) / 2) * 52;
      const c = el("g", {}, g);
      el("circle", { cx: x, cy: y, r: 22, fill: colour }, c);
      txt(c, x, y + 7, String(p), 20, { fill: "#fff" });
      return c;
    });
    const onlyA = chips(s.only_a, 255, C.a), common = chips(s.common, 450, C.common), onlyB = chips(s.only_b, 645, C.b);
    const hcfText = txt(g, 450, 480, `HCF = ${s.common.length ? s.common.join(" × ") + " = " : ""}${s.hcf}  (the overlap)`, 24, { fill: C.common });
    const lcmText = txt(g, 450, 512, `LCM = ${[...s.only_a, ...s.common, ...s.only_b].join(" × ")} = ${s.lcm}  (everything)`, 24, { fill: "#7c3aed" });
    const steps = [
      { name: "Prime factors", caption: `${s.a} = ${[...s.only_a, ...s.common].join(" × ")} and ${s.b} = ${[...s.common, ...s.only_b].join(" × ")}.` },
      { name: "Common factors", caption: `The factors both numbers share go in the overlap: ${s.common.join(", ") || "none (they are co-prime)"}.` },
      { name: "HCF", caption: `HCF = product of the overlap = ${s.hcf}. It is the biggest number that divides both.` },
      { name: "LCM", caption: `LCM = product of every factor in the picture = ${s.lcm}. It is the smallest number both divide into.` },
    ];
    return { steps, show: (k) => {
      [...onlyA, ...onlyB].forEach((c) => c.setAttribute("opacity", 1));
      common.forEach((c) => c.setAttribute("opacity", k >= 1 ? 1 : 0.15));
      hcfText.setAttribute("opacity", k >= 2 ? 1 : 0);
      lcmText.setAttribute("opacity", k >= 3 ? 1 : 0);
    } };
  }

  function division(svg, s) {
    const W = 900, H = 120 + s.steps.length * 90;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    const g = el("g", {}, svg);
    const rows = s.steps.map((st, i) => {
      const y = 70 + i * 90, gr = el("g", {}, g);
      el("rect", { x: 120, y: y - 40, width: 660, height: 70, rx: 12, fill: st.remainder === 0 ? "#dcfce7" : "#eff6ff", stroke: "#94a3b8" }, gr);
      txt(gr, 450, y + 6, `${st.dividend} = ${st.divisor} × ${st.quotient} + ${st.remainder}`, 28);
      txt(gr, 830, y + 6, st.remainder === 0 ? "✓" : "↓", 30, { fill: st.remainder === 0 ? C.prime : "#64748b" });
      return gr;
    });
    const fin = txt(g, 450, H - 20, `HCF = ${s.hcf} (the last divisor, when the remainder becomes 0)`, 24, { fill: C.prime });
    const steps = s.steps.map((st, i) => ({ name: `Division ${i + 1}`,
      caption: i === 0 ? `Divide the bigger number ${st.dividend} by the smaller ${st.divisor}: remainder ${st.remainder}.`
        : `Now divide the last divisor ${st.dividend} by the remainder ${st.divisor}: remainder ${st.remainder}.` }));
    steps.push({ name: "HCF", caption: `The remainder is 0, so the last divisor ${s.hcf} is the HCF.` });
    return { steps, show: (k) => {
      rows.forEach((r, i) => r.setAttribute("opacity", i <= k ? 1 : 0.06));
      fin.setAttribute("opacity", k >= steps.length - 1 ? 1 : 0);
    } };
  }

  function runners(svg, s) {
    const W = 900, H = 560, cx = 300, cy = 285, R = 210;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    const g = el("g", {}, svg);
    el("circle", { cx, cy, r: R + 22, fill: "#fed7aa" }, g);
    el("circle", { cx, cy, r: R - 22, fill: "#bbf7d0" }, g);
    for (const r of [R - 7, R + 7]) el("circle", { cx, cy, r, fill: "none", stroke: "#fff", "stroke-width": 2, "stroke-dasharray": "6 6" }, g);
    el("line", { x1: cx, y1: cy - R - 26, x2: cx, y2: cy - R + 26, stroke: C.ink, "stroke-width": 5 }, g);
    txt(g, cx, cy - R - 34, "START", 16);
    const colours = ["#2563eb", "#db2777", "#d97706", "#7c3aed"];
    const dots = s.laps.map((lap, i) => el("circle", { r: 13, fill: colours[i], stroke: "#fff", "stroke-width": 3 }, g));
    const clock = txt(g, cx, cy + 10, "0 min", 34);
    const legend = s.laps.map((lap, i) => {
      const y = 90 + i * 70;
      el("circle", { cx: 640, cy: y - 7, r: 12, fill: colours[i] }, g);
      txt(g, 665, y, `Runner ${i + 1}: one lap in ${lap} min`, 20, { "text-anchor": "start" });
      return txt(g, 665, y + 28, "", 15, { "text-anchor": "start", fill: "#475569", "font-weight": 400 });
    });
    const meet = txt(g, 690, 90 + s.laps.length * 70 + 40, `All meet at START after ${s.lcm} min (LCM)`, 22, { fill: C.prime });
    let t = 0;
    function draw(time) {
      t = time;
      runnerAngles(s.laps, t).forEach((a, i) => {
        const r = R - 12 + i * 8;
        dots[i].setAttribute("cx", cx + r * Math.cos(a));
        dots[i].setAttribute("cy", cy + r * Math.sin(a));
      });
      clock.textContent = `${Math.floor(t)} min`;
      s.laps.forEach((lap, i) => {
        const done = Math.floor(t / lap + 1e-9), first = Math.max(0, done - 5);
        legend[i].textContent = `back at START at: ${first ? "… " : ""}${Array.from({ length: done - first + 1 }, (_, k) => (first + k) * lap).join(", ")} min`;
      });
      meet.setAttribute("opacity", t >= s.lcm - 1e-6 ? 1 : 0);
    }
    let timer = null;
    function run(from, to) {
      clearInterval(timer);
      const start = performance.now(), span = Math.max(1, to - from), ms = Math.min(9000, 60 * span);
      timer = setInterval(() => {
        const f = Math.min(1, (performance.now() - start) / ms);
        draw(from + span * f);
        if (f >= 1) clearInterval(timer);
      }, 30);
    }
    const marks = [0, ...s.laps.slice().sort((a, b) => a - b), s.lcm];
    const steps = marks.map((m, i) => ({ name: i === 0 ? "Start" : i === marks.length - 1 ? "LCM" : `${m} minutes`,
      caption: i === 0 ? `All ${s.laps.length} runners start together. When will they ALL be at the start again?`
        : i === marks.length - 1 ? `After ${s.lcm} minutes every runner is at the start: ${s.lcm} is a multiple of ${s.laps.join(", ")} — the smallest one (LCM).`
        : `After ${m} minutes the runner with a ${m}-minute lap is back at the start — but the others are not.` }));
    return { steps, show: (k) => run(t, marks[k]), stop: () => clearInterval(timer) };
  }

  function sieve(svg, s) {
    const cols = 10, rows = Math.ceil(s.top / cols), size = 64;
    svg.setAttribute("viewBox", `0 0 ${cols * size + 40} ${rows * size + 40}`);
    const g = el("g", {}, svg);
    const primes = new Set(s.primes), twin = new Set(s.twins.flat());
    const cells = [];
    for (let n = 1; n <= s.top; n++) {
      const x = 20 + ((n - 1) % cols) * size, y = 20 + Math.floor((n - 1) / cols) * size;
      const gr = el("g", {}, g);
      const box = el("rect", { x, y, width: size - 6, height: size - 6, rx: 8, fill: "#f8fafc", stroke: "#cbd5e1" }, gr);
      txt(gr, x + (size - 6) / 2, y + 38, String(n), 22);
      cells.push({ n, box });
    }
    const small = [2, 3, 5, 7].filter((p) => p * p <= s.top || p <= s.top);
    const steps = [{ name: "Numbers", caption: `The numbers from 1 to ${s.top}. 1 is neither prime nor composite.` }]
      .concat(small.map((p) => ({ name: `Multiples of ${p}`, caption: `Cross out the multiples of ${p} (except ${p} itself) — they have ${p} as a factor.` })))
      .concat([{ name: "Primes", caption: `What is left are the primes: ${s.primes.length} prime numbers up to ${s.top}.` }]);
    if (s.twins.length) steps.push({ name: "Twin primes", caption: `Twin primes differ by 2: ${s.twins.map((t) => `(${t[0]}, ${t[1]})`).join(", ")}.` });
    return { steps, show: (k) => {
      const crossed = new Set([1]);
      small.slice(0, Math.max(0, k)).forEach((p) => { for (let m = 2 * p; m <= s.top; m += p) crossed.add(m); });
      const final = k >= small.length + 1;
      cells.forEach(({ n, box }) => {
        const isTwin = k >= small.length + 2 && twin.has(n);
        box.setAttribute("fill", isTwin ? "#fde68a" : final && primes.has(n) ? "#bbf7d0" : crossed.has(n) ? "#fee2e2" : "#f8fafc");
        box.setAttribute("stroke", final && primes.has(n) ? C.prime : "#cbd5e1");
      });
    } };
  }

  function balance(svg, s) {
    const W = 900, H = 460;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    const g = el("g", {}, svg);
    el("polygon", { points: "450,380 410,440 490,440", fill: "#475569" }, g);
    el("rect", { x: 140, y: 372, width: 620, height: 14, rx: 7, fill: "#64748b" }, g);
    const panL = el("g", {}, g), panR = el("g", {}, g);
    for (const [pan, x] of [[panL, 260], [panR, 640]]) {
      el("line", { x1: x, y1: 372, x2: x, y2: 300, stroke: "#64748b", "stroke-width": 4 }, pan);
      el("path", { d: `M${x - 150},300 Q${x},360 ${x + 150},300 Z`, fill: "#e2e8f0", stroke: "#64748b", "stroke-width": 3 }, pan);
    }
    const left = txt(g, 260, 270, "", 34, { fill: C.a }), right = txt(g, 640, 270, "", 34, { fill: C.b });
    const big = txt(g, 450, 90, "", 40);
    const history = s.steps.map((eq, i) => txt(g, 40, 30 + i * 0, "", 16, { "text-anchor": "start", fill: "#64748b", "font-weight": 400 }));
    const steps = s.steps.map((eq, i) => ({ name: `Step ${i + 1}`, caption: (s.reasons || [])[i] || "" }));
    return { steps, show: (k) => {
      const [l, r] = s.steps[k].split("=");
      left.textContent = l.trim();
      right.textContent = r.trim();
      big.textContent = s.steps[k];
      big.setAttribute("fill", k === s.steps.length - 1 ? C.prime : C.ink);
      history.forEach((h, i) => {
        h.setAttribute("y", 150 + i * 24);
        h.textContent = i < k ? `${i + 1}. ${s.steps[i]}` : "";
      });
    } };
  }

  /* Interactive angle explorer: drag the green ray; the kit measures and adds. */
  function angle(svg, s) {
    const mode = s.mode;
    const W = 900, H = 520, cx = 420, cy = mode === "vertical" ? 270 : 380, R = mode === "vertical" ? 220 : 300;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    const g = el("g", {}, svg);
    const limit = mode === "complementary" ? 90 : 180;
    let a = Math.min(limit - 1, Math.max(1, s.angle || 40));
    let cross = 35; // for vertically opposite angles: angle between the two lines
    const fixed = el("g", {}, g), moving = el("g", {}, g), labels = el("g", {}, g);
    const ray = (angleDeg, colour, width, name, parent) => {
      const x = cx + R * Math.cos(rad(angleDeg)), y = cy - R * Math.sin(rad(angleDeg));
      el("line", { x1: cx, y1: cy, x2: x, y2: y, stroke: colour, "stroke-width": width, "stroke-linecap": "round" }, parent);
      el("circle", { cx: x, cy: y, r: 6, fill: colour }, parent);
      if (name) txt(parent, cx + (R + 48) * Math.cos(rad(angleDeg)), cy - (R + 34) * Math.sin(rad(angleDeg)) + 7, name, 22);
    };
    const handle = el("circle", { r: 18, fill: "#16a34a", "fill-opacity": 0.35, stroke: "#16a34a", "stroke-width": 3, style: "cursor:grab" }, g);
    const readout = txt(g, 700, 60, "", 28);
    const readout2 = txt(g, 640, 100, "", 19, { fill: "#475569" });
    function draw() {
      fixed.innerHTML = "";
      moving.innerHTML = "";
      labels.innerHTML = "";
      if (mode === "vertical") {
        // two straight lines crossing at the vertex; drag rotates one line
        for (const [deg0, colour] of [[0, "#2563eb"], [cross, "#16a34a"]]) {
          ray(deg0, colour, 6, "", moving);
          ray(deg0 + 180, colour, 6, "", moving);
        }
        const parts = [[0, cross, "#fde68a"], [cross, 180, "#bfdbfe"], [180, 180 + cross, "#fde68a"], [180 + cross, 360, "#bfdbfe"]];
        parts.forEach(([a0, a1, colour], i) => {
          el("path", { d: arcPath(cx, cy, i % 2 ? 70 : 95, a0, a1), fill: colour, "fill-opacity": 0.8 }, fixed);
          const mid = rad((a0 + a1) / 2);
          txt(labels, cx + 135 * Math.cos(mid), cy - 135 * Math.sin(mid) + 7, `${Math.round(a1 - a0)}°`, 22);
        });
        handle.setAttribute("cx", cx + R * Math.cos(rad(cross)));
        handle.setAttribute("cy", cy - R * Math.sin(rad(cross)));
        readout.textContent = `Opposite angles: ${Math.round(cross)}° = ${Math.round(cross)}°`;
        readout2.textContent = `and ${Math.round(180 - cross)}° = ${Math.round(180 - cross)}°  (always equal)`;
        return;
      }
      const base = 0, top = mode === "complementary" ? 90 : 180;
      ray(base, "#2563eb", 6, mode === "parts" ? "arm QR" : "R", fixed);
      if (mode !== "parts") ray(top, "#2563eb", 6, mode === "complementary" ? "P" : "P", fixed);
      if (mode === "parts") {
        ray(a, "#2563eb", 6, "arm QP", fixed);
        el("path", { d: arcPath(cx, cy, 260, base, a), fill: "#bbf7d0", "fill-opacity": 0.6 }, fixed);
        txt(labels, cx + 160 * Math.cos(rad(a / 2)), cy - 160 * Math.sin(rad(a / 2)), "interior", 22, { fill: C.prime });
        txt(labels, cx + 170, cy + 80, "exterior (outside)", 22, { fill: "#b45309" });
        txt(labels, cx - 26, cy + 30, "Q (vertex)", 20);
        readout.textContent = `∠PQR = ${Math.round(a)}°`;
        readout2.textContent = "Drag the arm: the interior grows or shrinks";
      } else {
        ray(a, "#16a34a", 6, "S", moving);
        el("path", { d: arcPath(cx, cy, 90, base, a), fill: "#fde68a", "fill-opacity": 0.85 }, fixed);
        el("path", { d: arcPath(cx, cy, 70, a, top), fill: "#bfdbfe", "fill-opacity": 0.85 }, fixed);
        txt(labels, cx + 130 * Math.cos(rad(a / 2)), cy - 130 * Math.sin(rad(a / 2)) + 7, `${Math.round(a)}°`, 24);
        txt(labels, cx + 120 * Math.cos(rad((a + top) / 2)), cy - 120 * Math.sin(rad((a + top) / 2)) + 7, `${Math.round(top - a)}°`, 24);
        txt(labels, cx, cy + 32, "Q", 22);
        if (top === 180) el("line", { x1: cx - R, y1: cy, x2: cx + R, y2: cy, stroke: "#2563eb", "stroke-width": 6 }, fixed);
        readout.textContent = `${Math.round(a)}° + ${Math.round(top - a)}° = ${top}°`;
        readout2.textContent = { complementary: "complementary angles (sum 90°)", supplementary: "supplementary angles (sum 180°)",
          linear_pair: "a linear pair: adjacent angles on a straight line", adjacent: "adjacent angles: common vertex Q, common arm QS",
          opposite_rays: "QP and QR are opposite rays: one straight line, 180°" }[mode] || "";
      }
      handle.setAttribute("cx", cx + R * Math.cos(rad(a)));
      handle.setAttribute("cy", cy - R * Math.sin(rad(a)));
    }
    let dragging = false;
    const toLocal = (ev) => {
      const p = svg.createSVGPoint();
      p.x = ev.clientX;
      p.y = ev.clientY;
      return p.matrixTransform(svg.getScreenCTM().inverse());
    };
    handle.addEventListener("pointerdown", (ev) => { dragging = true; handle.setPointerCapture(ev.pointerId); });
    handle.addEventListener("pointerup", () => (dragging = false));
    handle.addEventListener("pointermove", (ev) => {
      if (!dragging) return;
      const q = toLocal(ev);
      const value = pointerAngle(cx, cy, q.x, q.y);
      if (mode === "vertical") cross = Math.min(170, Math.max(10, value > 180 ? value - 180 : value));
      else a = Math.min(limit - 1, Math.max(1, value > 270 ? 1 : value));
      draw();
    });
    draw();
    const names = { complementary: "Complementary", supplementary: "Supplementary", linear_pair: "Linear pair", vertical: "Vertically opposite",
      adjacent: "Adjacent", opposite_rays: "Opposite rays", parts: "Parts of an angle" };
    const presets = mode === "vertical" ? [35, 60, 90, 120] : mode === "complementary" ? [Math.round(a), 30, 45, 60, 75] : [Math.round(a), 30, 60, 90, 135];
    const steps = presets.map((p, i) => ({ name: `${names[mode]} ${i + 1}`,
      caption: i === 0 ? "Drag the green handle and watch the measures — try it with the class!"
        : mode === "parts" ? `Now ∠PQR = ${p}°: is it acute, right or obtuse? Point to the interior and the exterior.`
        : `Now at ${p}°: ask the class for the other angle first, then read it in the picture.` }));
    return { steps, show: (k) => { if (mode === "vertical") cross = presets[k]; else a = Math.min(limit - 1, presets[k]); draw(); } };
  }

  /* Angle (0..180) at vertex v between the rays to p and q — screen coordinates. */
  function angleAt(v, p, q) {
    const a = Math.atan2(p.y - v.y, p.x - v.x), b = Math.atan2(q.y - v.y, q.x - v.x);
    let d = Math.abs(deg(a - b));
    return d > 180 ? 360 - d : d;
  }
  /* Filled arc for the interior angle at v between rays to p and q (works for any orientation). */
  function wedge(parent, v, p, q, r, colour) {
    const a0 = pointerAngle(v.x, v.y, p.x, p.y), a1 = pointerAngle(v.x, v.y, q.x, q.y);
    const ccw = (a1 - a0 + 360) % 360;
    const [from, to] = ccw <= 180 ? [a0, a1] : [a1, a0];
    el("path", { d: arcPath(v.x, v.y, r, from, to), fill: colour, "fill-opacity": 0.85 }, parent);
    const mid = rad(from + (((to - from + 360) % 360) / 2));
    return { x: v.x + (r + 26) * Math.cos(mid), y: v.y - (r + 26) * Math.sin(mid) + 7 };
  }

  /* Triangle: drag corner A; the three angles always add up to 180°; extend BC → exterior angle = A + B. */
  function triangle(svg, s) {
    const W = 900, H = 520;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    const g = el("g", {}, svg);
    const B = { x: 170, y: 420 }, C = { x: 560, y: 420 }, D = { x: 800, y: 420 };
    const [a0, b0] = [s.angles[0], s.angles[1]];  // angles at A and B from the scene (computed / textbook)
    // place A from the angles at B and C: C angle = 180 − A − B
    const tB = rad(b0), tC = rad(180 - a0 - b0);
    const base = C.x - B.x, hb = (base * Math.sin(tC)) / Math.sin(rad(a0));
    let A = { x: B.x + hb * Math.cos(tB), y: B.y - hb * Math.sin(tB) };
    if (A.y < 70) A = { x: A.x, y: 70 };
    const shapes = el("g", {}, g), labels = el("g", {}, g);
    const handle = el("circle", { r: 18, fill: "#16a34a", "fill-opacity": 0.35, stroke: "#16a34a", "stroke-width": 3, style: "cursor:grab" }, g);
    const sum = txt(g, 450, 50, "", 26), sum2 = txt(g, 450, 84, "", 20, { fill: "#475569" });
    let stage = 0;
    function draw() {
      shapes.innerHTML = "";
      labels.innerHTML = "";
      const a = angleAt(A, B, C), b = angleAt(B, A, C), c = 180 - a - b;
      el("polygon", { points: `${A.x},${A.y} ${B.x},${B.y} ${C.x},${C.y}`, fill: "#eff6ff", stroke: "#1e3a8a", "stroke-width": 4 }, shapes);
      const pa = wedge(shapes, A, B, C, 40, "#fde68a"), pb = wedge(shapes, B, A, C, 40, "#bbf7d0"), pc = wedge(shapes, C, A, B, 40, "#fecaca");
      if (stage >= 2) {
        el("line", { x1: C.x, y1: C.y, x2: D.x, y2: D.y, stroke: "#1e3a8a", "stroke-width": 4, "stroke-dasharray": "10 6" }, shapes);
        const pe = wedge(shapes, C, A, D, 62, "#c4b5fd");
        txt(labels, pe.x + 10, pe.y - 8, `${Math.round(180 - c)}°`, 22, { fill: "#5b21b6" });
        txt(labels, D.x + 18, D.y + 7, "D", 22);
      }
      txt(labels, pa.x, pa.y, `${Math.round(a)}°`, 20);
      txt(labels, pb.x, pb.y, `${Math.round(b)}°`, 20);
      txt(labels, pc.x, pc.y, `${Math.round(c)}°`, 20);
      txt(labels, A.x, A.y - 24, "A", 22);
      txt(labels, B.x - 22, B.y + 8, "B", 22);
      txt(labels, C.x + 4, C.y + 30, "C", 22);
      handle.setAttribute("cx", A.x);
      handle.setAttribute("cy", A.y);
      sum.textContent = stage >= 1 ? `∠A + ∠B + ∠C = ${Math.round(a)}° + ${Math.round(b)}° + ${Math.round(c)}° = 180°` : "Three angles of a triangle";
      sum2.textContent = stage >= 3 ? `Exterior ∠ACD = ${Math.round(180 - c)}° = ∠A + ∠B = ${Math.round(a)}° + ${Math.round(b)}°`
        : stage >= 2 ? "Extend BC to D: ∠ACD is an exterior angle" : "Drag corner A — watch the angles change";
    }
    let dragging = false;
    const toLocal = (ev) => { const p = svg.createSVGPoint(); p.x = ev.clientX; p.y = ev.clientY; return p.matrixTransform(svg.getScreenCTM().inverse()); };
    handle.addEventListener("pointerdown", (ev) => { dragging = true; handle.setPointerCapture(ev.pointerId); });
    handle.addEventListener("pointerup", () => (dragging = false));
    handle.addEventListener("pointermove", (ev) => {
      if (!dragging) return;
      const q = toLocal(ev);
      A = { x: Math.min(W - 60, Math.max(60, q.x)), y: Math.min(B.y - 40, Math.max(60, q.y)) };
      draw();
    });
    const steps = [
      { name: "Triangle", caption: "Every triangle has three angles. Drag corner A to make any triangle you like." },
      { name: "Angle sum", caption: "However you drag it, ∠A + ∠B + ∠C is always 180°." },
      { name: "Exterior angle", caption: "Extend side BC to D. The angle ∠ACD outside the triangle is an exterior angle." },
      { name: "Remote interior angles", caption: "The exterior angle equals the sum of the two remote interior angles: ∠ACD = ∠A + ∠B." },
    ];
    return { steps, show: (k) => { stage = k; draw(); } };
  }

  /* Polygon: n sides → n − 2 triangles from one corner → angle sum (n − 2) × 180°. */
  function polygon(svg, s) {
    const W = 900, H = 520, cx = 330, cy = 280, R = 210;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    const g = el("g", {}, svg);
    const colours = ["#fde68a", "#bbf7d0", "#bfdbfe", "#fecaca", "#e9d5ff", "#fed7aa"];
    const sides = s.sides;
    const steps = sides.map((n) => ({ name: `${n} sides`,
      caption: `A polygon with ${n} sides splits into ${n - 2} triangles from one corner, so its angles add up to ${n - 2} × 180° = ${(n - 2) * 180}°.` }));
    return { steps, show: (k) => {
      g.innerHTML = "";
      const n = sides[k];
      const pts = Array.from({ length: n }, (_, i) => {
        const t = -Math.PI / 2 + (2 * Math.PI * i) / n;
        return { x: cx + R * Math.cos(t), y: cy + R * Math.sin(t) };
      });
      for (let i = 1; i < n - 1; i++) {
        el("polygon", { points: `${pts[0].x},${pts[0].y} ${pts[i].x},${pts[i].y} ${pts[i + 1].x},${pts[i + 1].y}`,
          fill: colours[(i - 1) % colours.length], stroke: "#64748b", "stroke-width": 2 }, g);
        const m = { x: (pts[0].x + pts[i].x + pts[i + 1].x) / 3, y: (pts[0].y + pts[i].y + pts[i + 1].y) / 3 };
        txt(g, m.x, m.y + 7, String(i), 22);
      }
      el("polygon", { points: pts.map((p) => `${p.x},${p.y}`).join(" "), fill: "none", stroke: "#1e3a8a", "stroke-width": 5 }, g);
      txt(g, 700, 170, `${n} sides`, 30);
      txt(g, 700, 220, `${n - 2} triangles`, 26, { fill: "#475569" });
      txt(g, 700, 280, `${n - 2} × 180° = ${(n - 2) * 180}°`, 30, { fill: C.prime });
    } };
  }

  /* ---------- 3D: real objects with an angle (hand-made tiny 3D renderer on a canvas) ---------- */
  function angle3d(svg, s) {
    const holder = svg.parentNode;
    svg.style.display = "none";
    const canvas = document.createElement("canvas");
    canvas.id = "mk3d";
    canvas.style.cssText = `width:100%;height:${svg.style.height};border:1px solid #e5e7eb;border-radius:10px;background:linear-gradient(#eff6ff,#fff);touch-action:none;cursor:grab`;
    holder.insertBefore(canvas, svg);
    const slider = document.createElement("input");
    Object.assign(slider, { type: "range", min: 5, max: s.mode === "complementary" ? 85 : 175, value: Math.round(s.angle || 40) });
    slider.style.cssText = "width:60%";
    const sliderBox = document.createElement("div");
    sliderBox.innerHTML = "<b>Angle: </b>";
    sliderBox.appendChild(slider);
    const sliderValue = document.createElement("b");
    sliderBox.appendChild(sliderValue);
    holder.insertBefore(sliderBox, svg);
    const ctx = canvas.getContext("2d");
    const view = { yaw: -0.6, pitch: 0.35 };
    const box = (x0, y0, z0, x1, y1, z1, colour) => {
      const v = [[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0], [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]];
      return [[0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 5, 4], [2, 3, 7, 6], [1, 2, 6, 5], [0, 3, 7, 4]].map((f) => ({ pts: f.map((i) => v[i]), colour }));
    };
    const rotZ = (pts, a, ox, oy) => pts.map(([x, y, z]) => [ox + (x - ox) * Math.cos(a) - (y - oy) * Math.sin(a), oy + (x - ox) * Math.sin(a) + (y - oy) * Math.cos(a), z]);
    const rotY = (pts, a, ox, oz) => pts.map(([x, y, z]) => [ox + (x - ox) * Math.cos(a) + (z - oz) * Math.sin(a), y, oz - (x - ox) * Math.sin(a) + (z - oz) * Math.cos(a)]);
    function scene(t) {
      // returns faces + an angle arc (centre, radius, from, to in the x-y plane) + labels
      const r = rad(t);
      if (s.object === "ramp") {
        const L = 4, h = L * Math.sin(r), w = L * Math.cos(r);
        const faces = box(-3, -0.1, -1.5, 3, 0, 1.5, "#d6d3d1").concat(box(-3 + w, 0, -1.5, -3 + w + 0.15, h + 0.5, 1.5, "#e7e5e4"));
        const tilted = box(-3, 0, -0.8, -3 + L, 0.12, 0.8, "#b45309").map((f) => ({ pts: rotZ(f.pts, r, -3, 0), colour: f.colour }));
        return { faces: faces.concat(tilted), arcs: [[-3, 0, 1.2, 0, t, "#fde68a", `${t}°`], [-3 + w, h, 0.8, 180 + t, 270, "#bfdbfe", `${90 - t}°`]],
          note: `Ramp: angle with the ground ${t}°, angle with the wall ${90 - t}° — complementary (sum 90°).`, arcZ: 0.9 };
      }
      if (s.object === "door") {
        const wall = box(-4, 0, -0.15, 0, 3.5, 0.15, "#e7e5e4").concat(box(1.6, 0, -0.15, 4, 3.5, 0.15, "#e7e5e4"));
        const door = box(0, 0.05, -0.06, 1.55, 3.3, 0.06, "#92400e").map((f) => ({ pts: rotY(f.pts, -r, 0, 0), colour: f.colour }));
        return { faces: wall.concat(door), arcs: [], floorArcs: [[0, 0, 1.2, 0, t, "#fde68a", `${t}°`], [0, 0, 0.9, t, 180, "#bfdbfe", `${180 - t}°`]],
          note: `Door opened ${t}°; the angle on the other side, up to the wall, is ${180 - t}° — supplementary (sum 180°).` };
      }
      if (s.object === "laptop") {
        const base = box(0, 0, -1.2, 2.6, 0.12, 1.2, "#475569");
        const lid = box(0, 0.12, -1.2, 2.6, 0.2, 1.2, "#1e293b").map((f) => ({ pts: rotZ(f.pts, r, 0, 0.12), colour: f.colour }));
        const screen = box(0.15, 0.2, -1.05, 2.45, 0.21, 1.05, "#38bdf8").map((f) => ({ pts: rotZ(f.pts, r, 0, 0.12), colour: f.colour }));
        return { faces: base.concat(lid, screen), arcs: [[0, 0.12, 1.1, 0, t, "#fde68a", `${t}°`], [0, 0.12, 0.8, t, 180, "#bfdbfe", `${180 - t}°`]],
          note: `Laptop lid open ${t}°; with the rest of the straight line it makes ${180 - t}° — a linear pair (sum 180°).`, arcZ: 1.35 };
      }
      if (s.object === "scissors") {
        const blade1 = box(-2.6, -0.06, -0.05, 2.6, 0.06, 0.05, "#94a3b8").map((f) => ({ pts: rotZ(f.pts, r / 2, 0, 0), colour: f.colour }));
        const blade2 = box(-2.6, -0.06, 0.06, 2.6, 0.06, 0.16, "#64748b").map((f) => ({ pts: rotZ(f.pts, -r / 2, 0, 0), colour: f.colour }));
        return { faces: blade1.concat(blade2), arcs: [[0, 0, 1, -t / 2, t / 2, "#fde68a", `${t}°`], [0, 0, 1, 180 - t / 2, 180 + t / 2, "#fde68a", `${t}°`],
          [0, 0, 0.7, t / 2, 180 - t / 2, "#bfdbfe", `${180 - t}°`]],
          note: `Scissors: the blades cross. Opposite angles are equal: ${t}° and ${t}°; the other pair ${180 - t}° and ${180 - t}°.` };
      }
      // clock
      const face = box(-2.2, -2.2, -0.1, 2.2, 2.2, 0, "#f8fafc");
      for (let h = 0; h < 12; h++) {
        const big = h % 3 === 0;
        face.push(...box(1.75, -0.04, 0, big ? 2.1 : 1.95, 0.04, 0.03, "#334155").map((f) => ({ pts: rotZ(f.pts, rad(h * 30), 0, 0), colour: f.colour })));
      }
      const hand1 = box(0, -0.06, 0.02, 1.9, 0.06, 0.08, "#1f2937").map((f) => ({ pts: rotZ(f.pts, rad(90), 0, 0), colour: f.colour }));
      const hand2 = box(0, -0.05, 0.1, 1.5, 0.05, 0.14, "#dc2626").map((f) => ({ pts: rotZ(f.pts, rad(90) - r, 0, 0), colour: f.colour }));
      return { faces: face.concat(hand1, hand2), arcs: [[0, 0, 0.9, 90 - t, 90, "#fde68a", `${t}°`]],
        note: `Clock hands make an angle of ${t}° (each minute mark is 6°; each hour mark is 30°).` };
    }
    function project(p, W, H) {
      const [x, y, z] = p;
      const cy = Math.cos(view.yaw), sy = Math.sin(view.yaw), cp = Math.cos(view.pitch), sp = Math.sin(view.pitch);
      const x1 = x * cy + z * sy, z1 = -x * sy + z * cy;
      const y1 = y * cp - z1 * sp, z2 = y * sp + z1 * cp;
      const k = 14 / (14 - z2), scale = Math.min(W, H) / 9;
      return [W / 2 + x1 * scale * k, H * 0.62 - y1 * scale * k, z2];
    }
    function draw() {
      const ratio = window.devicePixelRatio || 1;
      const W = canvas.clientWidth, H = canvas.clientHeight;
      canvas.width = W * ratio;
      canvas.height = H * ratio;
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      ctx.clearRect(0, 0, W, H);
      const t = Number(slider.value);
      sliderValue.textContent = ` ${t}°`;
      const sc = scene(t);
      const light = [0.4, 0.8, 0.5];
      const faces = sc.faces.map((f) => {
        const p = f.pts.map((q) => project(q, W, H));
        const [a, b, c] = f.pts;
        const u = [b[0] - a[0], b[1] - a[1], b[2] - a[2]], v = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
        const n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]];
        const len = Math.hypot(...n) || 1;
        const shade = 0.6 + 0.4 * Math.abs((n[0] * light[0] + n[1] * light[1] + n[2] * light[2]) / len);
        return { p, z: p.reduce((s2, q) => s2 + q[2], 0) / p.length, colour: f.colour, shade };
      }).sort((a, b) => a.z - b.z);
      for (const f of faces) {
        ctx.beginPath();
        f.p.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
        ctx.closePath();
        ctx.fillStyle = f.colour;
        ctx.globalAlpha = 1;
        ctx.fill();
        ctx.fillStyle = `rgba(0,0,0,${(1 - f.shade).toFixed(2)})`;
        ctx.fill();
        ctx.strokeStyle = "rgba(15,23,42,0.35)";
        ctx.stroke();
      }
      const drawArc = (cx3, cy3, r3, a0, a1, colour, label, flat) => {
        ctx.beginPath();
        const steps = 40;
        const z0 = sc.arcZ ?? 0.3;
        const pt = (a) => flat ? [cx3 + r3 * Math.cos(rad(a)), 0.02, r3 * Math.sin(rad(a))] : [cx3 + r3 * Math.cos(rad(a)), cy3 + r3 * Math.sin(rad(a)), z0];
        const c0 = project(flat ? [cx3, 0.02, 0] : [cx3, cy3, z0], W, H);
        ctx.moveTo(c0[0], c0[1]);
        for (let i = 0; i <= steps; i++) {
          const q = project(pt(a0 + ((a1 - a0) * i) / steps), W, H);
          ctx.lineTo(q[0], q[1]);
        }
        ctx.closePath();
        ctx.fillStyle = colour;
        ctx.globalAlpha = 0.8;
        ctx.fill();
        ctx.globalAlpha = 1;
        const m = project(pt((a0 + a1) / 2).map((v, i) => (i === 0 ? cx3 + (v - cx3) * 1.6 : i === 1 && !flat ? cy3 + (v - cy3) * 1.6 : i === 2 && flat ? v * 1.6 : v)), W, H);
        ctx.font = "700 20px 'Segoe UI', Arial";
        ctx.textAlign = "center";
        ctx.lineWidth = 4;
        ctx.strokeStyle = "#ffffff";
        ctx.strokeText(label, m[0], m[1]);
        ctx.fillStyle = "#111827";
        ctx.fillText(label, m[0], m[1]);
      };
      for (const a of sc.arcs || []) drawArc(...a, false);
      for (const a of sc.floorArcs || []) drawArc(...a, true);
      document.getElementById("steptext").textContent = sc.note;
    }
    let drag = null;
    canvas.addEventListener("pointerdown", (ev) => { drag = { x: ev.clientX, y: ev.clientY, yaw: view.yaw, pitch: view.pitch }; canvas.setPointerCapture(ev.pointerId); });
    canvas.addEventListener("pointermove", (ev) => { if (!drag) return; view.yaw = drag.yaw + (ev.clientX - drag.x) * 0.01; view.pitch = Math.max(-0.2, Math.min(1.3, drag.pitch + (ev.clientY - drag.y) * 0.01)); draw(); });
    canvas.addEventListener("pointerup", () => (drag = null));
    slider.addEventListener("input", draw);
    const presets = s.mode === "complementary" ? [Number(slider.value), 30, 45, 60] : [Number(slider.value), 45, 90, 135];
    const steps = presets.map((p, i) => ({ name: `${s.object} ${i + 1}`, caption: "" }));
    return { steps, show: (k) => { slider.value = presets[k]; draw(); }, after: draw };
  }

  /* ---------- player ---------- */
  function player(scene, start) {
    const svg = document.getElementById("mk");
    const kinds = { factor_tree: factorTree, venn, division, runners, sieve, balance, angle, angle3d, triangle, polygon };
    const view = kinds[scene.type](svg, scene);
    const steps = view.steps;
    let k = Math.min(start || 0, steps.length - 1), playing = false, timer = null;
    const $ = (id) => document.getElementById(id);
    function render() {
      view.show(k);
      const s = steps[k];
      $("stepname").textContent = `Step ${k + 1} of ${steps.length} — ${s.name}: `;
      if (s.caption) $("steptext").textContent = s.caption;
      $("back").disabled = k === 0;
      $("next").disabled = k >= steps.length - 1;
      $("play").textContent = playing ? "⏸ Pause" : "▶ Play";
      window.mk.current = k;
    }
    function go(i) { k = Math.max(0, Math.min(steps.length - 1, i)); render(); }
    function tick() {
      if (!playing) return;
      if (k >= steps.length - 1) { playing = false; render(); return; }
      go(k + 1);
      timer = setTimeout(tick, scene.type === "runners" ? 9500 : 3500);
    }
    $("next").onclick = () => { playing = false; go(k + 1); };
    $("back").onclick = () => { playing = false; go(k - 1); };
    $("restart").onclick = () => { playing = false; go(0); };
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
    window.mk = { steps: steps.length, current: k, go };
    render();
    if (view.after) window.addEventListener("resize", view.after);
  }

  return { treeDepth, runnerAngles, pointerAngle, product, angleAt, player };
})();

if (typeof module !== "undefined") {
  module.exports = MK;
} else if (typeof window !== "undefined" && window.MK_SCENE) {
  try {
    MK.player(window.MK_SCENE, window.MK_START || 0);
  } catch (e) {
    document.body.insertAdjacentHTML("beforeend", "<p style='color:#b91c1c'>Maths view error: " + String(e.message) + "</p>");
    throw e;
  }
}
