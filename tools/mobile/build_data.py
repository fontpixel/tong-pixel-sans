"""Data for the phone editor: work/mobile/NAME-data.json from the list and selection of select_glyphs.py."""
import json, sys, re
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools/editor"), str(ROOT / "tools/airepair")]
from store import Store
from common import tumbled
from prepare import ref_results
import reference
name = sys.argv[1]
sel = json.loads((ROOT / "work/mobile" / f"{name}.json").read_text())
s = Store(ROOT); tum = tumbled(); refs = ref_results(["phase2a-common"])
kr = lambda r: "TC" if r == "KR" else r
by_sym = {}
for gid, r in s.records.items():
    if r.get("state") == "approved" and r["group"] in ("SC", "TC", "JP", "KR"):
        for l in r["links"]:
            f = s.forms.get(l["shape_id"])
            if f and not f.get("movable") and len(f["rows"]) == 13:
                by_sym.setdefault((kr(r["group"]), l["symbol"]), []).append((gid, f["rows"]))
out = []
for p in sel["glyphs"]:
    gid = p["id"]; r = s.records[gid]; cur = s.current(gid)
    start = refs[gid]["rows"] if gid in refs else r["rows"]
    svg = reference.svg(gid, r["char"], 14, 14).decode()
    d = re.search(r' d="([^"]*)"', svg).group(1); tr = re.search(r'transform="([^"]*)"', svg).group(1)
    ex = []
    for c in p["components"][:4]:
        for eg, rows in by_sym.get((kr(r["group"]), c["symbol"]), [])[:3]:
            ex.append({"sym": c["symbol"], "id": eg, "ch": s.records[eg]["char"], "form": rows})
    same = [{"id": o, "ch": r["char"], "rows": s.records[o]["rows"]} for o in s.sibling_ids(gid)
            if s.records[o].get("state") == "approved" and s.records[o]["group"] in ("SC", "TC", "JP", "KR")]
    out.append({"id": gid, "ch": r["char"], "rg": r["group"], "rev": cur["revision"], "start": start, "repo": r["rows"],
                "src": "第二期 A 结果" if gid in refs else "当前 AI 版", "tum": tum.get(r["cp"]), "d": d, "tr": tr,
                "why": [f"{c['symbol']}（待修 {c['queued']} 字用到，已有范例 {c['exemplars_before']}）" for c in p["components"][:4]],
                "ex": ex, "same": same})
(ROOT / "work/mobile" / f"{name}-data.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
print(len(out), sum(len(o["ex"]) for o in out), (ROOT / "work/mobile" / f"{name}-data.json").stat().st_size)
