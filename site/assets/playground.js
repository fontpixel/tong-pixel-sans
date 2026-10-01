// Type with the real vector fonts: region (by lang), spacing, pixel shape, whole-number scale, grid, loupe.

import { LANG } from "./glyphs.js";
import { t, size } from "./i18n.js";

const PRESETS = [
  { id: "hello", region: "SC", text: "通格像素黑体：一个字，四种写法。\nTong Pixel Sans, 14 px pan-CJK." },
  { id: "qianzi", region: "SC", text: "天地玄黄，宇宙洪荒。日月盈昃，辰宿列张。\n寒来暑往，秋收冬藏。闰余成岁，律吕调阳。" },
  { id: "tc", region: "TC", text: "天地玄黃，宇宙洪荒。日月盈昃，辰宿列張。\n寒來暑往，秋收冬藏。閏餘成歲，律呂調陽。" },
  { id: "jp", region: "JP", text: "いろはにほへと　ちりぬるを\n吾輩は猫である。名前はまだ無い。" },
  { id: "kr", region: "KR", text: "다람쥐 헌 쳇바퀴에 타고파\n키스의 고유조건은 입술끼리 만나야 하고 특별한 기술은 필요치 않다." },
  { id: "latin", region: "SC", text: "The quick brown fox jumps over the lazy dog.\n“Quotes”, ellipsis… Ελληνικά, Кириллица, Tiếng Việt." },
  { id: "symbols", region: "SC", text: "←↑→↓ ①②③ ★☆ ♠♥♦♣ ¥€£ ∑∞≠≤≥ ℃ №\n㊤ ㎏ ㎡ ※ 〒 ♪ ◎ △ ▽ ◇ ■" },
  { id: "box", region: "SC", text: "┌──┬──┐ ░▒▓█ ⣿⠿⠛\n│通│格│ ▀▄▌▐ ⡇⢸⣀\n└──┴──┘ ◢◣◤◥ ⠁⠂⠄" },
];

export function initPlayground(site) {
  const out = document.getElementById("pg-out");
  const frame = document.getElementById("pg-frame");
  const loupe = document.getElementById("loupe");
  const lin = document.getElementById("loupe-in");
  const meta = document.getElementById("pg-meta");
  const status = document.getElementById("font-status");
  const presets = document.getElementById("pg-presets");
  const st = { region: "SC", width: "prop", shape: "square", s: window.innerWidth < 700 ? 2 : 3, grid: false, loupe: true };
  document.querySelectorAll("#pg-scale button").forEach(b => b.setAttribute("aria-pressed", String(+b.dataset.v === st.s)));

  out.contentEditable = "plaintext-only";
  if (out.contentEditable !== "plaintext-only") {
    out.contentEditable = "true";
    out.addEventListener("paste", e => {
      e.preventDefault();
      document.execCommand("insertText", false, (e.clipboardData || window.clipboardData).getData("text/plain"));
    });
  }
  out.textContent = PRESETS[0].text;

  const fontKey = () => (st.shape === "dot" ? "dot" : "square") + (st.width === "mono" ? "-mono" : "");
  const family = () => (site.fonts && site.fonts[fontKey()] ? site.fonts[fontKey()].family : "TPS Square");

  function fullFace() {
    const fam = family();
    for (const f of document.fonts) {
      if (f.family.replace(/["']/g, "") === fam && (!f.unicodeRange || /^U\+0-10FFFF$/i.test(f.unicodeRange))) return f;
    }
    return null;
  }

  function fontStatus() {
    const info = site.fonts && site.fonts[fontKey()];
    const face = fullFace();
    const full = info && info.full ? size(info.full) : "?";
    if (face && face.status === "loading") status.textContent = t("js.fontLoading", { full });
    else if (face && face.status === "loaded") status.textContent = t("js.fontLoaded");
    else if (face && face.status === "error") status.textContent = t("js.fontFailed");
    else status.textContent = info ? t("js.fontSubset", { size: size(info.subset), full }) : "";
  }

  function apply() {
    out.lang = LANG[st.region];
    lin.lang = LANG[st.region];
    for (const el of [out, lin]) {
      el.classList.toggle("mono", st.width === "mono");
      el.classList.toggle("dot", st.shape === "dot");
    }
    out.style.setProperty("--s", st.s);
    out.classList.toggle("grid", st.grid);
    for (let i = 1; i <= 8; i++) out.classList.toggle("s" + i, st.s === i);
    meta.textContent = t("js.pgMeta", { px: 14 * st.s, s: st.s, lang: LANG[st.region] });
    fontStatus();
  }

  function seg(id, key, conv = v => v) {
    const el = document.getElementById(id);
    el.addEventListener("click", e => {
      const b = e.target.closest("button");
      if (!b) return;
      st[key] = conv(b.dataset.v);
      el.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", String(x === b)));
      apply();
    });
    return el;
  }
  const regionSeg = seg("pg-region", "region");
  seg("pg-width", "width");
  seg("pg-shape", "shape");
  seg("pg-scale", "s", Number);
  for (const [id, key] of [["pg-grid", "grid"], ["pg-loupe", "loupe"]]) {
    const b = document.getElementById(id);
    b.addEventListener("click", () => {
      st[key] = !st[key];
      b.setAttribute("aria-pressed", String(st[key]));
      apply();
    });
  }

  function presetLabels() {
    presets.querySelectorAll("button").forEach(b => { b.textContent = t("preset." + b.dataset.id); });
  }
  PRESETS.forEach(p => {
    const b = document.createElement("button");
    b.type = "button";
    b.dataset.id = p.id;
    b.addEventListener("click", () => {
      out.textContent = p.text;
      st.region = p.region;
      regionSeg.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", String(x.dataset.v === p.region)));
      apply();
    });
    presets.append(b);
  });
  presetLabels();

  // loupe: a copy of the text at a larger whole-number scale, moved so the pointer stays centred
  const R = 98;
  function moveLoupe(e) {
    if (!st.loupe || e.pointerType === "touch") { loupe.classList.remove("on"); return; }
    const z = Math.max(2, Math.ceil(8 / st.s));
    const fr = frame.getBoundingClientRect(), or = out.getBoundingClientRect();
    const px = e.clientX - or.left, py = e.clientY - or.top;
    if (lin.textContent !== out.innerText) lin.textContent = out.innerText;
    lin.style.setProperty("--s", st.s * z);
    lin.style.width = out.clientWidth * z + "px";
    lin.style.transform = `translate(${Math.round(R - px * z)}px, ${Math.round(R - py * z)}px)`;
    loupe.style.transform = `translate(${Math.round(e.clientX - fr.left - R)}px, ${Math.round(e.clientY - fr.top - R)}px)`;
    loupe.classList.add("on");
  }
  frame.addEventListener("pointermove", moveLoupe);
  frame.addEventListener("pointerleave", () => loupe.classList.remove("on"));
  out.addEventListener("input", () => { loupe.classList.remove("on"); fontStatus(); });

  document.fonts.addEventListener("loading", fontStatus);
  document.fonts.addEventListener("loadingdone", fontStatus);
  document.fonts.addEventListener("loadingerror", fontStatus);
  document.addEventListener("tps-lang", () => { presetLabels(); apply(); });
  apply();

  return {
    /** Put a character into the playground (from the coverage page view). */
    type(ch, region) {
      out.textContent = ch;
      if (region) {
        st.region = region;
        regionSeg.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", String(x.dataset.v === region)));
      }
      apply();
    },
  };
}
