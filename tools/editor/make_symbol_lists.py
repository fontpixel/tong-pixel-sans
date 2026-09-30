"""Editor lists of the non-Han glyphs: one per category, and one of the glyphs to review first.

    .venv/bin/python tools/editor/make_symbol_lists.py [--first]

Writes tools/editor/data/lists/非汉字·NN 类别.txt (every glyph with its own pixels in that category, all
groups, in code point order) and, with --first, 建议先审·非汉字.txt (the glyphs not approved yet, most used first:
ASCII, full-width forms, CJK punctuation and kana; then Latin-1, general punctuation, common symbols,
bopomofo and Hangul letters; then basic Greek and Cyrillic). Old 非汉字·* lists are replaced. Changes no
glyph.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from store import Store  # noqa: E402

LISTS = HERE / "data/lists"
ORDER = {"SC": 0, "TC": 1, "JP": 2, "KR": 3, "HW": 4, "PR": 5, "GEOMETRIC-FULL": 6, "GEOMETRIC-HALF": 7}
ASCII_PUNCT = [(0x21, 0x2F), (0x3A, 0x40), (0x5B, 0x60), (0x7B, 0x7E)]
CATEGORIES = [   # (name, code point ranges); the first category that matches wins
    ("01 全角标点", [(0x3000, 0x303F), (0xFE10, 0xFE1F), (0xFE30, 0xFE6F), (0xFF01, 0xFF0F), (0xFF1A, 0xFF20), (0xFF3B, 0xFF40),
                   (0xFF5B, 0xFF65)]),
    ("02 西文标点", ASCII_PUNCT + [(0xA1, 0xBF), (0x2000, 0x206F)]),
    ("03 数字", [(0x30, 0x39), (0xFF10, 0xFF19)]),
    ("04 拉丁字母", [(0x41, 0x5A), (0x61, 0x7A), (0xC0, 0x24F), (0x1E00, 0x1EFF), (0x2C60, 0x2C7F), (0xA720, 0xA7FF),
                   (0xFB00, 0xFB06), (0xFF21, 0xFF3A), (0xFF41, 0xFF5A)]),
    ("05 国际音标与修饰字母", [(0x250, 0x2FF), (0x1D00, 0x1DBF)]),
    ("06 组合附加符号", [(0x300, 0x36F), (0x1AB0, 0x1AFF), (0x1DC0, 0x1DFF), (0x20D0, 0x20FF), (0x3099, 0x309A)]),
    ("07 希腊字母", [(0x370, 0x3FF), (0x1F00, 0x1FFF)]),
    ("08 西里尔字母", [(0x400, 0x52F), (0x1C80, 0x1C8F), (0x2DE0, 0x2DFF), (0xA640, 0xA69F)]),
    ("09 亚美尼亚文", [(0x530, 0x58F)]),
    ("10 希伯来文", [(0x590, 0x5FF), (0xFB1D, 0xFB4F)]),
    ("11 阿拉伯文", [(0x600, 0x6FF), (0x750, 0x77F), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)]),
    ("12 泰文", [(0xE00, 0xE7F)]),
    ("13 老挝文", [(0xE80, 0xEFF)]),
    ("14 格鲁吉亚文", [(0x10A0, 0x10FF), (0x1C90, 0x1CBF)]),
    ("15 假名", [(0x3040, 0x30FF), (0x31F0, 0x31FF), (0xFF66, 0xFF9F), (0x1B000, 0x1B16F)]),
    ("16 注音", [(0x3100, 0x312F), (0x31A0, 0x31BF)]),
    ("17 韩文字母", [(0x1100, 0x11FF), (0x3130, 0x318F), (0xA960, 0xA97F), (0xD7B0, 0xD7FF), (0xFFA0, 0xFFDC)]),
    ("18 上下标、分数与罗马数字", [(0x2070, 0x209F), (0x2150, 0x218F)]),
    ("19 货币符号", [(0x24, 0x24), (0xA2, 0xA5), (0x20A0, 0x20CF), (0xFFE0, 0xFFE6)]),
    ("20 字母式符号", [(0x2100, 0x214F)]),
    ("21 箭头", [(0x2190, 0x21FF), (0x27F0, 0x27FF), (0x2900, 0x297F), (0x2B00, 0x2B2F), (0xFFE9, 0xFFEC)]),
    ("22 数学符号", [(0x2200, 0x22FF), (0x27C0, 0x27EF), (0x2980, 0x2AFF)]),
    ("23 技术与控制符号", [(0x2300, 0x23FF), (0x2400, 0x243F)]),
    ("24 带圈与带括号的字母数字", [(0x2460, 0x24FF), (0x2776, 0x2793), (0x1F100, 0x1F1FF)]),
    ("25 几何图形", [(0x25A0, 0x25FF), (0x2B30, 0x2BFF), (0xFFED, 0xFFEE)]),
    ("26 杂项符号与装饰", [(0x2600, 0x27BF)]),
    ("27 CJK 带圈字与方块字", [(0x3200, 0x33FF), (0x1F200, 0x1F2FF)]),
    ("28 汉字笔画、部首与结构符", [(0x2E80, 0x2FFF), (0x31C0, 0x31EF)]),
    ("29 制表符、方块与盲文（程序生成）", [(0x2500, 0x259F), (0x2800, 0x28FF), (0xE0A0, 0xE0D4)]),
]
# glyphs to review first: (tier, ranges) — the lower tier comes first
FIRST = [
    (0, ASCII_PUNCT + [(0x30, 0x39), (0x41, 0x5A), (0x61, 0x7A), (0xFF01, 0xFF5E), (0x3000, 0x303F), (0x3040, 0x30FF)]),
    (1, [(0xA0, 0xFF), (0x2010, 0x203B), (0x20AC, 0x20AC), (0x2103, 0x2103), (0x2116, 0x2116), (0x2122, 0x2122),
         (0x2160, 0x216B), (0x2170, 0x217B), (0x2190, 0x2199), (0x21D2, 0x21D4), (0x2200, 0x2265), (0x2460, 0x2473),
         (0x25A0, 0x25CF), (0x2605, 0x2606), (0x2640, 0x2642), (0x3100, 0x312F), (0x3131, 0x318E), (0xFF61, 0xFF9F)]),
    (2, [(0x391, 0x3C9), (0x401, 0x451), (0x100, 0x17F)]),
]


def category(cp):
    return next((name for name, ranges in CATEGORIES if any(a <= cp <= b for a, b in ranges)), None)


def main():
    s = Store(HERE.parent.parent)
    by_cat = {}
    first = []
    for gid, g in s.glyphs.items():
        cp = s.records[gid]["cp"]
        name = category(cp)
        if name is None:
            continue
        by_cat.setdefault(name, []).append(gid)
        tier = next((t for t, ranges in FIRST if any(a <= cp <= b for a, b in ranges)), None)
        if tier is not None and s.records[gid]["state"] != "approved":
            first.append((tier, cp, ORDER.get(g["group"], 9), gid))
    key = lambda gid: (s.records[gid]["cp"], ORDER.get(s.records[gid]["group"], 9))
    for old in LISTS.glob("非汉字·*.txt"):
        old.unlink()
    for name, _ in CATEGORIES:
        ids = sorted(by_cat.get(name, []), key=key)
        if ids:
            done = sum(s.records[i]["state"] == "approved" for i in ids)
            (LISTS / f"非汉字·{name}.txt").write_text(
                f"# {name}：{len(ids)} 个字形，已通过 {done}（tools/editor/make_symbol_lists.py）\n" + "\n".join(ids) + "\n",
                encoding="utf-8")
            print(f"{name}: {len(ids)}（已通过 {done}）")
    if "--first" not in sys.argv:
        return
    first.sort()
    (LISTS / "建议先审·非汉字.txt").write_text(
        "# 还没通过的非汉字，最常用的在前：ASCII、全角字符、CJK 标点和假名；然后是 Latin-1、常用标点和符号、注音、韩文字母；"
        "再后是基本希腊、西里尔和拉丁扩展字母（tools/editor/make_symbol_lists.py）\n" + "\n".join(g for *_, g in first) + "\n",
        encoding="utf-8")
    print("建议先审·非汉字:", len(first), {t: sum(1 for x in first if x[0] == t) for t in (0, 1, 2)})


if __name__ == "__main__":
    main()
