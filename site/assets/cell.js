// The cell diagram: 通, A and g from the real bitmaps on the 14 px cell, with the metrics.

import { glyphs, palette, fitCanvas } from "./glyphs.js";

export function initCell() {
  const canvas = document.getElementById("cell-canvas");
  const keys = document.getElementById("cell-keys");
  let gs = null, hl = null, pinned = null;

  async function load() {
    gs = await Promise.all([..."通Ag"].map(async ch => (await glyphs(ch.codePointAt(0)))?.[0]));
    draw();
  }

  function draw() {
    if (!gs || gs.some(g => !g)) return;
    const pal = palette();
    const total = gs.reduce((a, g) => a + g.adv, 0);
    const avail = Math.min(canvas.parentElement.clientWidth, 640);
    const S = Math.max(6, Math.min(14, Math.floor((avail - 56) / total)));
    const W = total * S + 56, H = 14 * S + 2;
    const ctx = fitCanvas(canvas, W, H);
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = pal.panel;
    ctx.fillRect(0, 0, total * S + 1, H);
    const band = (y0, y1, col) => { ctx.globalAlpha = .16; ctx.fillStyle = col; ctx.fillRect(0, y0 * S, total * S + 1, (y1 - y0) * S); ctx.globalAlpha = 1; };
    const h = pinned || hl;
    if (h === "asc") band(0, 11, pal.SC);
    if (h === "desc") band(11, 14, pal.KR);
    ctx.fillStyle = pal.faint;
    for (let i = 0; i <= total; i++) ctx.fillRect(i * S, 0, 1, 14 * S);
    for (let j = 0; j <= 14; j++) ctx.fillRect(0, j * S, total * S + 1, 1);
    let x0 = 0;
    ctx.fillStyle = pal.rule;
    gs.forEach(g => { ctx.fillRect(x0 * S, 0, 1, 14 * S + 1); x0 += g.adv; });
    ctx.fillRect(x0 * S, 0, 1, 14 * S + 1);
    x0 = 0;
    gs.forEach(g => {
      ctx.fillStyle = pal.ink;
      for (let j = 0; j < g.h; j++)
        for (let i = 0; i < g.w; i++)
          if (g.bits[j * g.w + i]) ctx.fillRect((x0 + g.x + i) * S + 1, (g.top + j) * S + 1, S - 1, S - 1);
      x0 += g.adv;
    });
    // baseline
    ctx.fillStyle = pal.SC;
    ctx.fillRect(0, 11 * S, total * S + 1, h === "base" ? 3 : 1);
    if (h === "ink") { ctx.strokeStyle = pal.TC; ctx.lineWidth = 3; ctx.strokeRect(1 * S + 1.5, 1.5, 13 * S - 2, 13 * S - 2); }
    if (h === "em") { ctx.strokeStyle = pal.JP; ctx.lineWidth = 3; ctx.strokeRect(1.5, 1.5, 14 * S - 2, 14 * S - 2); }
    // numbers on the right
    ctx.font = '14px "TPS Square", sans-serif';
    ctx.fillStyle = pal.muted;
    const R = total * S + 10;
    ctx.fillStyle = h === "asc" ? pal.SC : pal.muted; ctx.fillText("11", R, Math.round(5.5 * S) + 5);
    ctx.fillStyle = h === "desc" ? pal.KR : pal.muted; ctx.fillText("3", R, Math.round(12.5 * S) + 5);
    ctx.fillStyle = pal.muted; ctx.fillRect(total * S + 3, 0, 4, 1); ctx.fillRect(total * S + 3, 11 * S, 4, 1); ctx.fillRect(total * S + 3, 14 * S, 4, 1);
    ctx.fillRect(total * S + 5, 0, 1, 14 * S);
  }

  keys.addEventListener("pointerover", e => { const b = e.target.closest("button"); if (b) { hl = b.dataset.k; draw(); } });
  keys.addEventListener("pointerout", () => { hl = null; draw(); });
  keys.addEventListener("focusin", e => { const b = e.target.closest("button"); if (b) { hl = b.dataset.k; draw(); } });
  keys.addEventListener("focusout", () => { hl = null; draw(); });
  keys.addEventListener("click", e => {
    const b = e.target.closest("button");
    if (!b) return;
    pinned = pinned === b.dataset.k ? null : b.dataset.k;
    keys.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", String(x.dataset.k === pinned)));
    draw();
  });
  keys.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", "false"));
  new ResizeObserver(draw).observe(canvas.parentElement);
  document.addEventListener("tps-theme", draw);
  document.fonts.ready.then(draw);
  load();
}
