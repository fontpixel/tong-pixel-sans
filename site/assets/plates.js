// The four plates: one character, one transparent sheet per region, stacked in 3D.
// Apart (t = 1) each sheet shows its region's glyph; together (t = 0) the sheets overprint and each
// differing pixel shrinks to its region's corner, so the flat view reads like a four-colour print.

import { REGIONS, LANG, glyphs, cellSet, sameSet, palette, reduceMotion } from "./glyphs.js";
import { t, fmt } from "./i18n.js";

const hex = cp => cp.toString(16).toUpperCase().padStart(4, "0");

/** Which regions share a form: "简体与日文相同；繁体与韩文相同。" */
export function relation(sets) {
  const groups = [];
  REGIONS.forEach((r, i) => {
    const g = groups.find(g => sameSet(sets[g[0]], sets[i]));
    if (g) g.push(i); else groups.push([i]);
  });
  if (groups.length === 1) return t("allSame");
  if (groups.length === 4) return t("allDiffer");
  const names = g => {
    const n = g.map(i => t("region." + REGIONS[i]));
    return n.length > 2 ? n.slice(0, -1).join(t("sep") === "；" ? "、" : ", ") + t("joinAnd") + n[n.length - 1] : n.join(t("joinAnd"));
  };
  const parts = groups.filter(g => g.length > 1).map(g => t("equal", { list: names(g) }));
  return parts.join(t("sep")) + (t("sep") === "；" ? "。" : ".");
}

/** "审核：简体、日文 已审核；繁体、韩文 AI 修整，待审" */
export function stateLine(gs) {
  const by = new Map();
  gs.forEach((g, i) => { if (g) { const k = g.state; by.set(k, [...(by.get(k) || []), t("region." + REGIONS[i])]); } });
  const sepList = t("sep") === "；" ? "、" : ", ";
  return t("review") + [...by].map(([st, rs]) => rs.join(sepList) + " " + t("state." + st)).join(t("sep"));
}

export function diffCount(sets) {
  const union = new Set(), inter = new Set(sets[0]);
  sets.forEach(s => { s.forEach(v => union.add(v)); });
  sets.slice(1).forEach(s => { for (const v of [...inter]) if (!s.has(v)) inter.delete(v); });
  return union.size - inter.size;
}

