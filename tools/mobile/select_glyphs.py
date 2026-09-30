"""Pick the glyphs whose hand repair helps the next AI rounds most, as a list for the editors.

    .venv/bin/python tools/mobile/select_glyphs.py NAME (--rounds R1 R2 … | --unapproved) [--count 150]

Demand: the components (IDS parts, not single strokes) of the glyphs still to be repaired in the
given rounds under work/airepair/ (unsubmitted batches only), or with --unapproved of every regional
glyph (SC TC JP) not approved yet, for a review list. With --unapproved a candidate's value is also
weighted by how common the character is (×3 for SC 常用 2500 / JP 教育汉字 / TC 常用 4808's first
half, ×2 for SC 3500 / JP 常用 / the rest of TC 4808). Supply: approved glyphs that serve as
exemplars for a component the way tools/airepair/prepare.py finds them (form links; an approved
glyph of the component character itself). A component is worth demand × (1, ½, ¼, ⅒ for 0, 1, 2,
3+ exemplars). Candidates are AI glyphs or drafts of common characters (the tables below); a glyph
is worth its four most valuable components (and itself as a component), divided by 1 + ⅛ of its
component count so that clear, common characters come first; each pick is the one adding the most
value, after which its components count as one exemplar richer. Writes tools/editor/data/lists/NAME.txt (glyph ids, best first) and
work/mobile/NAME.json (why each was picked). Changes no glyph.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools/editor"), str(ROOT / "tools/airepair")]
from store import Store  # noqa: E402
from segment import is_stroke  # noqa: E402
from verify import table_codepoints  # noqa: E402

REGIONS = ("SC", "TC", "JP", "KR")
COMMON = {"SC": ["prc-lit/changyong-3500.txt"], "TC": ["tw/tw-changyong-4808.txt", "hk/hk-changyong.txt"],
          "JP": ["jp/joyo.txt", "jp/jinmeiyo.txt"]}
WEIGHT = [1.0, 0.5, 0.25, 0.1]


def key_region(r):
    return "TC" if r == "KR" else r


def pending(rnd):
    """Glyph ids of a round's batches not yet submitted."""
    d = ROOT / "work/airepair" / rnd
    out = []
    for b in sorted((d / "batches").iterdir()):
        st = d / "state" / f"{b.name}.json"
        if st.exists() and json.loads(st.read_text()).get("status") == "submitted":
            continue
        out += json.loads((b / "batch.json").read_text())["ids"]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name")
    ap.add_argument("--rounds", nargs="+", default=[])
    ap.add_argument("--unapproved", action="store_true", help="demand from every unapproved regional glyph")
    ap.add_argument("--count", type=int, default=150)
    a = ap.parse_args()
    s = Store(ROOT)
    parts_cache = {}

    def comps(gid):
        if gid not in parts_cache:
            try:
                _, parts = s._parts(gid)
            except Exception:
                parts = []
            parts_cache[gid] = sorted({p["symbol"] for p in parts if p["key"] != "whole" and not is_stroke(p["symbol"])})
        return parts_cache[gid]

    if a.unapproved:
        queue = [g for g, r in s.records.items() if r["group"] in ("SC", "TC", "JP") and "alias" not in r
                 and r.get("state") in ("ai", "edited", "draft")]
    else:
        queue = list(dict.fromkeys(g for r in a.rounds for g in pending(r) if g in s.records))
    weight = {}
    if a.unapproved:
        tiers = {"SC": [("prc-lit/changyong-2500.txt", 3), ("prc-lit/changyong-3500.txt", 2)],
                 "JP": [("jp/kyoiku.txt", 3), ("jp/joyo.txt", 2)]}
        for reg, tl in tiers.items():
            for t, w in reversed(tl):
                for cp in table_codepoints(ROOT / "build-data/coverage" / t):
                    weight[f"U+{cp:04X}.{reg}"] = w
        tw = table_codepoints(ROOT / "build-data/coverage/tw/tw-changyong-4808.txt")
        for i, cp in enumerate(tw):
            weight[f"U+{cp:04X}.TC"] = 3 if i < len(tw) // 2 else 2
    demand, users = Counter(), defaultdict(list)
    for g in queue:
        reg = key_region(s.records[g]["group"])
        for c in comps(g):
            demand[reg, c] += 1
            users[reg, c].append(g)
    exemplars = Counter()
    for gid, r in s.records.items():
        if r.get("state") == "approved" and r["group"] in REGIONS:
            reg = key_region(r["group"])
            for sym in {l["symbol"] for l in r["links"]} | {r["char"]}:
                exemplars[reg, sym] += 1
    cands = set()
    for reg, tables in COMMON.items():
        for t in tables:
            for cp in table_codepoints(ROOT / "build-data/coverage" / t):
                g = f"U+{cp:04X}.{reg}"
                if g in s.records and "alias" not in s.records[g]:
                    cands.add(g)
    cands = [g for g in cands if s.records[g].get("state") in ("ai", "draft") and s.records[g]["group"] in ("SC", "TC", "JP")]

    def value(g):
        reg = key_region(s.records[g]["group"])
        keys = {(reg, c) for c in comps(g)} | {(reg, s.records[g]["char"])}
        vals = sorted((demand[k] * WEIGHT[min(exemplars[k], 3)] for k in keys), reverse=True)
        return weight.get(g, 1) * sum(vals[:4]) / (1 + len(comps(g)) / 8), keys

    picked = []
    scores = {g: value(g)[0] for g in cands}
    for _ in range(a.count):
        # lazy greedy: values only fall as exemplars are added
        order = sorted(scores, key=lambda g: -scores[g])
        best = None
        for g in order:
            v, keys = value(g)
            scores[g] = v
            if best is None or v > best[1]:
                best = (g, v, keys)
            nxt = order[order.index(g) + 1] if order.index(g) + 1 < len(order) else None
            if nxt is None or scores[nxt] <= best[1]:
                break
        g, v, keys = best
        if v <= 0:
            break
        why = sorted(((demand[k], exemplars[k], k[1]) for k in keys if demand[k]), reverse=True)
        picked.append({"id": g, "char": s.records[g]["char"], "value": round(v, 1),
                       "components": [{"symbol": c, "queued": d, "exemplars_before": e} for d, e, c in why]})
        for k in keys:
            exemplars[k] += 1
        del scores[g]
    lst = ROOT / "tools/editor/data/lists" / f"{a.name}.txt"
    lst.write_text((f"# 优先审核的汉字：常用，且部件在未审字里用得多、已通过范例少（tools/mobile/select_glyphs.py --unapproved）\n"
                    if a.unapproved else f"# 手修后最能帮到后续 AI 轮次的字（tools/mobile/select_glyphs.py，轮次 {' '.join(a.rounds)}）\n")
                   + "\n".join(p["id"] for p in picked) + "\n", encoding="utf-8")
    (ROOT / "work/mobile").mkdir(parents=True, exist_ok=True)
    (ROOT / "work/mobile" / f"{a.name}.json").write_text(json.dumps({"rounds": a.rounds, "queued": len(queue), "glyphs": picked},
                                                                  ensure_ascii=False, indent=1))
    print(len(queue), "queued;", len(picked), "picked:", "".join(p["char"] for p in picked))
    print(Counter(p["id"][-2:] for p in picked))


if __name__ == "__main__":
    main()
