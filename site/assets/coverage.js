// Coverage: the BMP as a 256×256 map, one pixel per code point; the required tables as overlays;
// a page view (256 code points) drawn from the real bitmaps.

import { REGIONS, LANG, preload, glyphsSync, palette, fitCanvas } from "./glyphs.js";
import { t, fmt, lang } from "./i18n.js";
import { stateLine } from "./plates.js";

const hex = (n, w = 4) => n.toString(16).toUpperCase().padStart(w, "0");

function loadMask(src) {
  return new Promise((ok, bad) => {
    const img = new Image();
    img.onload = () => {
      const c = document.createElement("canvas");
      c.width = img.width; c.height = img.height;
      const ctx = c.getContext("2d", { willReadFrequently: true });
      ctx.drawImage(img, 0, 0);
      const d = ctx.getImageData(0, 0, img.width, img.height).data;
      const out = new Uint8Array(img.width * img.height);
      for (let i = 0; i < out.length; i++) out[i] = d[i * 4] > 127 ? 1 : 0;
      ok({ w: img.width, h: img.height, bits: out });
    };
    img.onerror = bad;
    img.src = src;
  });
}

function rgb(color) {
  const c = document.createElement("canvas").getContext("2d");
  c.fillStyle = color;
  const v = c.fillStyle;
  if (v.startsWith("#")) return [1, 3, 5].map(i => parseInt(v.slice(i, i + 2), 16));
  const m = v.match(/[\d.]+/g) || [0, 0, 0];
  return m.slice(0, 3).map(Number);
}

