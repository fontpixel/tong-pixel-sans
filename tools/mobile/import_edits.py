"""Import the phone editor's results into glyphs/ (as the user's own saves).

    .venv/bin/python tools/mobile/import_edits.py NAME DIR [--dry-run]

NAME is the phone data (work/mobile/NAME-data.json, from build_data.py); DIR holds one JSON file per
glyph ({id, rev, rows, state, note, t}), e.g. the `edits` collection of the phone editor's database
saved by Claude, or the “复制全部结果” text saved as one file (a JSON list).
approved -> state approved; edited -> edited (unchanged pixels keep the glyph's state); skipped ->
nothing. A glyph whose pixels changed on the computer since the phone data was built is skipped; one
already carrying the phone version is left alone (so the import can be rerun). A form link whose pixels
the phone edit removed is unlinked from that glyph first (links never change pixels; forms stay).
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools/editor"))
from store import Conflict, Store  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("name")
ap.add_argument("src", type=Path)
ap.add_argument("--dry-run", action="store_true")
a = ap.parse_args()
built = {g["id"]: g for g in json.loads((ROOT / "work/mobile" / f"{a.name}-data.json").read_text())}
entries = []
for p in sorted(a.src.rglob("*.json")) if a.src.is_dir() else [a.src]:
    v = json.loads(p.read_text())
    entries += v if isinstance(v, list) else [v]
s = Store(ROOT)
done, skipped, todo = Counter(), [], []
for e in sorted(entries, key=lambda e: e["id"]):
    if e["state"] not in ("approved", "edited"):
        done[e["state"]] += 1
        continue
    cur = s.current(e["id"])
    if cur["rows"] == e["rows"] and (cur["state"] == e["state"] or e["state"] == "edited"):
        done["already imported"] += 1
        continue
    if cur["rows"] != built[e["id"]]["repo"]:
        skipped.append((e["id"], "changed on the computer since"))
        continue
    todo.append(e)
if a.dry_run:
    done["to import"] = len(todo)
else:
    # one pass over the form library: drop every link whose pixels a phone edit removed
    lib, unlink = s._library(), []
    for e in todo:
        cur = s.current(e["id"])
        ink = {(y, x) for y, r in enumerate(e["rows"]) for x, v in enumerate(r) if v == "#"}
        keep = []
        for l in cur["links"]:
            f = lib["shapes"].get(l["shape_id"])
            placed = s._placed(f, l, 13, 13) if f else None
            if placed is not None and all((y, x) in ink for y, r in enumerate(placed) for x, v in enumerate(r) if v == "#"):
                keep.append(l)
        if len(keep) < len(cur["links"]):
            unlink.append(s._revision(cur, cur["rows"], keep, "解除关联，保留当前像素", cur["approved"]))
            done["links removed"] += len(cur["links"]) - len(keep)
    if unlink:
        s._collect(lib, {v["id"]: v for v in unlink})
        s._commit_shapes(unlink, lib)
    for e in todo:
        try:
            new = s.save({"id": e["id"], "expected_revision": s.current(e["id"])["revision"], "rows": e["rows"],
                          "approved": e["state"] == "approved", "note": "手机修字" + ("：" + e["note"] if e.get("note") else "")})
            done[new["state"]] += 1
        except (Conflict, ValueError) as err:
            skipped.append((e["id"], str(err)))
print(json.dumps({"result": done, "skipped": skipped}, ensure_ascii=False, indent=1))
