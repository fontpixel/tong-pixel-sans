// Glyph bitmaps of the four regional proportional faces, from gen/g/<PAGE>.json (made by site/build.py).
// A glyph: {adv, x, top, w, h, state, bits}; cell coordinates: column x + i, row top + j, row 0 = ascent line.

export const REGIONS = ["SC", "TC", "JP", "KR"];
export const LANG = { SC: "zh-Hans", TC: "zh-Hant", JP: "ja", KR: "ko" };
export const STATE = { A: "approved", E: "edited", D: "derived", I: "ai", R: "draft", H: "hangul-ai", C: "hangul-composed", G: "generated", B: "blank" };

let known = null;
const pages = new Map();

export function setPages(list) { known = new Set(list); }

function pageKey(cp) { return (cp >> 8).toString(16).toUpperCase().padStart(2, "0"); }

function loadPage(key) {
  let p = pages.get(key);
  if (!p) {
    p = { data: undefined, glyphs: new Map() };
    p.promise = (known && !known.has(key))
      ? Promise.resolve(null)
      : fetch(`gen/g/${key}.json`).then(r => (r.ok ? r.json() : null)).catch(() => null);
    p.promise.then(d => { p.data = d; });
    pages.set(key, p);
  }
  return p;
}

function decode(rec) {
  const [adv, x, top, w, h, st, hex] = rec.split(".");
  const W = +w, H = +h, bits = new Uint8Array(W * H);
  for (let i = 0; i < hex.length; i++) {
    const v = parseInt(hex[i], 16);
    for (let b = 0; b < 4; b++) {
      const k = i * 4 + b;
      if (k < bits.length) bits[k] = (v >> (3 - b)) & 1;
    }
  }
  return { adv: +adv, x: +x, top: +top, w: W, h: H, state: STATE[st] || "ai", bits };
}

function fromPage(p, cp) {
  if (!p.data) return null;
  const e = p.data.c[cp.toString(16).toUpperCase()];
  if (e === undefined) return null;
  const idx = Array.isArray(e) ? e : [e, e, e, e];
  return idx.map(i => {
    let g = p.glyphs.get(i);
    if (!g) { g = decode(p.data.l[i]); g.id = i; p.glyphs.set(i, g); }
    return g;
  });
}

/** Load every page the text needs. */
export async function preload(text) {
  const keys = new Set();
  for (const ch of text) keys.add(pageKey(ch.codePointAt(0)));
  await Promise.all([...keys].map(k => loadPage(k).promise));
}

/** The four regional glyphs of a code point, or null; call preload() first. */
export function glyphsSync(cp) { return fromPage(loadPage(pageKey(cp)), cp); }

export async function glyphs(cp) {
  const p = loadPage(pageKey(cp));
  await p.promise;
  return fromPage(p, cp);
}

/** Set of lit cells as numbers y * 64 + x (cell coordinates). */
export function cellSet(g) {
  const s = new Set();
  if (!g) return s;
  for (let j = 0; j < g.h; j++)
    for (let i = 0; i < g.w; i++)
      if (g.bits[j * g.w + i]) s.add((g.top + j) * 64 + g.x + i);
  return s;
}

export function sameSet(a, b) {
  if (a.size !== b.size) return false;
  for (const v of a) if (!b.has(v)) return false;
  return true;
}

/** Colours from the CSS custom properties (they change with the theme). */
export function palette() {
  const cs = getComputedStyle(document.documentElement);
  const v = n => cs.getPropertyValue(n).trim();
  return { ink: v("--ink"), paper: v("--paper"), panel: v("--panel"), muted: v("--muted"), rule: v("--rule"),
    faint: v("--faint"), grid: v("--grid"), SC: v("--sc"), TC: v("--tc"), JP: v("--jp"), KR: v("--kr") };
}

/** Size a canvas for its CSS size at the device pixel ratio; returns the 2D context scaled to CSS px. */
export function fitCanvas(canvas, w, h) {
  const dpr = Math.max(1, Math.round(window.devicePixelRatio || 1));
  canvas.width = Math.round(w * dpr);
  canvas.height = Math.round(h * dpr);
  canvas.style.width = w + "px";
  canvas.style.height = h + "px";
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return ctx;
}

/** 13×13 bit string ("0101…") of the site data -> Set of cell numbers (x + 1 offset like a CJK glyph). */
export function bitString(s, size = 13) {
  const out = new Set();
  for (let i = 0; i < s.length; i++) if (s[i] === "1") out.add(Math.floor(i / size) * 64 + (i % size) + 1);
  return out;
}

export const reduceMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