export function initCoverage(site) {
  const map = document.getElementById("cov-map");
  const read = document.getElementById("cov-read");
  const tablesEl = document.getElementById("cov-tables");
  const pageBox = document.getElementById("cov-page");
  const pageH = document.getElementById("cov-page-h");
  const pageCanvas = document.getElementById("cov-page-canvas");
  const pageRegion = document.getElementById("cov-page-region");
  let cov = null, tables = null, pinned = -1, preview = -1, cursor = 0x4E, page = -1, region = 0, pageSel = -1;

  const ctx = map.getContext("2d");
  const img = ctx.createImageData(256, 256);

  function drawMap() {
    if (!cov) return;
    const pal = palette();
    const ink = rgb(pal.ink), faint = rgb(pal.faint), hi = rgb(pal.SC), miss = rgb(pal.TC), panel = rgb(pal.panel);
    const ti = preview >= 0 ? preview : pinned;
    const off = ti >= 0 && tables ? ti * 65536 : -1;
    const d = img.data;
    for (let i = 0; i < 65536; i++) {
      const lit = cov.bits[i];
      const inT = off >= 0 && tables.bits[off + i];
      let c;
      if (inT) c = lit ? hi : miss;
      else if (lit) c = off >= 0 ? faint : ink;
      else c = off >= 0 ? panel : faint;
      d[i * 4] = c[0]; d[i * 4 + 1] = c[1]; d[i * 4 + 2] = c[2]; d[i * 4 + 3] = 255;
    }
    ctx.putImageData(img, 0, 0);
    if (document.activeElement === map) {
      const x = (cursor % 16) * 16, y = Math.floor(cursor / 16) * 16;
      ctx.strokeStyle = pal.TC;
      ctx.lineWidth = 1;
      ctx.strokeRect(x + .5, y + .5, 15, 15);
    }
  }

  function readTable(i) {
    const tb = site.tables[i];
    const pct = tb.count ? (Math.floor(tb.covered / tb.count * 1000) / 10).toString().replace(/\.0$/, "") + "%" : "—";
    read.textContent = t("covTable", { name: lang() === "en" ? tb.en : tb.zh, count: fmt(tb.count), pct })
      + (tb.smp ? " " + t("covSmp", { n: fmt(tb.smp) }) : "");
  }

  function readCp(cp) {
    read.innerHTML = "";
    const lit = cov && cov.bits[cp];
    if (lit) {
      const big = document.createElement("span");
      big.className = "big";
      big.lang = "zh-Hans";
      big.textContent = String.fromCodePoint(cp);
      read.append(big);
    }
    read.append(`U+${hex(cp)}　${lit ? t("covHave") : t("covMissing")}`);
  }

  function chips() {
    tablesEl.innerHTML = "";
    const order = ["cn", "tw", "jp", "kr", "intl"];
    for (const sec of order) {
      const g = document.createElement("div");
      g.className = "cov-group";
      const h = document.createElement("h3");
      h.textContent = t("covGroups." + sec);
      const box = document.createElement("div");
      box.className = "cov-chips";
      site.tables.forEach((tb, i) => {
        if (tb.section !== sec || !tb.count) return;
        const b = document.createElement("button");
        b.type = "button";
        b.setAttribute("aria-pressed", String(i === pinned));
        const name = document.createElement("span");
        name.textContent = lang() === "en" ? tb.en : tb.zh;
        const n = document.createElement("span");
        n.className = "n";
        n.textContent = fmt(tb.count);
        b.append(name, n);
        const enter = () => { preview = i; drawMap(); readTable(i); };
        const leave = () => { preview = -1; drawMap(); if (pinned >= 0) readTable(pinned); };
        b.addEventListener("pointerenter", enter);
        b.addEventListener("pointerleave", leave);
        b.addEventListener("focus", enter);
        b.addEventListener("blur", leave);
        b.addEventListener("click", () => {
          pinned = pinned === i ? -1 : i;
          tablesEl.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", "false"));
          b.setAttribute("aria-pressed", String(pinned === i));
          preview = -1;
          drawMap();
          if (pinned >= 0) readTable(pinned); else read.textContent = t("covHint");
        });
        box.append(b);
      });
      g.append(h, box);
      tablesEl.append(g);
    }
  }

  // --- the page view
  async function openPage(p) {
    page = p;
    pageSel = -1;
    pageBox.hidden = false;
    pageH.textContent = t("covPage", { a: hex(p * 256), b: hex(p * 256 + 255) });
    let text = "";
    for (let i = 0; i < 256; i++) text += String.fromCodePoint(p * 256 + i);
    await preload(text);
    drawPage();
    pageBox.scrollIntoView({ block: "nearest", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }

  function pageGeom() {
    const avail = pageBox.clientWidth - 30;
    const s = avail >= 16 * 34 + 28 ? 2 : 1;
    const cell = 14 * s + 4;
    return { s, cell, L: 28, T: 21, W: 28 + 16 * cell, H: 21 + 16 * cell };
  }

  function drawPage() {
    if (page < 0) return;
    const pal = palette();
    const { s, cell, L, T, W, H } = pageGeom();
    const c = fitCanvas(pageCanvas, W, H);
    c.clearRect(0, 0, W, H);
    c.font = '14px "TPS Square", sans-serif';
    c.fillStyle = pal.muted;
    for (let i = 0; i < 16; i++) {
      c.fillText(hex(i, 1), L + i * cell + cell / 2 - 3, 14);
      c.fillText(hex(i, 1) + "_", 0, T + i * cell + cell / 2 + 5);
    }
    for (let i = 0; i < 256; i++) {
      const cp = page * 256 + i, x = L + (i % 16) * cell, y = T + Math.floor(i / 16) * cell;
      c.fillStyle = i === pageSel ? pal.faint : pal.panel;
      c.fillRect(x, y, cell - 1, cell - 1);
      c.fillStyle = pal.rule;
      c.fillRect(x + cell - 1, y, 1, cell);
      c.fillRect(x, y + cell - 1, cell, 1);
      const gs = glyphsSync(cp);
      if (!gs) continue;
      const g = gs[region];
      c.fillStyle = pal.ink;
      const ox = x + 2 + Math.max(0, Math.floor((14 - g.adv) / 2)) * s;
      for (let j = 0; j < g.h; j++)
        for (let k = 0; k < g.w; k++)
          if (g.bits[j * g.w + k]) c.fillRect(ox + (g.x + k) * s, y + 2 + (g.top + j) * s, s, s);
    }
  }

  pageCanvas.addEventListener("click", e => {
    const { cell, L, T, W } = pageGeom();
    const r = pageCanvas.getBoundingClientRect();
    const k = W / r.width;
    const x = Math.floor(((e.clientX - r.left) * k - L) / cell), y = Math.floor(((e.clientY - r.top) * k - T) / cell);
    if (x < 0 || x > 15 || y < 0 || y > 15) return;
    pageSel = y * 16 + x;
    const cp = page * 256 + pageSel;
    drawPage();
    readCp(cp);
    const gs = glyphsSync(cp);
    if (gs) {
      const p = document.createElement("span");
      p.className = "muted";
      p.textContent = "　" + stateLine(gs);
      read.append(document.createElement("br"), p);
    }
  });
  pageRegion.addEventListener("click", e => {
    const b = e.target.closest("button");
    if (!b) return;
    region = +b.dataset.v;
    pageRegion.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", String(x === b)));
    drawPage();
  });
  document.getElementById("cov-page-close").addEventListener("click", () => { pageBox.hidden = true; page = -1; map.focus(); });

  // --- map pointer and keyboard
  const cpAt = e => {
    const r = map.getBoundingClientRect();
    const x = Math.floor((e.clientX - r.left - 1) / (r.width - 2) * 256), y = Math.floor((e.clientY - r.top - 1) / (r.height - 2) * 256);
    return Math.max(0, Math.min(255, y)) * 256 + Math.max(0, Math.min(255, x));
  };
  map.addEventListener("pointermove", e => { if (cov) readCp(cpAt(e)); });
  map.addEventListener("pointerleave", () => { if (pinned >= 0) readTable(pinned); });
  map.addEventListener("click", e => { const cp = cpAt(e); cursor = cp >> 8; openPage(cp >> 8); });
  map.addEventListener("focus", () => { drawMap(); read.textContent = t("covHint"); });
  map.addEventListener("blur", drawMap);
  map.addEventListener("keydown", e => {
    const mv = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -16, ArrowDown: 16 }[e.key];
    if (mv) {
      e.preventDefault();
      cursor = (cursor + mv + 256) % 256;
      drawMap();
      read.textContent = t("covPage", { a: hex(cursor * 256), b: hex(cursor * 256 + 255) });
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      openPage(cursor);
    }
  });

  document.addEventListener("tps-theme", () => { drawMap(); drawPage(); });
  document.addEventListener("tps-lang", () => { chips(); if (pinned >= 0) readTable(pinned); if (page >= 0) pageH.textContent = t("covPage", { a: hex(page * 256), b: hex(page * 256 + 255) }); });
  let lastW = 0;
  new ResizeObserver(() => { if (pageBox.clientWidth !== lastW) { lastW = pageBox.clientWidth; drawPage(); } }).observe(pageBox);

  chips();
  read.textContent = t("covHint");
  loadMask("gen/coverage.png").then(m => { cov = m; drawMap(); }).catch(() => {});
  loadMask("gen/tables.png").then(m => { tables = m; drawMap(); }).catch(() => {});
}
