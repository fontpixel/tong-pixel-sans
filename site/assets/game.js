// A CRT screen with a blue-window RPG: title menu, a dialogue with typewriter text, a choice, a reply.
// The text comes from the language file (game.*); the region buttons set the lang attribute, so the
// same lines show each region's glyph forms (OpenType locl). Enter / Space / click advance, arrows choose.

import { LANG, reduceMotion } from "./glyphs.js";
import { t, fmt } from "./i18n.js";
import { spaceString } from "./autospace.js";

const ART = [
  "",
  "  s                     s                mmm",
  "         s                      s       mmmmm",
  "                                        mmmmm",
  "    s              s                     mmm",
  "                         s",
  "              rrrrrrrrrrrr",
  "   s        rrrrrrrrrrrrrrrr        s",
  "           rrrrrrrrrrrrrrrrrr",
  "          rrrrrrrrrrrrrrrrrrrr",
  "           wwwwwwwwwwwwwwwwww",
  "           wyyywwwwddwwwwyyyw",
  "           wyyywwwwddwwwwyyyw",
  "           wwwwwwwwddwwwwwwww",
  "gggggggggggggggggggggggggggggggggggggggggggggggg",
];
const ART_COLORS = { s: "#dfe6ff", m: "#ffe9a0", r: "#c8463c", w: "#8a5a3c", y: "#ffd75a", d: "#3a2418", g: "#2f7a4a" };

