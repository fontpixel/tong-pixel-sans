"""Add the characters that tables require but no font has yet, as drafts ready for AI repair.

    .venv/bin/python tools/airepair/add_glyphs.py [--dry-run]
    .venv/bin/python tools/airepair/add_glyphs.py --symbols FILE [--dry-run]

For every (table, region) in REQUESTS, each code point that none of the 8 fonts has gets a glyph in
that region: a phase-searched draft (tools/editor/draft.py: WorkBench rendering of the region's Source
Han Sans at w320 with the sub-pixel phase search), state `draft`, the recipe in its `# AI:` note.
Where two regions ask for the same code point and their Source Han outlines are identical at w320
and w400, the second region gets an alias instead (as the original packages deduplicated). A region
whose Source Han lacks the character borrows the first region font that has it (noted). Combining
kana voicing marks become zero-advance proportional glyphs. A character with a compatibility or canonical
decomposition to an ideograph (Kangxi radicals, KS X 1001 compatibility ideographs) whose Source Han
outline equals that ideograph's becomes an alias of the ideograph's glyph. Symbols that Source Han lacks
become half-width and proportional drafts from Source Sans 3, or Noto Sans Math, like the other western
glyphs (their reference entries go to tools/editor/data/reference-western.txt). Han characters that no
Source Han Sans has (extension B and later) are drafted from Plangothic P1 (遍黑体, weight 400).
Writes a report to reports/add-glyphs.md.

With --symbols, the code points listed in FILE (lines “U+XXXX …”) are added instead of the tables':
- a symbol some region's Source Han Sans draws full-width gets a regional draft in the first such
  region (SC → TC → JP → KR; other regions fall back to it), or in every such region for CJK and
  vertical punctuation (U+3000–303F, FE10–FE1F, FE30–FE4F), sharing identical outlines as aliases;
  when Source Sans 3 or Noto Sans also has it, half-width and proportional drafts too (as ↑ ○);
- one Source Han Sans lacks: half-width and proportional drafts from the first western font that
  has it (Source Sans 3, Noto Sans, Noto Sans Math, Noto Sans Symbols, Noto Sans Symbols 2), except
  East Asian wide ones (⌚ ⏩ ☔ …), which get a full-width SC draft from that font;
- one Source Han Sans draws narrow: half-width and proportional drafts (from the western font, else
  Source Han Sans JP), the regions added to build-data/narrow-width.txt; combining marks become
  zero-advance proportional glyphs.
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
    ("jp/kana-marks.txt", "JP"), ("jp/joyo.txt", "JP"), ("jp/jisx0208-l2.txt", "JP"), ("jp/jinmeiyo.txt", "JP"),
    ("intl/iicore.txt", "TC"), ("kr/hangul-jamo.txt", "KR"),
    ("hk/hk-changyong.txt", "TC"),
    ("prc-lit/kangxi-radicals.txt", "SC"), ("prc-lit/radicals-supplement.txt", "SC"),
    ("prc-lit/tongyong-7000.txt", "SC"), ("prc-lit/hanyi-jianfan.txt", "SC"),
    ("prc-lit/fangzheng-jianfan.txt", "SC"), ("gb/gb12345.txt", "SC"),
]
ORDER = ["SC", "TC", "JP", "KR"]
COMBINING = {0x3099, 0x309A}
SYMBOL_FONTS = [("SourceSans3-VF.otf", (320,), "Source Sans 3 w320"), ("NotoSansMath-Regular.ttf", (), "Noto Sans Math")]
WESTERN_ORDER = [("SourceSans3-VF.otf", (320,), "Source Sans 3 w320"), ("NotoSans-VF.ttf", (320, 100), "Noto Sans w320"),
                 ("NotoSansMath-Regular.ttf", (), "Noto Sans Math"), ("NotoSansSymbols-Regular.ttf", (), "Noto Sans Symbols"),
                 ("NotoSansSymbols2-Regular.ttf", (), "Noto Sans Symbols 2")]
PUNCTUATION = [(0x3000, 0x303F), (0xFE10, 0xFE1F), (0xFE30, 0xFE4F)]   # drawn per region (、。 differ)
NARROW = ROOT / "build-data/narrow-width.txt"
WESTERN_REF = ROOT / "tools/editor/data/reference-western.txt"


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


def extension(cp):
    """Hash of the Plangothic P1 outline (None if it lacks the character or is not installed)."""
    path = FONTS / draft.EXTENSION[0]
    if not path.exists():
        return None
    from fontTools.ttLib import TTFont
    from fontTools.pens.recordingPen import DecomposingRecordingPen
    if "ext" not in _fonts:
        f = TTFont(str(path))
        _fonts["ext"] = (f, f.getBestCmap())
    f, cmap = _fonts["ext"]
    if cp not in cmap:
        return None
    gs = f.getGlyphSet()
    pen = DecomposingRecordingPen(gs)
    gs[cmap[cp]].draw(pen)
    return "ext:" + hashlib.sha256(repr(pen.value).encode()).hexdigest()


def add_references(entries):
    """Add (glyph id, label, face w, face h, leftmost ink column) lines to reference-western.txt, in order."""
    lines = WESTERN_REF.read_text(encoding="utf-8").splitlines()
    head = [l for l in lines if not l.startswith("U+")]
    body = {l.split("\t")[0]: l for l in lines if l.startswith("U+")}
    for gid, label, fw, fh, left in entries:
        body[gid] = f"{gid}\t{label}\t{fw}\t{fh}\t{left}"
    key = lambda g: (int(g[2:].split(".")[0], 16), g)
    WESTERN_REF.write_text("\n".join(head + [body[g] for g in sorted(body, key=key)]) + "\n", encoding="utf-8")


def left_column(rows):
    return min(x for r in rows for x, v in enumerate(r) if v == "#")


_cmaps = {}


def has(name, cp):
    if name not in _cmaps:
        from fontTools.ttLib import TTFont
        _cmaps[name] = set(TTFont(str(FONTS / name)).getBestCmap()) if (FONTS / name).exists() else set()
    return cp in _cmaps[name]


def advance(region, cp):
    """The Source Han Sans advance (units of 1000) of the character in a region, None if missing."""
    f, cmap = font(region)
    return f["hmtx"][cmap[cp]][0] if cp in cmap else None


def add_narrow(entries):
    """Add {region: {code points}} to build-data/narrow-width.txt (ranges rewritten in order)."""
    lines = NARROW.read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines:
        if not line or line.startswith("#") or line.split()[0] not in entries:
            out.append(line)
            continue
        region, *parts = line.split()
        cps = set(entries[region])
        for part in parts:
            a, _, b = part.partition("..")
            cps.update(range(int(a, 16), int(b or a, 16) + 1))
        ranges, run = [], None
        for cp in sorted(cps):
            if run and cp == run[1] + 1:
                run[1] = cp
            else:
                run = [cp, cp]; ranges.append(run)
        out.append(" ".join([region] + [f"{a:04X}" if a == b else f"{a:04X}..{b:04X}" for a, b in ranges]))
    NARROW.write_text("\n".join(out) + "\n", encoding="utf-8")


def symbols(listing, have):
    """(new glyphs, reference entries, narrow-width additions, report) for the listed symbols."""
    new, refs, narrow, report = [], [], {}, []
    sh_jp = (FONTS / "SourceHanSansJP-VF.otf", (320,), "思源 JP w320")
    for line in listing.read_text(encoding="utf-8").splitlines():
        if not line.startswith("U+"):
            continue
        cp = int(line.split()[0][2:], 16)
        ch = chr(cp)
        if cp in have:
            continue
        adv = {r: advance(r, cp) for r in ORDER}
        full = [r for r in ORDER if adv[r] is not None and adv[r] > 700]
        thin = [r for r in ORDER if adv[r] is not None and adv[r] <= 700]
        west = next(((FONTS / n, c, l) for n, c, l in WESTERN_ORDER if has(n, cp)), None)
        wide = unicodedata.east_asian_width(ch) in ("W", "F")
        if unicodedata.category(ch) == "Mn" and (thin or full):
            r = draft.proportional(sh_jp[0], sh_jp[1], ch, tight=False)
            new.append({"group": "PR", "cp": cp, "rows": r["rows"], "state": "draft",
                        "metrics": ["adv=0"] + ([f"x={r['x_offset']}"] if r["x_offset"] else []),
                        "ai_note": f"底稿：思源黑体 JP w320 组合用符号（零步进），字面 {r['face'][0]}×{r['face'][1]}"})
            refs.append((f"U+{cp:04X}.PR", sh_jp[2], *r["face"], left_column(r["rows"])))
            for reg in thin:
                narrow.setdefault(reg, set()).add(cp)
            report.append(f"{ch} U+{cp:04X}.PR 组合符号（零步进）")
            continue
        if not full and not thin and not west:
            report.append(f"{ch} U+{cp:04X}：参考字体都没有，跳过")
            continue
        parts = []
        if full:
            regions = full if any(a <= cp <= b for a, b in PUNCTUATION) else full[:1]
            made = {}
            for region in regions:
                h = outline(region, cp)
                same = next((gid for hh, gid in made.values() if hh == h), None)
                if same:
                    new.append({"group": region, "cp": cp, "alias": same})
                    parts.append(f"{region}=别名")
                    continue
                try:
                    d = draft.regional(ch, region)
                except ValueError as e:
                    parts.append(f"{region} 画不出（{e}）")
                    continue
                new.append({"group": region, "cp": cp, "rows": d["rows"], "state": "draft",
                            "ai_note": f"底稿：思源黑体 {region} w320 相位搜索 {d['phase_k']}/16，字面 {d['face'][0]}×{d['face'][1]}（补充符号）"})
                made[region] = (h, f"U+{cp:04X}.{region}")
                parts.append(region)
        elif wide and west:
            d = draft.regional(ch, "SC", font=west)
            new.append({"group": "SC", "cp": cp, "rows": d["rows"], "state": "draft",
                        "ai_note": f"底稿：{west[2]} 相位搜索 {d['phase_k']}/16，字面 {d['face'][0]}×{d['face'][1]}（补充符号，全角；思源黑体没有）"})
            parts.append(f"SC（{west[2]}）")
        src = west if west and (not full or west[2].startswith(("Source Sans 3", "Noto Sans w"))) and not (wide and not full) \
            else (sh_jp if thin and not west else None)
        if src:
            hw = draft.half_width(src[0], src[1], ch)
            pr = draft.proportional(src[0], src[1], ch, tight=True)
            for grp, r, metrics in (("HW", hw, ["adv=7"]), ("PR", pr, ["adv=auto"])):
                if r is None:
                    continue
                new.append({"group": grp, "cp": cp, "rows": r["rows"], "state": "draft", "metrics": metrics,
                            "ai_note": f"底稿：{src[2]} 相位搜索 {r['phase_k']}/16，字面 {r['face'][0]}×{r['face'][1]}（补充符号）"})
                refs.append((f"U+{cp:04X}.{grp}", src[2], *r["face"], left_column(r["rows"])))
                parts.append(grp)
            for reg in thin:
                narrow.setdefault(reg, set()).add(cp)
        report.append(f"{ch} U+{cp:04X}：" + "、".join(parts) + (f"（{src[2]}）" if src else ""))
    return new, refs, narrow, report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--symbols", type=Path, help="add the symbols listed in this file instead of the tables' characters")
    a = ap.parse_args()
    s = Store(ROOT)
    have = set()
    for _, prop, mono in build.faces(ROOT):
        have |= set(prop) | set(mono)
    if a.symbols:
        new, refs, narrow, report = symbols(a.symbols, have)
        counts = {}
        for n in new:
            k = f"{n['group']} {'别名' if 'alias' in n else '底稿'}"
            counts[k] = counts.get(k, 0) + 1
        lines = ["# 补充符号（底稿）", "", f"清单 {a.symbols.name}；新增 {len(new)} 条：" + "，".join(f"{k} {v}" for k, v in sorted(counts.items())),
                 "窄字（build-data/narrow-width.txt）：" + "，".join(f"{r} +{len(v)}" for r, v in sorted(narrow.items())), "", "## 每个符号", ""] + [f"- {r}" for r in report]
        (ROOT / "reports").mkdir(exist_ok=True)
        (ROOT / "reports/add-symbols.md").write_text("\n".join(lines) + "\n")
        print("\n".join(lines[:4]))
        if not a.dry_run:
            s.add_glyphs(new)
            add_references(refs)
            if narrow:
                add_narrow(narrow)
        return
    wanted = {}   # cp -> {region: [table names]}
    for table, region in REQUESTS:
        for cp in table_codepoints(ROOT / "build-data/coverage" / table):
            if cp in have or unicodedata.category(chr(cp)) in ("Cc", "Cs", "Co", "Cn"):
                continue
            wanted.setdefault(cp, {}).setdefault(region, []).append(table)
    new, report, compat, refs = [], [], [], []
    for cp in sorted(wanted):
        ch = chr(cp)
        u = unified(cp)
        # KS X 1001 / Big5 compatibility ideographs are drawn like their ideograph; the Japanese ones
        # (jinmeiyō 神 祖 …, U+FA30–) keep their older forms unless the outline is really the same
        if u is not None and ((0xF900 <= cp <= 0xFAFF and "KR" in wanted[cp]) or any(outline(r, cp) and outline(r, cp) == outline(r, u) for r in wanted[cp])):
            compat.append(cp)                          # drawn like its ideograph: share that glyph
            continue
        if not any(outline(r, cp) for r in ORDER) and cp not in COMBINING and not extension(cp):
            from fontTools.ttLib import TTFont
            found = next(((FONTS / name, coords, label) for name, coords, label in SYMBOL_FONTS
                          if (FONTS / name).exists() and cp in TTFont(str(FONTS / name)).getBestCmap()), None)
            if found:
                sans, coords, label = found
                hw = draft.half_width(sans, coords, ch)
                pr = draft.proportional(sans, coords, ch, tight=True)
                for grp, r, metrics in (("HW", hw, ["adv=7"]), ("PR", pr, ["adv=auto"])):
                    new.append({"group": grp, "cp": cp, "rows": r["rows"], "state": "draft", "metrics": metrics,
                                "ai_note": f"底稿：{label} 相位搜索 {r['phase_k']}/16，字面 {r['face'][0]}×{r['face'][1]}（{'、'.join(Path(t).stem for rr in wanted[cp] for t in wanted[cp][rr])}）"})
                    refs.append((f"U+{cp:04X}.{grp}", label, *r["face"], left_column(r["rows"])))
                report.append(f"{ch} U+{cp:04X}：思源黑体没有，按西文从 {label.split(' w')[0]} 生成等宽 / 比例底稿")
                continue
        if cp in COMBINING:
            r = draft.proportional(FONTS / "SourceHanSansJP-VF.otf", (320,), ch, tight=False)
            new.append({"group": "PR", "cp": cp, "rows": r["rows"], "state": "draft",
                        "metrics": ["adv=0"] + ([f"x={r['x_offset']}"] if r["x_offset"] else []),
                        "ai_note": f"底稿：思源黑体 JP w320 组合用符号（零步进），字面 {r['face'][0]}×{r['face'][1]}"})
            refs.append((f"U+{cp:04X}.PR", "思源 JP w320", *r["face"], left_column(r["rows"])))
            report.append(f"{ch} U+{cp:04X}.PR 组合符号")
            continue
        made = {}   # region -> (outline hash, glyph id)
        for region in sorted(wanted[cp], key=ORDER.index):
            src = region if outline(region, cp) else next((r for r in ORDER if outline(r, cp)), None)
            if src is None and extension(cp):
                src = region                           # draft.regional falls back to Plangothic P1
            if src is None:
                report.append(f"{ch} U+{cp:04X}：思源黑体各地区和遍黑体都没有此字，跳过")
                continue
            h = outline(src, cp) or extension(cp)
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
            note = f"底稿：{d['label'].replace('思源 ', '思源黑体 ')} 相位搜索 {d['phase_k']}/16，字面 {d['face'][0]}×{d['face'][1]}（{tables}）"
            if d["label"].startswith("遍黑体"):
                note += "；思源黑体各地区都没有此字，取自遍黑体 P1（Plangothic，OFL）"
            elif src != region:
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
        if refs:
            add_references(refs)
        drafts = [f"U+{n['cp']:04X}.{n['group']}" for n in new if "alias" not in n and n["group"] in ORDER]
        (ROOT / "work/airepair").mkdir(parents=True, exist_ok=True)
        (ROOT / "work/airepair/new-glyphs.txt").write_text("\n".join(drafts) + "\n")
        print(f"added; {len(drafts)} regional drafts listed in work/airepair/new-glyphs.txt")


if __name__ == "__main__":
    main()
