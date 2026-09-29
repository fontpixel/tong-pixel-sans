"""Import a round's submitted versions into glyphs/ as new AI versions (state stays `ai`).

    .venv/bin/python tools/airepair/import_round.py NAME [--dry-run] [--exclude 字…] [--only-ids FILE] [--masters-only] [--alias-identical]

A glyph edited since the round was prepared (revision differs from items.json) or no longer in state
`ai` is skipped, never overwritten. The previous AI version is archived in history/ai-originals by
the store; links whose form pixels are no longer in the new version are removed from that glyph only.
With --masters-only, only glyphs that are their character's master are imported (the other regions
are left for a derivation round, whose import would otherwise find them changed).
With --alias-identical (derivation rounds), a derived glyph whose imported pixels equal its master's
current pixels becomes an alias of the master (docs/design-rules.md §2).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, ROUNDS, read_json  # noqa: E402
from store import Conflict, Store  # noqa: E402
from prepare import master_of  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--exclude", default="", help="characters not to import")
    ap.add_argument("--only-ids", help="file with the glyph ids to import (one per line)")
    ap.add_argument("--masters-only", action="store_true", help="import only glyphs that are their character's master")
    ap.add_argument("--alias-identical", action="store_true", help="derived glyphs identical to their master become aliases")
    a = ap.parse_args()
    rnd = Path(a.name) if "/" in a.name else ROUNDS / a.name
    info = read_json(rnd / "round.json")
    items = {i["id"]: i for i in read_json(rnd / "items.json")["items"]}
    only = set(Path(a.only_ids).read_text().split()) if a.only_ids else None
    prefix = f"AI 修字 {info['name']}（{info['model']} {info['effort']}，{info['created_at'][:10]}）"
    s = Store(ROOT)
    done, skipped, dropped, aliased = [], [], Counter(), []
    for p in sorted((rnd / "results").glob("*.json")):
        for g in read_json(p)["glyphs"]:
            if g["char"] in a.exclude or (only is not None and g["id"] not in only):
                skipped.append((g["id"], "not selected")); continue
            if a.masters_only and master_of(s, s.records[g["id"]]["cp"]) != g["id"]:
                skipped.append((g["id"], "not the master (left for derivation)")); continue
            if a.dry_run:
                cur = s.current(g["id"])
                if cur["revision"] != items[g["id"]]["revision"] or cur["state"] != "ai":
                    skipped.append((g["id"], "changed since the round was prepared"))
                else:
                    done.append(g["id"])
                continue
            try:
                out = s.import_ai(g["id"], g["rows"], prefix + ("：" + g["note"] if g["note"] else ""), items[g["id"]]["revision"])
            except Conflict as e:
                skipped.append((g["id"], str(e))); continue
            done.append(g["id"])
            dropped.update(out["dropped_links"])
            master = items[g["id"]].get("master", {}).get("id")
            if a.alias_identical and master and "alias" not in s.records[master] and s.records[master]["rows"] == g["rows"]:
                s.make_alias({"id": g["id"], "target": master, "expected_revision": out["current"]["revision"]})
                aliased.append(g["id"])
    print(json.dumps({"imported": len(done), "skipped": len(skipped), "skipped_detail": skipped[:50],
                      "links_removed": sum(dropped.values()), "aliased": len(aliased)}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
