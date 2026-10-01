"""Prepare a read-only audit: pages of numbered glyphs for an AI to look through and list clear errors.

    .venv/bin/python tools/airepair/audit.py NAME [--out DIR] [--portable] [--per-page 80] [--pages-per-batch 10]

Takes every glyph with its own pixels in state ai, derived, edited or hangul-ai (not approved, not drafts,
not generated or composed ones) of the regional groups, the Small western groups (HW, PR) and the Large
ones (HW-L, PR-L), in group then code point order. Writes DIR/NAME/ (default work/airepair/NAME/):
batches/bNNN/page-NN.png (the glyphs at 4×, numbered, each regional glyph with its Source Han Sans
reference beside it, western glyphs on their baseline) and batches/bNNN/pages.tsv (page, number, id,
character, state), PROTOCOL.md and PROMPT.md. The AI writes results/bNNN.tsv. Changes no glyph.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HERE, ROOT, ROUNDS, REGIONS, font, grey  # noqa: E402
from store import Store  # noqa: E402

ORDER = ["SC", "TC", "JP", "KR", "PR", "HW", "PR-L", "HW-L"]
STATES = ("ai", "derived", "edited", "hangul-ai")
TYPES = ["断笔", "多余黑块", "不对称", "部件间距", "越界", "写法错误", "同族不一致", "离开基线", "其他"]


def page_png(entries, path, title, sc=None):
    from PIL import Image, ImageDraw
    small, big = font(12), font(16)
    rows_max = max(len(e["rows"]) for e in entries)
    regional = entries[0]["group"] in REGIONS
    sc = sc or (5 if regional else 4)
    cw = max((len(e["rows"][0]) for e in entries), default=13)
    cell_w = (cw + 1) * sc + (44 if regional else 0) + 12
    cell_h = (rows_max + 1) * sc + 22
    cols = max(1, 1500 // cell_w)
    lines = -(-len(entries) // cols)
    im = Image.new("RGB", (cols * cell_w + 20, 34 + lines * cell_h), "white")
    d = ImageDraw.Draw(im)
    d.text((10, 6), title, font=big, fill=(0, 0, 0))
    for i, e in enumerate(entries):
        x, y = 10 + (i % cols) * cell_w, 34 + (i // cols) * cell_h
        d.text((x, y), f"{e['n']} {e['char'] if e['char'].isprintable() else ''} {e['cp']:04X}", font=small, fill=(0, 0, 0))
        top = y + 16
        h, w = len(e["rows"]), len(e["rows"][0])
        d.rectangle((x - 1, top - 1, x + w * sc, top + h * sc), outline=(200, 200, 200))
        if e.get("baseline") is not None:
            d.line((x, top + e["baseline"] * sc, x + w * sc, top + e["baseline"] * sc), fill=(240, 160, 160))
        for yy, r in enumerate(e["rows"]):
            for xx, v in enumerate(r):
                if v == "#":
                    d.rectangle((x + xx * sc, top + yy * sc, x + (xx + 1) * sc - 1, top + (yy + 1) * sc - 1), fill=(0, 0, 0))
        if regional and e.get("ref") is not None:
            ref = Image.fromarray(255 - e["ref"]).convert("RGB")
            ref.thumbnail((40, 40))
            im.paste(ref, (x + w * sc + 4, top))
    im.save(path, optimize=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name")
    ap.add_argument("--out", type=Path, default=ROUNDS)
    ap.add_argument("--portable", action="store_true")
    ap.add_argument("--per-page", type=int, default=80)
    ap.add_argument("--pages-per-batch", type=int, default=10)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    out = (a.out if a.out.is_absolute() else ROOT / a.out) / a.name
    if out.exists():
        raise SystemExit(f"{out} exists")
    s = Store(ROOT)
    recs = [r for r in s.records.values() if r["group"] in ORDER and "alias" not in r and r["state"] in STATES]
    recs.sort(key=lambda r: (ORDER.index(r["group"]), r["cp"]))
    pages = []
    for g in ORDER:
        mine = [r for r in recs if r["group"] == g]
        pages += [mine[i:i + a.per_page] for i in range(0, len(mine), a.per_page)]
    batches = [pages[i:i + a.pages_per_batch] for i in range(0, len(pages), a.pages_per_batch)]
    from store import baseline_row
    for bi, batch in enumerate(batches, 1):
        bid = f"b{bi:03d}"
        bdir = out / "batches" / bid
        bdir.mkdir(parents=True)
        tsv = ["page\tn\tid\tchar\tstate"]
        for pi, page in enumerate(batch, 1):
            entries = []
            for n, r in enumerate(page, 1):
                e = {"n": n, "id": r["id"], "char": r["char"], "cp": r["cp"], "group": r["group"], "rows": r["rows"],
                     "baseline": None if r["group"] in REGIONS else baseline_row(r["group"])}
                if r["group"] in REGIONS:
                    try:
                        e["ref"] = grey(r["char"], r["group"], ppem=40)
                    except Exception:   # noqa: BLE001  (no reference: the glyph alone)
                        e["ref"] = None
                entries.append(e)
                tsv.append(f"{pi}\t{n}\t{r['id']}\t{r['char'] if r['char'].isprintable() else ''}\t{r['state']}")
            group = page[0]["group"]
            page_png(entries, bdir / f"page-{pi:02d}.png",
                     f"{a.name} {bid} 第 {pi} 页 · {group} · {len(page)} 字" + (" · 右侧小图为思源参考" if group in REGIONS else " · 红线 = 基线"))
        (bdir / "pages.tsv").write_text("\n".join(tsv) + "\n", encoding="utf-8")
        print(bid, sum(len(p) for p in batch), flush=True)
    (out / "results").mkdir()
    kit = str(out.relative_to(ROOT)) if a.portable else str(out)
    subs = {"{KIT}": kit, "{NAME}": a.name, "{N}": str(len(batches)), "{LAST}": f"b{len(batches):03d}",
            "{TYPES}": "、".join(TYPES), "{WORKERS}": str(a.workers), "{GLYPHS}": f"{len(recs):,}", "{PAGES}": str(len(pages))}
    for name in ("PROTOCOL-audit.md", "PROMPT-audit.md"):
        t = (HERE / "templates" / name).read_text(encoding="utf-8")
        for k, v in subs.items():
            t = t.replace(k, v)
        (out / name.replace("-audit", "")).write_text(t, encoding="utf-8")
    (out / "round.json").write_text(f'{{"name": "{a.name}", "kind": "audit", "created_at": "{time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}", '
                                    f'"glyphs": {len(recs)}, "pages": {len(pages)}, "batches": {len(batches)}}}\n')
    print(f"{len(recs)} glyphs, {len(pages)} pages, {len(batches)} batches")


if __name__ == "__main__":
    main()
