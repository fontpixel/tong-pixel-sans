// Page languages. The text lives in i18n/<code>.json (flat keys, the same in every file); English is the
// fallback for keys a file does not have. Static elements carry data-i18n / data-i18n-attr /
// data-i18n-list / data-i18n-bi attributes (see index.html); scripts call t().

export const LANGS = {
  zh: { tag: "zh-Hans", fp: "zh", name: "简体中文" },
  en: { tag: "en", fp: "en", name: "English" },
  "zh-Hant": { tag: "zh-Hant", fp: "zh-Hant", name: "繁體中文" },
  ja: { tag: "ja", fp: "ja", name: "日本語" },
  ko: { tag: "ko", fp: "ko", name: "한국어" },
  fr: { tag: "fr", fp: "fr", name: "Français" },
};
const FONTPIXEL = "https://fontpixel.com";

let cur = document.documentElement.getAttribute("data-lang") || "zh";
let dict = {}, en = {};
const cache = {};
let stats = {};

function load(code) {
  if (!cache[code]) cache[code] = fetch(`i18n/${code}.json`).then(r => (r.ok ? r.json() : {})).catch(() => ({}));
  return cache[code];
}

/** Current language code: zh, en, zh-Hant, ja, ko, fr. */
export function lang() { return cur; }
export function tag() { return (LANGS[cur] || LANGS.zh).tag; }

export async function setLanguage(code) {
  if (!LANGS[code]) code = "zh";
  const [d, e] = await Promise.all([load(code), load("en")]);
  cur = code;
  dict = d; en = e;
  const root = document.documentElement;
  root.setAttribute("data-lang", code);
  root.lang = LANGS[code].tag;
  apply();
  root.classList.remove("i18n-wait");
}

export function t(key, vars) {
  let v = dict[key];
  if (v === undefined || v === "") v = en[key];
  if (v === undefined) return "";
  if (typeof v === "string" && vars) v = v.replace(/\{(\w+)\}/g, (_, k) => (vars[k] ?? ""));
  return v;
}
export function tEn(key) { return en[key]; }

export function fmt(n) {
  try { return n.toLocaleString(tag()); } catch (e) { return String(n); }
}
export function size(n) {
  return n >= 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB";
}

/** Numbers shown in the text: {approved, perRegion, tables, smp, version}. */
export function setStats(s) { Object.assign(stats, s); fillStats(); }
export function fillStats(root = document) {
  root.querySelectorAll("[data-stat]").forEach(el => {
    const v = stats[el.dataset.stat];
    if (v !== undefined) el.textContent = typeof v === "number" ? fmt(v) : v;
  });
}

function links(root) {
  const fp = (LANGS[cur] || LANGS.zh).fp;
  root.querySelectorAll("a[data-fp]").forEach(a => { a.href = `${FONTPIXEL}/${fp}${a.dataset.fp}`; });
}

export function apply(root = document) {
  root.querySelectorAll("[data-i18n]").forEach(el => {
    const v = t(el.dataset.i18n);
    if (typeof v !== "string" || !v) return;
    if (el.tagName === "TITLE") el.textContent = v;
    else el.innerHTML = v;
  });
  root.querySelectorAll("[data-i18n-attr]").forEach(el => {
    el.dataset.i18nAttr.split(";").forEach(pair => {
      const [attr, key] = pair.split(":");
      const v = t(key);
      if (v) el.setAttribute(attr, v);
    });
  });
  root.querySelectorAll("[data-i18n-list]").forEach(el => {
    const v = t(el.dataset.i18nList);
    if (!Array.isArray(v)) return;
    el.innerHTML = "";
    v.forEach(s => { const li = document.createElement("li"); li.textContent = s; el.append(li); });
  });
  root.querySelectorAll("[data-i18n-bi]").forEach(el => {
    const k = el.dataset.i18nBi, v = t(k), e = en[k];
    el.innerHTML = "";
    const a = document.createElement("span");
    a.textContent = v;
    el.append(a);
    if (cur !== "en" && e && e !== v) {
      const b = document.createElement("span");
      b.className = "bi";
      b.lang = "en";
      b.textContent = e;
      el.append(b);
    }
  });
  links(root);
  fillStats(root);
  document.dispatchEvent(new Event("tps-lang"));
}
