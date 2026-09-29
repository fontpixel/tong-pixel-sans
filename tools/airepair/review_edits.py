"""What did people change after an AI round? Evidence for a new lessons report (docs/lessons/).

    .venv/bin/python tools/airepair/review_edits.py SINCE_COMMIT [--out DIR] [--round NAME …]

Compares every glyph whose pixels or state changed between SINCE_COMMIT (usually the commit that
imported an AI round) and the working tree, keeps the ones a person changed (now `approved` or
`edited` by hand — glyphs that only followed an edited shared form are listed separately), and
writes to DIR (default work/review-<commit>/):
  edits-NN.png   Source Han | TUMBLED | before (the AI version) | after (red = removed, blue = added),
                 most changed first
  stats.json     widths, edges, 2×2 blocks, distance to TUMBLED, before and after
  summary.md     the numbers, and the glyph lists
Changes nothing in the repository.
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, diff_colors, draw_bits, font, reference_png, tumbled  # noqa: E402
from store import Store, parse_block  # noqa: E402


def old_blocks(commit, rel):
    text = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{rel}"], capture_output=True, text=True).stdout
    out = {}
    for b in text.split("\n\n"):
        lines = [l for l in b.split("\n") if l]
        if lines:
            r = parse_block(rel.split("/")[1], lines)
            out[r["id"]] = r
    return out


def metrics(rows, tum):
    xs = [x for r in rows for x, v in enumerate(r) if v == "#"]
    ys = [y for y, r in enumerate(rows) if "#" in r]
    blocks = sum(1 for y in range(len(rows) - 1) for x in range(len(rows[0]) - 1)
                 if rows[y][x] == rows[y + 1][x] == rows[y][x + 1] == rows[y + 1][x + 1] == "#")
    d = min(sum(a != b for r1, r2 in zip(tum[:i] + tum[i + 1:], rows) for a, b in zip(r1, r2)) for i in range(14)) if tum else None
    return {"left": min(xs), "right": max(xs), "top": min(ys), "bottom": max(ys), "width": max(xs) - min(xs) + 1,
            "blocks": blocks, "ink": len(xs), "to_tumbled": d}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("since")
    ap.add_argument("--out")
    a = ap.parse_args()
    out = Path(a.out) if a.out else ROOT / "work" / f"review-{a.since[:8]}"
    (out / "refs").mkdir(parents=True, exist_ok=True)
    s = Store(ROOT)
    tum = tumbled()
    files = subprocess.run(["git", "-C", str(ROOT), "diff", "--name-only", a.since, "--", "glyphs"],
                           capture_output=True, text=True).stdout.split()
    edits, followed = [], []
    for rel in files:
        old = old_blocks(a.since, rel)
        for gid, o in old.items():
            r = s.records.get(gid)
            if not r or "alias" in r or "alias" in o or r["group"] not in ("SC", "TC", "JP"):
                continue
            if o["rows"] == r["rows"] and o["state"] == r["state"]:
                continue
            changed = sum(p != q for r1, r2 in zip(o["rows"], r["rows"]) for p, q in zip(r1, r2))
            item = {"id": gid, "char": r["char"], "region": r["group"], "before_state": o["state"], "state": r["state"],
                    "changed": changed, "before": o["rows"], "after": r["rows"], "note": " ".join(r["human_note"]),
                    "tumbled": tum.get(r["cp"])}
            # a glyph that only moved with an edited shared form: its state became `edited`, not by its own save
            if r["state"] == "edited" and o["state"] in ("ai", "approved") and changed <= 10 and not r["human_note"]:
                followed.append(item)
            elif r["state"] in ("approved", "edited"):
                edits.append(item)
    for it in edits:
        it["m_before"], it["m_after"] = metrics(it["before"], it["tumbled"]), metrics(it["after"], it["tumbled"])
    # sheets
    from PIL import Image, ImageDraw
    big, small = font(18), font(13)
    order = sorted([e for e in edits if e["changed"]], key=lambda e: (-e["changed"], e["id"]))
    sc, rowh, per = 7, 15 * 7 + 34, 16
    W = 10 + 110 + 3 * (15 * sc + 24) + 50
    for k in range(0, len(order), per):
        part = order[k:k + per]
        im = Image.new("RGB", (W * 2, 40 + rowh * ((len(part) + 1) // 2)), "white")
        d = ImageDraw.Draw(im)
        d.text((10, 8), f"人工修改（自 {a.since[:8]}）第 {k // per + 1} 页 · 思源 | 圆石 | 修前（AI）| 修后（红=删，蓝=加）", font=big, fill=(0, 0, 0))
        for i, e in enumerate(part):
            x0, y0 = (i % 2) * W + 10, 40 + (i // 2) * rowh
            ref = out / "refs" / f"{e['id']}.png"
            if not ref.exists():
                reference_png(e["char"], e["region"], ref)
            d.text((x0, y0), f"{e['char']} {e['id']} · 改 {e['changed']} 点 · {e['before_state']}→{e['state']}", font=small, fill=(0, 0, 0))
            im.paste(Image.open(ref).convert("RGB").resize((98, 98)), (x0, y0 + 18))
            x = x0 + 110
            if e["tumbled"]:
                draw_bits(d, e["tumbled"], x, y0 + 18, sc, label="圆石", fnt=small)
            x += 15 * sc + 24
            draw_bits(d, e["before"], x, y0 + 18, sc, label="修前", fnt=small)
            x += 15 * sc + 24
            draw_bits(d, e["after"], x, y0 + 18, sc, label="修后", fnt=small, colors=diff_colors(e["before"], e["after"]))
        im.save(out / f"edits-{k // per + 1:02d}.png")
    # stats
    med = lambda xs: statistics.median(xs) if xs else 0
    ch = [e["changed"] for e in edits]
    wb, wa = Counter(e["m_before"]["width"] for e in edits), Counter(e["m_after"]["width"] for e in edits)
    tb = [e["m_before"]["to_tumbled"] for e in edits if e["tumbled"]]
    ta = [e["m_after"]["to_tumbled"] for e in edits if e["tumbled"]]
    closer = sum(e["m_after"]["to_tumbled"] < e["m_before"]["to_tumbled"] for e in edits if e["tumbled"] and e["changed"])
    farther = sum(e["m_after"]["to_tumbled"] > e["m_before"]["to_tumbled"] for e in edits if e["tumbled"] and e["changed"])
    lines = [f"# 人工修改（自 {a.since}）", "",
             f"- 人工修改或审核的字形 {len(edits)}：" + "，".join(f"{k} {v}" for k, v in Counter(f"{e['before_state']}→{e['state']}" for e in edits).items()),
             f"- 像素有改动 {sum(c > 0 for c in ch)}，只审核未改 {sum(c == 0 for c in ch)}；改动中位 {med(ch)}，最多 {max(ch) if ch else 0}",
             f"- 随共享形态同步变化（不是逐字修改）{len(followed)}：" + " ".join(f"{e['char']}{e['id'][-3:]}" for e in followed),
             f"- 宽度（列）修前 {sorted(wb.items())} → 修后 {sorted(wa.items())}",
             f"- 左缘 x0：修前 {sum(e['m_before']['left'] == 0 for e in edits)} → 修后 {sum(e['m_after']['left'] == 0 for e in edits)}；"
             f"右缘 x12：{sum(e['m_before']['right'] == 12 for e in edits)} → {sum(e['m_after']['right'] == 12 for e in edits)}",
             f"- 2×2 黑块：{sum(e['m_before']['blocks'] for e in edits)} → {sum(e['m_after']['blocks'] for e in edits)}；墨迹像素中位 {med([e['m_before']['ink'] for e in edits])} → {med([e['m_after']['ink'] for e in edits])}",
             f"- 与圆石距离中位 {med(tb)} → {med(ta)}；改动后更接近圆石 {closer}，更远 {farther}", "",
             "## 改动最大", "", " ".join(f"{e['char']}{e['id'][-3:]}{e['changed']}" for e in order[:60]), ""]
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    (out / "stats.json").write_text(json.dumps([{k: v for k, v in e.items() if k not in ("tumbled",)} for e in edits], ensure_ascii=False))
    print("\n".join(lines[:10]))
    print("written to", out)


if __name__ == "__main__":
    main()
