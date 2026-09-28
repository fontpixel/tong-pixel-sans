"""Link IDS component forms to the glyphs you drew or approved. Pixels and review states never change.

    python3 tools/editor/auto_link.py [--dry-run] [--states approved,edited]      (needs numpy)

Every SC/TC/JP glyph is split into its BabelStone IDS components (segment.py, ids-mask-v1: masks are
subsets of the glyph's own black pixels; three passes learn each component's usual size and shape
from the clean splits of other glyphs). Only glyphs in the given states get links, and only for
component slots that are still free: existing links are kept, an outer component already linked
keeps its inner ones unlinked, and identical ink at the same coordinates reuses an existing form.
The run aborts if any link would change a pixel. Writes reports/auto-link.md (what was linked and
what could not be split).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import segment  # noqa: E402
from store import ROOT, Store  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--states", default="approved,edited")
    ap.add_argument("--workers", type=int, default=None)
    a = ap.parse_args()
    states = set(a.states.split(","))
    s = Store(ROOT)
    with s.lock():
        heads = {gid: s.current(gid) for gid, g in s.glyphs.items() if g["group"] in ("SC", "TC", "JP")}
    glyphs = [(gid, s.glyphs[gid]["char"], s.glyphs[gid]["locale"], heads[gid]["rows"]) for gid in heads]
    targets = {gid for gid, c in heads.items() if c["state"] in states}
    print(f"segmenting {len(glyphs)} glyphs (links only for {len(targets)} in states {sorted(states)})…", flush=True)
    results, prior = segment.segment_all(glyphs, workers=a.workers)
    plan, declined = segment.plan([g for g in glyphs if g[0] in targets], results, prior, s.w, s.h)
    for item in plan:
        item["expected_revision"] = heads[item["id"]]["revision"]
    before = {gid: len(heads[gid]["links"]) for gid in targets}
    report = {"glyphs_segmented": len(glyphs), "targets": len(targets),
              "planned_links": sum(len(i["links"]) for i in plan), "declined": dict(declined)}
    if not a.dry_run:
        report["result"] = s.auto_link(plan, segment.ALGORITHM)
    after = {gid: len(s.current(gid)["links"]) for gid in targets}
    gained = {gid: after[gid] - before[gid] for gid in targets if after[gid] > before[gid]}
    still_none = sorted(gid for gid in targets if after[gid] == 0)
    lines = ["# 自动关联部件（ids-mask-v1）", "",
             f"对象：状态为 {'、'.join(sorted(states))} 的字 {len(targets)} 个；像素和审核状态不变。" + ("（试运行，未写入）" if a.dry_run else ""), "",
             f"- 新增关联的字：{len(gained)}，新增关联 {sum(gained.values())} 处",
             f"- 计划中的关联：{report['planned_links']}；未能分出的部件：{json.dumps(report['declined'], ensure_ascii=False)}",
             f"- 结果：{json.dumps(report.get('result', {}), ensure_ascii=False)}",
             f"- 仍然没有任何关联的字：{len(still_none)}", "",
             "## 仍然没有任何关联的字", "",
             " ".join(f"{s.glyphs[g]['char']}{g[-3:]}" for g in still_none), ""]
    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    (out / "auto-link.md").write_text("\n".join(lines))
    print("\n".join(lines[:8]))


if __name__ == "__main__":
    main()
