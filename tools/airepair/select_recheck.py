"""Pick AI glyphs that break the newer rules, for a recheck round.

    .venv/bin/python tools/airepair/select_recheck.py OUT --exclude-rounds R1 R2 … [--ref-round R …]

Pool: regional glyphs (SC TC JP) in state `ai` that are their character's master (prepare.master_of)
and have a TUMBLED 18 glyph (the user ran only those at first; --all-chars: every character, and KR too),
minus the glyphs of the given rounds. Each is
checked in its latest version (the last --ref-round result if any, else the repository):
- L049: side-by-side components 2+ blank columns apart (common.wide_gaps);
- L038/L052: ink 11 columns or narrower where the region's Source Han Sans ink is at least 0.86 em
  wide (not the enclosed 囗 characters, which are 11 columns by rule);
- L053: ink not from row 0 to row 12 where the Source Han ink is at least 0.86 em tall.
Writes OUT (glyph ids) and OUT.json ({id: the issues, in words}). Changes nothing else.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, FONTS, tumbled, wide_gaps  # noqa: E402
from prepare import master_of, ref_results  # noqa: E402
from store import Store  # noqa: E402
import draft  # noqa: E402

_fonts = {}


def ink_em(char, region):
    """Source Han ink (width, height) in em, or None."""
    from fontTools.ttLib import TTFont
    from fontTools.pens.boundsPen import BoundsPen
    if region not in _fonts:
        f = TTFont(str(FONTS / f"SourceHanSans{region}-VF.otf"))
        _fonts[region] = (f, f.getBestCmap(), f.getGlyphSet(location={"wght": 400}))
    f, cmap, gs = _fonts[region]
    if ord(char) not in cmap:
        return None
    pen = BoundsPen(gs)
    gs[cmap[ord(char)]].draw(pen)
    if not pen.bounds:
        return None
    x0, y0, x1, y1 = pen.bounds
    return (x1 - x0) / 1000, (y1 - y0) / 1000


def pending(rnd):
    d = ROOT / "work/airepair" / rnd
    out = []
    for b in sorted((d / "batches").iterdir()):
        st = d / "state" / f"{b.name}.json"
        if not (st.exists() and json.loads(st.read_text()).get("status") == "submitted"):
            out += json.loads((b / "batch.json").read_text())["ids"]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", type=Path)
    ap.add_argument("--exclude-rounds", nargs="*", default=[])
    ap.add_argument("--ref-round", nargs="*", default=[])
    ap.add_argument("--all-chars", action="store_true", help="also the characters TUMBLED 18 lacks, and Korean (KR) masters")
    a = ap.parse_args()
    s = Store(ROOT)
    tum = tumbled()
    refs = ref_results(a.ref_round)
    skip = {g for r in a.exclude_rounds for g in pending(r)}
    issues, count = {}, Counter()
    for gid, r in s.records.items():
        regions = ("SC", "TC", "JP", "KR") if a.all_chars else ("SC", "TC", "JP")
        if r["group"] not in regions or "alias" in r or r["state"] != "ai" or gid in skip or (r["cp"] not in tum and not a.all_chars):
            continue
        if master_of(s, r["cp"]) != gid:
            continue
        rows = refs[gid]["rows"] if gid in refs else r["rows"]
        found = []
        for p, q, c in wide_gaps(r["char"], r["group"], rows):
            found.append(f"{p} 与 {q} 之间空了 {c} 列（L049：只空 0–1 列）")
        xs = [x for row in rows for x, v in enumerate(row) if v == "#"]
        ys = [y for y, row in enumerate(rows) if "#" in row]
        em = ink_em(r["char"], r["group"])
        if em and xs and ys:
            w = max(xs) - min(xs) + 1
            if w <= 11 and em[0] >= 0.86 and r["char"] not in draft.SQUARE:
                found.append(f"墨迹只有 {w} 列宽，思源的字面是宽的（L052：优先 13 列，至少 12 列）")
            if (min(ys) > 0 or max(ys) < 12) and em[1] >= 0.86:
                found.append(f"墨迹只占第 {min(ys)}–{max(ys)} 行（L053：用满第 0–12 行）")
        if found:
            issues[gid] = found
            for f in found:
                count[f.split("（")[1].split("：")[0]] += 1
    ids = sorted(issues, key=lambda g: (s.records[g]["cp"], g))
    a.out.write_text("\n".join(ids) + "\n")
    a.out.with_suffix(".json").write_text(json.dumps(issues, ensure_ascii=False, indent=1))
    print(len(ids), dict(count), Counter(g[-2:] for g in ids))


if __name__ == "__main__":
    main()
