"""Add the characters that tables require but no font has yet, as drafts ready for AI repair.

    .venv/bin/python tools/airepair/add_glyphs.py [--dry-run]

For every (table, region) in REQUESTS, each code point that none of the 8 fonts has gets a glyph in
that region: a phase-searched draft (tools/editor/draft.py: WorkBench rendering of the region's Source
Han Sans at w320 with the sub-pixel phase search), state `draft`, the recipe in its `# AI:` note.
Where two regions ask for the same code point and their Source Han outlines are identical at w320
and w400, the second region gets an alias instead (as the original packages deduplicated). A region
whose Source Han lacks the character borrows the first region font that has it (noted). Combining
kana voicing marks become zero-advance proportional glyphs. A character with a compatibility or canonical
decomposition to an ideograph (Kangxi radicals, KS X 1001 compatibility ideographs) whose Source Han
outline equals that ideograph's becomes an alias of the ideograph's glyph. Symbols that Source Han lacks
but Source Sans 3 has become half-width and proportional drafts, like the other western glyphs.
Writes a report to reports/add-glyphs.md.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import FONTS, ROOT  # noqa: E402

sys.path.insert(0, str(ROOT / "tools"))
import build  # noqa: E402
from verify import table_codepoints  # noqa: E402
from store import Store  # noqa: E402
import draft  # noqa: E402

REQUESTS = [  # (table under build-data/coverage/, region)
    ("kr/ksx1001-hanja.txt", "KR"), ("kr/ksx1001-symbols.txt", "KR"),
    ("jp/kana-marks.txt", "JP"), ("jp/joyo.txt", "JP"),
    ("hk/hk-changyong.txt", "TC"),
    ("prc-lit/kangxi-radicals.txt", "SC"), ("prc-lit/radicals-supplement.txt", "SC"),
    ("prc-lit/tongyong-7000.txt", "SC"), ("prc-lit/hanyi-jianfan.txt", "SC"),
    ("prc-lit/fangzheng-jianfan.txt", "SC"), ("gb/gb12345.txt", "SC"),
]
ORDER = ["SC", "TC", "JP", "KR"]
COMBINING = {0x3099, 0x309A}


def unified(cp):
    """The ideograph a radical or compatibility ideograph decomposes to (None otherwise)."""
    d = unicodedata.decomposition(chr(cp)).split()
    if not d:
        return None
    u = int(d[1] if d[0].startswith("<") else d[0], 16)
    return u if unicodedata.name(chr(u), "").startswith("CJK UNIFIED") else None


_fonts = {}


def font(region):
    if region not in _fonts:
        from fontTools.ttLib import TTFont
        f = TTFont(str(FONTS / f"SourceHanSans{region}-VF.otf"))
        _fonts[region] = (f, f.getBestCmap())
    return _fonts[region]


def outline(region, cp):
    """Hash of the decomposed outline at w320 and w400 (None if the font lacks the character)."""
    from fontTools.pens.recordingPen import DecomposingRecordingPen
    f, cmap = font(region)
    name = cmap.get(cp)
    if name is None:
        return None
    h = hashlib.sha256()
    for w in (320, 400):
        gs = f.getGlyphSet(location={"wght": w})
        pen = DecomposingRecordingPen(gs)
        gs[name].draw(pen)
        h.update(repr(pen.value).encode())
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    s = Store(ROOT)
    have = set()
    for _, prop, mono in build.faces(ROOT):
        have |= set(prop) | set(mono)
    wanted = {}   # cp -> {region: [table names]}
    for table, region in REQUESTS:
        for cp in table_codepoints(ROOT / "build-data/coverage" / table):
            if cp in have or unicodedata.category(chr(cp)) in ("Cc", "Cs", "Co", "Cn"):
                continue
            wanted.setdefault(cp, {}).setdefault(region, []).append(table)
    new, report, compat = [], [], []
    for cp in sorted(wanted):
        ch = chr(cp)
        u = unified(cp)
        if u is not None and (0xF900 <= cp <= 0xFAFF or any(outline(r, cp) and outline(r, cp) == outline(r, u) for r in wanted[cp])):
            compat.append(cp)                          # drawn like its ideograph: share that glyph
            continue
        if not any(outline(r, cp) for r in ORDER) and cp not in COMBINING:
            sans = FONTS / "SourceSans3-VF.otf"
            from fontTools.ttLib import TTFont
            if cp in TTFont(str(sans)).getBestCmap():
                hw = draft.half_width(sans, (320,), ch)
                pr = draft.proportional(sans, (320,), ch, tight=True)
                for grp, r, metrics in (("HW", hw, ["adv=7"]), ("PR", pr, ["adv=auto"])):
                    new.append({"group": grp, "cp": cp, "rows": r["rows"], "state": "draft", "metrics": metrics,
                                "ai_note": f"底稿：Source Sans 3 w320 相位搜索 {r['phase_k']}/16，字面 {r['face'][0]}×{r['face'][1]}（{'、'.join(Path(t).stem for rr in wanted[cp] for t in wanted[cp][rr])}）"})
                report.append(f"{ch} U+{cp:04X}：思源黑体没有，按西文从 Source Sans 3 生成等宽 / 比例底稿")
                continue
        if cp in COMBINING:
            r = draft.proportional(FONTS / "SourceHanSansJP-VF.otf", (320,), ch, tight=False)
            new.append({"group": "PR", "cp": cp, "rows": r["rows"], "state": "draft",
                        "metrics": ["adv=0"] + ([f"x={r['x_offset']}"] if r["x_offset"] else []),
                        "ai_note": f"底稿：思源黑体 JP w320 组合用符号（零步进），字面 {r['face'][0]}×{r['face'][1]}"})
            report.append(f"{ch} U+{cp:04X}.PR 组合符号")
            continue
        made = {}   # region -> (outline hash, glyph id)
        for region in sorted(wanted[cp], key=ORDER.index):
            src = region if outline(region, cp) else next((r for r in ORDER if outline(r, cp)), None)
            if src is None:
                report.append(f"{ch} U+{cp:04X}：思源黑体各地区都没有此字，跳过")
                continue
            h = outline(src, cp)
            same = next((gid for (hh, gid) in made.values() if hh == h), None)
            tables = "、".join(Path(t).stem for t in wanted[cp][region])
            if same:
                new.append({"group": region, "cp": cp, "alias": same})
                report.append(f"{ch} U+{cp:04X}.{region} = {same}（思源轮廓相同）")
                continue
            try:
                d = draft.regional(ch, src)
            except ValueError as e:
                report.append(f"{ch} U+{cp:04X}.{region}：{e}")
                continue
            note = f"底稿：思源黑体 {src} w320 相位搜索 {d['phase_k']}/16，字面 {d['face'][0]}×{d['face'][1]}（{tables}）"
            if src != region:
                note += f"；思源 {region} 没有此字，借用 {src} 的字形"
            gid = f"U+{cp:04X}.{region}"
            new.append({"group": region, "cp": cp, "rows": d["rows"], "state": "draft", "ai_note": note})
            made[region] = (h, gid)
    # radicals and compatibility ideographs → the ideograph's glyph (in any region, following aliases)
    ids_after = {f"U+{n['cp']:04X}.{n['group']}": n for n in new}
    for cp in compat:
        uni = unified(cp)
        region_first = sorted(wanted[cp], key=ORDER.index)[0]
        target = None
        for region in [region_first] + [r for r in ["KR", "TC", "JP", "SC"] if r != region_first]:
            gid = f"U+{uni:04X}.{region}"
            rec = s.records.get(gid) or ids_after.get(gid)
            if rec is None:
                continue
            target = rec["alias"] if "alias" in rec else gid
            break
        if target:
            new.append({"group": region_first, "cp": cp, "alias": target})
            continue
        # the ideograph itself is missing too: draw the radical
        src = region_first if outline(region_first, cp) else next((r for r in ORDER if outline(r, cp)), None)
        try:
            d = draft.regional(chr(cp), src)
        except (ValueError, TypeError):
            report.append(f"{chr(cp)} U+{cp:04X}：对应的汉字 U+{uni:04X} 也没有，思源也画不出，跳过")
            continue
        new.append({"group": region_first, "cp": cp, "rows": d["rows"], "state": "draft",
                    "ai_note": f"底稿：思源黑体 {src} w320 相位搜索 {d['phase_k']}/16，字面 {d['face'][0]}×{d['face'][1]}（部首；对应的汉字 {chr(uni)} 本字体没有）"})
        report.append(f"{chr(cp)} U+{cp:04X}：对应的汉字 {chr(uni)} 本字体没有，直接画部首")
    counts = {}
    for n in new:
        k = f"{n['group']} {'别名' if 'alias' in n else '底稿'}"
        counts[k] = counts.get(k, 0) + 1
    lines = ["# 新增字（底稿）", "", f"新增 {len(new)} 条：" + "，".join(f"{k} {v}" for k, v in sorted(counts.items())),
             f"共用对应汉字字形的部首和兼容汉字：{len(compat)}", "", "## 说明", ""] + [f"- {r}" for r in report]
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports/add-glyphs.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:4]))
    if not a.dry_run:
        s.add_glyphs(new)
        drafts = [f"U+{n['cp']:04X}.{n['group']}" for n in new if "alias" not in n and n["group"] != "PR"]
        (ROOT / "work/airepair").mkdir(parents=True, exist_ok=True)
        (ROOT / "work/airepair/new-glyphs.txt").write_text("\n".join(drafts) + "\n")
        print(f"added; {len(drafts)} regional drafts listed in work/airepair/new-glyphs.txt")


if __name__ == "__main__":
    main()
