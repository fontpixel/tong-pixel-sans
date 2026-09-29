"""Prepare an AI repair round: pick glyphs, split them into batches, write each batch's inputs.

    .venv/bin/python tools/airepair/prepare.py NAME (--representative | --list FILE | --ids ID …)
        [--batch-size 50] [--ref-round NAME …] [--workers 10] [--effort xhigh]

Writes work/airepair/NAME/ (not in git): items.json, batches/bNNN/ (inputs.txt, input-*.png,
examples-*.png, batch.json), refs/, LESSONS.md, PROTOCOL.md, PROMPT.md. Only glyphs in state `ai`
are taken (your edited or approved glyphs never go to the AI). Each glyph is repaired from its
current version; the inputs are the region's Source Han Sans (the form to follow), TUMBLED 18 (a
pixel model), approved glyphs that share a component (pixels to reuse, found through the form
links), the same character's approved glyphs in other regions, and — with --ref-round — the
submitted results of earlier rounds that share a component (for consistency across rounds).
Nothing in the repository changes.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

from common import HERE, ROOT, ROUNDS, REGIONS, draw_bits, font, one_to_one, read_json, reference_png, region_match, tumbled

sys.path.insert(0, str(ROOT / "tools/editor"))
from store import Store  # noqa: E402
from segment import is_stroke  # noqa: E402  (single strokes are not components)


def select(s, a):
    if a.representative:
        ids = [g["id"] for g in read_json(ROOT / "tools/editor/data/representative.json")["glyphs"]]
    elif a.list:
        ids = [l.strip() for l in Path(a.list).read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    else:
        ids = a.ids
    take, skipped = [], Counter()
    for gid in ids:
        rec = s.records.get(gid)
        if rec is None or "alias" in rec or rec["group"] not in REGIONS:
            skipped["不是简 / 繁 / 日的独立字形"] += 1
        elif rec["state"] != "ai":
            skipped[f"状态 {rec['state']}（不交给 AI）"] += 1
        elif gid not in take:
            take.append(gid)
    # keep a character's regional glyphs next to each other
    order = {gid: i for i, gid in enumerate(take)}
    first = {}
    for gid in take:
        first.setdefault(s.records[gid]["cp"], order[gid])
    take.sort(key=lambda g: (first[s.records[g]["cp"]], order[g]))
    return take, skipped


def ref_results(names):
    """{glyph id: {'char', 'rows', 'round'}} submitted in earlier rounds."""
    out = {}
    for name in names:
        for p in sorted((ROUNDS / name / "results").glob("*.json")):
            for g in read_json(p)["glyphs"]:
                out[g["id"]] = {"char": g["char"], "rows": g["rows"], "round": name}
    return out


def input_page(items, path, title):
    from PIL import Image, ImageDraw
    small, big = font(13), font(18)
    sc, rowh = 8, 15 * 8 + 34
    W = 20 + 130 + 2 * (15 * sc + 30) + 60
    im = Image.new("RGB", (W * 2, 40 + rowh * ((len(items) + 1) // 2)), "white")
    d = ImageDraw.Draw(im)
    d.text((10, 8), title, font=big, fill=(0, 0, 0))
    for i, it in enumerate(items):
        X, Y = (i % 2) * W + 10, 40 + (i // 2) * rowh
        d.text((X, Y), f"{it['char']} {it['id']} · 圆石写法：{it['tumbled_match']}", font=small, fill=(0, 0, 0))
        im.paste(Image.open(it["_ref"]).convert("RGB").resize((112, 112)), (X, Y + 18))
        d.text((X, Y + 18 + 114), f"思源 {it['region']}", font=small, fill=(90, 90, 90))
        x = X + 130
        draw_bits(d, it["rows"], x, Y + 18, sc, label="当前 13×13", fnt=small)
        x += 15 * sc + 30
        if it["tumbled"]:
            draw_bits(d, it["tumbled"], x, Y + 18, sc, label="圆石 13×14", fnt=small)
        else:
            d.text((x, Y + 60), "（圆石没有此字）", font=small, fill=(90, 90, 90))
        x += 15 * sc + 30
        one_to_one(im, [it["rows"]] + ([it["tumbled"]] if it["tumbled"] else []), x, Y + 30, gap=20)
        d.text((x, Y + 50), "1:1", font=small, fill=(90, 90, 90))
    im.save(path)


def examples_page(examples, path, title):
    from PIL import Image, ImageDraw
    small, big = font(13), font(18)
    sc, cols = 6, 6
    cw, ch = 14 * sc + 44, 14 * sc + 44
    im = Image.new("RGB", (cols * cw + 20, 40 + ch * max(1, -(-len(examples) // cols))), "white")
    d = ImageDraw.Draw(im)
    d.text((10, 8), title, font=big, fill=(0, 0, 0))
    for i, e in enumerate(examples):
        x, y = 10 + (i % cols) * cw, 40 + (i // cols) * ch
        d.text((x, y), f"{e['char']} {e['id'][-2:]}", font=small, fill=(0, 0, 0))
        draw_bits(d, e["rows"], x, y + 18, sc)
        d.text((x, y + 18 + 14 * sc + 2), "、".join(e["for"])[:9], font=small, fill=(90, 90, 90))
    im.save(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--representative", action="store_true", help="the “接下来建议修” list")
    g.add_argument("--list", help="a file with one glyph id per line")
    g.add_argument("--ids", nargs="+")
    ap.add_argument("--batch-size", type=int, default=50)
    ap.add_argument("--ref-round", nargs="*", default=[])
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--model", default="gpt-6-astra")
    ap.add_argument("--effort", default="xhigh")
    a = ap.parse_args()
    out = ROUNDS / a.name
    if out.exists():
        raise SystemExit(f"{out} exists")
    s = Store(ROOT)
    ids, skipped = select(s, a)
    if not ids:
        raise SystemExit("no glyphs to repair")
    tum = tumbled()
    refs = ref_results(a.ref_round)
    approved = {gid: r for gid, r in s.records.items() if r.get("state") == "approved" and r["group"] in REGIONS}
    by_symbol = {}
    for gid, r in approved.items():
        for l in r["links"]:
            by_symbol.setdefault((r["group"], l["symbol"]), []).append((l["slot"], gid))
    # an approved glyph of a character that is itself a component (中 for 忠), same region
    standalone = {(r["group"], r["char"]): gid for gid, r in approved.items()}
    ref_by_symbol = {}
    for gid in refs:
        if gid in s.records:
            _, parts = s._parts(gid)
            for p in parts:
                if p["key"] != "whole" and not is_stroke(p["symbol"]):
                    lst = ref_by_symbol.setdefault((s.records[gid]["group"], p["symbol"]), [])
                    if gid not in lst:
                        lst.append(gid)
    (out / "refs").mkdir(parents=True)
    items = []
    for gid in ids:
        rec = s.records[gid]
        it = {"id": gid, "char": rec["char"], "region": rec["group"], "cp": rec["cp"], "revision": s.current(gid)["revision"],
              "rows": rec["rows"], "ai_note": " ".join(rec["ai_note"]), "tumbled": tum.get(rec["cp"])}
        it["tumbled_match"] = region_match(it["char"], it["region"], it["tumbled"]) if it["tumbled"] else "圆石没有此字"
        it["_ref"] = str(out / "refs" / f"{gid}.png")
        reference_png(it["char"], it["region"], it["_ref"])
        _, parts = s._parts(gid)
        comps = []
        seen_symbols = set()
        for p in parts:
            if p["key"] == "whole" or is_stroke(p["symbol"]) or p["symbol"] in seen_symbols:
                continue
            seen_symbols.add(p["symbol"])
            cands = [(slot, x) for slot, x in by_symbol.get((it["region"], p["symbol"]), []) if x != gid]
            cands.sort(key=lambda c: c[0] != p["key"])            # the same position first
            ex = list(dict.fromkeys(x for _, x in cands))[:4]
            alone = standalone.get((it["region"], p["symbol"]))
            if alone and alone != gid and alone not in ex:
                ex.append(alone)
            rr = [x for x in ref_by_symbol.get((it["region"], p["symbol"]), []) if x != gid][:3]
            if ex or rr:
                comps.append({"symbol": p["symbol"], "label": p["label"], "approved": ex, "earlier_rounds": rr})
        it["components"] = comps
        it["same_char_approved"] = [f"U+{it['cp']:04X}.{r}" for r in REGIONS if f"U+{it['cp']:04X}.{r}" in approved]
        items.append(it)
    # batches, keeping a character's regional glyphs together
    groups = []
    for it in items:
        if groups and groups[-1][0]["cp"] == it["cp"]:
            groups[-1].append(it)
        else:
            groups.append([it])
    batches, cur = [], []
    for grp in groups:
        if cur and len(cur) + len(grp) > a.batch_size:
            batches.append(cur); cur = []
        cur += grp
    if cur:
        batches.append(cur)
    for bi, batch in enumerate(batches, 1):
        bid = f"b{bi:03d}"
        bdir = out / "batches" / bid
        bdir.mkdir(parents=True)
        for it in batch:
            it["batch"] = bid
        pages = [batch[i:i + 16] for i in range(0, len(batch), 16)]
        for k, pg in enumerate(pages, 1):
            input_page(pg, bdir / f"input-{k:02d}.png", f"{a.name} {bid} 第 {k}/{len(pages)} 页 · 思源参考（写法依据）| 当前版本 | 圆石 18（像素范本）")
        ex, rex = {}, {}
        for it in batch:
            for x in it["same_char_approved"]:
                ex.setdefault(x, set()).add(f"{it['char']}同字")
            for c in it["components"]:
                for x in c["approved"]:
                    ex.setdefault(x, set()).add(f"{it['char']}的{c['symbol']}")
                for x in c["earlier_rounds"]:
                    rex.setdefault(x, set()).add(f"{it['char']}的{c['symbol']}")
        exl = [{"id": x, "char": approved[x]["char"], "rows": approved[x]["rows"], "for": sorted(v)} for x, v in sorted(ex.items())][:72]
        for k in range(0, len(exl), 36):
            examples_page(exl[k:k + 36], bdir / f"examples-{k // 36 + 1:02d}.png", f"{bid} · 已审核通过的相关字（部件可逐像素复用）")
        rexl = [{"id": x, "char": refs[x]["char"], "rows": refs[x]["rows"], "for": sorted(v)} for x, v in sorted(rex.items())][:36]
        if rexl:
            examples_page(rexl, bdir / "earlier-01.png", f"{bid} · 前几轮已修的同部件字（待审核，写法保持一致）")
        lines = [f"{a.name} {bid}: {len(batch)} glyphs. 每字：当前 13×13（改动基准，行号 0–12）与圆石 18 的 13×14。"]
        for it in batch:
            lines += ["", f"{it['id']} {it['char']} region={it['region']} 圆石写法={it['tumbled_match']}"
                      + (f" 同字已通过={','.join(it['same_char_approved'])}" if it["same_char_approved"] else "")]
            if it["ai_note"]:
                lines.append(f"  上一轮 AI 说明：{it['ai_note']}")
            for c in it["components"]:
                if c["approved"]:
                    lines.append(f"  部件 {c['label']}：已通过范例 " + " ".join(f"{approved[x]['char']}({x})" for x in c["approved"]))
                if c["earlier_rounds"]:
                    lines.append(f"  部件 {c['label']}：前几轮已修 " + " ".join(f"{refs[x]['char']}({x})" for x in c["earlier_rounds"]))
            lines.append("  当前：")
            lines += [f"    {y:2d} {r}" for y, r in enumerate(it["rows"])]
            if it["tumbled"]:
                lines.append("  圆石 13×14：")
                lines += [f"    {y:2d} {r}" for y, r in enumerate(it["tumbled"])]
        (bdir / "inputs.txt").write_text("\n".join(lines) + "\n")
        (bdir / "batch.json").write_text(json.dumps({"id": bid, "ids": [it["id"] for it in batch]}, ensure_ascii=False, indent=1))
    for it in items:
        it["reference"] = str(Path(it.pop("_ref")).relative_to(out))
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    (out / "items.json").write_text(json.dumps({"items": items, "skipped": dict(skipped)}, ensure_ascii=False, indent=1))
    (out / "round.json").write_text(json.dumps({"name": a.name, "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                                "repository_head": head, "model": a.model, "effort": a.effort, "workers": a.workers,
                                                "batches": [b[0]["batch"] for b in batches], "ref_rounds": a.ref_round},
                                               ensure_ascii=False, indent=1))
    # readers and prompts for this round
    rules = (ROOT / "docs/design-rules.md").read_text(encoding="utf-8")
    keep = [sec for sec in rules.split("\n## ") if sec.startswith(("1.", "2.", "3.", "8."))]
    (out / "LESSONS.md").write_text("# 本轮读本\n\n以下先是用户确认的规则（必须遵守），再是从人工修改归纳的候选规律与自检清单。\n\n## "
                                    + "\n## ".join(keep) + "\n\n---\n\n" + (ROOT / "docs/lessons/worker-lessons.md").read_text(encoding="utf-8"))
    subs = {"{KIT}": str(out), "{PY}": str(ROOT / ".venv/bin/python"), "{WF}": str(HERE / "workflow.py"), "{NAME}": a.name,
            "{MODEL}": a.model, "{EFFORT}": a.effort, "{WORKERS}": str(a.workers), "{N}": str(len(batches)),
            "{BATCH_SIZE}": str(a.batch_size), "{LAST}": batches[-1][0]["batch"]}
    for name in ("PROTOCOL.md", "PROMPT.md"):
        t = (HERE / "templates" / name).read_text(encoding="utf-8")
        for k, v in subs.items():
            t = t.replace(k, v)
        (out / name).write_text(t)
    print(json.dumps({"round": a.name, "glyphs": len(items), "batches": len(batches), "skipped": dict(skipped),
                      "tumbled": Counter(i["tumbled_match"].split("（")[0] for i in items),
                      "with_approved_components": sum(any(c["approved"] for c in i["components"]) for i in items)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
