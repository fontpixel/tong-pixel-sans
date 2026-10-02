"""Find glyphs with mechanical errors, for a repair round. Changes nothing.

    .venv/bin/python tools/airepair/check_glyphs.py OUT [--groups SC TC JP KR …]

Checks every glyph with its own pixels in state ai, derived, edited or hangul-ai (not approved, not drafts,
not generated or composed ones) against the reference the editor overlays (the region's Source Han Sans
at the 13 × 13 ink box for regional glyphs):
- 断笔: more 8-connected pieces than the reference rendered at the same size (a stroke broken in two);
- 多余黑块: a solid 2×2 block where the reference is not solid (coverage under 0.6);
- 不对称: the reference outline is mirror-symmetric (draft.Face.symmetry ≥ 0.85) but the glyph differs from
  its mirror image (within its ink box) in more than 2 pixels;
- 离开基线 (western letters): no ink on the row just above the baseline for a letter that should stand on it.
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


def regional_reference(char, region):
    """Grey coverage (0–1) of the Source Han glyph scaled into a 13×13 box like the drafts (face 14)."""
    np = draft._np()
    a = grey(char, region, ppem=14).astype(float) / 255
    out = np.zeros((13, 13))
    h, w = min(a.shape[0], 13), min(a.shape[1], 13)
    y0, x0 = (13 - h) // 2, (13 - w) // 2
    out[y0:y0 + h, x0:x0 + w] = a[:h, :w]
    return out


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


def check_regional(rec):
    np = draft._np()
    rows = rec["rows"]
    b = np.array([[v == "#" for v in r] for r in rows], bool)
    if not b.any():
        return []
    out = []
    try:
        ref = regional_reference(rec["char"], rec["group"])
    except Exception:          # noqa: BLE001
        ref = None
    if ref is not None and ref.any():
        n, m = pieces(b), pieces(ref > 0.5)
        if n > m and n - m >= 1 and m > 0:
            out.append(f"断笔：点阵有 {n} 个连通块，思源参考只有 {m} 个，可能有笔画断开")
        blk = b[:-1, :-1] & b[1:, :-1] & b[:-1, 1:] & b[1:, 1:]
        cover = (ref[:-1, :-1] + ref[1:, :-1] + ref[:-1, 1:] + ref[1:, 1:]) / 4
        bad = int((blk & (cover < 0.6)).sum())
        if bad:
            ys, xs = np.nonzero(blk & (cover < 0.6))
            out.append(f"多余黑块：{bad} 处 2×2 实心黑块（如第 {ys[0]} 行第 {xs[0]} 列起），思源参考在那里不是实心")
    if symmetric(rec["char"], rec["group"]):
        mm = draft.mirror_mismatch(b)
        if mm > 2:
            out.append(f"不对称：思源参考左右对称，点阵与其镜像有 {mm} 个像素不同")
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
