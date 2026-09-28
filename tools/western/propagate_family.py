"""Propagate the user's edited base letters and diacritics to every derived western glyph.

For one width group (.HW or .PR) of ext-v5:

1. Base letters. For every letter the user edited (human revision after the AI result), each
   other glyph of the same group whose family base is that letter (À Á Â … for A) is updated:
   the AI base pixels (the base letter's AI result) are located in the glyph (exact subset, small
   offset allowed) and replaced by the user's version at the same place. Diacritics move with the
   base: marks above follow the base's top edge, marks below its bottom edge, both its centre.
2. Diacritics. For every mark shape the user changed on a letter (e.g. the cedilla of Ç), glyphs
   of the same case with that mark whose AI mark was drawn exactly like the AI mark of the source
   letter get the user's mark, placed relative to the base as in the source letter.

Glyphs the user edited or approved are never touched. A glyph whose base cannot be located, or
whose result would leave the cell or let a mark touch the base, is reported for manual work.
Changed glyphs are saved with state `derived` and a note; review them in the editor or with git diff.
--dry-run writes nothing but the report and before/after sheet (reports/propagate-<group>.*).
"""
from __future__ import annotations

import argparse
import json
import unicodedata
from pathlib import Path

from common import open_store, items as load_items, ai_rows, by_script, yours, changed, save_derived, REPORTS, FONT

ABOVE_LIMIT = 0  # marks are pixels outside the base; classified by position relative to it


def pix(rows):
    return {(y, x) for y, r in enumerate(rows) for x, v in enumerate(r) if v == "#"}


def render(points, w, h):
    return ["".join("#" if (y, x) in points else "." for x in range(w)) for y in range(h)]


def locate(base, glyph, reach=3):
    """Offset (dy, dx) placing `base` exactly inside `glyph` (both pixel sets), nearest first."""
    if not base:
        return None
    for d in range(reach + 1):
        for dy in range(-d, d + 1):
            for dx in range(-d, d + 1):
                if max(abs(dy), abs(dx)) != d:
                    continue
                if {(y + dy, x + dx) for y, x in base} <= glyph:
                    return dy, dx
    return None


def drop_rows(points, rel_rows):
    """Remove the given rows (relative to the top of `points`) and close the gaps upward-down:
    rows above a removed row move down, so the bottom (baseline) stays where it is."""
    top = min(y for y, _ in points)
    out = set()
    for y, x in points:
        r = y - top
        if r in rel_rows:
            continue
        out.add((y + sum(1 for k in rel_rows if k > r), x))
    return out


def compressed(b0, glyph):
    """(offset, removed rows) if the AI base appears in `glyph` with one or two rows removed."""
    top, bottom = min(y for y, _ in b0), max(y for y, _ in b0)
    n = bottom - top + 1
    for k in (1, 2):
        from itertools import combinations
        for rel in combinations(range(1, n - 1), k):  # never the top or bottom row
            cand = drop_rows(b0, set(rel))
            off = locate(cand, glyph)
            if off is not None:
                return off, set(rel)
    return None


def shift(points, dy, dx):
    return {(y + dy, x + dx) for y, x in points}


def bbox(points):
    ys = [y for y, _ in points]; xs = [x for _, x in points]
    return min(ys), max(ys), min(xs), max(xs)


