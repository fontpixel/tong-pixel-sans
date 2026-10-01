"""Comparison sheets of a round's submitted results, for the user's decision. Changes nothing.

    .venv/bin/python tools/airepair/compare.py NAME

Writes work/airepair/NAME/compare/: sheet-NN.png (every glyph: Source Han | TUMBLED | before |
after with removed pixels red and added blue | 1:1, most changed first), text-SC.png … (the
characters typeset at 1:1 and 3×, before then after) and summary.md.
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROUNDS, cell, diff_colors, draw_bits, font, one_to_one, read_json  # noqa: E402


def load(rnd):
    items = {i["id"]: i for i in read_json(rnd / "items.json")["items"]}
    out = []
    for p in sorted((rnd / "results").glob("*.json")):
        for g in read_json(p)["glyphs"]:
            g["changed"] = sum(a != b for r1, r2 in zip(g["before"], g["rows"]) for a, b in zip(r1, r2))
            g["item"] = items[g["id"]]
            out.append(g)
    return out


def sheets(rnd, glyphs, out):
    from PIL import Image, ImageDraw
    big, small = font(18), font(13)
    order = sorted(glyphs, key=lambda g: (-g["changed"], g["id"]))
    sc, per = 7, 16
    rowh = (max(len(g["rows"]) for g in glyphs) + 1) * sc + 50
    W = 10 + 110 + 3 * (15 * sc + 24) + 60
    for k in range(0, len(order), per):
        part = order[k:k + per]
        im = Image.new("RGB", (W * 2, 40 + rowh * ((len(part) + 1) // 2)), "white")
        d = ImageDraw.Draw(im)
        d.text((10, 8), f"{rnd.name} 第 {k // per + 1} 页 · 思源 | 圆石 | 修前 | 修后（红=删，蓝=加）· 按改动量排序", font=big, fill=(0, 0, 0))
        for i, g in enumerate(part):
            it = g["item"]
            x0, y0 = (i % 2) * W + 10, 40 + (i // 2) * rowh
            d.text((x0, y0), f"{g['char']} {g['id']} · 改 {g['changed']} 点 · 圆石：{g['tumbled']}"
                   + (" · 复用 " + "、".join(g["reuse"])[:28] if g["reuse"] else ""), font=small, fill=(0, 0, 0))
            im.paste(Image.open(rnd / it["reference"]).convert("RGB").resize((98, 98)), (x0, y0 + 18))
            x = x0 + 110
            if it["tumbled"]:
                draw_bits(d, it["tumbled"], x, y0 + 18, sc, label="圆石", fnt=small)
            x += 15 * sc + 24
            box, xo = cell(g["id"], g["before"])
            draw_bits(d, g["before"], x, y0 + 18, sc, box=box, x_off=xo, label="修前", fnt=small)
            x += 15 * sc + 24
            box, xo = cell(g["id"], g["rows"])
            draw_bits(d, g["rows"], x, y0 + 18, sc, box=box, x_off=xo, label="修后", fnt=small,
                      colors=diff_colors(g["before"], g["rows"]) if len(g["before"][0]) == len(g["rows"][0]) else None)
            x += 15 * sc + 24
            one_to_one(im, [g["before"], g["rows"]], x, y0 + 30)
            d.text((x, y0 + 48), "1:1", font=small, fill=(90, 90, 90))
            if g["note"]:
                d.text((x0 + 110, y0 + 18 + len(g["rows"]) * sc + 18), g["note"][:48], font=small, fill=(110, 110, 110))
        im.save(out / f"sheet-{k // per + 1:02d}.png")


def text_sheets(glyphs, out):
    from PIL import Image, ImageDraw
    fnt = font(16)
    for region in ("SC", "TC", "JP"):
        gs = [g for g in glyphs if g["region"] == region]
        if not gs:
            continue
        per_line = 40
        lines = [gs[i:i + per_line] for i in range(0, len(gs), per_line)]
        blocks = [(s, label, key) for s in (1, 3) for label, key in (("修前", "before"), ("修后", "rows"))]
        im = Image.new("L", (20 + per_line * 14 * 3, 30 + sum(24 + len(lines) * 16 * s for s, _, _ in blocks)), 255)
        d = ImageDraw.Draw(im)
        d.text((10, 6), f"{region} · {len(gs)} 字 · 1:1 与 3×，各先修前后修后", font=fnt, fill=0)
        y = 30
        for s, label, key in blocks:
            d.text((10, y), f"{label} {s}×", font=fnt, fill=90)
            y += 22
            for li, line in enumerate(lines):
                for ci, g in enumerate(line):
                    for yy, r in enumerate(g[key]):
                        for xx, v in enumerate(r):
                            if v == "#":
                                X, Y = 10 + (ci * 14 + 1 + xx) * s, y + (li * 16 + yy) * s
                                d.rectangle((X, Y, X + s - 1, Y + s - 1), fill=0)
            y += len(lines) * 16 * s + 2
        im.save(out / f"text-{region}.png")


def summary(rnd, glyphs, out):
    ch = [g["changed"] for g in glyphs]
    lines = [f"# {rnd.name}：结果摘要", "",
             f"- 字形：{len(glyphs)}（" + "，".join(f"{k} {v}" for k, v in sorted(Counter(g['region'] for g in glyphs).items())) + "）",
             f"- 改动：{sum(c > 0 for c in ch)} 字有改动，{sum(c == 0 for c in ch)} 字保持原样；改动像素中位数 {statistics.median(ch)}，最多 {max(ch)}",
             "- 圆石：" + "，".join(f"{k} {v}" for k, v in Counter(g["tumbled"] for g in glyphs).most_common()),
             f"- 逐像素复用已通过部件：{sum(bool(g['reuse']) for g in glyphs)} 字",
             f"- 两轮复看：{sum(g['rounds'] >= 2 for g in glyphs)} 字", "", "## 仍有问题说明的字", ""]
    lines += [f"- {g['char']} {g['id']}：{g['note']}" for g in glyphs if g["note"]]
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:7]))


def main():
    name = sys.argv[1]
    rnd = Path(name) if "/" in name else ROUNDS / name
    glyphs = load(rnd)
    if not glyphs:
        raise SystemExit("no submitted results yet")
    out = rnd / "compare"
    out.mkdir(exist_ok=True)
    sheets(rnd, glyphs, out)
    text_sheets(glyphs, out)
    summary(rnd, glyphs, out)
    print("written to", out)


if __name__ == "__main__":
    main()
