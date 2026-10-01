// How it is made: shared component forms, before/after review, and the review progress field.

import { palette, fitCanvas, bitString } from "./glyphs.js";
import { t, fmt, lang } from "./i18n.js";

function glyphCanvas(set, color, S = 6, extra) {
  const c = document.createElement("canvas");
  const N = 14, size = N * S + 1;
  const ctx = fitCanvas(c, size, size);
  const pal = palette();
  ctx.fillStyle = pal.faint;
  for (let i = 0; i <= N; i++) { ctx.fillRect(i * S, 0, 1, size); ctx.fillRect(0, i * S, size, 1); }
  for (const v of set) {
    ctx.fillStyle = color(v, pal);
    ctx.fillRect((v % 64) * S + 1, Math.floor(v / 64) * S + 1, S - 1, S - 1);
  }
  if (extra) extra(ctx, pal, S);
  return c;
}

export function initMaking(site) {
  // --- components
  const tabs = document.getElementById("rad-tabs");
  const grid = document.getElementById("rad-grid");
  const info = document.getElementById("rad-info");
  let cur = 0;
  function showRad() {
    const r = site.radicals[cur];
    if (!r) return;
    const form = new Set();
    r.form.forEach((row, y) => [...row].forEach((c, x) => { if (c === "#") form.add(y * 64 + x + 1); }));
    info.textContent = t("js.radInfo", { n: fmt(r.count), comp: r.comp, k: r.chars.length });
    grid.innerHTML = "";
    [...r.chars].forEach((ch, i) => {
      const fig = document.createElement("figure");
      const set = bitString(r.glyphs[i]);
      fig.append(glyphCanvas(set, (v, pal) => (form.has(v) ? pal.SC : pal.ink)));
      const cap = document.createElement("figcaption");
      cap.lang = "zh-Hans";
      cap.textContent = ch;
      fig.append(cap);
      grid.append(fig);
    });
    tabs.querySelectorAll("button").forEach((b, i) => b.setAttribute("aria-pressed", String(i === cur)));
  }
  site.radicals.forEach((r, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.lang = "zh-Hans";
    b.textContent = r.comp;
    b.addEventListener("click", () => { cur = i; showRad(); });
    tabs.append(b);
  });

  // --- review before / after
  const rg = document.getElementById("review-grid");
  function showReview() {
    rg.innerHTML = "";
    site.review.forEach(r => {
      const a = bitString(r.before), b = bitString(r.after);
      const fig = document.createElement("figure");
      const pair = document.createElement("div");
      pair.className = "review-pair";
      pair.append(glyphCanvas(a, (v, pal) => pal.ink, 5));
      const arrow = document.createElement("span");
      arrow.setAttribute("aria-hidden", "true");
      arrow.textContent = "→";
      pair.append(arrow);
      pair.append(glyphCanvas(b, (v, pal) => (a.has(v) ? pal.ink : pal.TC), 5, (ctx, pal, S) => {
        ctx.strokeStyle = pal.TC;
        ctx.lineWidth = 1;
        for (const v of a) if (!b.has(v)) ctx.strokeRect((v % 64) * S + 1.5, Math.floor(v / 64) * S + 1.5, S - 2, S - 2);
      }));
      const cap = document.createElement("figcaption");
      cap.textContent = t("js.reviewCap", { ch: r.ch, r: t("region." + r.region), d: r.diff });
      fig.setAttribute("aria-label", `${t("js.before")} / ${t("js.after")}: ${cap.textContent}`);
      fig.append(pair, cap);
      rg.append(fig);
    });
  }

  // --- progress field
  const sc = document.getElementById("status-canvas");
  const bands = document.getElementById("status-bands");
  const legend = document.getElementById("status-legend");
  const S = site.status;
  const colorOf = (st, pal) => ({ approved: pal.SC, edited: pal.TC, derived: pal.JP, ai: pal.rule, "hangul-ai": pal.rule,
    "hangul-composed": pal.faint, generated: pal.faint, draft: pal.TC }[st] || pal.rule);
  let codes = null;
  const img = new Image();
  img.onload = () => {
    const c = document.createElement("canvas");
    c.width = img.width; c.height = img.height;
    const x = c.getContext("2d", { willReadFrequently: true });
    x.drawImage(img, 0, 0);
    const d = x.getImageData(0, 0, img.width, img.height).data;
    codes = new Uint8Array(img.width * img.height);
    for (let i = 0; i < codes.length; i++) codes[i] = d[i * 4];
    drawStatus();
  };
  img.src = "gen/status.png";

  function drawStatus() {
    const w = S.width, h = Math.ceil(S.total / w);
    const pal = palette();
    sc.width = w; sc.height = h;
    sc.style.width = w * 2 + 2 + "px";
    const ctx = sc.getContext("2d");
    ctx.fillStyle = pal.panel;
    ctx.fillRect(0, 0, w, h);
    if (codes) {
      const id = ctx.createImageData(w, h);
      const cache = {};
      for (let i = 0; i < S.total; i++) {
        const st = S.order[codes[i] - 1];
        const col = cache[st] || (cache[st] = parse(colorOf(st, pal)));
        id.data.set([col[0], col[1], col[2], 255], i * 4);
      }
      ctx.putImageData(id, 0, 0);
    }
    bands.innerHTML = "";
    bands.style.height = h * 2 + "px";
    S.bands.forEach(b => {
      const li = document.createElement("li");
      li.style.top = Math.floor(b.start / w) * 2 + "px";
      li.style.height = Math.max(14, Math.ceil(b.count / w) * 2) + "px";
      li.textContent = `${t("group." + b.group)}${t("js.gap")}${fmt(b.count)}`;
      if (b.count / w * 2 < 14 && !["GEOMETRIC-FULL", "GEOMETRIC-HALF"].includes(b.group)) li.style.height = "14px";
      bands.append(li);
    });
    // the small western and geometric bands share labels
    const lis = bands.querySelectorAll("li");
    if (lis.length === 8) {
      lis[7].remove();
      lis[5].remove();
      lis[4].textContent = `${t("group.latin")}${t("js.gap")}${fmt(S.bands[4].count + S.bands[5].count)}`;
      lis[6].textContent = `${t("group.geometric")}${t("js.gap")}${fmt(S.bands[6].count + S.bands[7].count)}`;
    }
    legend.innerHTML = "";
    Object.entries(S.counts).forEach(([st, n]) => {
      const li = document.createElement("li");
      const i = document.createElement("i");
      i.style.background = colorOf(st, pal);
      const name = document.createElement("span");
      name.textContent = t("stateShort." + st);
      const num = document.createElement("span");
      num.className = "n";
      num.textContent = fmt(n);
      li.append(i, name, num);
      legend.append(li);
    });
    const tot = document.createElement("li");
    tot.className = "muted";
    tot.textContent = t("js.legendTotal", { n: fmt(S.total) });
    legend.append(tot);
  }

  function parse(color) {
    const c = document.createElement("canvas").getContext("2d");
    c.fillStyle = color;
    const v = c.fillStyle;
    if (v.startsWith("#")) return [1, 3, 5].map(i => parseInt(v.slice(i, i + 2), 16));
    return (v.match(/[\d.]+/g) || [0, 0, 0]).slice(0, 3).map(Number);
  }

  showRad();
  showReview();
  drawStatus();
  document.addEventListener("tps-theme", () => { showRad(); showReview(); drawStatus(); });
  document.addEventListener("tps-lang", () => { showRad(); showReview(); drawStatus(); });
}
