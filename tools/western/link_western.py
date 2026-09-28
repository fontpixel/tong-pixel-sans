"""Link Latin, Greek and Cyrillic letters to movable forms: base letters and diacritics.

- Base forms: every plain letter of .HW and of .PR gets a form cropped from its current bitmap
  (“A · 等宽”, “A · 比例”). A Greek/Cyrillic letter drawn exactly like a Latin one shares that form.
- Variants (À Ǻ ấ ё …): the base form is looked up anywhere in the glyph (exact); if the capital was
  squeezed to make room for an accent, a “压扁” form (the base with the same row(s) removed) is used.
- Diacritics: one form per mark, case and script (Latin/Cyrillic vs Greek), shared by .HW and .PR.
  Its standard shape is the one you drew (all your letters with that mark must agree), else the most
  common one.
- A link is made only when the glyph's pixels at that place are exactly the form: linking never
  changes a pixel. Re-running is safe: forms are reused by name and pixels, slots already linked are kept.
Everything else is reported (reports/link-western.md, .json, .png at the repository root): letters you
  drew differently, letters the AI drew differently, homoglyphs that differ, conflicting marks.
--dry-run writes only the reports.
"""
from __future__ import annotations

import argparse
import sys
import json
import unicodedata
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

from common import open_store, items as load_items, drawn_by as who_drew, REPORTS, FONT, HERE

GROUPS = {"HW": "等宽", "PR": "比例"}
sys.path.insert(0, str(HERE.parent / 'editor'))
from western import SPACING, MARK_ZH, HOMOGLYPHS, marks_of



def pix(rows):
    return {(y, x) for y, r in enumerate(rows) for x, v in enumerate(r) if v == "#"}


def crop(points):
    """(form rows, top-left x, top-left y) of a pixel set."""
    ys = [y for y, _ in points]; xs = [x for _, x in points]
    y0, x0 = min(ys), min(xs)
    h, w = max(ys) - y0 + 1, max(xs) - x0 + 1
    rows = ["".join("#" if (y + y0, x + x0) in points else "." for x in range(w)) for y in range(h)]
    return tuple(rows), x0, y0


def form_pix(rows):
    return pix(rows)


def positions(form, ink, w, h, prefer=None):
    """All (x, y) where the form's ink lies exactly within `ink`; nearest to `prefer` first."""
    fp = form_pix(form)
    fh, fw = len(form), len(form[0])
    out = []
    for y0 in range(0, h - fh + 1):
        for x0 in range(0, w - fw + 1):
            if all((y + y0, x + x0) in ink for y, x in fp):
                out.append((x0, y0))
    if prefer:
        out.sort(key=lambda p: abs(p[0] - prefer[0]) + abs(p[1] - prefer[1]))
    return out