def touches(a, b):
    return any((y + dy, x + dx) in b for y, x in a for dy in (-1, 0, 1) for dx in (-1, 0, 1))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--group", choices=["HW", "PR"], required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--include", default="", help="characters to rebuild even though you edited/approved them")
    a = ap.parse_args()
    store = open_store()
    items = load_items(store, groups=(a.group,), scripts=("western", "kana", "thai", "arabic"))

    def user_edited(gid):
        return changed(store, gid) and not generated(gid)

    def hw_user(gid):
        """.PR only: the .HW twin is your own drawing (then .PR follows it through sync_pr.py)."""
        if a.group != "PR":
            return False
        twin = gid[:-3] + ".HW"
        if twin not in store.glyphs:
            return False
        return changed(store, twin) and not generated(twin)

    def plain(gid):
        f = items[gid]["family"]
        return not f["marks"] and f["base"] == items[gid]["char"]

    MARK = "（程序连带更新，待审核）"

    def generated(gid):
        """Current version was written by a script (never approved): recompute it from the AI result."""
        return by_script(store, gid)

    def touched(gid):
        return yours(store, gid) or (not plain(gid) and hw_user(gid))

    def start(gid):
        return ai_rows(store, gid) if generated(gid) else store.current(gid)["rows"]

    by_char = {e["char"]: gid for gid, e in items.items()}
    edited = {gid for gid in items if user_edited(gid) or (not plain(gid) and hw_user(gid))}
    # Base letters: any changed plain letter is a source, including a .PR base copied from .HW.
    # Every plain letter is a base: an unchanged base (e.g. edited back to the AI shape) still
    # rebuilds variants that hold an older derived version.
    bases = {gid for gid in items if plain(gid)}
    report = {"group": a.group, "edited_sources": sorted(items[g]["char"] for g in edited), "updated": [], "manual": [],
              "skipped_user_glyphs": []}
    new_rows = {}

    # 1. base letters
    for gid, e in sorted(items.items()):
        f = e["family"]
        base_gid = by_char.get(f["base"])
        if not f["marks"] and f["base"] == e["char"]:
            continue
        if base_gid is None or base_gid not in bases or gid == base_gid:
            continue
        if touched(gid) and e["char"] not in a.include:
            report["skipped_user_glyphs"].append(e["char"]); continue
        cur = ai_rows(store, gid) if e["char"] in a.include else start(gid); w, h = len(cur[0]), len(cur)
        g = pix(cur)
        b0 = pix(ai_rows(store, base_gid)); b1 = pix(store.current(base_gid)["rows"])
        off = locate(b0, g)
        squeeze = None
        if off is None:
            found = compressed(b0, g)
            if found is None:
                if b0 == b1:   # base unchanged: nothing to replace; drop an outdated derived version
                    if generated(gid) and store.current(gid)["rows"] != cur:
                        new_rows[gid] = (cur, f"恢复 AI 原稿（基字 {f['base']} 与 AI 原稿相同）")
                    continue
                report["manual"].append({"char": e["char"], "id": gid, "why": "AI 基字不在此字中（形状已被改变）"}); continue
            off, squeeze = found
            b0 = drop_rows(b0, squeeze)
            # the same rows (counted from the top) are removed from the user's base
            b1 = drop_rows(b1, squeeze)
        placed0 = shift(b0, *off)
        marks = g - placed0
        t0, bt0, l0, r0 = bbox(placed0)
        placed1 = shift(b1, *off)
        t1, bt1, l1, r1 = bbox(placed1)
        dcx = round(((l1 + r1) - (l0 + r0)) / 2)
        moved = set()
        for y, x in marks:
            dy = (t1 - t0) if y < t0 else (bt1 - bt0) if y > bt0 else 0
            moved.add((y + dy, x + dcx))
        out = placed1 | moved
        if any(not (0 <= y < h and 0 <= x < w) for y, x in out):
            # keep the marks where they were (horizontal centring only) if they still clear the base
            moved = {(y, x + dcx) for y, x in marks}
            out = placed1 | moved
            if any(not (0 <= y < h and 0 <= x < w) for y, x in out) or touches(moved, placed1):
                report["manual"].append({"char": e["char"], "id": gid, "why": "换基字后超出字格"}); continue
        if moved and touches(moved, placed1) and not touches(marks, placed0):
            report["manual"].append({"char": e["char"], "id": gid, "why": "换基字后变音符与基字相连"}); continue
        new_rows[gid] = (render(out, w, h), f"随基字 {f['base']} 的人工修改更新" + ("（按 AI 原稿同样压缩 1 行）" if squeeze and len(squeeze) == 1 else "（按 AI 原稿同样压缩 2 行）" if squeeze else ""))

    # 2. diacritics changed on an edited letter with marks (e.g. the cedilla of Ç)
    def split(gid, rows_now):
        """(base pixels, mark pixels) of a glyph, using its base letter's current and AI rows."""
        f = items[gid]["family"]; bg = by_char.get(f["base"])
        if bg is None:
            return None
        g = pix(rows_now)
        for cand in (store.current(bg)["rows"], ai_rows(store, bg)):
            off = locate(pix(cand), g)
            if off is not None:
                bp = shift(pix(cand), *off)
                return bp, g - bp
        return None

    mark_sources, conflicts = {}, {}
    for gid in edited:
        f = items[gid]["family"]
        if not f["marks"] or len(f["marks"]) != 1:
            continue
        if f["base"] in "ÆæŒœ":   # marks on ligatures are fitted to them; never a source for other letters
            continue
        new = split(gid, store.current(gid)["rows"]); old = split(gid, ai_rows(store, gid))
        if not new or not old or not new[1] or not old[1]:
            continue
        bn, mn = new; bo, mo = old
        if mn == mo:
            continue
        case = "upper" if items[gid]["char"].isupper() else "lower"
        script = "greek" if "GREEK" in unicodedata.name(items[gid]["char"], "") else "latin"
        # mark relative to the base: below marks to the bottom edge, above marks to the top edge; centred
        def rel(bp, mp):
            t, bt, l, r = bbox(bp); below = min(y for y, _ in mp) > bt
            ref_y = bt if below else t; cx2 = l + r
            return below, {(y - ref_y, 2 * x - cx2) for y, x in mp}
        below, new_rel = rel(bn, mn); _, old_rel = rel(bo, mo)
        key = (f["marks"][0], case, script)
        src = {"char": items[gid]["char"], "below": below, "new": new_rel, "old": old_rel}
        if key in mark_sources and mark_sources[key] is not None and mark_sources[key]["new"] != new_rel:
            conflicts.setdefault(key, {mark_sources[key]["char"]}).add(src["char"])
            mark_sources[key] = None     # drawn differently on two letters: do not guess
        elif key not in mark_sources:
            mark_sources[key] = src
        elif mark_sources[key] is None:
            conflicts[key].add(src["char"])
    report["mark_conflicts"] = {f"{m} ({c}, {sc})": "".join(sorted(v)) for (m, c, sc), v in conflicts.items()}
    mark_sources = {k: v for k, v in mark_sources.items() if v is not None}
    report["edited_marks"] = {f"{m} ({c}, {sc})": s["char"] for (m, c, sc), s in mark_sources.items()}
    for gid, e in sorted(items.items()):
        f = e["family"]
        case = "upper" if e["char"].isupper() else "lower"
        script = "greek" if "GREEK" in unicodedata.name(e["char"], "") else "latin"
        hit = [(m, mark_sources[(m, case, script)]) for m in f["marks"] if (m, case, script) in mark_sources]
        if not hit or (gid in edited or touched(gid)) and e["char"] not in a.include or any(s["char"] == e["char"] for _, s in hit):
            continue
        rows_now = new_rows.get(gid, (start(gid), ""))[0]
        sp = split(gid, rows_now)
        if sp is None:
            report["manual"].append({"char": e["char"], "id": gid, "why": "找不到基字，无法替换变音符"}); continue
        bp, mp = sp
        t, bt, l, r = bbox(bp); cx2 = l + r
        w, h = len(rows_now[0]), len(rows_now)
        out = set(bp) | set(mp); note_marks = []
        for m, s in hit:
            part = {(y, x) for y, x in mp if (y > bt) == s["below"]}
            ref_y = bt if s["below"] else t
            rel_now = {(y - ref_y, 2 * x - cx2) for y, x in part}
            # A true cedilla (Ç Ş Ţ Ȩ …) always takes the new shape; the Latvian comma-style
            # cedillas of G K L N R keep theirs unless drawn exactly like the source's old mark.
            # One-mark Latin/Cyrillic letters always take your new mark (the Latvian comma-style
            # cedillas of G K L N R and Greek tonos excepted); stacked marks only when they match.
            always = len(f["marks"]) == 1 and "GREEK" not in unicodedata.name(e["char"], "") \
                and not (m == "CEDILLA" and f["base"].upper() in "GKLNR")
            if rel_now != s["old"] and not always:
                report["manual"].append({"char": e["char"], "id": gid, "why": f"{m} 的原写法与 {s['char']} 不同，未自动替换"}); continue
            new_part = {(ref_y + dy, (cx2 + dx2) // 2) for dy, dx2 in s["new"]}
            out = (out - part) | new_part; note_marks.append(f"{m}（取自 {s['char']}）")
        if not note_marks:
            continue
        if any(not (0 <= y < h and 0 <= x < w) for y, x in out):
            report["manual"].append({"char": e["char"], "id": gid, "why": "换变音符后超出字格"}); continue
        prev = new_rows.get(gid, (None, ""))[1]
        new_rows[gid] = (render(out, w, h), "；".join(filter(None, [prev, "变音符随人工修改更新：" + "、".join(note_marks)])))

    report["updated"] = [{"char": items[g]["char"], "id": g, "note": n} for g, (_, n) in sorted(new_rows.items())]
    out_dir = REPORTS; out_dir.mkdir(exist_ok=True)
    (out_dir / f"propagate-{a.group}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    sheet(store, items, new_rows, out_dir / f"propagate-{a.group}.png", a.group)
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in report.items()}, ensure_ascii=False))
    if a.dry_run:
        return
    saved = sum(save_derived(store, gid, rows, note + MARK) for gid, (rows, note) in sorted(new_rows.items()))
    print("saved", saved)


