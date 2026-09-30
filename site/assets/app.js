// Tong Pixel Sans home page: language, theme, and the interactive sections.

import { setPages } from "./glyphs.js";
import { t, fmt, size, lang } from "./i18n.js";
import { initPlates } from "./plates.js";
import { initDiff } from "./diff.js";
import { initPlayground } from "./playground.js";
import { initCoverage } from "./coverage.js";
import { initMaking } from "./making.js";
import { initCell } from "./cell.js";

const root = document.documentElement;
const store = {
  get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set(k, v) { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) { /* no storage */ } },
};

// ------------------------------------------------------------ language
function setLang(l) {
  root.classList.toggle("ui-en", l === "en");
  root.lang = l === "en" ? "en" : "zh-Hans";
  store.set("tps-lang", l);
  try {
    const u = new URL(location.href);
    if (l === "en") u.searchParams.set("lang", "en"); else u.searchParams.delete("lang");
    history.replaceState(null, "", u);
  } catch (e) { /* file: URLs */ }
  document.getElementById("lang-btn").setAttribute("aria-label", t("langBtn"));
  themeLabel();
  document.dispatchEvent(new Event("tps-lang"));
}
document.getElementById("lang-btn").addEventListener("click", () => setLang(lang() === "en" ? "zh" : "en"));
document.getElementById("lang-btn").setAttribute("aria-label", t("langBtn"));

// ------------------------------------------------------------ theme: auto -> light -> dark -> auto
const themeBtn = document.getElementById("theme-btn");
function themeNow() { return root.getAttribute("data-theme") || "auto"; }
function themeLabel() {
  const k = themeNow();
  themeBtn.querySelector(".theme-label").textContent = t("theme." + k);
  themeBtn.setAttribute("aria-label", (lang() === "en" ? "Theme: " : "主题：") + t("theme." + k));
}
themeBtn.addEventListener("click", () => {
  const next = { auto: "light", light: "dark", dark: "auto" }[themeNow()];
  if (next === "auto") root.removeAttribute("data-theme"); else root.setAttribute("data-theme", next);
  store.set("tps-theme", next === "auto" ? null : next);
  themeLabel();
  document.dispatchEvent(new Event("tps-theme"));
});
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => document.dispatchEvent(new Event("tps-theme")));
themeLabel();

// ------------------------------------------------------------ downloads: sizes from downloads/manifest.json
async function downloads() {
  let man = null;
  try { const r = await fetch("downloads/manifest.json", { cache: "no-cache" }); if (r.ok) man = await r.json(); } catch (e) { /* offline */ }
  const fill = () => {
    for (const id of ["dl-version", "dl-version-en"]) document.getElementById(id).textContent = man && man.version ? man.version : "—";
    document.querySelectorAll("a[data-file]").forEach(a => {
      let s = a.parentElement.querySelector(".size");
      if (!s) { s = document.createElement("span"); s.className = "size"; a.after(s); }
      const n = man && man.files ? man.files[a.dataset.file] : undefined;
      const known = typeof n === "number";
      s.textContent = known ? size(n) : (man ? t("missingFile") : "");
      a.parentElement.classList.toggle("missing", !!man && !known);
      const ext = a.dataset.file.split(".").pop().toUpperCase();
      a.setAttribute("aria-label", `${a.dataset.file.split("/").pop()}${known ? ", " + size(n) : ""}`);
      a.textContent = ext;
    });
  };
  fill();
  document.addEventListener("tps-lang", fill);
}

// ------------------------------------------------------------ sections, started when they come near
function whenNear(id, fn) {
  const el = document.getElementById(id);
  if (!el) return;
  if (!("IntersectionObserver" in window)) { fn(); return; }
  const io = new IntersectionObserver(es => {
    if (es.some(e => e.isIntersecting)) { io.disconnect(); fn(); }
  }, { rootMargin: "800px 0px" });
  io.observe(el);
}

async function main() {
  downloads();
  let site;
  try {
    const r = await fetch("gen/site.json");
    site = await r.json();
  } catch (e) {
    console.warn("gen/site.json missing: run site/build.py", e);
    return;
  }
  setPages(site.pages);
  document.querySelectorAll("[data-stat]").forEach(el => {
    const k = el.dataset.stat;
    const v = k === "approved" ? site.status.counts.approved : site.stats[k];
    if (typeof v === "number") el.textContent = fmt(v);
  });
  const run = (name, fn) => { try { fn(); } catch (e) { console.error(name, e); } };
  run("plates", () => initPlates(site));
  whenNear("forms", () => run("diff", initDiff));
  whenNear("type", () => run("playground", () => initPlayground(site)));
  whenNear("shapes", () => run("split", initSplit));
  whenNear("mono", () => run("terminal", initTerminal));
  whenNear("cell", () => run("cell", initCell));
  whenNear("coverage", () => run("coverage", () => initCoverage(site)));
  whenNear("making", () => run("making", () => initMaking(site)));
}

// ------------------------------------------------------------ square / dot divider
function initSplit() {
  const box = document.getElementById("split");
  const range = document.getElementById("split-range");
  const set = v => { box.style.setProperty("--pos", v + "%"); range.value = String(v); };
  range.addEventListener("input", () => set(+range.value));
  let drag = false;
  const at = e => { const r = box.getBoundingClientRect(); set(Math.max(0, Math.min(100, Math.round((e.clientX - r.left) / r.width * 100)))); };
  box.addEventListener("pointerdown", e => { if (e.pointerType === "touch") return; drag = true; box.setPointerCapture(e.pointerId); at(e); });
  box.addEventListener("pointermove", e => { if (drag) at(e); });
  box.addEventListener("pointerup", () => { drag = false; });
  box.addEventListener("click", e => { if (e.pointerType === "touch" || e.detail) at(e); });
  set(50);
}

// ------------------------------------------------------------ terminal column guide
function initTerminal() {
  const b = document.getElementById("term-cols");
  const term = document.getElementById("term");
  b.addEventListener("click", () => {
    const on = b.getAttribute("aria-pressed") !== "true";
    b.setAttribute("aria-pressed", String(on));
    term.classList.toggle("cols", on);
  });
}

main();