def drop_rows(form, rel):
    return tuple(r for i, r in enumerate(form) if i not in rel)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    s = open_store()
    items = load_items(s)

    def drawn_by(gid):
        return who_drew(s, gid)

    def letter(ch):
        return unicodedata.category(ch)[0] == "L"

    def script(ch):
        return "希腊" if "GREEK" in unicodedata.name(ch, "") else "拉丁/西里尔"

    forms, plan = {}, defaultdict(list)
    switch = []   # homoglyphs to move from their own form to the identical Latin one
    report = {"forms": [], "manual": [], "linked": defaultdict(list)}
    base_form = {}      # (group, char) -> (form key, rows, x, y) where the plain letter sits
    samples = defaultdict(list)   # (mark, case, script) -> [(pattern, drawer, gid, x, y)]
    pending = []                  # variants with located base: (gid, group, remaining pixels, marks)

    for g, zh in GROUPS.items():
        gi = {gid: e for gid, e in items.items() if gid.endswith("." + g)}
        by_char = {e["char"]: gid for gid, e in gi.items()}
        plain = {gid for gid, e in gi.items() if letter(e["char"]) and not e["family"]["marks"]
                 and e["family"]["base"] == e["char"]}
        # 1. base letters, Latin first so homoglyphs can share their forms
        order = sorted(plain, key=lambda gid: (gi[gid]["char"] in HOMOGLYPHS, gid))
        for gid in order:
            ch = gi[gid]["char"]
            cur = s.current(gid)
            ink = pix(cur["rows"])
            if not ink:
                continue
            rows, x, y = crop(ink)
            lat = HOMOGLYPHS.get(ch)
            if lat and (g, lat) in base_form and base_form[(g, lat)][1] == rows:
                key = base_form[(g, lat)][0]
                # drawn exactly like the Latin letter now but still on its own form: share the Latin one
                lib = s._library()
                own = [l for l in cur.get("links", []) if l["slot"] == "mv:base"
                       and lib["shapes"].get(l["shape_id"], {}).get("name") != forms[key]["name"]]
                if own:
                    switch.append(gid)
            else:
                if lat and (g, lat) in base_form:
                    report["manual"].append({"char": ch, "id": gid, "group": zh, "kind": "同形字母",
                                             "why": f"和拉丁 {lat} 长得不一样（{drawn_by(gid)}画的），未共用 {lat} 的形态",
                                             "drawer": drawn_by(gid)})
                key = f"base:{g}:{ch}"
                forms[key] = {"symbol": ch, "locale": g, "name": f"{ch} · {zh}", "rows": list(rows)}
            base_form[(g, ch)] = (key, rows, x, y)
            plan[gid].append({"form": key, "slot": "mv:base", "symbol": ch, "x": x, "y": y})
            report["linked"]["基本字母"].append(ch + ("" if g == "HW" else "·比例"))
        # 2. variants: find the base
        for gid, e in sorted(gi.items()):
            ch, f = e["char"], e["family"]
            if gid in plain or not letter(ch) or not f["name"].startswith(("latin-", "greek-", "cyrillic-")):
                continue
            cur = s.current(gid)
            src = base_form.get((g, f["base"]))
            if src is None:
                report["manual"].append({"char": ch, "id": gid, "group": zh, "kind": "基字",
                                         "why": f"没有基本字母 {f['base']} 的形态", "drawer": drawn_by(gid)}); continue
            key, brows, bx, by = src
            rows = cur["rows"]; w, h = len(rows[0]), len(rows)
            ink = pix(rows)
            found = positions(brows, ink, w, h, prefer=(bx, by))
            used_key, used_rows = key, brows
            if not found:
                for k in (1, 2):
                    for rel in combinations(range(1, len(brows) - 1), k):
                        cand = drop_rows(brows, set(rel))
                        found = positions(cand, ink, w, h, prefer=(bx, by + k))
                        if found:
                            used_rows = cand
                            used_key = f"squeeze:{g}:{f['base']}:{'-'.join(map(str, rel))}"
                            if used_key not in forms:
                                rn = "、".join(str(r + 1) for r in rel)
                                forms[used_key] = {"symbol": f["base"], "locale": g, "rows": list(cand),
                                                   "name": f"{f['base']} · {zh} · 压扁（去掉第 {rn} 行）"}
                            break
                    if found:
                        break
            if not found:
                report["manual"].append({"char": ch, "id": gid, "group": zh, "kind": "基字",
                                         "why": f"里面的 {f['base']} 和标准写法不一样（{drawn_by(gid)}画的）",
                                         "drawer": drawn_by(gid)}); continue
            x0, y0 = found[0]
            placed = {(y + y0, x + x0) for y, x in form_pix(used_rows)}
            plan[gid].append({"form": used_key, "slot": "mv:base", "symbol": f["base"], "x": x0, "y": y0})
            rest = ink - placed
            if any(m not in SPACING for m in marks_of(f)):
                # hook, bar, stroke, tail…: part of the letter, drawn per letter; only the base is shared
                report["linked"]["只关联基字（钩、横、斜线等属于字母本身）"].append(ch + ("" if g == "HW" else "·比例"))
                continue
            if f["marks"] and rest:
                pending.append((gid, g, rest, placed))
                if len(f["marks"]) == 1:
                    pat = crop(rest)
                    case = "大写" if ch.isupper() else "小写"
                    samples[(marks_of(f)[0], case, script(ch))].append((pat[0], drawn_by(gid), gid, pat[1], pat[2]))
            elif f["marks"]:
                report["manual"].append({"char": ch, "id": gid, "group": zh, "kind": "变音符",
                                         "why": "找不到变音符（可能与基字重叠）", "drawer": drawn_by(gid)})
    # 3. the standard shape of each mark
    standard, conflicts = {}, {}
    for k, lst in samples.items():
        # The most common shape is the standard (your changed marks were already propagated, so
        # they are the majority); a tie is a conflict for you to decide.
        counts = Counter(p for p, *_ in lst)
        top = counts.most_common(2)
        if len(top) > 1 and top[0][1] == top[1][1]:
            conflicts[k] = sorted({items[gid]["char"] for *_, gid, _, _ in lst})
            continue
        standard[k] = top[0][0]
    for (mark, case, sc), rows in standard.items():
        key = f"mark:{mark}:{case}:{sc}"
        sym = SPACING.get(mark, mark)
        forms[key] = {"symbol": sym, "locale": "WEST", "rows": list(rows),
                      "name": f"{sym} {MARK_ZH.get(mark, mark)} · {case} · {sc}"}
    # 4. link marks where the glyph has exactly the standard shapes
    for gid, g, rest, placed in pending:
        e = items[gid]; ch, f = e["char"], e["family"]
        case = "大写" if ch.isupper() else "小写"; sc = script(ch)
        rows = s.current(gid)["rows"]; w, h = len(rows[0]), len(rows)
        marks = marks_of(f); why = None; links = []
        for m in marks:
            k = (m, case, sc)
            if k in conflicts:
                why = f"{MARK_ZH.get(m, m)}有两种写法一样多（{''.join(conflicts[k])}），不知以哪个为准"; break
            if k not in standard:
                why = f"没有{MARK_ZH.get(m, m)}的标准写法"; break
        if why is None:
            # every mark on exactly its own pixels, together exactly the pixels outside the base
            def place(i, left):
                if i == len(marks):
                    return [] if not left else None
                std = standard[(marks[i], case, sc)]
                for x0, y0 in positions(std, left, w, h):
                    got = place(i + 1, left - {(y + y0, x + x0) for y, x in form_pix(std)})
                    if got is not None:
                        return [(x0, y0)] + got
                return None
            spots = place(0, set(rest))
            if spots is None:
                why = ("变音符和标准写法不一样" if len(marks) == 1 else "叠加的变音符和标准写法对不上") + f"（{drawn_by(gid)}画的）"
            else:
                links = [{"form": f"mark:{m}:{case}:{sc}", "slot": f"mv:mark:{i}", "symbol": SPACING.get(m, m),
                          "x": x0, "y": y0} for i, (m, (x0, y0)) in enumerate(zip(marks, spots))]
        if why:
            report["manual"].append({"char": ch, "id": gid, "group": GROUPS[g], "kind": "变音符", "why": why,
                                     "drawer": drawn_by(gid)})
            continue
        plan[gid].extend(links)
        report["linked"]["带变音符的字母"].append(ch + ("" if g == "HW" else "·比例"))
    report["mark_conflicts"] = {f"{MARK_ZH.get(m, m)}·{c}·{sc}": "".join(v) for (m, c, sc), v in conflicts.items()}
    report["standard_marks"] = {forms[f"mark:{m}:{c}:{sc}"]["name"]: rows for (m, c, sc), rows in standard.items()}
    used = {it["form"] for its in plan.values() for it in its}
    forms = {k: v for k, v in forms.items() if k in used}
    uses = Counter(it["form"] for its in plan.values() for it in its)
    report["forms"] = sorted(({"name": v["name"], "users": uses[k]} for k, v in forms.items()), key=lambda r: r["name"])
    write_report(report, s, items)
    report["switched_to_latin"] = [items[g]["char"] for g in switch]
    print(json.dumps({"forms": len(forms), "glyphs": len(plan), "links": sum(uses.values()), "switch_to_latin": len(switch),
                      "manual": len(report["manual"]), "mark_conflicts": report["mark_conflicts"]}, ensure_ascii=False))
    if a.dry_run:
        return
    if switch:
        print(s.movable_unlink(switch, "改为共用同形拉丁字母的形态，像素不变"))
    print(s.movable_link(forms, dict(plan), "自动关联可移动形态（基字、变音符），像素不变"))


