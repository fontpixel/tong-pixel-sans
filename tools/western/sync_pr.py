"""Copy the half-width (.HW) western glyphs the user changed to their proportional (.PR) twins.

Rules (user decisions, 2026-09-27):
- A .PR glyph gets the .HW rows cropped to the ink plus one blank column on the right, same rows
  (so the same height and baseline).
- A .PR glyph the user edited directly is kept (unless listed with --force).
- Wide letters are proportional on purpose: W M m w Æ Œ æ œ and every glyph whose family base is one
  of them (Ŵ Ẃ ẃ Ǽ …) are never copied; their .PR versions are drawn separately. `--restore-wide`
  puts back the AI original for such .PR glyphs that currently hold a copy from .HW.
Changed glyphs are saved with state `derived` and a note; --dry-run only reports.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import open_store, items as load_items, ai_rows, by_script, changed as px_changed, save_derived

COPY = "按用户要求从等宽版"
WIDE_BASES = set("WMmwÆŒæœ")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", default="", help="characters whose .PR is overwritten even if you edited it")
    ap.add_argument("--restore-wide", action="store_true")
    ap.add_argument("--variants", default="", help="letters with diacritics to copy from .HW anyway")
    a = ap.parse_args()
    s = open_store()
    family = {gid: e["family"] for gid, e in load_items(s, groups=("HW",), scripts=("western", "kana", "thai", "arabic")).items()}

    def changed(gid):
        return px_changed(s, gid)

    def program(gid):
        return by_script(s, gid)

    def user_pr(pr):
        return changed(pr) and not program(pr)

    def variant(hw):
        f = family.get(hw, {})
        return bool(f.get("marks")) or f.get("base", s.original(hw)["char"]) != s.original(hw)["char"]

    def wide(hw):
        f = family.get(hw, {})
        return f.get("base") in WIDE_BASES or s.original(hw)["char"] in WIDE_BASES

    copied, kept, skipped_wide, restored = [], [], [], []
    for hw in sorted(g for g in s.glyphs if g.endswith(".HW") and g in family):
        pr = hw[:-3] + ".PR"
        if pr not in s.glyphs:
            continue
        ch = s.original(hw)["char"]
        if wide(hw):
            cur = s.current(pr)
            if a.restore_wide and cur.get("note", "").startswith(COPY) and not cur["approved"]:
                restored.append(ch)
                if not a.dry_run:
                    save_derived(s, pr, ai_rows(s, pr), "宽字母的比例版不照抄等宽版，恢复 AI 原稿的宽版本（待审核）")
            elif changed(hw):
                skipped_wide.append(ch)
            continue
        if not changed(hw):
            continue
        # Letters with diacritics are derived inside .PR from the .PR base (propagate_family --group PR);
        # --variants copies them from .HW instead (fallback for glyphs the propagation cannot do).
        # A variant you drew yourself in .HW (Ę, Ǿ, ç …) is still copied; derived ones are not.
        if variant(hw) and program(hw) and s.original(hw)["char"] not in a.variants:
            continue
        if user_pr(pr) and ch not in a.force:
            kept.append(ch); continue
        new = s.fitted_copy(hw, pr)
        cur = s.current(pr)
        if cur["rows"] == new:
            continue
        copied.append(ch)
        if not a.dry_run:
            save_derived(s, pr, new, f"{COPY} {hw} 复制（墨迹靠左，右留 1 像素字距；待审核）")
    print("copied", len(copied), "".join(copied))
    print("kept your .PR edits", len(kept), "".join(kept))
    print("wide, not copied", len(skipped_wide), "".join(skipped_wide))
    print("wide, restored to AI original", len(restored), "".join(restored))


if __name__ == "__main__":
    main()
