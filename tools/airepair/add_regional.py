"""Give a region its own glyph where it borrows another region's glyph but writes the character differently.

    .venv/bin/python tools/airepair/add_regional.py [--dry-run]

For each (table, region) in REQUESTS, a code point the fonts have but the region has no glyph (nor alias)
for is served by the fallback order of tools/build.py. When the region's Source Han Sans outline (w320
and w400) differs from the outline of the region whose glyph is served, the region gets a draft that is
a pixel copy of the served glyph (state `draft`; docs/design-rules.md §2: 麵 in the simplified font
needs 麦, not 麥). A derivation round (prepare.py --derive) then changes only the strokes written
differently. Writes reports/add-regional.md and work/airepair/regional-drafts.txt.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT  # noqa: E402

sys.path.insert(0, str(ROOT / "tools"))
import build  # noqa: E402
from verify import table_codepoints  # noqa: E402
from store import Store  # noqa: E402
from add_glyphs import outline  # noqa: E402

REQUESTS = [("jp/jisx0208-l2.txt", "JP"), ("gb/gbk-hanzi.txt", "SC")]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    s = Store(ROOT)
    new, report, count = [], [], Counter()
    for table, region in REQUESTS:
        for cp in table_codepoints(ROOT / "build-data/coverage" / table):
            if f"U+{cp:04X}.{region}" in s.records or any(n["cp"] == cp and n["group"] == region for n in new):
                continue
            src = next((r for r in build.FALLBACK[region] if f"U+{cp:04X}.{r}" in s.records), None)
            if src is None:
                continue
            gid = f"U+{cp:04X}.{src}"
            target = s.records[gid].get("alias", gid)
            tgroup = target.rsplit(".", 1)[1]
            mine, theirs = outline(region, cp), outline(tgroup, cp)
            if mine is None or mine == theirs:
                count[f"{region} 写法相同，照旧借用"] += 1
                continue
            new.append({"group": region, "cp": cp, "rows": list(s.records[target]["rows"]), "state": "draft",
                        "ai_note": f"底稿：复制自 {target}（本地区思源写法不同，待从母版派生）"})
            count[f"{region} 新建底稿（复制自 {tgroup}）"] += 1
    lines = ["# 补地区版（底稿）", ""] + [f"- {k}：{v}" for k, v in sorted(count.items())]
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports/add-regional.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    if not a.dry_run and new:
        s.add_glyphs(new)
        (ROOT / "work/airepair/regional-drafts.txt").write_text("\n".join(f"U+{n['cp']:04X}.{n['group']}" for n in new) + "\n")


if __name__ == "__main__":
    main()