def write_report(report, s, items):
    out = REPORTS
    out.mkdir(exist_ok=True)
    (out / "link-western.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    by = defaultdict(list)
    for m in report["manual"]:
        by[(m["drawer"], m["kind"], m["why"])].append(f"{m['char']}（{m['group']}）")
    lines = ["# 西文可移动形态关联报告", "",
             f"新建形态 {len(report['forms'])} 个；已关联：基本字母 {len(report['linked']['基本字母'])}，带变音符的字母 {len(report['linked']['带变音符的字母'])}，只关联基字 {len(report['linked']['只关联基字（钩、横、斜线等属于字母本身）'])}。", ""]
    if report["mark_conflicts"]:
        lines += ["## 变音符有两种写法一样多，不知以哪个为准", ""] + [f"- {k}：{v}" for k, v in report["mark_conflicts"].items()] + [""]
    for drawer in ("你", "程序", "AI"):
        part = {k: v for k, v in by.items() if k[0] == drawer}
        if not part:
            continue
        lines += [f"## 未关联 · {drawer}画的", ""]
        for (_, kind, why), chars in sorted(part.items()):
            lines.append(f"- {kind}：{why} —— {'、'.join(chars)}")
        lines.append("")
    lines += ["## 新建的形态", ""] + [f"- {f['name']}：{f['users']} 字" for f in report["forms"]]
    (out / "link-western.md").write_text("\n".join(lines) + "\n")
    sheet(report, s, items, out / "link-western.png")


def sheet(report, s, items, path):
    """Every unlinked glyph next to its base letter (same width), grouped by who drew it."""
    from PIL import Image, ImageDraw, ImageFont
    S, pad = 4, 10
    font = ImageFont.truetype(str(FONT), 15)
    small = ImageFont.truetype(str(FONT), 12)
    entries = sorted(report["manual"], key=lambda m: ({"你": 0, "程序": 1, "AI": 2}[m["drawer"]], m["kind"], m["id"]))
    cell_w, cell_h, cols = 2 * 16 * S + 3 * pad, 14 * S + 40, 8
    rows_n = -(-len(entries) // cols)
    im = Image.new("RGB", (cols * cell_w + 20, 50 + rows_n * cell_h), "white")
    d = ImageDraw.Draw(im)
    d.text((10, 10), f"未关联 {len(entries)} 字 · 每格：左 = 这个字，右 = 它的基本字母（同一版本）· 标题颜色：红 = 你画的，蓝 = 程序，灰 = AI", font=font, fill="black")

    def draw(rows, x, y):
        w = len(rows[0])
        d.rectangle((x - 1, y - 1, x + w * S, y + 14 * S), outline="#d8dce0")
        d.line((x, y + 11 * S, x + w * S - 1, y + 11 * S), fill="#f3b0b0")
        for yy, r in enumerate(rows):
            for xx, v in enumerate(r):
                if v == "#":
                    d.rectangle((x + xx * S, y + yy * S, x + (xx + 1) * S - 1, y + (yy + 1) * S - 1), fill="black")
    for i, m in enumerate(entries):
        x, y = 10 + (i % cols) * cell_w, 44 + (i // cols) * cell_h
        color = {"你": "#c0392b", "程序": "#2e5fa3", "AI": "#666"}[m["drawer"]]
        d.text((x, y), f"{m['char']} {m['id']}", font=small, fill=color)
        draw(s.current(m["id"])["rows"], x, y + 18)
        base = items[m["id"]]["family"]["base"]
        bid = f"U+{ord(base):04X}.{m['id'][-2:]}"
        if bid in s.glyphs and bid != m["id"]:
            draw(s.current(bid)["rows"], x + 16 * S + pad, y + 18)
    im.save(path)


if __name__ == "__main__":
    main()
