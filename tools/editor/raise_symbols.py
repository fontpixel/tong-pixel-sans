"""Raise full-width symbols that sit lower than their Source Han position (dry run unless --apply).

    .venv/bin/python tools/editor/raise_symbols.py [--apply]

The full-width (regional) symbol, punctuation and number glyphs were drafted about one pixel lower
than Source Han places them relative to the Han characters (the editor's reference outline: em 14 px,
0.5 px right, baseline 11.8 px below the cell top). For each unapproved, unedited regional glyph of a
symbol, punctuation or number whose ink centre lies at least 0.75 px below the outline's, the rows move up
by that offset rounded (1 or 2 rows), when there is room above. Pixels keep their shape; the state
becomes `derived` (a program change). Approved and edited glyphs are listed, never changed.
"""
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from store import Store  # noqa: E402
from fontTools.ttLib import TTFont  # noqa: E402
from fontTools.pens.boundsPen import BoundsPen  # noqa: E402

BASE = 11.8


def main():
    s = Store(HERE.parent.parent)
    fonts, moved, listed = {}, [], []
    for gid, r in sorted(s.records.items()):
        if "alias" in r or r["group"] not in ("SC", "TC", "JP", "KR"):
            continue
        cp, ch = r["cp"], r["char"]
        if unicodedata.category(ch)[0] not in "PSN" or 0xAC00 <= cp <= 0xD7AF:
            continue
        if 0x2E80 <= cp <= 0x2FFF or 0x31C0 <= cp <= 0x31EF:      # radicals and strokes fill the box like Han
            continue
        g = r["group"]
        if g not in fonts:
            f = TTFont(str(HERE.parent.parent / f"reference-fonts/SourceHanSans{g}-VF.otf"))
            fonts[g] = (f.getBestCmap(), f.getGlyphSet(location={"wght": 400}), f["head"].unitsPerEm)
        cmap, gs, upem = fonts[g]
        if cp not in cmap:
            continue
        bp = BoundsPen(gs)
        gs[cmap[cp]].draw(bp)
        if not bp.bounds:
            continue
        y0, y1 = bp.bounds[1], bp.bounds[3]
        ys = [y for y, row in enumerate(r["rows"]) if "#" in row]
        if not ys:
            continue
        off = (min(ys) + max(ys) + 1) / 2 - (BASE - y1 * 14 / upem + BASE - y0 * 14 / upem) / 2
        k = round(off)
        if off < 0.75 or k < 1 or min(ys) - k < 0:
            continue
        if r["state"] in ("approved", "edited"):
            listed.append(f"{ch} {gid}（{r['state']}，低 {off:.1f} 像素）")
            continue
        rows = r["rows"][k:] + ["." * len(r["rows"][0])] * k
        moved.append((gid, ch, k, rows))
    print(f"上移 {len(moved)} 个；已通过或改过、只列出的 {len(listed)} 个")
    print("".join(ch for _, ch, _, _ in moved[:200]))
    print("；".join(listed[:80]))
    if "--apply" in sys.argv:
        for gid, ch, k, rows in moved:
            cur = s.current(gid)
            s.save({"id": gid, "expected_revision": cur["revision"], "rows": rows, "approved": False, "origin": "program",
                    "note": f"程序：整体上移 {k} 像素，与思源黑体中的位置对齐（tools/editor/raise_symbols.py）"})
        print("applied")


if __name__ == "__main__":
    main()
