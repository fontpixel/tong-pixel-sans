// "One text, four forms": the same text set in the four regional faces from the real bitmaps,
// pixels that differ in colour, plus an overprint row with one corner of each pixel per region.

import { REGIONS, LANG, preload, glyphsSync, cellSet, sameSet, palette, fitCanvas } from "./glyphs.js";
import { t, fmt, lang } from "./i18n.js";
import { relation, stateLine, diffCount } from "./plates.js";

const hex = cp => cp.toString(16).toUpperCase().padStart(4, "0");

export function initDiff() {
  const ta = document.getElementById("diff-text");
  const view = document.getElementById("diff-view");
  const canvas = document.getElementById("diff-canvas");
  const sum = document.getElementById("diff-sum");
  const seg = document.getElementById("diff-scale");
  const body = document.getElementById("insp-body");
  let s = 2, items = [], layout = [], sel = -1, timer = 0, seq = 0, curW = 1;

  async function update() {
    const my = ++seq;
    const text = ta.value;
    await preload(text);
    if (my !== seq) return;
    items = [];
    for (const ch of text) {
      if (ch === "\n") { items.push({ br: true }); continue; }
      const cp = ch.codePointAt(0);
      const gs = glyphsSync(cp);
      if (!gs) { items.push({ ch, cp, gs: null, w: 14, n: 0 }); continue; }
      const sets = gs.map(cellSet);
      const w = Math.max(...gs.map(g => g.adv));
      items.push({ ch, cp, gs, sets, w, n: diffCount(sets) });
    }
    const chars = items.filter(i => !i.br && !/\s/.test(i.ch));
    const differ = chars.filter(i => i.n > 0);
    sum.textContent = chars.length
      ? t("diffSum", { n: fmt(chars.length), m: fmt(differ.length), p: fmt(differ.reduce((a, i) => a + i.n, 0)) })
      : t("diffNone");
    if (sel >= items.length || sel < 0 || items[sel].br) sel = items.findIndex(i => i.n > 0);
    render();
    inspect();
  }

  function render() {
    const pal = palette();
    const W = Math.max(200, view.clientWidth - 30);
    curW = W;
    const L = 28;                        // label column
    const rh = 14 * s + s;               // row pitch
    const gh = 5 * rh + 14;              // one line of text: four regions and the overprint row
    layout = [];
    let x = L, line = 0;
    items.forEach((it, i) => {
      if (it.br) { x = L; line++; return; }
      if (x + it.w * s > W && x > L) { x = L; line++; }
      layout.push({ i, x, line, w: it.w * s });
      x += it.w * s;
    });
    const lines = Math.max(1, line + 1);
    const H = lines * gh - 14;
    const ctx = fitCanvas(canvas, W, H);
    canvas.style.width = "100%";
    canvas.style.height = "auto";
    canvas.style.aspectRatio = `${W} / ${H}`;
    ctx.clearRect(0, 0, W, H);
    ctx.textBaseline = "alphabetic";
    ctx.font = '14px "TPS Square", sans-serif';
    for (let l = 0; l < lines; l++) {
      const y0 = l * gh;
      REGIONS.forEach((r, k) => {
        ctx.fillStyle = pal[r];
        const lab = lang() === "en" ? r : t("region." + r)[0];
        ctx.fillText(lab, 0, y0 + k * rh + Math.round((rh - 14) / 2) + 11);
      });
      // key for the overprint row
      const ky = y0 + 4 * rh + Math.round((rh - 14) / 2);
      REGIONS.forEach((r, k) => { ctx.fillStyle = pal[r]; ctx.fillRect(1 + (k % 2) * 6, ky + 1 + (k >> 1) * 6, 6, 6); });
      if (l < lines - 1) { ctx.fillStyle = pal.rule; ctx.fillRect(L, y0 + gh - 8, W - L, 1); }
    }
    for (const p of layout) {
      const it = items[p.i], y0 = p.line * gh;
      if (p.i === sel) {
        ctx.fillStyle = pal.faint;
        ctx.fillRect(p.x, y0 - 2, p.w, 5 * rh + 2);
      }
      if (!it.gs) {
        ctx.strokeStyle = pal.muted;
        ctx.lineWidth = 1;
        for (let k = 0; k < 5; k++) ctx.strokeRect(p.x + 1.5 * s + .5, y0 + k * rh + 1.5 * s + .5, 11 * s - 1, 11 * s - 1);
        continue;
      }
      const shared = new Set([...it.sets[0]].filter(v => it.sets.every(st => st.has(v))));
      it.sets.forEach((set, k) => {
        const yy = y0 + k * rh;
        for (const v of set) {
          ctx.fillStyle = shared.has(v) ? pal.ink : pal[REGIONS[k]];
          ctx.fillRect(p.x + (v % 64) * s, yy + Math.floor(v / 64) * s, s, s);
        }
      });
      const yq = y0 + 4 * rh, h = s / 2;
      const union = new Set();
      it.sets.forEach(st => st.forEach(v => union.add(v)));
      for (const v of union) {
        const X = p.x + (v % 64) * s, Y = yq + Math.floor(v / 64) * s;
        if (shared.has(v)) { ctx.fillStyle = pal.ink; ctx.fillRect(X, Y, s, s); continue; }
        it.sets.forEach((st, k) => {
          if (!st.has(v)) return;
          ctx.fillStyle = pal[REGIONS[k]];
          ctx.fillRect(X + (k % 2) * h, Y + (k >> 1) * h, h, h);
        });
      }
    }
  }

  function card(label, color, set, sets, k, note) {
    const fig = document.createElement("figure");
    fig.className = "insp-card";
    const c = document.createElement("canvas");
    const S = 7, N = 14;
    const ctx = fitCanvas(c, N * S + 2, N * S + 2);
    const pal = palette();
    ctx.fillStyle = pal.panel; ctx.fillRect(0, 0, N * S + 2, N * S + 2);
    ctx.fillStyle = pal.faint;
    for (let i = 0; i <= N; i++) { ctx.fillRect(1 + i * S, 1, 1, N * S); ctx.fillRect(1, 1 + i * S, N * S, 1); }
    const shared = new Set([...sets[0]].filter(v => sets.every(st => st.has(v))));
    const union = new Set(); sets.forEach(st => st.forEach(v => union.add(v)));
    const draw = (v, col, x = 0, y = 0, w = S - 1) => { ctx.fillStyle = col; ctx.fillRect(2 + (v % 64) * S + x, 2 + Math.floor(v / 64) * S + y, w, w); };
    if (k >= 0) {
      for (const v of set) draw(v, shared.has(v) ? pal.ink : pal[REGIONS[k]]);
    } else {
      for (const v of union) {
        if (shared.has(v)) { draw(v, pal.ink); continue; }
        sets.forEach((st, j) => { if (st.has(v)) draw(v, pal[REGIONS[j]], (j % 2) * 3, (j >> 1) * 3, 3); });
      }
    }
    const cap = document.createElement("figcaption");
    const lab = document.createElement("span");
    lab.className = "lab";
    lab.style.setProperty("--c", color);
    lab.textContent = label;
    cap.append(lab);
    if (note) {
      const st = document.createElement("span");
      st.className = "st";
      st.textContent = note;
      cap.append(st);
    }
    fig.append(c, cap);
    return fig;
  }

  function inspect() {
    body.innerHTML = "";
    const it = items[sel];
    if (!it || it.br || !it.gs) return;
    const head = document.createElement("p");
    head.className = "insp-head";
    const big = document.createElement("span");
    big.className = "big";
    big.textContent = it.ch;
    head.append(big, `U+${hex(it.cp)}　${relation(it.sets)} ${t("pixelsDiffer", { n: fmt(it.n) })}`);
    body.append(head);
    REGIONS.forEach((r, k) => {
      const prev = REGIONS.findIndex((_, j) => j < k && sameSet(it.sets[j], it.sets[k]));
      const note = (prev >= 0 ? t("same", { r: t("region." + REGIONS[prev]) }) + (lang() === "en" ? ", " : "，") : "") + t("state." + it.gs[k].state);
      body.append(card(t("region." + r) + (lang() === "en" ? "" : " " + r), `var(--${r.toLowerCase()})`, it.sets[k], it.sets, k, note));
    });
    body.append(card(lang() === "en" ? "Overprint" : "叠印", "var(--ink)", null, it.sets, -1, ""));
    const p = document.createElement("p");
    p.className = "muted insp-head";
    p.textContent = stateLine(it.gs);
    body.append(p);
  }

  function step(dir) {
    if (!items.length) return;
    let i = sel;
    for (let n = 0; n < items.length; n++) {
      i = (i + dir + items.length) % items.length;
      if (items[i].n > 0) { sel = i; break; }
    }
    render();
    inspect();
  }

  canvas.addEventListener("click", e => {
    const r = canvas.getBoundingClientRect();
    const k = curW / r.width;
    const x = (e.clientX - r.left) * k, y = (e.clientY - r.top) * k;
    const gh = 5 * (14 * s + s) + 14;
    const hit = layout.find(p => x >= p.x && x < p.x + p.w && Math.floor(y / gh) === p.line);
    if (hit) { sel = hit.i; render(); inspect(); }
  });
  document.getElementById("insp-prev").addEventListener("click", () => step(-1));
  document.getElementById("insp-next").addEventListener("click", () => step(1));
  ta.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(update, 150); });
  seg.addEventListener("click", e => {
    const b = e.target.closest("button");
    if (!b) return;
    s = +b.dataset.v;
    seg.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", String(x === b)));
    render();
  });
  let lastW = 0;
  new ResizeObserver(() => { if (view.clientWidth !== lastW) { lastW = view.clientWidth; if (items.length) render(); } }).observe(view);
  document.addEventListener("tps-theme", () => { render(); inspect(); });
  document.addEventListener("tps-lang", () => { update(); });
  document.fonts.ready.then(() => { if (items.length) render(); });
  update();
}
