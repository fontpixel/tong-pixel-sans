"""Prepare an AI repair round: pick glyphs, split them into batches, write each batch's inputs.

    .venv/bin/python tools/airepair/prepare.py NAME (--representative | --list FILE | --ids ID … | --derive [--list FILE])
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
else its edited one, else a repaired one before a draft, the first of SC TC JP KR among equals. --masters-only leaves out the other regions'
glyphs (they are derived later). --derive prepares a derivation round instead: every non-master
regional glyph in state ai or draft, whose starting point (“当前”) is a pixel copy of its master —
the master's latest result in the --ref-round rounds if it is not reviewed, else its current
version; the worker changes only the strokes the two regions write differently.
--symbols prepares a symbol round (with --list): full-width (regional), half-width (HW) and
proportional (PR) glyphs, or the Large size's HW-L / PR-L glyphs (a round of Large glyphs only: each with
its Small version as the letterform to follow, the zone-mapped outline as reference); the reader is design-rules §1 4 5 7 and docs/lessons/symbols.md, the
examples are existing glyphs of the same group near the code point (the same family: ①–⑮ for ⑯) and
the same code point's approved glyphs in other groups.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

from common import HERE, ROOT, ROUNDS, REGIONS, cell, draw_bits, font, one_to_one, read_json, reference_png, region_match, tumbled, western_png

sys.path.insert(0, str(ROOT / "tools/editor"))
from store import Store  # noqa: E402
from segment import is_stroke  # noqa: E402  (single strokes are not components)


def master_of(s, cp):
    """The master glyph of a code point: approved, else edited, else a repaired glyph (not a draft), else a
    draft; the first of SC TC JP KR among equals."""
    recs = [s.records[g] for g in (f"U+{cp:04X}.{r}" for r in REGIONS) if g in s.records and "alias" not in s.records[g]]
    if not recs:
        return None
    rank = {"approved": 0, "edited": 1, "draft": 3}
    # a regional draft that is a pixel copy of another region's glyph (add_regional.py) is never the master
    copy = lambda r: r["state"] == "draft" and any(n.startswith("底稿：复制自") for n in r.get("ai_note", []))
    return min(recs, key=lambda r: (rank.get(r["state"], 2) + (2 if copy(r) else 0), REGIONS.index(r["group"])))["id"]


def select(s, a):
    if a.derive:
        wanted = None
        if a.list or a.ids:
            wanted = set(a.ids or [l.strip() for l in Path(a.list).read_text(encoding="utf-8").splitlines()
                                   if l.strip() and not l.startswith("#")])
        ids = sorted((g for g, r in s.records.items() if r["group"] in REGIONS and "alias" not in r
                      and r["state"] in ("ai", "draft", "edited") and master_of(s, r["cp"]) != g
                      and (wanted is None or g in wanted)),
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
        if rec is None or "alias" in rec or rec["group"] not in REGIONS + (("HW", "PR", "HW-L", "PR-L") if a.symbols else ()):
            skipped["不是简 / 繁 / 日 / 韩的独立字形"] += 1
        elif rec["state"] not in ("ai", "draft", "edited"):     # edited = changed but not approved: unfinished
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
    sc = 8
    rowh = (max(len(it["rows"]) for it in items) + 1) * sc + 34
    W = 20 + 130 + 2 * (15 * sc + 30) + 60
    im = Image.new("RGB", (W * 2, 40 + rowh * ((len(items) + 1) // 2)), "white")
    d = ImageDraw.Draw(im)
    d.text((10, 8), title, font=big, fill=(0, 0, 0))
    for i, it in enumerate(items):
        X, Y = (i % 2) * W + 10, 40 + (i // 2) * rowh
        symbol = it["tumbled_match"] == "符号轮不参考圆石"
        d.text((X, Y), f"{it['char']} {it['id']}" + ("" if symbol else f" · 圆石写法：{it['tumbled_match']}"), font=small, fill=(0, 0, 0))
        im.paste(Image.open(it["_ref"]).convert("RGB").resize((112, 112)), (X, Y + 18))
        d.text((X, Y + 18 + 114), "参考字体" if it["region"] in ("HW", "PR", "HW-L", "PR-L") else f"思源 {it['region']}", font=small, fill=(90, 90, 90))
        x = X + 130
        box, xo = cell(it["id"], it["rows"])
        draw_bits(d, it["rows"], x, Y + 18, sc, box=box, x_off=xo, label=f"当前 {len(it['rows'][0])}×{len(it['rows'])}", fnt=small)
        x += 15 * sc + 30
        if it.get("small"):
            box, xo = cell(it["small"]["id"], it["small"]["rows"])
            draw_bits(d, it["small"]["rows"], x, Y + 18, sc, box=box, x_off=xo, label=f"小号版 {it['small']['mark']}", fnt=small)
        elif it["tumbled"]:
            draw_bits(d, it["tumbled"], x, Y + 18, sc, label="圆石 13×14", fnt=small)
        elif not symbol:
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
    cw, ch = 14 * sc + 44, max(len(e["rows"]) for e in examples) * sc + 44
    im = Image.new("RGB", (cols * cw + 20, 40 + ch * max(1, -(-len(examples) // cols))), "white")
    d = ImageDraw.Draw(im)
    d.text((10, 8), title, font=big, fill=(0, 0, 0))
    for i, e in enumerate(examples):
        x, y = 10 + (i % cols) * cw, 40 + (i // cols) * ch
        d.text((x, y), f"{e['char']} {e['id'][-2:]}", font=small, fill=(0, 0, 0))
        box, xo = cell(e["id"], e["rows"])
        draw_bits(d, e["rows"], x, y + 18, sc, box=box, x_off=xo)
        d.text((x, y + 18 + len(e["rows"]) * sc + 2), "、".join(e["for"])[:9], font=small, fill=(90, 90, 90))
    im.save(path)


DERIVE_TASK = ("本批是**同字各地区的派生**（LESSONS.md L050，用户确认）。每个字的“当前”版本就是它的**母版**——同一个字另一地区的版本"
               "（已审核，或 AI 已修）——的逐像素副本。请对照 input 图里本地区和母版地区的两张思源参考，找出两地**写法**不同的笔画"
               "（点的方向、笔画是否出头、笔画数、部件写法），在副本上**只改这些像素**；**不要**跟两地思源之间的比例、位置、粗细差异，"
               "也不要顺手改母版里你觉得可以更好的地方。13×13 下写法没有区别的就不改（changes 写 {}）——这很常见，不要为了显得改过而改。"
               "改动一般只有几个到十几个像素；超过 20 个像素时在 note 里写明原因。圆石不适用，tumbled 一律写“未借鉴”，没有已通过范例和 examples 图。"
               "“旧版”是这个地区以前独立修的版本：某处地区写法它处理得好，可以借鉴那一处，但不能以旧版为基础。")


EDITED_TASK = ("本批的字**用户改过一部分、还没审核通过**（例如只改了共享的左偏旁形态，其余还是 AI 版）：用户认为这些字还没修完。"
               "你在**当前版本**上继续修：用户改过的部分和 inputs.txt 列出的“已关联的部件”保持不动，除非明显有错；其余部分按规则和范例修好。")


RECHECK_TASK = ("本批是**按新规则的回头修**：这些字已经由 AI 修过，但不符合用户最近确认的规则。inputs.txt 每字列出了“本轮要改”的问题"
                "（部件间空了 2 列以上、字修窄了、没用满第 0–12 行），一般应当改掉：部件靠拢到只空 0–1 列，省下的空间给部件加宽，"
                "整字尽量撑到 13 列（L052）、用满上下（L053）。**占满 13×13 是优先方向，不是硬性要求**（用户确认）：改了会拉变形、破坏思源的比例或写法时就不改，"
                "在 note 里说明。改时照已通过的范例和 L051 统一左偏旁；列出的问题以外，满意的地方可以不改。")


SYMBOL_TASK = ("本批是**符号的底稿**：由参考字体点阵化（相位搜索），还没经 AI 或人工修。全角符号在 13×13 墨迹内，等宽符号 7×14，"
               "比例符号宽度可变、高 14（基线在第 10 行下，第 11–13 行是降部）。请在底稿基础上完整修字：形状清楚、1 像素笔画、对称的要对称，"
               "同族（圈号、括号号、箭头、几何图形、上下标、西里尔字母）与 examples 里已有的同族字形用一样的像素写法。")


LARGE_TASK = ("本批是 **14 Large（大号版）的底稿**：由参考字体按大号规格点阵化，还没经 AI 或人工修。大号版规格（用户 2026-10-01 决定，T 比例）："
              "**大写和数字 10 行（第 4–13 行），小写 x 高 7 行（第 7–13 行），升部（b d f h k l）10 行、与大写同高（第 4–13 行），"
              "降部 3 行（第 14–16 行）**；g j p q y 的主体与 n o u 同高同位。**变音符不压缩**：大写上的符号放在第 0–3 行、与字母隔 1 行，"
              "越南文叠两层也照常画；小写上的符号与 x 高隔 1 行。笔画 1 像素；对称的字母左右逐点对称。"
              "等宽字墨迹最多 6 列（7 列格），比例字墨迹从第 0 列起、宽度按字形需要。"
              "**写法照同码位的小号版**（inputs.txt 列出，✓ 为用户已通过，改 = 用户改过）：小号版上用户确定的形状要保留，按大号尺寸重画；"
              "examples 里已通过的大号字（同族、同底字母）是大号写法的范例，变音符、圆弧、斜线的像素写法要和它们一致。")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--representative", action="store_true", help="the “接下来建议修” list")
    g.add_argument("--list", help="a file with one glyph id per line")
    g.add_argument("--ids", nargs="+")
    ap.add_argument("--derive", action="store_true", help="a derivation round: every non-master regional AI glyph or draft "
                    "(only those in --list / --ids when given)")
    ap.add_argument("--masters-only", action="store_true", help="leave out glyphs that are not their character's master")
    ap.add_argument("--symbols", action="store_true", help="a symbol round: regional, HW and PR glyphs from --list")
    ap.add_argument("--start-from-ref", action="store_true", help="start each glyph from its latest --ref-round result if it has one")
    ap.add_argument("--issues", type=Path, help="JSON {glyph id: [issues]}: what this round must fix, shown per glyph (a recheck round)")
    ap.add_argument("--batch-size", type=int, default=50)
    ap.add_argument("--ref-round", nargs="*", default=[])
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--model", default="gpt-6-astra")
    ap.add_argument("--effort", default="xhigh")
    ap.add_argument("--max-views", type=int, default=2, help="visual review rounds allowed per glyph")
    ap.add_argument("--out", type=Path, default=ROUNDS, help="parent directory of the round (default work/airepair/)")
    ap.add_argument("--kit-path", help="with --portable: the round's path as the worker will see it (default: its path under the repository)")
    ap.add_argument("--portable", action="store_true", help="paths in PROTOCOL.md / PROMPT.md relative to the repository "
                    "root and `python3`, for a round committed to a branch and run elsewhere (e.g. Codex in the cloud)")
    a = ap.parse_args()
    if not (a.derive or a.representative or a.list or a.ids):
        ap.error("one of --representative, --list, --ids or --derive is required")
    out = (a.out if a.out.is_absolute() else ROOT / a.out) / a.name
    if out.exists():
        raise SystemExit(f"{out} exists")
    s = Store(ROOT)
    ids, skipped = select(s, a)
    if not ids:
        raise SystemExit("no glyphs to repair")
    tum = tumbled()
    refs = ref_results(a.ref_round)
    issues = json.loads(a.issues.read_text()) if a.issues else None
    confirmed = {l["shape_id"] for r in s.records.values() if r.get("state") == "approved" for l in r["links"]}
    approved = {gid: r for gid, r in s.records.items() if r.get("state") == "approved" and r["group"] in REGIONS}
    by_symbol = {}
    for gid, r in approved.items():
        for l in r["links"]:
            by_symbol.setdefault((r["group"], l["symbol"]), []).append((l["slot"], gid))
    # an approved glyph of a character that is itself a component (中 for 忠), same region
    standalone = {(r["group"], r["char"]): gid for gid, r in approved.items()}
    ref_by_symbol = {}
    for gid in refs:
        if gid in s.glyphs:          # not an alias
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
              "rows": refs[gid]["rows"] if a.start_from_ref and gid in refs else rec["rows"],
              "ai_note": " ".join(rec["ai_note"]), "tumbled": tum.get(rec["cp"])}
        if a.start_from_ref and gid in refs:
            it["start"] = f"{refs[gid]['round']} 的结果（未导入）"
        # only forms the user confirmed (used by an approved glyph), or everything a person changed in an edited glyph
        it["linked"] = sorted({l["symbol"] for l in rec["links"] if rec["state"] == "edited" or l["shape_id"] in confirmed})
        if issues:
            it["issues"] = issues.get(gid, [])
        it["tumbled_match"] = region_match(it["char"], it["region"], it["tumbled"]) if it["tumbled"] and not a.derive and not a.symbols else "圆石没有此字"
        it["_ref"] = str(out / "refs" / f"{gid}.png")
        if rec["group"] in ("HW", "PR", "HW-L", "PR-L"):
            western_png(gid, it["char"], it["_ref"])
        else:
            reference_png(it["char"], it["region"], it["_ref"])
        if a.symbols:
            near = sorted((o for o, r in s.records.items() if r["group"] == rec["group"] and "alias" not in r and o != gid
                           and r["state"] != "draft" and abs(r["cp"] - rec["cp"]) <= 48 and r["cp"] >> 7 == rec["cp"] >> 7),
                          key=lambda o: (s.records[o]["state"] != "approved", abs(s.records[o]["cp"] - rec["cp"])))
            it["family"] = near[:8]
            if rec["group"].endswith("-L"):
                import unicodedata
                small_id = gid.removesuffix("-L")
                small_id = s.records.get(small_id, {}).get("alias", small_id)        # an alias: the glyph it shares
                if small_id in s.records and "rows" in s.records[small_id]:
                    st = s.records[small_id]["state"]
                    it["small"] = {"id": small_id, "rows": s.records[small_id]["rows"], "state": st,
                                   "mark": {"approved": "✓", "edited": "改"}.get(st, "")}
                base = unicodedata.normalize("NFD", it["char"])[0]
                base_id = f"U+{ord(base):04X}.{rec['group']}"
                if base != it["char"] and base_id in s.records and "rows" in s.records[base_id] and s.records[base_id]["state"] != "draft":
                    it["family"] = [base_id] + [x for x in it["family"] if x != base_id][:7]
            if 0x1100 <= rec["cp"] <= 0x11FF:        # conjoining jamo: the compatibility jamo of the same letter
                import unicodedata
                name = unicodedata.name(it["char"], "")
                for role in ("CHOSEONG ", "JUNGSEONG ", "JONGSEONG "):
                    name = name.replace(role, "LETTER ")
                try:
                    compat = f"U+{ord(unicodedata.lookup(name)):04X}.KR"
                except KeyError:
                    compat = None
                if compat in s.records and "alias" not in s.records[compat]:
                    it["family"] = [compat] + [x for x in it["family"] if x != compat][:7]
            it["same_char_approved"] = [o for o in s.sibling_ids(gid) if s.records[o].get("state") == "approved"]
            it["same_char"] = [o for o in s.sibling_ids(gid) if o not in it["same_char_approved"]]   # other versions, any state
            it["components"], it["tumbled"], it["tumbled_match"] = [], None, "符号轮不参考圆石"
            items.append(it)
            continue
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
                input_page(pg, bdir / f"input-{k:02d}.png", f"{a.name} {bid} 第 {k}/{len(pages)} 页 · " + (
                    "参考轮廓（大号规格）| 当前版本 | 小号版（写法依据）" if pg[0]["region"].endswith("-L") else
                    "参考（写法依据）| 当前版本" if a.symbols else "思源参考（写法依据）| 当前版本 | 圆石 18（像素范本）"))
        ex, rex = {}, {}
        if a.symbols:
            for it in batch:
                for x in it["same_char_approved"]:
                    ex.setdefault(x, set()).add(f"{it['char']}同码位")
                for x in it.get("same_char", []):
                    ex.setdefault(x, set()).add(f"{it['char']}同码位（未审）")
                for x in it["family"]:
                    ex.setdefault(x, set()).add("同族")
            exl = [{"id": x, "char": s.records[x]["char"] + ("✓" if s.records[x]["state"] == "approved" else ""), "rows": s.records[x]["rows"],
                    "for": sorted(v)} for x, v in sorted(ex.items())]
            for k in range(0, len(exl), 36):
                examples_page(exl[k:k + 36], bdir / f"examples-{k // 36 + 1:02d}.png", f"{bid} · 同族已有字形（✓ 为已通过；族内圆圈、括号、箭头头部等像素要一致）")
            lines = [f"{a.name} {bid}: {len(batch)} glyphs（符号）。每字的“当前”是改动基准，行号从 0 起；宽 × 高见每字标注。"]
            for it in batch:
                w, h = len(it["rows"][0]), len(it["rows"])
                kind = {"HW": "等宽 7×14", "PR": "比例（宽度可变，墨迹从第 0 列起，右留 1 列）", "HW-L": "大号等宽 7×18",
                        "PR-L": "大号比例（宽度可变 × 18，墨迹从第 0 列起）"}.get(it["region"], "全角 13×13")
                lines += ["", f"{it['id']} {it['char']} U+{it['cp']:04X} {kind} 当前 {w}×{h}{' 底稿' if it['state'] == 'draft' else ''}"
                          + (f" 同码位已通过={','.join(it['same_char_approved'])}" if it["same_char_approved"] else "")
                          + (f" 同码位其他版本（未审）={','.join(it['same_char'])}" if it.get("same_char") else "")
                          + (f" 同族={' '.join(s.records[x]['char'] + '(' + x + ')' for x in it['family'][:6])}" if it["family"] else "")]
                if it["ai_note"]:
                    lines.append(f"  底稿说明：{it['ai_note'].removeprefix('底稿：')}")
                if it.get("small"):
                    sm = it["small"]
                    lines.append(f"  小号版 {sm['id']}（{ {'approved': '已通过', 'edited': '用户改过，未通过'}.get(sm['state'], '未审核') }；写法依据）：")
                    lines += [f"    {y:2d} {r}" for y, r in enumerate(sm["rows"])]
                lines.append("  当前：")
                lines += [f"    {y:2d} {r}" for y, r in enumerate(it["rows"])]
            (bdir / "inputs.txt").write_text("\n".join(lines) + "\n")
            (bdir / "batch.json").write_text(json.dumps({"id": bid, "ids": [it["id"] for it in batch]}, ensure_ascii=False, indent=1))
            continue
        for it in batch:
            for x in it["same_char_approved"]:
                ex.setdefault(x, set()).add(f"{it['char']}同字")
            for c in it["components"]:
                for x in c["approved"]:
                    ex.setdefault(x, set()).add(f"{it['char']}的{c['symbol']}")
                for x in c["earlier_rounds"]:
                    rex.setdefault(x, set()).add(f"{it['char']}的{c['symbol']}")
        exl = [{"id": x, "char": approved[x]["char"], "rows": approved[x]["rows"], "for": sorted(v)} for x, v in sorted(ex.items())]
        for k in range(0, len(exl), 36):
            examples_page(exl[k:k + 36], bdir / f"examples-{k // 36 + 1:02d}.png", f"{bid} · 已审核通过的相关字（部件可逐像素复用）")
        rexl = [{"id": x, "char": refs[x]["char"], "rows": refs[x]["rows"], "for": sorted(v)} for x, v in sorted(rex.items())]
        for k in range(0, len(rexl), 36):
            examples_page(rexl[k:k + 36], bdir / f"earlier-{k // 36 + 1:02d}.png", f"{bid} · 前几轮已修的同部件字（待审核，写法保持一致）")
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
            if it["state"] == "edited":
                lines.append("  用户改过、还没通过：在当前版本上继续修，保留用户改过的地方，除非明显有错")
            if it["linked"]:
                lines.append(f"  本字已关联、写法经用户确认的部件（像素尽量不动）：{'、'.join(it['linked'])}")
            if it.get("start"):
                lines.append(f"  “当前”取自 {it['start']}")
            for x in it.get("issues", []):
                lines.append(f"  本轮要改：{x}")
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
                                                "batches": [b[0]["batch"] for b in batches], "ref_rounds": a.ref_round,
                                                "max_views": a.max_views},
                                               ensure_ascii=False, indent=1))
    # readers and prompts for this round
    rules = (ROOT / "docs/design-rules.md").read_text(encoding="utf-8")
    keep = [sec for sec in rules.split("\n## ") if sec.startswith(("1.", "4.", "5.", "7.") if a.symbols else ("1.", "2.", "3.", "8."))]
    reader = ROOT / "docs/lessons" / ("symbols.md" if a.symbols else "worker-lessons.md")
    (out / "LESSONS.md").write_text("# 本轮读本\n\n以下先是用户确认的规则（必须遵守），再是修字要点与自检清单。\n\n## "
                                    + "\n## ".join(keep) + "\n\n---\n\n" + reader.read_text(encoding="utf-8"))
    drafts = sum(i["state"] == "draft" for i in items)
    large = a.symbols and all(i["region"].endswith("-L") for i in items)
    task = DERIVE_TASK if a.derive else LARGE_TASK if large else SYMBOL_TASK if a.symbols else RECHECK_TASK if issues else EDITED_TASK if all(
        i["state"] == "edited" for i in items) else ("本批的字**是新增字的底稿**：由思源黑体点阵化（WorkBench 渲染加相位搜索），还没经 AI 或人工修。请在底稿基础上完整修字，"
            "像修第一轮那样认真处理每个字（结构、笔画、密处取舍），不要只做微调。" if drafts == len(items) else
            "本批的字**已经由 AI 修过**，你在**当前版本**的基础上继续修整。满意的字可以不改。" if not drafts else
            "本批大多数字**已经由 AI 修过**，在当前版本上继续修整，满意的可以不改；inputs.txt 标为“底稿”的字是新增字的底稿，要完整修。")
    kit, py, wf = (a.kit_path or str(out.relative_to(ROOT)), "python3", "tools/airepair/workflow.py") if a.portable else \
        (str(out), str(ROOT / ".venv/bin/python"), str(HERE / "workflow.py"))
    subs = {"{KIT}": kit, "{TASK}": task, "{PY}": py, "{WF}": wf, "{NAME}": a.name,
            "{MODEL}": a.model, "{EFFORT}": a.effort, "{WORKERS}": str(a.workers), "{N}": str(len(batches)),
            "{BATCH_SIZE}": str(a.batch_size), "{LAST}": batches[-1][0]["batch"],
            "{MAX_VIEWS}": {2: "两", 3: "三"}.get(a.max_views, str(a.max_views))}
    for name in ("PROTOCOL.md", "PROMPT.md"):
        proto = "PROTOCOL-large.md" if large else "PROTOCOL-symbols.md"
        t = (HERE / "templates" / (proto if a.symbols and name == "PROTOCOL.md" else name)).read_text(encoding="utf-8")
        for k, v in subs.items():
            t = t.replace(k, v)
        (out / name).write_text(t)
    print(json.dumps({"round": a.name, "glyphs": len(items), "batches": len(batches), "skipped": dict(skipped),
                      "tumbled": Counter(i["tumbled_match"].split("（")[0] for i in items),
                      "with_approved_components": sum(any(c["approved"] for c in i["components"]) for i in items)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
