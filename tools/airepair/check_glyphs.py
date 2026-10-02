"""Find glyphs with mechanical errors, for a repair round. Changes nothing.

    .venv/bin/python tools/airepair/check_glyphs.py OUT [--groups SC TC JP KR …]

Checks every glyph with its own pixels in state ai, derived, edited or hangul-ai (not approved, not drafts,
not generated or composed ones) against the reference the editor overlays (the region's Source Han Sans
at the 13 × 13 ink box for regional glyphs):
- 断笔: more 8-connected pieces than the reference outline has (rendered at 104 px, so only the pieces the
  design really has count); on the approved glyphs this flags 3 %, on the AI glyphs 8 % (2026-10-02);
- 不对称: the reference outline is mirror-symmetric (draft.Face.symmetry ≥ 0.85) but the glyph differs from
  its mirror image (within its ink box) in more than 2 pixels;
- 离开基线 (western letters): no ink on the row just above the baseline for a letter that should stand on it.
(A 2×2 block check was dropped: a fifth of the approved glyphs have one, so it tells too little.)
Writes OUT (glyph ids) and OUT.json ({id: [issues, in words]}) for prepare.py --issues.
"""
from __future__ import annotations

import argparse
import json
import sys
import unicodedata as ud
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import FONTS, REGIONS, grey  # noqa: E402
from store import Store, baseline_row  # noqa: E402
import draft  # noqa: E402

STATES = ("ai", "derived", "edited", "hangul-ai")
WESTERN = ("HW", "PR", "HW-L", "PR-L")


def pieces(b):
    return draft.components(b)


_sym = {}


def symmetric(char, region):
    key = (char, region)
    if key not in _sym:
        try:
            f = draft._face(FONTS / f"SourceHanSans{region}-VF.otf", 13, 13, (400,), (0.2, 0, 0, 0.2, 0, 40))
            _sym[key] = f.symmetry(char) >= draft.SYMMETRIC
        except Exception:      # noqa: BLE001  (no reference: no symmetry check)
            _sym[key] = False
    return _sym[key]


_pieces = {}


def outline_pieces(char, region):
    key = (char, region)
    if key not in _pieces:
        try:
            _pieces[key] = pieces(grey(char, region, ppem=104) > 128)
        except Exception:      # noqa: BLE001  (no reference)
            _pieces[key] = 0
    return _pieces[key]


def check_regional(rec):
    np = draft._np()
    b = np.array([[v == "#" for v in r] for r in rec["rows"]], bool)
    if not b.any():
        return []
    out = []
    n, m = pieces(b), outline_pieces(rec["char"], rec["group"])
    if m and n > m:
        out.append(f"断笔：点阵有 {n} 个连通块，思源字形本身只有 {m} 个，可能有笔画断开（自动推断，请先确认）")
    if symmetric(rec["char"], rec["group"]):
        mm = draft.mirror_mismatch(b)
        if mm > 2:
            out.append(f"不对称：思源参考左右对称，点阵与其镜像有 {mm} 个像素不同（自动推断，请先确认）")
    return out


def check_western(rec):
    ch, rows = rec["char"], rec["rows"]
    cat = ud.category(ch)
    base = ud.normalize("NFD", ch)[0]
    if cat not in ("Lu", "Ll") or not base.isascii() or base in "gjpqyJQ":
        return []
    br = baseline_row(rec["group"])
    if any("#" in r for r in rows) and "#" not in rows[br - 1]:
        return [f"离开基线：字母主体没有坐在基线上（第 {br - 1} 行无墨）"]
    return []


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", type=Path)
    ap.add_argument("--groups", nargs="*", default=list(REGIONS) + list(WESTERN))
    a = ap.parse_args()
    s = Store(Path(__file__).resolve().parent.parent.parent)
    issues, count = {}, Counter()
    for gid, rec in sorted(s.records.items(), key=lambda kv: (kv[1]["group"], kv[1]["cp"])):
        if rec["group"] not in a.groups or "alias" in rec or rec["state"] not in STATES:
            continue
        found = check_regional(rec) if rec["group"] in REGIONS else check_western(rec)
        if found:
            issues[gid] = found
            for f in found:
                count[f.split("：")[0]] += 1
    a.out.write_text("\n".join(issues) + "\n")
    a.out.with_suffix(".json").write_text(json.dumps(issues, ensure_ascii=False, indent=1))
    print(len(issues), dict(count), Counter(g.rsplit(".", 1)[1] for g in issues))


if __name__ == "__main__":
    main()
