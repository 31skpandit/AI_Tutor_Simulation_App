/* AI Teaching Studio — 3D chemistry player (written by hand, not by AI).
 *
 * Plays a scene computed by app/lessons/reactions.py: atoms (nucleus + electron shells), electrons that keep the
 * colour of the atom they came from, bonds, ionic attraction lines and name tags, in a few steps
 * (e.g. atoms → electron transfer → ions → ionic bond). This file only DRAWS and ANIMATES; it never decides
 * chemistry. A small perspective renderer on a 2D canvas: depth-sorted shaded spheres, shells as 3D rings,
 * drag to turn, scroll to zoom. No libraries, no network.
 */
const C3D = (() => {
  "use strict";

  /* ---------- pure maths (unit-tested in Node) ---------- */
  const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
  const lerp = (a, b, t) => a + (b - a) * t;
  const lerp3 = (a, b, t) => [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)];
  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

  function rotate(p, yaw, pitch) {
    const cy = Math.cos(yaw), sy = Math.sin(yaw), cp = Math.cos(pitch), sp = Math.sin(pitch);
    const x = p[0] * cy + p[2] * sy;
    const z1 = -p[0] * sy + p[2] * cy;
    const y = p[1] * cp - z1 * sp;
    const z = p[1] * sp + z1 * cp;
    return [x, y, z];
  }

  /* Screen position and size factor of a world point. cam: {yaw, pitch, scale, dist, cx, cy} */
  function project(p, cam) {
    const r = rotate(p, cam.yaw, cam.pitch);
    const k = cam.dist / Math.max(0.2, cam.dist - r[2]);
    return { x: cam.cx + r[0] * cam.scale * k, y: cam.cy - r[1] * cam.scale * k, z: r[2], k: k };
  }

  const SPIN_DEG_PER_S = 22;

  /* World position of an electron placement: fixed {p} or on shell s of atom a at angle ang (degrees). */
  function placement(pl, atomPos, shellRadius, seconds) {
    if (!pl) return [0, 0, 0];
    if (pl.p) return pl.p;
    const centre = atomPos[pl.a];
    const turn = pl.spin ? seconds * SPIN_DEG_PER_S * (pl.s % 2 ? 1 : -1) : 0;
    const a = ((pl.ang + turn) * Math.PI) / 180;
    const r = shellRadius[pl.s] || 1;
    return [centre[0] + r * Math.cos(a), centre[1] + r * Math.sin(a), centre[2]];
  }

  /* Interpolated picture between two steps at progress u (0 → 1). Pure: used by the renderer and the tests. */
  function frame(scene, from, to, u, seconds) {
    const e = ease(clamp(u, 0, 1));
    const A = scene.steps[from], B = scene.steps[to];
    const atoms = scene.atoms.map((spec, i) => {
      const a = A.atoms[i], b = B.atoms[i];
      return {
        spec: spec,
        p: lerp3(a.p, b.p, e),
        label: e < 0.5 ? a.label : b.label,
        sub: e < 0.5 ? a.sub : b.sub,
        shellsFrom: a.shells || 0,
        shellsTo: b.shells || 0,
        u: e,
      };
    });
    const pos = atoms.map((a) => a.p);
    const electrons = scene.electrons.map((spec, j) => {
      const pa = A.electrons[j], pb = B.electrons[j];
      let p = lerp3(placement(pa, pos, scene.shellRadius, seconds), placement(pb, pos, scene.shellRadius, seconds), e);
      if (pb && pb.jump && pa && pa.a !== pb.a && from < to) {
        const arc = Math.sin(Math.PI * e);
        p = [p[0], p[1] + 0.7 * arc, p[2] + 1.4 * arc];
      }
      const oa = pa && pa.o !== undefined ? pa.o : 1, ob = pb && pb.o !== undefined ? pb.o : 1;
      return { color: spec.color, p: p, alpha: lerp(oa, ob, e) };
    });
    const fade = (listA, listB, keyOf) => {
      const out = new Map();
      for (const x of listA || []) out.set(keyOf(x), { item: x, alpha: 1 - e });
      for (const x of listB || []) {
        const k = keyOf(x);
        if (out.has(k)) out.set(k, { item: e < 0.5 ? out.get(k).item : x, alpha: 1 });
        else out.set(k, { item: x, alpha: e });
      }
      return [...out.values()].filter((v) => v.alpha > 0.01);
    };
    const bondKey = (b) => Math.min(b.a, b.b) + "-" + Math.max(b.a, b.b) + ":" + (b.style || "solid");
    return {
      atoms: atoms,
      electrons: electrons,
      bonds: fade(A.bonds, B.bonds, bondKey),
      links: fade(A.links, B.links, (l) => l.a + "-" + l.b),
      tags: fade(A.tags, B.tags, (t) => t.text + "@" + t.p.join(",")),
    };
  }

  /* ---------- drawing ---------- */

  function shade(hex, f) {
    const n = parseInt(hex.slice(1), 16);
    const ch = (s) => clamp(Math.round(((n >> s) & 255) * f), 0, 255);
    return "rgb(" + ch(16) + "," + ch(8) + "," + ch(0) + ")";
  }

  function light(hex) {
    const n = parseInt(hex.slice(1), 16);
    return 0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255) > 150;
  }

  function sphere(ctx, x, y, r, hex, alpha) {
    const g = ctx.createRadialGradient(x - r * 0.35, y - r * 0.35, r * 0.1, x, y, r);
    g.addColorStop(0, shade(hex, 1.55));
    g.addColorStop(0.55, hex);
    g.addColorStop(1, shade(hex, 0.55));
    ctx.globalAlpha = alpha;
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalAlpha = 1;
  }

  function textBox(ctx, str, x, y, size, color, bg, weight) {
    ctx.font = (weight || "600") + " " + size + "px 'Segoe UI', Arial, sans-serif";
    const w = ctx.measureText(str).width;
    if (bg) {
      ctx.fillStyle = bg;
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(x - w / 2 - 5, y - size * 0.72, w + 10, size * 1.44, 5);
      else ctx.rect(x - w / 2 - 5, y - size * 0.72, w + 10, size * 1.44);
      ctx.fill();
    }
    ctx.fillStyle = color;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(str, x, y);
  }

  function render(ctx, scene, pic, cam, opts) {
    const items = [];
    const R = scene.shellRadius;
    const showShells = opts.shells !== false;
    for (const a of pic.atoms) {
      const most = Math.max(a.shellsFrom, a.shellsTo);
      if (!showShells) continue;
      for (let s = 1; s <= most; s++) {
        const alpha = lerp(s <= a.shellsFrom ? 1 : 0, s <= a.shellsTo ? 1 : 0, a.u);
        if (alpha < 0.02) continue;
        const N = 48;
        for (let k = 0; k < N; k++) {
          const t1 = (k / N) * Math.PI * 2, t2 = ((k + 1) / N) * Math.PI * 2;
          const p1 = project([a.p[0] + R[s] * Math.cos(t1), a.p[1] + R[s] * Math.sin(t1), a.p[2]], cam);
          const p2 = project([a.p[0] + R[s] * Math.cos(t2), a.p[1] + R[s] * Math.sin(t2), a.p[2]], cam);
          items.push({
            z: (p1.z + p2.z) / 2,
            draw: () => {
              ctx.globalAlpha = 0.55 * alpha;
              ctx.strokeStyle = "#64748b";
              ctx.lineWidth = 1.6;
              ctx.beginPath();
              ctx.moveTo(p1.x, p1.y);
              ctx.lineTo(p2.x, p2.y);
              ctx.stroke();
              ctx.globalAlpha = 1;
            },
          });
        }
      }
    }
    const P = pic.atoms.map((a) => project(a.p, cam));
    for (const { item: b, alpha } of pic.bonds) {
      const pa = P[b.a], pb = P[b.b];
      const ca = scene.atoms[b.a].color, cb = scene.atoms[b.b].color;
      items.push({
        z: Math.min(pa.z, pb.z) - 0.01, // behind both atoms, so a bond never covers an atom's name
        draw: () => {
          const style = b.style || "solid";
          ctx.globalAlpha = alpha;
          ctx.lineCap = "round";
          if (style === "ionic" || style === "thin") {
            ctx.setLineDash(style === "ionic" ? [3, 6] : []);
            ctx.strokeStyle = style === "ionic" ? "#7c3aed" : "#475569";
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.moveTo(pa.x, pa.y);
            ctx.lineTo(pb.x, pb.y);
            ctx.stroke();
            ctx.setLineDash([]);
            ctx.globalAlpha = 1;
            return;
          }
          const order = b.order || 1;
          const dx = pb.x - pa.x, dy = pb.y - pa.y, len = Math.hypot(dx, dy) || 1;
          const nx = -dy / len, ny = dx / len;
          const width = Math.max(3, 0.13 * cam.scale * (pa.k + pb.k) / 2);
          const gap = order > 1 ? width * 1.25 : 0;
          if (style === "dashed") ctx.setLineDash([width * 1.2, width * 1.2]);
          for (let k = 0; k < order; k++) {
            const o = (k - (order - 1) / 2) * gap;
            const x1 = pa.x + nx * o, y1 = pa.y + ny * o, x2 = pb.x + nx * o, y2 = pb.y + ny * o;
            const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
            ctx.lineWidth = width + 2;
            ctx.strokeStyle = "rgba(30,41,59,0.55)";
            ctx.beginPath();
            ctx.moveTo(x1, y1);
            ctx.lineTo(x2, y2);
            ctx.stroke();
            ctx.lineWidth = width;
            ctx.strokeStyle = shade(ca, 1.1);
            ctx.beginPath();
            ctx.moveTo(x1, y1);
            ctx.lineTo(mx, my);
            ctx.stroke();
            ctx.strokeStyle = shade(cb, 1.1);
            ctx.beginPath();
            ctx.moveTo(mx, my);
            ctx.lineTo(x2, y2);
            ctx.stroke();
          }
          ctx.setLineDash([]);
          ctx.globalAlpha = 1;
        },
      });
    }
    for (const { item: l, alpha } of pic.links) {
      const pa = P[l.a], pb = P[l.b];
      items.push({
        z: Math.max(pa.z, pb.z) + 0.5,
        draw: () => {
          ctx.globalAlpha = alpha;
          ctx.setLineDash([8, 6]);
          ctx.lineWidth = 3;
          const g = ctx.createLinearGradient(pa.x, pa.y, pb.x, pb.y);
          g.addColorStop(0, "#dc2626");
          g.addColorStop(1, "#2563eb");
          ctx.strokeStyle = g;
          ctx.beginPath();
          ctx.moveTo(pa.x, pa.y);
          ctx.lineTo(pb.x, pb.y);
          ctx.stroke();
          ctx.setLineDash([]);
          textBox(ctx, "attraction", (pa.x + pb.x) / 2, (pa.y + pb.y) / 2 - 14, 13, "#111827", "rgba(255,255,255,0.85)", "600");
          ctx.globalAlpha = 1;
        },
      });
    }
    const subs = [];
    pic.atoms.forEach((a, i) => {
      const p = P[i];
      const r = Math.max(9, a.spec.r * cam.scale * p.k);
      items.push({
        z: p.z,
        draw: () => {
          sphere(ctx, p.x, p.y, r, a.spec.color, 1);
          textBox(ctx, a.label, p.x, p.y, Math.round(clamp(r * 0.85, 12, 26)), light(a.spec.color) ? "#111827" : "#ffffff", null, "700");
        },
      });
      if (a.sub && opts.subs !== false) {
        const ring = showShells ? (scene.shellRadius[Math.max(a.shellsFrom, a.shellsTo)] || 0) * cam.scale * p.k : 0;
        subs.push({ text: a.sub, x: p.x, y: p.y + Math.max(r, ring) + 14 });
      }
    });
    for (const e of pic.electrons) {
      if (e.alpha < 0.02) continue;
      const p = project(e.p, cam);
      const r = Math.max(4.5, 0.11 * cam.scale * p.k);
      items.push({
        z: p.z + 0.02,
        draw: () => {
          sphere(ctx, p.x, p.y, r, e.color, e.alpha);
          ctx.globalAlpha = e.alpha;
          ctx.strokeStyle = "rgba(255,255,255,0.9)";
          ctx.lineWidth = 1.2;
          ctx.beginPath();
          ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
          ctx.stroke();
          ctx.globalAlpha = 1;
        },
      });
    }
    items.sort((a, b) => a.z - b.z);
    for (const it of items) it.draw();
    // Electron-shell labels ("2, 8, 1") on top of everything, moved down when two would overlap.
    ctx.font = "600 13px 'Segoe UI', Arial, sans-serif";
    const placed = [];
    for (const s of subs) {
      const w = ctx.measureText(s.text).width + 10;
      let y = s.y;
      for (let tries = 0; tries < 8; tries++) {
        const hit = placed.some((q) => Math.abs(q.x - s.x) < (q.w + w) / 2 && Math.abs(q.y - y) < 18);
        if (!hit) break;
        y += 18;
      }
      placed.push({ x: s.x, y: y, w: w });
      textBox(ctx, s.text, s.x, y, 13, "#334155", "rgba(255,255,255,0.92)", "600");
    }
    for (const { item: t, alpha } of pic.tags) {
      const p = project(t.p, cam);
      ctx.globalAlpha = alpha;
      textBox(ctx, t.text, p.x, p.y, t.plain ? 28 : 19, "#111827", t.plain ? null : "rgba(255,255,255,0.9)", "700");
      ctx.globalAlpha = 1;
    }
  }

  /* Camera scale that fits every step of the scene into w × h pixels. */
  function fitScale(scene, w, h) {
    let mx = 1, my = 1;
    for (const step of scene.steps) {
      step.atoms.forEach((a) => {
        const ring = scene.shellRadius[a.shells || 0] || 0.6;
        mx = Math.max(mx, Math.abs(a.p[0]) + ring + 0.25);
        my = Math.max(my, Math.abs(a.p[1]) + ring + (a.sub ? 0.45 : 0.25));
      });
      for (const t of step.tags || []) {
        mx = Math.max(mx, Math.abs(t.p[0]) + 1.2);
        my = Math.max(my, Math.abs(t.p[1]) + 0.6);
      }
      for (const e of step.electrons || []) {
        if (e.p) {
          mx = Math.max(mx, Math.abs(e.p[0]) + 0.4);
          my = Math.max(my, Math.abs(e.p[1]) + 0.4);
        }
      }
    }
    return Math.min(w / (2 * mx), h / (2 * my)) * 0.94;
  }

  /* ---------- the player (browser only) ---------- */

  function player(scene, opts) {
    const canvas = document.getElementById("c3d");
    const ctx = canvas.getContext("2d");
    const el = (id) => document.getElementById(id);
    const flat = scene.kind !== "reaction";
    const view = { yaw: flat ? 0.22 : 0.35, pitch: flat ? 0.16 : 0.28, zoom: 1, turning: false };
    const state = { from: 0, to: 0, u: 1, start: 0, playing: false, holdUntil: 0, speed: 1 };
    const t0 = performance.now();
    let width = 0, height = 0, base = 1;

    function resize() {
      const ratio = window.devicePixelRatio || 1;
      width = canvas.clientWidth;
      height = canvas.clientHeight;
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      base = fitScale(scene, width, height);
    }

    function duration(to) {
      const jumps = scene.steps[to].electrons.some((p) => p && p.jump);
      return (jumps ? 3200 : 2200) / state.speed;
    }

    function goTo(index, instant) {
      index = clamp(index, 0, scene.steps.length - 1);
      const now = performance.now();
      state.from = instant ? index : state.to; // a running transition is cut short and continues from its target
      state.to = index;
      state.u = instant || state.from === index ? 1 : 0;
      state.start = now;
      state.holdUntil = 0;
      showCaption();
      draw();
    }

    function showCaption() {
      const step = scene.steps[state.to];
      el("stepname").textContent = "Step " + (state.to + 1) + " of " + scene.steps.length + " — " + step.name + ": ";
      el("steptext").textContent = step.caption;
      el("play").textContent = state.playing ? "⏸ Pause" : "▶ Play";
      el("back").disabled = state.to === 0;
      el("next").disabled = state.to === scene.steps.length - 1;
      [...el("dots").children].forEach((d, i) => d.classList.toggle("on", i === state.to));
    }

    function draw() {
      const now = performance.now();
      if (state.u < 1) state.u = clamp((now - state.start) / duration(state.to), 0, 1);
      if (view.turning) view.yaw += 0.004;
      ctx.clearRect(0, 0, width, height);
      const cam = { yaw: view.yaw, pitch: view.pitch, scale: base * view.zoom, dist: 14, cx: width / 2, cy: height / 2 };
      const pic = frame(scene, state.from, state.to, state.u, (now - t0) / 1000);
      render(ctx, scene, pic, cam, { shells: el("shells") ? el("shells").checked : true });
      window.chem3d.frames++;
    }

    function tick() {
      const now = performance.now();
      if (state.playing && state.u >= 1) {
        if (!state.holdUntil) {
          const words = scene.steps[state.to].caption.length;
          state.holdUntil = now + Math.max(2600, words * 38) / state.speed;
        } else if (now >= state.holdUntil) {
          if (state.to < scene.steps.length - 1) goTo(state.to + 1);
          else {
            state.playing = false;
            showCaption();
          }
        }
      }
      draw();
      requestAnimationFrame(tick);
    }

    // controls
    el("play").onclick = () => {
      if (!state.playing && state.to === scene.steps.length - 1) goTo(0, true);
      state.playing = !state.playing;
      state.holdUntil = 0;
      showCaption();
    };
    el("next").onclick = () => {
      state.playing = false;
      goTo(state.to + 1);
    };
    el("back").onclick = () => {
      state.playing = false;
      goTo(state.to - 1);
    };
    el("restart").onclick = () => {
      state.playing = false;
      goTo(0, true);
    };
    el("speed").onchange = (ev) => (state.speed = Number(ev.target.value) || 1);
    el("turn").onchange = (ev) => (view.turning = ev.target.checked);
    el("reset").onclick = () => {
      view.yaw = flat ? 0.22 : 0.35;
      view.pitch = flat ? 0.16 : 0.28;
      view.zoom = 1;
    };
    if (el("shells")) el("shells").onchange = () => draw();
    scene.steps.forEach((s, i) => {
      const d = document.createElement("button");
      d.className = "dot";
      d.title = s.name;
      d.textContent = String(i + 1);
      d.onclick = () => {
        state.playing = false;
        goTo(i);
      };
      el("dots").appendChild(d);
    });
    let drag = null;
    canvas.addEventListener("pointerdown", (ev) => {
      drag = { x: ev.clientX, y: ev.clientY, yaw: view.yaw, pitch: view.pitch };
      canvas.setPointerCapture(ev.pointerId);
    });
    canvas.addEventListener("pointermove", (ev) => {
      if (!drag) return;
      view.yaw = drag.yaw + (ev.clientX - drag.x) * 0.01;
      view.pitch = clamp(drag.pitch + (ev.clientY - drag.y) * 0.01, -1.4, 1.4);
    });
    canvas.addEventListener("pointerup", () => (drag = null));
    canvas.addEventListener(
      "wheel",
      (ev) => {
        ev.preventDefault();
        view.zoom = clamp(view.zoom * (ev.deltaY < 0 ? 1.1 : 0.9), 0.4, 4);
      },
      { passive: false }
    );
    document.addEventListener("keydown", (ev) => {
      if (ev.key === "ArrowRight") el("next").click();
      if (ev.key === "ArrowLeft") el("back").click();
      if (ev.key === " ") {
        ev.preventDefault();
        el("play").click();
      }
    });
    window.addEventListener("resize", () => {
      resize();
      draw();
    });

    el("title").textContent = scene.title;
    el("legend").innerHTML = "";
    for (const item of scene.legend || []) {
      const span = document.createElement("span");
      const dot = document.createElement("i");
      dot.style.background = item.color;
      if (item.ball) dot.className = "ball";
      span.appendChild(dot);
      span.appendChild(document.createTextNode(item.text));
      el("legend").appendChild(span);
    }
    window.chem3d = { frames: 0, goTo: goTo, steps: scene.steps.length, current: () => state.to };
    resize();
    goTo(clamp(opts.start || 0, 0, scene.steps.length - 1), true);
    requestAnimationFrame(tick);
  }

  return { ease, lerp, lerp3, rotate, project, placement, frame, fitScale, player };
})();

if (typeof module !== "undefined") {
  module.exports = C3D;
} else if (typeof window !== "undefined" && window.CHEM3D_SCENE) {
  try {
    C3D.player(window.CHEM3D_SCENE, { start: window.CHEM3D_START || 0 });
  } catch (e) {
    document.body.insertAdjacentHTML("beforeend", "<p style='color:#b91c1c'>3D view error: " + String(e.message) + "</p>");
    throw e;
  }
}