export function initGame() {
  const screen = document.getElementById("crt-screen");
  const game = document.getElementById("game");
  const live = document.getElementById("game-live");
  const regionSeg = document.getElementById("game-region");
  const art = document.getElementById("game-art");
  const els = {
    title: game.querySelector(".g-title"), logo: game.querySelector(".g-logo"), sub: game.querySelector(".g-sub"),
    place: game.querySelector(".g-place"), scene: game.querySelector(".g-scene"),
    menu: game.querySelector(".g-menu"), status: game.querySelector(".g-status"),
    dialog: game.querySelector(".g-dialog"), name: game.querySelector(".g-name"),
    text: game.querySelector(".g-text"), more: game.querySelector(".g-more"),
    choice: game.querySelector(".g-choice"),
  };
  const st = { mode: "title", line: 0, sel: 0, region: "SC", hp: 12, gold: 1280, typing: 0, full: "", shown: 0 };

  // pixel art, drawn at a whole-number scale
  function drawArt() {
    const s = window.innerWidth < 700 ? 2 : 6;
    const W = 48, H = ART.length;
    art.width = W * s; art.height = H * s;
    art.style.width = W * s + "px"; art.style.height = H * s + "px";
    const c = art.getContext("2d");
    c.clearRect(0, 0, art.width, art.height);
    ART.forEach((row, y) => [...row.padEnd(W, " ")].forEach((ch, x) => {
      if (ART_COLORS[ch]) { c.fillStyle = ART_COLORS[ch]; c.fillRect(x * s, y * s, s, s); }
    }));
  }

  const list = key => { const v = t(key); return Array.isArray(v) ? v : []; };

  function status() {
    els.status.innerHTML = "";
    const cells = [t("game.hero"), "Lv.7", `HP ${st.hp}/48`, "MP 9/20", `${fmt(st.gold)}G`];
    cells.forEach((s, i) => {
      const span = document.createElement("span");
      span.textContent = spaceString(s);
      if (i === 2) span.className = st.hp < 20 ? "g-low" : "g-ok";
      els.status.append(span);
    });
  }

  function menu(items, el) {
    el.innerHTML = "";
    items.forEach((s, i) => {
      const li = document.createElement("li");
      li.textContent = spaceString(s);
      li.className = i === st.sel ? "on" : "";
      li.addEventListener("click", e => { e.stopPropagation(); st.sel = i; confirm(); });
      li.addEventListener("pointerenter", () => { st.sel = i; mark(el); });
      el.append(li);
    });
  }
  function mark(el) { [...el.children].forEach((li, i) => li.classList.toggle("on", i === st.sel)); }

  function type(text, name) {
    clearInterval(st.typing);
    els.name.textContent = name ? spaceString(name) : "";
    els.name.hidden = !name;
    st.full = [...spaceString(text)];
    live.textContent = (name ? name + ": " : "") + text;
    els.more.classList.remove("on");
    if (reduceMotion()) { finish(); return; }
    st.shown = 0;
    els.text.textContent = "";
    st.typing = setInterval(() => {
      st.shown++;
      els.text.textContent = st.full.slice(0, st.shown).join("");
      if (st.shown >= st.full.length) finish();
    }, 45);
  }
  function finish() {
    clearInterval(st.typing);
    st.typing = 0;
    els.text.textContent = st.full.join("");
    els.more.classList.add("on");
  }

  function show(mode) {
    st.mode = mode;
    const title = mode === "title" || mode === "settings";
    els.title.hidden = !title;
    els.scene.hidden = title;
    els.status.hidden = title;
    els.dialog.hidden = title;
    els.choice.hidden = mode !== "choice";
    els.logo.textContent = spaceString(t("game.logo"));
    els.sub.textContent = spaceString(t("game.press"));
    els.place.textContent = spaceString(t("game.place"));
    if (mode === "title") {
      st.sel = 0;
      menu(list("game.menu"), els.menu);
      live.textContent = t("game.logo") + ". " + list("game.menu").join(", ");
    } else if (mode === "settings") {
      st.sel = ["SC", "TC", "JP", "KR"].indexOf(st.region);
      menu(["SC", "TC", "JP", "KR"].map(r => `${t("game.textRegion")}${t("js.colon")}${t("region." + r)}`), els.menu);
    } else if (mode === "talk") {
      status();
      type((list("game.lines")[st.line] || "").replace("{hp}", st.hp), t("game.speaker"));
    } else if (mode === "choice") {
      st.sel = 0;
      menu(list("game.choices"), els.choice);
      live.textContent = list("game.choices").join(", ");
    }
  }

  function confirm() {
    if (st.mode === "title") {
      if (st.sel === 2) { show("settings"); return; }
      st.hp = 12; st.gold = 1280;
      st.line = 0;
      show("talk");
    } else if (st.mode === "settings") {
      setRegion(["SC", "TC", "JP", "KR"][st.sel]);
      show("title");
    } else if (st.mode === "choice") {
      const k = st.sel;
      if (k === 0) { st.hp = 48; st.gold -= 50; }
      if (k === 1) { st.gold -= 8; }
      status();
      st.mode = "reply";
      els.choice.hidden = true;
      type(list("game.replies")[k] || "", t("game.speaker"));
    }
  }

  function advance() {
    if (st.typing) { finish(); return; }
    if (st.mode === "talk") {
      const lines = list("game.lines");
      if (st.line < lines.length - 1) { st.line++; show("talk"); } else show("choice");
    } else if (st.mode === "reply") show("title");
    else confirm();
  }

  function setRegion(r) {
    st.region = r;
    game.lang = LANG[r];
    regionSeg.querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.v === r)));
  }

  screen.addEventListener("keydown", e => {
    const menuEl = st.mode === "choice" ? els.choice : (st.mode === "title" || st.mode === "settings") ? els.menu : null;
    if ((e.key === "ArrowDown" || e.key === "ArrowUp") && menuEl) {
      e.preventDefault();
      const n = menuEl.children.length;
      st.sel = (st.sel + (e.key === "ArrowDown" ? 1 : n - 1)) % n;
      mark(menuEl);
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      if (menuEl && !st.typing) confirm(); else advance();
    } else if (e.key === "Escape" && st.mode !== "title") {
      e.preventDefault();
      clearInterval(st.typing); st.typing = 0;
      show("title");
    }
  });
  screen.addEventListener("click", () => { screen.focus({ preventScroll: true }); if (st.mode === "talk" || st.mode === "reply") advance(); });
  regionSeg.addEventListener("click", e => {
    const b = e.target.closest("button");
    if (b) setRegion(b.dataset.v);
  });
  document.getElementById("game-restart").addEventListener("click", () => { clearInterval(st.typing); st.typing = 0; show("title"); screen.focus({ preventScroll: true }); });
  document.addEventListener("tps-lang", () => { clearInterval(st.typing); st.typing = 0; show(st.mode === "settings" ? "settings" : "title"); });

  drawArt();
  window.addEventListener("resize", drawArt);
  setRegion("SC");
  show("title");
}
