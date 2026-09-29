"""Prepare an AI repair round: pick glyphs, split them into batches, write each batch's inputs.

    .venv/bin/python tools/airepair/prepare.py NAME (--representative | --list FILE | --ids ID … | --derive)
        [--masters-only] [--batch-size 50] [--ref-round NAME …] [--workers 10] [--effort xhigh]

Writes work/airepair/NAME/ (not in git): items.json, batches/bNNN/ (inputs.txt, input-*.png,
examples-*.png, batch.json), refs/, LESSONS.md, PROTOCOL.md, PROMPT.md. Only glyphs in state `ai`
are taken (your edited or approved glyphs never go to the AI). Each glyph is repaired from its
current version; the inputs are the region's Source Han Sans (the form to follow), TUMBLED 18 (a
pixel model), approved glyphs that share a component (pixels to reuse, found through the form
links), the same character's approved glyphs in other regions, and — with --ref-round — the
submitted results of earlier rounds that share a component (for consistency across rounds).
Nothing in the repository changes.

A character's regional glyphs derive from one master (docs/design-rules.md §2): its approved glyph,
else its edited one, else the first of SC TC JP KR. --masters-only leaves out the other regions'
glyphs (they are derived later). --derive prepares a derivation round instead: every non-master
regional glyph in state ai or draft, whose starting point (“当前”) is a pixel copy of its master —
the master's latest result in the --ref-round rounds if it is not reviewed, else its current
version; the worker changes only the strokes the two regions write differently.
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


def master_of(s, cp):
    """The master glyph of a code point: approved, else edited, else the first of SC TC JP KR."""
    recs = [s.records[g] for g in (f"U+{cp:04X}.{r}" for r in REGIONS) if g in s.records and "alias" not in s.records[g]]
    if not recs:
        return None
    return min(recs, key=lambda r: ({"approved": 0, "edited": 1}.get(r["state"], 2), REGIONS.index(r["group"])))["id"]


def select(s, a):
    if a.derive:
        ids = sorted((g for g, r in s.records.items() if r["group"] in REGIONS and "alias" not in r
                      and r["state"] in ("ai", "draft") and master_of(s, r["cp"]) != g),
                     key=lambda g: (s.records[g]["cp"], REGIONS.index(s.records[g]["group"])))
    elif a.representative:
        ids = [g["id"] for g in read_json(ROOT / "tools/editor/data/representative.json")["glyphs"]]
    elif a.list:
        ids = [l.strip() for l in Path(a.list).read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    else:
        ids = a.ids
    take, skipped = [], Counter()
    for gid in ids:
        rec = s.records.get(gid)
        if rec is None or "alias" in rec or rec["group"] not in REGIONS:
            skipped["不是简 / 繁 / 日 / 韩的独立字形"] += 1
        elif rec["state"] not in ("ai", "draft"):
            skipped[f"状态 {rec['state']}（不交给 AI）"] += 1
        elif a.masters_only and master_of(s, rec["cp"]) != gid:
            skipped["不是母版（之后从母版派生）"] += 1
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


def derive_page(items, path, title):
    from PIL import Image, ImageDraw
    small, big = font(13), font(18)
    sc, rowh = 8, 15 * 8 + 34
    W = 20 + 2 * 130 + 2 * (15 * sc + 30) + 60
    im = Image.new("RGB", (W * 2, 40 + rowh * ((len(items) + 1) // 2)), "white")
    d = ImageDraw.Draw(im)
    d.text((10, 8), title, font=big, fill=(0, 0, 0))
    for i, it in enumerate(items):
        X, Y = (i % 2) * W + 10, 40 + (i // 2) * rowh
        m = it["master"]
        d.text((X, Y), f"{it['char']} {it['id']} ← 母版 {m['id']}", font=small, fill=(0, 0, 0))
        for k, (ref, label) in enumerate(((it["_ref"], f"思源 {it['region']}（本字）"), (it["_master_ref"], f"思源 {m['id'][-2:]}（母版）"))):
            im.paste(Image.open(ref).convert("RGB").resize((112, 112)), (X + k * 130, Y + 18))
            d.text((X + k * 130, Y + 18 + 114), label, font=small, fill=(90, 90, 90))
        x = X + 260
        draw_bits(d, it["rows"], x, Y + 18, sc, label="母版 = 当前", fnt=small)
        x += 15 * sc + 30
        draw_bits(d, it["old_rows"], x, Y + 18, sc, label="旧版（仅参考）", fnt=small)
        x += 15 * sc + 30
        one_to_one(im, [it["rows"], it["old_rows"]], x, Y + 30, gap=20)
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


DERIVE_TASK = ("本批是**同字各地区的派生**（LESSONS.md L050，用户确认）。每个字的“当前”版本就是它的**母版**——同一个字另一地区的版本"
               "（已审核，或 AI 已修）——的逐像素副本。请对照 input 图里本地区和母版地区的两张思源参考，找出两地**写法**不同的笔画"
               "（点的方向、笔画是否出头、笔画数、部件写法），在副本上**只改这些像素**；**不要**跟两地思源之间的比例、位置、粗细差异，"
               "也不要顺手改母版里你觉得可以更好的地方。13×13 下写法没有区别的就不改（changes 写 {}）——这很常见，不要为了显得改过而改。"
               "改动一般只有几个到十几个像素；超过 20 个像素时在 note 里写明原因。圆石不适用，tumbled 一律写“未借鉴”，没有已通过范例和 examples 图。"
               "“旧版”是这个地区以前独立修的版本：某处地区写法它处理得好，可以借鉴那一处，但不能以旧版为基础。")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--representative", action="store_true", help="the “接下来建议修” list")
    g.add_argument("--list", help="a file with one glyph id per line")
    g.add_argument("--ids", nargs="+")
    g.add_argument("--derive", action="store_true", help="a derivation round: every non-master regional AI glyph or draft")
    ap.add_argument("--masters-only", action="store_true", help="leave out glyphs that are not their character's master")
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
        it = {"id": gid, "char": rec["char"], "region": rec["group"], "cp": rec["cp"], "revision": s.current(gid)["revision"], "state": rec["state"],
              "rows": rec["rows"], "ai_note": " ".join(rec["ai_note"]), "tumbled": tum.get(rec["cp"])}
        it["tumbled_match"] = region_match(it["char"], it["region"], it["tumbled"]) if it["tumbled"] and not a.derive else "圆石没有此字"
        it["_ref"] = str(out / "refs" / f"{gid}.png")
        reference_png(it["char"], it["region"], it["_ref"])
        if a.derive:
            mid = master_of(s, rec["cp"])
            m = s.records[mid]
            if m["state"] not in ("approved", "edited") and mid in refs:
                mrows, source = refs[mid]["rows"], f"{refs[mid]['round']} 的结果，未审核"
            else:
                mrows, source = m["rows"], {"approved": "已通过", "edited": "人工改过，未通过"}.get(m["state"], "当前 AI 版，未审核")
            it["master"] = {"id": mid, "state": m["state"], "source": source}
            it["old_rows"], it["rows"] = (refs[gid]["rows"] if gid in refs else it["rows"]), list(mrows)
            it["_master_ref"] = str(out / "refs" / f"{mid}.png")
            if not Path(it["_master_ref"]).exists():
                reference_png(it["char"], m["group"], it["_master_ref"])
            it["components"], it["same_char_approved"], it["tumbled"] = [], [], None
            it["tumbled_match"] = "派生轮不参考圆石"
            items.append(it)
            continue
        _, parts = s._parts(gid)
        comps = []
        seen_symbols = set()
        for p in parts:
            if p["key"] == "whole" or is_stroke(p["symbol"]) or p["symbol"] in seen_symbols:
                continue
            seen_symbols.add(p["symbol"])
            cands = [(slot, x) for slot, x in by_symbol.get((it["region"], p["symbol"]), []) if x != gid]
            if not cands and it["region"] == "KR":       # Korean hanja follow the traditional forms
                cands = [(slot, x) for slot, x in by_symbol.get(("TC", p["symbol"]), [])]
            cands.sort(key=lambda c: c[0] != p["key"])            # the same position first
            ex = list(dict.fromkeys(x for _, x in cands))[:4]
            alone = standalone.get((it["region"], p["symbol"])) or (standalone.get(("TC", p["symbol"])) if it["region"] == "KR" else None)
            if alone and alone != gid and alone not in ex:
                ex.append(alone)
            rr = [x for x in ref_by_symbol.get((it["region"], p["symbol"]), []) if x != gid][:3]
            if not rr and it["region"] == "KR":
                rr = ref_by_symbol.get(("TC", p["symbol"]), [])[:3]
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
            if a.derive:
                derive_page(pg, bdir / f"input-{k:02d}.png", f"{a.name} {bid} 第 {k}/{len(pages)} 页 · 思源：本字地区 | 母版地区 · 母版（改动基准）| 旧版（仅参考）")
            else:
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
        if a.derive:
            lines = [f"{a.name} {bid}: {len(batch)} glyphs. 地区派生：每字的“当前”是母版（同一个字另一地区的版本）的逐像素副本，行号 0–12；"
                     "只改本地区写法与母版地区不同的笔画。“旧版”是这个地区以前独立修的版本，仅供参考。"]
            for it in batch:
                lines += ["", f"{it['id']} {it['char']} region={it['region']} 母版={it['master']['id']}（{it['master']['source']}）"]
                lines.append("  当前（= 母版副本，改动基准）：")
                lines += [f"    {y:2d} {r}" for y, r in enumerate(it["rows"])]
                lines.append("  旧版（仅参考，不作基础）：")
                lines += [f"    {y:2d} {r}" for y, r in enumerate(it["old_rows"])]
            (bdir / "inputs.txt").write_text("\n".join(lines) + "\n")
            (bdir / "batch.json").write_text(json.dumps({"id": bid, "ids": [it["id"] for it in batch]}, ensure_ascii=False, indent=1))
            continue
        for it in batch:
            lines += ["", f"{it['id']} {it['char']} region={it['region']}{' 底稿' if it['state'] == 'draft' else ''} 圆石写法={it['tumbled_match']}"
                      + (f" 同字已通过={','.join(it['same_char_approved'])}" if it["same_char_approved"] else "")]
            if it["ai_note"]:
                lines.append(f"  底稿说明：{it['ai_note'].removeprefix('底稿：')}" if it["state"] == "draft" else f"  上一轮 AI 说明：{it['ai_note']}")
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
        if "_master_ref" in it:
            it["master_reference"] = str(Path(it.pop("_master_ref")).relative_to(out))
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
    drafts = sum(i["state"] == "draft" for i in items)
    task = DERIVE_TASK if a.derive else ("本批的字**是新增字的底稿**：由思源黑体点阵化（WorkBench 渲染加相位搜索），还没经 AI 或人工修。请在底稿基础上完整修字，"
            "像修第一轮那样认真处理每个字（结构、笔画、密处取舍），不要只做微调。" if drafts == len(items) else
            "本批的字**已经由 AI 修过**，你在**当前版本**的基础上继续修整。满意的字可以不改。" if not drafts else
            "本批大多数字**已经由 AI 修过**，在当前版本上继续修整，满意的可以不改；inputs.txt 标为“底稿”的字是新增字的底稿，要完整修。")
    subs = {"{KIT}": str(out), "{TASK}": task, "{PY}": str(ROOT / ".venv/bin/python"), "{WF}": str(HERE / "workflow.py"), "{NAME}": a.name,
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
