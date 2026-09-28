"""Build every proportional (.PR) letter with diacritics from the .PR base letter and the diacritics
of its half-width (.HW) twin, so the marks are identical in both widths while each width keeps
its own base (wide W M m w Æ Œ stay wide in .PR).

For a derived .PR glyph X (family base B, marks):
- split the current .HW X into the .HW base B (exact, or with the rows the .HW version squeezed
  out to make room for the marks) and the marks;
- take the current .PR B, squeeze out the same rows (counted from the top) if the .HW did;
- place each mark pixel at the same vertical offset from the base (above marks from the base top,
  below marks from the base bottom, others unchanged) and the same horizontal offset from the base
  centre as in .HW;
- crop to the ink and keep one blank column on the right (the proportional spacing rule).
A .PR glyph you drew or approved yourself is never touched, nor one whose .HW twin you drew yourself
(sync_pr.py copies those). Anything that cannot be split is listed for manual work.
Changed glyphs are saved with state `derived`; --dry-run only reports and draws the sheet.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import open_store, items as load_items, yours, save_derived, REPORTS
from propagate_family import pix, locate, compressed, drop_rows, shift, bbox, render, sheet

NOTE = "由比例版基字 {b} + 等宽版的变音符组成（程序连带更新，待审核）"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--include", default="", help="characters to rebuild even though you edited/approved them")
    a = ap.parse_args()
    s = open_store()
    items = load_items(s, groups=("PR",))
    pr_of = {e["char"]: g for g, e in items.items()}

    def mine(gid):
        return yours(s, gid)

    new_rows, manual, skipped = {}, [], []
    for gid, e in sorted(items.items()):
        f = e["family"]
        if not f["marks"] and f["base"] == e["char"]:
            continue
        hw = gid[:-3] + ".HW"
        base_pr = pr_of.get(f["base"])
        if hw not in s.glyphs or base_pr is None:
            continue
        if (mine(gid) or mine(hw)) and e["char"] not in a.include:
            skipped.append(e["char"]); continue
        base_hw = base_pr[:-3] + ".HW"
        hw_rows = s.current(hw)["rows"]; g = pix(hw_rows)
        b_hw = pix(s.current(base_hw)["rows"])
        off = locate(b_hw, g, 3); squeeze = set()
        if off is None:
            c = compressed(b_hw, g)
            if c is None:
                manual.append({"char": e["char"], "id": gid, "why": "等宽版里找不到基字"}); continue
            off, squeeze = c
            b_hw = drop_rows(b_hw, squeeze)
        placed = shift(b_hw, *off)
        marks = g - placed
        if not marks:
            manual.append({"char": e["char"], "id": gid, "why": "等宽版里没有变音符"}); continue
        t0, bt0, l0, r0 = bbox(placed)
        b_pr = pix(s.current(base_pr)["rows"])
        if squeeze:
            b_pr = drop_rows(b_pr, squeeze)
        t1, bt1, l1, r1 = bbox(b_pr)
        out = set(b_pr)
        for y, x in marks:
            dy = (t1 - t0) if y < t0 else (bt1 - bt0) if y > bt0 else 0
            # same horizontal offset from the base centre (half pixels rounded to the right, as in .HW)
            out.add((y + dy, x - (l0 + r0) / 2 + (l1 + r1) / 2))
        out = {(y, int(x + 0.5)) for y, x in out}
        h = len(hw_rows)
        if any(not 0 <= y < h for y, _ in out):
            manual.append({"char": e["char"], "id": gid, "why": "超出字格高度"}); continue
        x_min = min(x for _, x in out)
        out = {(y, x - x_min) for y, x in out}
        w = max(x for _, x in out) + 2
        new_rows[gid] = (render(out, w, h), NOTE.format(b=f["base"]))

    report = {"updated": [{"char": items[g]["char"], "id": g} for g in sorted(new_rows)], "manual": manual,
              "skipped_yours": skipped}
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "derive-PR.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    sheet(s, items, new_rows, REPORTS / "derive-PR.png", "PR")
    print(json.dumps({k: len(v) for k, v in report.items()}))
    if a.dry_run:
        return
    n = sum(save_derived(s, gid, rows, note) for gid, (rows, note) in sorted(new_rows.items()))
    print("saved", n)


if __name__ == "__main__":
    main()