export function initPlates(site) {
  const stage = document.getElementById("plates-stage");
  const stack = document.getElementById("stack");
  const info = document.getElementById("plates-info");
  const picker = document.getElementById("picker");
  const input = document.getElementById("pick-input");
  const btn = document.getElementById("explode-btn");
  const range = document.getElementById("explode-range");
  const toggles = document.getElementById("plate-toggles");
  btn.removeAttribute("aria-pressed");

  const visible = [true, true, true, true];
  let cur = null;           // {ch, cp, gs, sets}
  let tval = reduceMotion() ? 1 : 0;
  let anim = null;

  const plates = REGIONS.map((r, k) => {
    const el = document.createElement("div");
    el.className = "plate";
    el.style.setProperty("--c", `var(--${r.toLowerCase()})`);
    el.style.setProperty("--lift", String(3 - k));
    el.style.setProperty("--k", String(k));
    const cv = document.createElement("canvas");
    const tab = document.createElement("span");
    tab.className = "plate-tab";
    tab.setAttribute("aria-hidden", "true");
    el.append(cv, tab);
    stack.append(el);
    const tb = document.createElement("button");
    tb.type = "button";
    tb.style.setProperty("--c", `var(--${r.toLowerCase()})`);
    tb.setAttribute("aria-pressed", "true");
    tb.addEventListener("click", () => {
      visible[k] = !visible[k];
      if (!visible.some(Boolean)) visible[k] = true;
      tb.setAttribute("aria-pressed", String(visible[k]));
      el.classList.toggle("off", !visible[k]);
      draw();
      describe();
    });
    toggles.append(tb);
    return { r, k, el, cv, tab, tb };
  });

  function labels() {
    plates.forEach(p => {
      p.tab.textContent = t("region." + p.r) + (t("region." + p.r) === p.r ? "" : " " + p.r);
      p.tb.textContent = t("region." + p.r);
    });
    btn.querySelector(".zh").textContent = tval > .5 ? "合拢" : "拆开";
    btn.querySelector(".en").textContent = tval > .5 ? "Stack" : "Separate";
  }

  function sizeCanvases() {
    const sheet = stack.getBoundingClientRect().width / (tval > 0 ? 1 : 1);
    const css = stack.offsetWidth || sheet;
    const dpr = Math.min(3, Math.max(2, Math.round(window.devicePixelRatio || 1) * 1.5));
    plates.forEach(p => {
      p.cv.width = Math.round(css * dpr);
      p.cv.height = Math.round(css * dpr);
    });
  }

  function draw() {
    if (!plates[0].cv.width) sizeCanvases();
    const pal = palette();
    const W = plates[0].cv.width, c = W / 15, off = c / 2;      // 15 cells: the 14×14 cell with half a cell margin
    const ease = x => x * x * (3 - 2 * x);
    const q = ease(Math.min(1, Math.max(0, tval / .45)));
    const shared = new Set();
    if (cur) {
      const vis = cur.sets.filter((_, i) => visible[i]);
      vis[0].forEach(v => { if (vis.every(s => s.has(v))) shared.add(v); });
    }
    plates.forEach(p => {
      const ctx = p.cv.getContext("2d");
      ctx.clearRect(0, 0, W, W);
      // film grid
      ctx.fillStyle = pal[p.r];
      ctx.globalAlpha = .16;
      for (let i = 0; i <= 14; i++) {
        ctx.fillRect(Math.round(off + i * c), Math.round(off), 1, Math.round(14 * c));
        ctx.fillRect(Math.round(off), Math.round(off + i * c), Math.round(14 * c), 1);
      }
      ctx.globalAlpha = .55;       // baseline ticks in the margin
      ctx.fillRect(0, Math.round(off + 11 * c), Math.round(off * .8), Math.max(1, Math.round(c / 10)));
      ctx.fillRect(Math.round(W - off * .8), Math.round(off + 11 * c), Math.round(off * .8), Math.max(1, Math.round(c / 10)));
      ctx.globalAlpha = 1;
      if (!cur) return;
      const qx = p.k % 2, qy = p.k >> 1;
      for (const v of cur.sets[p.k]) {
        const x = v % 64, y = Math.floor(v / 64);
        const X = off + x * c, Y = off + y * c;
        if (shared.has(v)) {
          ctx.fillStyle = pal.ink;
          ctx.fillRect(Math.round(X), Math.round(Y), Math.round(X + c) - Math.round(X), Math.round(Y + c) - Math.round(Y));
        } else {
          ctx.fillStyle = pal[p.r];
          const x0 = X + (1 - q) * qx * c / 2, y0 = Y + (1 - q) * qy * c / 2;
          const s = c / 2 + q * c / 2;
          ctx.fillRect(Math.round(x0), Math.round(y0), Math.round(x0 + s) - Math.round(x0), Math.round(y0 + s) - Math.round(y0));
        }
      }
    });
  }

  function setT(v) {
    tval = v;
    stage.style.setProperty("--t", v.toFixed(4));
    range.value = String(Math.round(v * 100));
    draw();
    labels();
  }

  function animateTo(target, ms = 900) {
    if (anim) cancelAnimationFrame(anim);
    if (reduceMotion()) { setT(target); return; }
    const from = tval, t0 = performance.now();
    const step = now => {
      const k = Math.min(1, (now - t0) / ms);
      const e = k < .5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
      setT(from + (target - from) * e);
      if (k < 1) anim = requestAnimationFrame(step); else anim = null;
    };
    anim = requestAnimationFrame(step);
  }

  function describe() {
    if (!cur) return;
    const { ch, cp, gs, sets } = cur;
    const nVis = visible.filter(Boolean).length;
    const n = nVis === 4 ? diffCount(sets) : diffCount(sets.filter((_, i) => visible[i]));
    info.innerHTML = "";
    const big = document.createElement("span");
    big.className = "big";
    big.lang = "zh-Hans";
    big.textContent = ch;
    const p1 = document.createElement("span");
    p1.textContent = `U+${hex(cp)}　${relation(sets)} ${nVis === 4 ? t("pixelsDiffer", { n: fmt(n) }) : t("pixelsDifferVisible", { n: fmt(n) })}`;
    const br = document.createElement("br");
    const p2 = document.createElement("span");
    p2.className = "muted";
    p2.textContent = stateLine(gs);
    info.append(big, p1, br, p2);
  }

  async function show(ch) {
    const cp = ch.codePointAt(0);
    const gs = await glyphs(cp);
    if (!gs) {
      info.textContent = t("notInFont", { ch });
      return false;
    }
    cur = { ch, cp, gs, sets: gs.map(cellSet) };
    picker.querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.ch === ch)));
    draw();
    describe();
    return true;
  }

  // picker
  site.featured.forEach(f => {
    const b = document.createElement("button");
    b.type = "button";
    b.dataset.ch = f.ch;
    b.lang = "zh-Hans";
    b.textContent = f.ch;
    b.setAttribute("aria-pressed", "false");
    b.addEventListener("click", () => { input.value = ""; show(f.ch); });
    picker.append(b);
  });
  input.addEventListener("input", () => {
    const ch = [...input.value.trim()][0];
    if (ch) show(ch);
  });

  btn.addEventListener("click", () => animateTo(tval > .5 ? 0 : 1));
  range.addEventListener("input", () => { if (anim) cancelAnimationFrame(anim); anim = null; setT(range.value / 100); });

  // drag to turn the stack
  let drag = null, yaw = 0;
  stage.addEventListener("pointerdown", e => {
    if (e.pointerType === "touch") return;          // keep vertical page scrolling on touch
    drag = { x: e.clientX, yaw };
    stage.setPointerCapture(e.pointerId);
    stage.classList.add("dragging");
  });
  stage.addEventListener("pointermove", e => {
    if (!drag) return;
    yaw = Math.max(-70, Math.min(70, drag.yaw + (e.clientX - drag.x) * .35));
    stage.style.setProperty("--yaw", yaw.toFixed(1) + "deg");
  });
  const end = () => { drag = null; stage.classList.remove("dragging"); };
  stage.addEventListener("pointerup", end);
  stage.addEventListener("pointercancel", end);

  new ResizeObserver(() => { sizeCanvases(); draw(); }).observe(stack);
  document.addEventListener("tps-theme", draw);
  document.addEventListener("tps-lang", () => { labels(); describe(); });

  labels();
  setT(tval);
  const first = site.featured[0].ch;
  show(first).then(() => {
    if (!reduceMotion()) setTimeout(() => animateTo(1, 1500), 350);
  });
}