def sheet(store, items, new_rows, path, group):
    from PIL import Image, ImageDraw, ImageFont
    S, cols = 4, 12
    ids = sorted(new_rows)
    cw = max((len(store.current(g)["rows"][0]) for g in ids), default=7) * S * 2 + 30
    ch = 14 * S + 26
    im = Image.new("RGB", (cols * cw + 20, 50 + max(1, -(-len(ids) // cols)) * ch), "white")
    d = ImageDraw.Draw(im)
    font = ImageFont.truetype(str(FONT), 14)
    d.text((10, 10), f"{group}：连带更新 {len(ids)} 字 · 每格左 = 现在，右 = 更新后", font=font, fill="black")
    for i, gid in enumerate(ids):
        x0, y0 = 10 + (i % cols) * cw, 40 + (i // cols) * ch
        d.text((x0, y0), items[gid]["char"], font=font, fill="black")
        for k, rows in enumerate([store.current(gid)["rows"], new_rows[gid][0]]):
            xx = x0 + 16 + k * (len(rows[0]) * S + 6)
            d.rectangle((xx - 1, y0 - 1, xx + len(rows[0]) * S, y0 + 14 * S), outline="#dde")
            d.line((xx, y0 + 11 * S, xx + len(rows[0]) * S - 1, y0 + 11 * S), fill="#f3b0b0")
            for y, r in enumerate(rows):
                for x, v in enumerate(r):
                    if v == "#":
                        d.rectangle((xx + x * S, y0 + y * S, xx + (x + 1) * S - 1, y0 + (y + 1) * S - 1), fill="black")
    im.save(path)


if __name__ == "__main__":
    main()
