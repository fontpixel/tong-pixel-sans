// Tong Pixel Sans home page: language, theme, and the interactive sections.

import { setPages } from "./glyphs.js";
import { t, fmt, size, lang, LANGS, setLanguage, setStats } from "./i18n.js";
import { watch as autospace } from "./autospace.js";
import { initPlates } from "./plates.js";
import { initDiff } from "./diff.js";
import { initPlayground } from "./playground.js";
import { initCoverage } from "./coverage.js";
import { initMaking } from "./making.js";
import { initCell } from "./cell.js";
import { initGame } from "./game.js";

const root = document.documentElement;
const store = {
  get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set(k, v) { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) { /* no storage */ } },
};

// ------------------------------------------------------------ language menu
const langBtn = document.getElementById("lang-btn");
const langMenu = document.getElementById("lang-list");
const langBox = document.getElementById("langmenu");
const items = [...langMenu.querySelectorAll("[data-lang]")];

async function chooseLang(code) {
  store.set("tps-lang", code);
  try {
    const u = new URL(location.href);
    if (code === "zh") u.searchParams.delete("lang"); else u.searchParams.set("lang", code);
    history.replaceState(null, "", u);
  } catch (e) { /* file: URLs */ }
  await setLanguage(code);
  markLang();
}
function markLang() {
  items.forEach(a => a.setAttribute("aria-checked", String(a.dataset.lang === lang())));
}
let closeTimer = 0;
function openMenu(focus) {
  clearTimeout(closeTimer);
  langMenu.hidden = false;
  langBtn.setAttribute("aria-expanded", "true");
  if (focus) (items.find(a => a.dataset.lang === lang()) || items[0]).focus();
}
function closeMenu(refocus) {
  langMenu.hidden = true;
  langBtn.setAttribute("aria-expanded", "false");
  if (refocus) langBtn.focus();
}
langBtn.addEventListener("click", e => {
  if (e.pointerType === "mouse") { openMenu(false); return; }
  if (langMenu.hidden) openMenu(e.detail === 0); else closeMenu(false);
});
langBtn.addEventListener("keydown", e => {
  if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); openMenu(true); }
});
langBox.addEventListener("pointerenter", e => { if (e.pointerType === "mouse") openMenu(false); });
langBox.addEventListener("pointerleave", e => { if (e.pointerType === "mouse") closeTimer = setTimeout(() => closeMenu(false), 250); });
langMenu.addEventListener("keydown", e => {
  const i = items.indexOf(document.activeElement);
  if (e.key === "ArrowDown") { e.preventDefault(); items[(i + 1) % items.length].focus(); }
  else if (e.key === "ArrowUp") { e.preventDefault(); items[(i - 1 + items.length) % items.length].focus(); }
  else if (e.key === "Home") { e.preventDefault(); items[0].focus(); }
  else if (e.key === "End") { e.preventDefault(); items[items.length - 1].focus(); }
  else if (e.key === "Escape") { e.preventDefault(); closeMenu(true); }
  else if (e.key === "Tab") closeMenu(false);
  else if (e.key === " ") { e.preventDefault(); document.activeElement.click(); }
});
items.forEach(a => a.addEventListener("click", e => {
  e.preventDefault();
  const kb = document.activeElement === a;
  closeMenu(kb);
  chooseLang(a.dataset.lang);
}));
document.addEventListener("pointerdown", e => { if (!langBox.contains(e.target)) closeMenu(false); });
markLang();

// ------------------------------------------------------------ theme: light or dark; the system decides until the visitor chooses
const themeBtn = document.getElementById("theme-btn");
const sysDark = window.matchMedia("(prefers-color-scheme: dark)");
function themeNow() { return root.getAttribute("data-theme") || (sysDark.matches ? "dark" : "light"); }
function themeLabel() {
  const dark = themeNow() === "dark";
  themeBtn.setAttribute("aria-label", t(dark ? "theme.toLight" : "theme.toDark"));
  themeBtn.title = t(dark ? "theme.toLight" : "theme.toDark");
}
themeBtn.addEventListener("click", () => {
  const next = themeNow() === "dark" ? "light" : "dark";
  root.setAttribute("data-theme", next);
  store.set("tps-theme", next);
  themeLabel();
  document.dispatchEvent(new Event("tps-theme"));
});
sysDark.addEventListener("change", () => { themeLabel(); document.dispatchEvent(new Event("tps-theme")); });
document.addEventListener("tps-lang", themeLabel);

// ------------------------------------------------------------ downloads: sizes from downloads/manifest.json
async function downloads() {
  let man = null;
  try { const r = await fetch("downloads/manifest.json", { cache: "no-cache" }); if (r.ok) man = await r.json(); } catch (e) { /* offline */ }
  const fill = () => {
    setStats({ version: man && man.version ? man.version : "—" });
    document.querySelectorAll("a[data-file]").forEach(a => {
      let s = a.parentElement.querySelector(".size");
      if (!s) { s = document.createElement("span"); s.className = "size"; a.after(s); }
      const n = man && man.files ? man.files[a.dataset.file] : undefined;
      const known = typeof n === "number";
      s.textContent = known ? size(n) : (man ? t("js.missingFile") : "");
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
  autospace();
  initNotes();
  await setLanguage(lang());
  themeLabel();
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
  setStats({ approved: site.status.counts.approved || 0, perRegion: site.stats.perRegion, tables: site.stats.tables, smp: site.stats.smp });
  const run = (name, fn) => { try { fn(); } catch (e) { console.error(name, e); } };
  run("plates", () => initPlates(site));
  whenNear("forms", () => run("diff", initDiff));
  whenNear("type", () => run("playground", () => initPlayground(site)));
  whenNear("shapes", () => run("split", initSplit));
  whenNear("mono", () => run("terminal", initTerminal));
  whenNear("game-sec", () => run("game", initGame));
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

// ------------------------------------------------------------ footnotes: the note shows next to its marker
function initNotes() {
  let pop = null;
  const show = a => {
    const note = document.getElementById(a.dataset.note);
    if (!note) return;
    hide();
    pop = document.createElement("div");
    pop.className = "note-pop";
    pop.setAttribute("aria-hidden", "true");
    pop.innerHTML = note.querySelector("span").innerHTML;
    document.body.append(pop);
    const r = a.getBoundingClientRect();
    const w = Math.min(420, document.documentElement.clientWidth - 32);
    pop.style.width = w + "px";
    const left = Math.max(16, Math.min(Math.round(r.left + scrollX), document.documentElement.clientWidth - w - 16));
    pop.style.left = left + "px";
    pop.style.top = Math.round(r.bottom + scrollY + 7) + "px";
  };
  const hide = () => { if (pop) { pop.remove(); pop = null; } };
  document.addEventListener("pointerover", e => { const a = e.target.closest && e.target.closest("a[data-note]"); if (a && e.pointerType === "mouse") show(a); });
  document.addEventListener("pointerout", e => { if (e.target.closest && e.target.closest("a[data-note]")) hide(); });
  document.addEventListener("focusin", e => { const a = e.target.closest && e.target.closest("a[data-note]"); if (a) show(a); else hide(); });
  document.addEventListener("keydown", e => { if (e.key === "Escape") hide(); });
  document.addEventListener("tps-lang", hide);
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
