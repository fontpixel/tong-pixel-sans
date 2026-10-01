"""Drafts for the Large size (PR-L, HW-L: 18-row cells, the baseline under row 13) in the T proportions
(docs/design-rules.md §5.1): capitals and digits 10 px, x-height 7, ascenders 10 (as high as the capitals),
descenders 3; nothing above row 0 or below row 17, but accents are not squeezed into the capital height.

    .venv/bin/python tools/editor/draft_large.py [--dry-run] [--only U+0041,U+00E9…] [--sheet PNG]

For every western glyph of the Small size in scope (letters, digits, punctuation, combining marks,
Latin-1 to Number Forms, Thai, Arabic, Hebrew, Georgian, Armenian, Lao; not arrows, mathematical
operators, geometric shapes, dingbats or East Asian half-width forms, which keep their Small glyph on the
same baseline) that has no Large glyph yet, a draft (state `draft`) is drawn from the reference font the
Small glyph was drawn from (tools/editor/data/reference-western.txt), except that the monospace Latin,
Greek and Cyrillic come from Source Code Pro:
- the outline is scaled as Source Han Sans scales Latin next to 13-px Han ink (em = 13 / 0.9229 px);
- for the Latin-like fonts its vertical zones are moved onto whole pixels piecewise-linearly: baseline
  0, x-height 7 (lowercase), capital height 10, ascender 10 (lowercase), descender −3; what lies above
  or below keeps its own size, squeezed only where it would leave the cell (rows 0–17); Armenian and
  Georgian use their own zones; Thai, Lao, Hebrew, Arabic and the symbol fonts are only scaled;
- then rendered as the Small drafts are (FreeType mono, 16 sub-pixel phases, tools/editor/draft.py);
  proportional glyphs get adv=auto (ink + 1 column) or stay zero-advance marks; monospace glyphs are
  narrowed until the ink fits 6 of the 7 columns.
A Small glyph that is an alias gets the same alias among the Large glyphs. Each draft's recipe goes to
its `# AI:` note and its reference outline to tools/editor/data/reference-western.txt.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import threading
import unicodedata as ud
from functools import lru_cache
from pathlib import Path

os.environ["FREETYPE_PROPERTIES"] = "cff:no-stem-darkening=1 autofitter:no-stem-darkening=1"
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]
import build  # noqa: E402
import draft  # noqa: E402

FONTS = HERE.parent.parent / "reference-fonts"
H, BASE = 18, 14                     # cell rows; first row below the baseline
TOP, BOTTOM = 14, 4                  # rows above / below the baseline the ink may use
SPEC = {"x": 7, "cap": 10, "asc": 10, "desc": 3}
PX_PER_EM = 13 / 0.9229              # Source Han Sans Han ink 13 px
SCOPE = [(0x0020, 0x218F), (0x0E00, 0x0EFF), (0xFB00, 0xFB4F), (0xFB50, 0xFDFF), (0xFE20, 0xFE2F), (0xFE70, 0xFEFF)]
EXCLUDE = [(0x2190, 0x2BFF), (0x3000, 0xFAFF), (0xFE10, 0xFE1F), (0xFE30, 0xFE6F), (0xFF00, 0xFFFF)]
# label (prefix, as in reference-western.txt) -> font file, variation location, zone source
FONTS_BY_LABEL = {"Source Code Pro": ("SourceCodePro-VF.otf", {"wght": 330}, "latin"),
                  "Source Sans 3": ("SourceSans3-VF.otf", {"wght": 320}, "latin"),
                  "Noto Sans Thai": ("NotoSansThai-VF.ttf", {"wght": 320, "wdth": 100}, None),
                  "Noto Sans Arabic": ("NotoSansArabic-VF.ttf", {"wght": 320, "wdth": 100}, None),
                  "Noto Sans Math": ("NotoSansMath-Regular.ttf", {}, None),
                  "Noto Sans Symbols 2": ("NotoSansSymbols2-Regular.ttf", {}, None),
                  "Noto Sans Symbols": ("NotoSansSymbols-Regular.ttf", {}, None),
                  "Noto Sans Hebrew": ("NotoSansHebrew-Regular.ttf", {}, None),
                  "Noto Sans Georgian": ("NotoSansGeorgian-Regular.ttf", {}, "georgian"),
                  "Noto Sans Armenian": ("NotoSansArmenian-Regular.ttf", {}, "armenian"),
                  "Noto Sans Lao": ("NotoSansLao-Regular.ttf", {}, None),
                  "Noto Sans": ("NotoSans-VF.ttf", {"wght": 320, "wdth": 100}, "latin"),
                  "思源 JP": ("SourceHanSansJP-VF.otf", {"wght": 320}, "latin")}
# characters whose top / bottom give the zones: (x-height, capital height, ascender, descender)
ZONE_CHARS = {"latin": ("x", "H", "d", "p"), "armenian": ("ս", "Ս", "լ", "ք"), "georgian": ("ო", None, "ბ", "ქ")}
_lock = threading.RLock()


def in_scope(cp):
    return any(a <= cp <= b for a, b in SCOPE) and not any(a <= cp <= b for a, b in EXCLUDE)


def lowercase(ch):
    cp = ord(ch)
    return ud.category(ch) in ("Ll", "Mn") or 0x10D0 <= cp <= 0x10FF


def font_key(label):
    return next((k for k in FONTS_BY_LABEL if label.startswith(k)), None)


# ---------------------------------------------------------------- zone-mapped outlines
def piecewise(knots):
    knots = sorted(knots)

    def f(y):
        if y <= knots[0][0]:
            return knots[0][1] + (y - knots[0][0]) * SLOPE[0]
        for (a, ta), (b, tb) in zip(knots, knots[1:]):
            if y <= b:
                return tb if b == a else ta + (tb - ta) * (y - a) / (b - a)
        return knots[-1][1] + (y - knots[-1][0]) * SLOPE[0]
    return f


SLOPE = [1.0]


class Source:
    """One reference font, instanced and subset: draws a character's outline with the vertical zones on
    whole pixels, in the units of a font whose em is 14 px tall (so it renders at an integer size)."""

    def __init__(self, key, chars):
        from fontTools import subset
        from fontTools.pens.boundsPen import BoundsPen
        from fontTools.ttLib import TTFont
        from fontTools.varLib import instancer
        name, loc, zones = FONTS_BY_LABEL[key]
        font = TTFont(str(FONTS / name))
        opt = subset.Options(); opt.layout_features = []; opt.notdef_outline = True; opt.name_IDs = ["*"]
        sub = subset.Subsetter(opt)
        extra = [c for z in ZONE_CHARS.get(zones, ()) if z for c in z]
        sub.populate(unicodes=sorted({ord(c) for c in chars + "".join(extra)}))
        sub.subset(font)
        if "fvar" in font:
            axes = {a.axisTag for a in font["fvar"].axes}
            font = instancer.instantiateVariableFont(font, {k: v for k, v in loc.items() if k in axes})
        self.key, self.font, self.zones = key, font, zones
        self.glyphs, self.cmap, self.upm = font.getGlyphSet(), font.getBestCmap(), font["head"].unitsPerEm
        self.label = key + (f" w{loc['wght']}" if "wght" in loc else "")
        self.z = {}
        if zones:
            xc, cc, ac, dc = ZONE_CHARS[zones]

            def bounds(c):
                p = BoundsPen(self.glyphs); self.glyphs[self.cmap[ord(c)]].draw(p); return p.bounds
            self.z = {"x": bounds(xc)[3], "asc": bounds(ac)[3], "desc": bounds(dc)[1]}
            self.z["cap"] = bounds(cc)[3] if cc else self.z["asc"]

    def px(self, v):
        """pixels -> units of the em-14 font"""
        return v * self.upm / 14

    def mapping(self, ch, lo, hi):
        """y (source units) -> y (units of the em-14 font)."""
        s = PX_PER_EM / 14                      # natural scale relative to the em-14 font
        SLOPE[0] = s
        if not self.z:
            knots = [(0, 0)]
            top_src, top_t = 0, 0
        else:
            z, u = self.z, self.px
            if lowercase(ch):
                knots = [(z["desc"], u(-SPEC["desc"])), (0, 0), (z["x"], u(SPEC["x"])), (z["asc"], u(SPEC["asc"]))]
            else:
                knots = [(z["desc"], u(-SPEC["desc"])), (0, 0), (z["cap"], u(SPEC["cap"]))]
        f = piecewise(knots)
        if hi > knots[-1][0] and f(hi) > self.px(TOP):        # squeeze what would leave the cell
            knots.append((hi, self.px(TOP)))
        if lo < knots[0][0] and f(lo) < self.px(-BOTTOM):
            knots.append((lo, self.px(-BOTTOM)))
        return piecewise(knots)

    def draw(self, ch, pen, x_scale):
        from fontTools.pens.boundsPen import BoundsPen
        from fontTools.pens.recordingPen import DecomposingRecordingPen
        name = self.cmap[ord(ch)]
        rec = DecomposingRecordingPen(self.glyphs); self.glyphs[name].draw(rec)
        bp = BoundsPen(None); rec.replay(bp)
        if bp.bounds is None:
            return False
        f = self.mapping(ch, bp.bounds[1], bp.bounds[3])
        for op, args in rec.value:
            pts = [None if p is None else (p[0] * x_scale, f(p[1])) for p in args] if op not in ("closePath", "endPath") else []
            getattr(pen, op)(*pts)
        return True

    def advance(self, ch):
        return self.font["hmtx"][self.cmap[ord(ch)]][0]


@lru_cache(maxsize=None)
def _source(key, chars):
    return Source(key, chars)


def mapped_font(key, chars, mono):
    """Path of a TrueType font with `chars` zone-mapped from the source font (em = 14 px; the proportional
    widths are scaled to the Source Han size, the monospace ones are scaled by the face width later)."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.cu2quPen import Cu2QuPen
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    src = _source(key, chars)
    x_scale = 1.0 if mono else PX_PER_EM / 14
    glyf, hmtx, cmap, order = {".notdef": TTGlyphPen(None).glyph()}, {".notdef": (src.upm // 2, 0)}, {}, [".notdef"]
    for ch in chars:
        if ord(ch) not in src.cmap:
            continue
        tt = TTGlyphPen(None)
        if not src.draw(ch, Cu2QuPen(tt, 1.0, reverse_direction=not src.font.has_key("glyf")), x_scale):
            continue
        name = f"u{ord(ch):04X}"
        glyf[name], hmtx[name], cmap[ord(ch)] = tt.glyph(), (round(src.advance(ch) * x_scale), 0), name
        order.append(name)
    fb = FontBuilder(src.upm, isTTF=True)
    fb.setupGlyphOrder(order); fb.setupCharacterMap(cmap); fb.setupGlyf(glyf); fb.setupHorizontalMetrics(hmtx)
    fb.setupHorizontalHeader(ascent=src.upm, descent=-src.upm // 2)
    fb.setupNameTable({"familyName": "TongLargeDraft", "styleName": "Regular"}); fb.setupOS2(); fb.setupPost()
    path = Path(tempfile.gettempdir()) / f"tong-large-{key.replace(' ', '')}-{'m' if mono else 'p'}-{abs(hash(chars)):x}.ttf"
    fb.save(str(path))
    return path, src.label


# ---------------------------------------------------------------- rendering
def place(r, cell_w, x):
    np = draft._np()
    ink, oy, ox = draft.crop(r["b"])
    h, w = ink.shape
    top = BASE - (r["top"] - oy)
    if top < 0 or top + h > H or x < 0 or x + w > cell_w:
        return None
    grid = np.zeros((H, cell_w), bool)
    grid[top:top + h, x:x + w] = ink
    return draft.rows_of(grid)


def half_width(path, ch, widest=13, max_ink=6, cell_w=7):
    for fw in range(widest, 3, -1):
        r = draft._face(path, fw, 14, (), (0.2, 0, 0, 0.2, 40, 60)).best(ch)
        if r is None:
            return None
        ink, _, _ = draft.crop(r["b"])
        if ink.shape[1] <= max_ink or fw == 4:
            rows = place(r, cell_w, max((cell_w - ink.shape[1]) // 2, 0))
            return rows and {"rows": rows, "metrics": ["adv=7"], "face": fw, "k": r["k"]}
    return None


def proportional(path, ch, zero_advance):
    r = draft._face(path, 14, 14, (), (0.2, 0, 0, 0.2, 40, 60)).best(ch)
    if r is None:
        return None
    ink, oy, ox = draft.crop(r["b"])
    if zero_advance:
        rows = place(r, ink.shape[1], 0)
        return rows and {"rows": rows, "metrics": ["adv=0", f"x={r['left'] + ox}"], "face": 14, "k": r["k"], "left": r["left"] + ox}
    rows = place(r, ink.shape[1], 0)
    return rows and {"rows": rows, "metrics": ["adv=auto"], "face": 14, "k": r["k"], "left": 0}


# ---------------------------------------------------------------- the plan
def plan(store, only=None):
    """[(large id, small record, font key)] to draw, and [(large id, alias target)] to alias."""
    labels = {}
    for line in (HERE / "data/reference-western.txt").read_text(encoding="utf-8").splitlines():
        if line.startswith("U+"):
            gid, label = line.split("\t")[:2]
            labels[gid] = label
    todo, aliases = [], []
    for gid, rec in sorted(store.records.items(), key=lambda kv: (kv[1]["cp"], kv[1]["group"])):
        group, cp = rec["group"], rec["cp"]
        if group not in ("HW", "PR") or not in_scope(cp) or (only and cp not in only):
            continue
        big = f"U+{cp:04X}.{group}-L"
        if big in store.records:
            continue
        if "alias" in rec:
            t = rec["alias"]
            tcp, tgroup = int(t[2:].split(".")[0], 16), t.split(".")[1]
            if tgroup in ("HW", "PR") and in_scope(tcp):
                aliases.append((big, f"U+{tcp:04X}.{tgroup}-L"))
            continue
        key = font_key(labels.get(gid, ""))
        if key is None:
            continue
        if group == "HW" and key in ("Source Sans 3", "Noto Sans") and cp in _scp_cmap():
            key = "Source Code Pro"             # monospace Latin, Greek, Cyrillic and punctuation
        todo.append((big, rec, key))
    return todo, aliases


@lru_cache(maxsize=1)
def _scp_cmap():
    from fontTools.ttLib import TTFont
    return set(TTFont(str(FONTS / FONTS_BY_LABEL["Source Code Pro"][0])).getBestCmap())


def draw_all(todo):
    """{large id: draft} for the planned glyphs, grouped by font and kind so each font is built once."""
    by = {}
    for big, rec, key in todo:
        by.setdefault((key, big.endswith(".HW-L")), []).append((big, rec))
    out, failed = {}, []
    for (key, mono), items in sorted(by.items()):
        chars = "".join(sorted({chr(rec["cp"]) for _, rec in items}))
        path, label = mapped_font(key, chars, mono)
        for big, rec in items:
            ch = chr(rec["cp"])
            meta = dict(t.split("=", 1) for t in rec["metrics"])
            try:
                r = half_width(path, ch, 12 if key == "Source Code Pro" else 13) if mono else \
                    proportional(path, ch, meta.get("adv") == "0")
            except Exception as e:                      # noqa: BLE001  (report, keep going)
                r, err = None, str(e)
            if not r:
                failed.append(big); continue
            r["label"] = label
            out[big] = r
        print(f"{key} {'等宽' if mono else '比例'}: {len(items)}", flush=True)
    return out, failed


def single(gid, char, label):
    """The draft of one Large glyph, for the editor's “相位底稿”."""
    key = font_key(label)
    if key is None:
        raise ValueError("没有这个字的参考字体记录")
    mono = gid.endswith(".HW-L")
    path, lab = mapped_font(key, char, mono)
    r = half_width(path, char, 12 if key == "Source Code Pro" else 13) if mono else \
        proportional(path, char, ud.category(char) == "Mn")
    if not r:
        raise ValueError("无法生成底稿（放不进 18 行字格）")
    return {**r, "label": lab}


def note(r):
    return (f"大号版底稿（T 规格：大写 10、x 高 7、升部 10、降部 3）：{r['label']}，按思源比例（汉字墨迹 13 px）"
            f"缩放并把各区高度对齐到整像素，面宽 {r['face']}，相位 {r['k']}/16（tools/editor/draft_large.py）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", help="code points, e.g. U+0041,U+00E9")
    a = ap.parse_args()
    from store import Store
    s = Store(HERE.parent.parent)
    only = {int(c.strip()[2:], 16) for c in a.only.split(",")} if a.only else None
    todo, aliases = plan(s, only)
    print(f"to draw: {len(todo)}, aliases: {len(aliases)}", flush=True)
    drafts, failed = draw_all(todo)
    print(f"drawn {len(drafts)}, failed {len(failed)}: {' '.join(failed[:40])}")
    if a.dry_run:
        return drafts
    new = [{"group": big.split(".")[1], "cp": int(big[2:].split(".")[0], 16), "rows": r["rows"], "state": "draft",
            "metrics": r["metrics"], "ai_note": note(r)} for big, r in drafts.items()]
    targets = set(drafts) | {b for b in s.records if b.endswith("-L")}
    new += [{"group": big.split(".")[1], "cp": int(big[2:].split(".")[0], 16), "alias": t}
            for big, t in aliases if t in targets]
    s.add_glyphs(new)
    with open(HERE / "data/reference-western.txt", "a", encoding="utf-8") as fh:
        for big, r in drafts.items():
            fh.write(f"{big}\t{r['label']} T\t{r['face']}\t14\t{_left(r['rows'])}\n")
    print(f"added {len(new)}")
    return drafts


def _left(rows):
    return min(x for r in rows for x, v in enumerate(r) if v == "#")


if __name__ == "__main__":
    main()
