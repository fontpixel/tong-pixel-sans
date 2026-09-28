"""Rank not-yet-approved glyphs by how many other glyphs share their components.

    python3 tools/editor/rank_representative.py

Components are BabelStone IDS nodes (depth <= 3, composites included, single strokes
excluded), keyed by region, component and position (e.g. SC 氵·左). Usage is counted over
every SC/TC glyph with its own pixels. A component whose SC and TC forms
are the same (class “shared” in data/cross-region.json) is one key for both
regions, so an approved SC glyph also covers it for TC. Components already present in a
currently approved glyph count as covered. Greedy order: each next glyph is the one whose
still-uncovered components are used by the most glyphs in total. Stops when no remaining
glyph covers an uncovered component used by at least MIN_USES glyphs.

Writes data/representative.json for the editor's “最具代表性” filters. Changes only the review
order, never pixels. Rerun after approving many glyphs to get the next round.
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from store import Store, ROOT
from structure import database, POSITIONS

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from verify import table_codepoints  # noqa: E402

HERE = Path(__file__).resolve().parent
PRIMITIVES = set("一丨丿丶乀乁乙乚亅𠃌𠃍")
MIN_USES = 3
UNCOMMON_FACTOR = 0.7  # prefer familiar characters when coverage is similar
COMMON_TABLES = {"SC": ROOT / "build-data/coverage/prc-lit/changyong-3500.txt",
                 "TC": ROOT / "build-data/coverage/tw/tw-changyong-4808.txt"}


SHARED = set()  # component symbols whose SC and TC forms are the same (cross-region table)


def load_shared():
    path = HERE / "data/cross-region.json"
    if path.exists():
        data = json.loads(path.read_text())
        SHARED.update(s for s, v in data["components"].items() if v.get("SC-TC", {}).get("class") == "shared")


def components(db, char, locale):
    info = db.lookup(char, locale)
    if not info["available"]:
        return set()
    out = set()

    def visit(node, depth):
        if not node["children"] or depth > 2:
            return
        for i, child in enumerate(node["children"]):
            sym = child["symbol"]
            if (sym not in PRIMITIVES and not sym.startswith("{") and sym not in ("？", "?") and sym != char
                    and not 0x2FF0 <= ord(sym[0]) <= 0x2FFF):  # skip bare IDS operators
                position = POSITIONS.get(node["symbol"], ["未知"] * len(node["children"]))[i]
                out.add(("SC+TC" if sym in SHARED and locale in ("SC", "TC") else locale, sym, position))
            visit(child, depth + 1)

    visit(info["tree"], 0)
    return out


def main():
    db = database()
    load_shared()
    store = Store(ROOT)
    queue = {gid: g for gid, g in store.glyphs.items() if g["group"] in ("SC", "TC")}
    approved = {gid for gid in queue if store.records[gid]["state"] == "approved"}
    usage = Counter()
    for g in queue.values():
        usage.update(components(db, g["char"], g["locale"]))
    comps = {gid: components(db, g["char"], g["locale"]) for gid, g in queue.items()}
    common = {loc: table_codepoints(p) for loc, p in COMMON_TABLES.items()}
    factor = {gid: 1.0 if ord(g["char"]) in common.get(g["locale"], ()) else UNCOMMON_FACTOR for gid, g in queue.items()}
    covered = set().union(*(comps[g] for g in approved if g in comps))
    candidates = {gid for gid in queue if gid not in approved and comps[gid]}
    by_comp = defaultdict(set)
    for gid in candidates:
        for c in comps[gid]:
            by_comp[c].add(gid)
    ranked = []
    while candidates:
        def gain(gid):
            return sum(usage[c] for c in comps[gid] - covered if usage[c] >= MIN_USES)
        best = max(candidates, key=lambda g: (gain(g) * factor[g], -len(comps[g]), g))
        g = gain(best)
        if g <= 0:
            break
        new = sorted((c for c in comps[best] - covered if usage[c] >= MIN_USES), key=lambda c: -usage[c])
        ranked.append({"id": best, "char": queue[best]["char"], "locale": queue[best]["locale"], "gain": g,
                       "common": factor[best] == 1.0,
                       "components": [{"symbol": s, "position": p, "uses": usage[(l, s, p)]} for l, s, p in new]})
        covered |= set(new)
        candidates.discard(best)
    out = {"schema": 1, "min_uses": MIN_USES, "approved_at_ranking": len(approved),
           "components_counted": len(usage), "glyphs": ranked}
    (HERE / "data/representative.json").write_text(json.dumps(out, ensure_ascii=False))
    print(len(ranked), "representative glyphs (SC", sum(r["locale"] == "SC" for r in ranked), "/ TC", sum(r["locale"] == "TC" for r in ranked), "); common", sum(r["common"] for r in ranked))
    print("top 40:", "".join(r["char"] for r in ranked[:40]))
    for r in ranked[:8]:
        print(" ", r["char"], r["id"], r["gain"], " ".join(f'{c["symbol"]}·{c["position"]}({c["uses"]})' for c in r["components"][:5]))


if __name__ == "__main__":
    main()
