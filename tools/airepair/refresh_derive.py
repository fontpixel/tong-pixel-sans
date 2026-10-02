"""Put the masters' repaired pixels into a derivation round prepared before they existed. Needs no fonts.

    python3 tools/airepair/refresh_derive.py --round DERIVE_KIT --masters MASTERS_KIT [MASTERS_KIT …]

A derivation round (prepare.py --derive) starts each regional glyph from a pixel copy of its master. When the
masters are still being repaired in another round, prepare the derivation round anyway, and once that round is
submitted run this: every glyph whose master has a submitted result in MASTERS_KIT/results/ starts from that
result instead ("当前" in items.json, the input pages and inputs.txt are rewritten). Refuses a round that has
already been started (state/ with claims). Changes nothing outside DERIVE_KIT.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare import derive_page  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--round", type=Path, required=True)
    ap.add_argument("--masters", type=Path, nargs="+", required=True)
    a = ap.parse_args()
    kit = a.round
    if any((kit / "state").glob("b*.json")):
        raise SystemExit(f"{kit} has been started; refresh it before claiming any batch")
    results = {}
    for m in a.masters:
        for p in sorted((m / "results").glob("*.json")):
            for g in json.loads(p.read_text(encoding="utf-8"))["glyphs"]:
                results[g["id"]] = (g["rows"], m.name)
    data = json.loads((kit / "items.json").read_text(encoding="utf-8"))
    items, changed, missing = data["items"], 0, []
    for it in items:
        mid = it["master"]["id"]
        if mid in results:
            rows, name = results[mid]
            if rows != it["rows"]:
                changed += 1
            it["rows"] = list(rows)
            it["master"]["source"] = f"{name} 的结果，未审核"
        else:
            missing.append(mid)
    (kit / "items.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    name = json.loads((kit / "round.json").read_text(encoding="utf-8"))["name"]
    by_batch = {}
    for it in items:
        by_batch.setdefault(it["batch"], []).append(it)
    for bid, batch in sorted(by_batch.items()):
        bdir = kit / "batches" / bid
        for old in bdir.glob("input-*.png"):
            old.unlink()
        for it in batch:
            it["_ref"], it["_master_ref"] = str(kit / it["reference"]), str(kit / it["master_reference"])
        pages = [batch[i:i + 16] for i in range(0, len(batch), 16)]
        for k, pg in enumerate(pages, 1):
            derive_page(pg, bdir / f"input-{k:02d}.png",
                        f"{name} {bid} 第 {k}/{len(pages)} 页 · 思源：本字地区 | 母版地区 · 母版（改动基准）| 旧版（仅参考）")
        lines = [f"{name} {bid}: {len(batch)} glyphs. 地区派生：每字的“当前”是母版（同一个字另一地区的版本）的逐像素副本，行号 0–12；"
                 "只改本地区写法与母版地区不同的笔画。“旧版”是这个地区以前独立修的版本，仅供参考。"]
        for it in batch:
            lines += ["", f"{it['id']} {it['char']} region={it['region']} 母版={it['master']['id']}（{it['master']['source']}）"]
            lines.append("  当前（= 母版副本，改动基准）：")
            lines += [f"    {y:2d} {r}" for y, r in enumerate(it["rows"])]
            lines.append("  旧版（仅参考，不作基础）：")
            lines += [f"    {y:2d} {r}" for y, r in enumerate(it["old_rows"])]
        (bdir / "inputs.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"glyphs": len(items), "from_results": len(items) - len(missing), "changed": changed,
                      "masters_without_result": sorted(set(missing))[:20]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
