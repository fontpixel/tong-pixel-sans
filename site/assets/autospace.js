// Display-only spacing between CJK (Han, kana, Hangul, Bopomofo) and Latin letters / digits.
// The texts are written without spaces; here a THIN SPACE U+2009 goes in between. In the proportional
// fonts it is 3 px wide at 14 px (always whole pixels at multiples of 14), unlike CSS text-autospace
// (1/8 em). Monospace text, code, and what the visitor types are left alone.

const CJK = /[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Hangul}\p{Script=Bopomofo}]/u;
const LAT = /[\p{Script=Latin}\p{Script=Greek}\p{Script=Cyrillic}0-9]/u;
const PAIR = /([\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Hangul}\p{Script=Bopomofo}])(?=[\p{Script=Latin}\p{Script=Greek}\p{Script=Cyrillic}0-9])|([\p{Script=Latin}\p{Script=Greek}\p{Script=Cyrillic}0-9])(?=[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Hangul}\p{Script=Bopomofo}])/gu;
const SKIP = "pre, code, textarea, input, select, script, style, svg, canvas, [contenteditable], .loupe, .game, .term, .code, .no-space";
const THIN = "\u2009";

const need = (a, b) => (CJK.test(a) && LAT.test(b)) || (LAT.test(a) && CJK.test(b));

const blockOf = (() => {
  const cache = new WeakMap();
  return el => {
    let e = el;
    while (e && e !== document.body) {
      let inline = cache.get(e);
      if (inline === undefined) { inline = getComputedStyle(e).display.startsWith("inline"); cache.set(e, inline); }
      if (!inline) return e;
      e = e.parentElement;
    }
    return document.body;
  };
})();

/** The same spacing for a plain string (for text a script reveals bit by bit). */
export function spaceString(s) { return s.replace(PAIR, (m, a, b) => (a || b) + THIN); }

export function space(root) {
  if (!root || (root.closest && root.closest(SKIP))) return;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: n => (n.parentElement && n.parentElement.closest(SKIP) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
  });
  let prevBlock = null, prevChar = "";
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const s0 = n.data;
    if (!s0) continue;
    const block = blockOf(n.parentElement);
    if (block !== prevBlock) { prevBlock = block; prevChar = ""; }
    let s = s0.replace(PAIR, (m, a, b) => (a || b) + THIN);
    if (prevChar && need(prevChar, s[0])) s = THIN + s;
    if (s !== s0) n.data = s;
    prevChar = s[s.length - 1];
  }
}

/** Space the page now and whenever its text changes. */
export function watch() {
  document.documentElement.classList.add("autospaced");
  const run = els => {
    obs.disconnect();
    const blocks = new Set();
    els.forEach(el => { if (el && el.isConnected) blocks.add(blockOf(el)); });
    blocks.forEach(space);
    obs.takeRecords();
    obs.observe(document.body, { childList: true, characterData: true, subtree: true });
  };
  const obs = new MutationObserver(records => {
    run(records.map(r => (r.type === "characterData" ? r.target.parentElement : r.target)));
  });
  run([document.body]);
}
