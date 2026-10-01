"""Build the generated part of the Tong Pixel Sans home page (site/gen/, not in git).

    .venv/bin/python site/build.py            (after tools/export.py has filled site/downloads/)

Reads the plain-text glyph sources through tools/build.py (so the page shows exactly the glyphs the
fonts are built from) and writes:

  gen/g/<PAGE>.json   glyph bitmaps of the four regional proportional faces, one file per 256 code
                      points, fetched by the page only when a character on that page is shown
  gen/site.json       featured characters, component and review examples, character tables, counts
  gen/coverage.png    the Basic Multilingual Plane, one pixel per code point: lit = in the fonts
  gen/tables.png      the same map for every required character table, stacked (256 x 256 each)
  gen/status.png      every drawn glyph bitmap (aliases not counted) as one pixel; value = review state
  gen/favicon.svg     the 通 glyph
  gen/fonts/*.woff2   subsets of the four vector fonts with just the characters the page itself uses
  gen/fonts.css       @font-face rules: subset first by unicode-range, the full font in downloads/
                      only for characters outside it (the browser loads it only when needed)

It also writes the Simplified Chinese text of i18n/zh.json into index.html (the text shown before any script
runs). Run it again after changing the page text (i18n/*.json, assets/*.js) so the font subsets cover it:
zh and en are in the page subset; zh-Hant, ja, ko and fr each get a small extra subset of their own characters.
Needs fontTools (with brotli) for the subsets; everything else is the standard library.
"""
from __future__ import annotations

import json
import re
import shutil
import struct
import sys
import unicodedata
import zlib
from collections import Counter, defaultdict
from pathlib import Path

SITE = Path(__file__).resolve().parent
ROOT = SITE.parent
GEN = SITE / "gen"
sys.path.insert(0, str(ROOT / "tools"))
import build  # noqa: E402

REGIONS = build.REGIONS
STATE_CODE = {"approved": "A", "edited": "E", "derived": "D", "ai": "I", "draft": "R",
              "hangul-ai": "H", "hangul-composed": "C", "generated": "G", "blank": "B"}
STATUS_ORDER = ["approved", "edited", "derived", "ai", "hangul-ai", "hangul-composed", "generated", "draft"]
GROUPS = ["SC", "TC", "JP", "KR", "HW", "PR", "GEOMETRIC-FULL", "GEOMETRIC-HALF"]
FEATURED = "通化令次這麵素骨直如、"
RADICALS = ["氵", "艹", "辶", "讠", "亻", "纟", "口"]
VECTOR = {"square": "TongPixelSans-Square", "square-mono": "TongPixelSansMono-Square",
          "dot": "TongPixelSans-Dot", "dot-mono": "TongPixelSansMono-Dot"}
FAMILY = {"square": "TPS Square", "square-mono": "TPS Square Mono", "dot": "TPS Dot", "dot-mono": "TPS Dot Mono"}
TABLE_EN = {"GB/T 2312 符号": "GB/T 2312 symbols", "常用国字": "Common national characters (TW)",
            "次常用国字": "Less common national characters (TW)", "谚文音节": "Hangul syllables",
            "谚文兼容字母": "Hangul compatibility jamo", "注音": "Bopomofo", "平假名": "Hiragana",
            "片假名": "Katakana", "半角假名": "Half-width katakana", "越南文": "Vietnamese",
            "希腊": "Greek", "西里尔": "Cyrillic", "阿拉伯": "Arabic", "泰文": "Thai",
            "制表符": "Box drawing", "方块元素": "Block elements", "盲文": "Braille",
            "平/片假名区其他字符": "Other kana-block characters", "常用漢字表": "Jōyō kanji",
            "香港常用字字形表": "Hong Kong common character forms", "康熙部首": "Kangxi radicals",
            "汉字部首补充": "CJK radicals supplement", "现代汉语通用字表": "Modern Chinese common characters",
            "汉仪简繁字表": "Hanyi simplified & traditional set", "方正简繁字表": "FounderType simplified & traditional set",
            "日本人名用漢字": "Jinmeiyō kanji", "韩文组合字母": "Hangul jamo", "通用规范汉字表": "General Standard Chinese Characters",
            "KS X 1001 汉字": "KS X 1001 hanja", "KS X 1001 符号": "KS X 1001 symbols",
            "JIS X 0208 第一水準": "JIS X 0208 level 1", "JIS X 0208 第二水準": "JIS X 0208 level 2",
            "JIS X 0208 非汉字": "JIS X 0208 non-kanji", "GB/T 2312": "GB/T 2312",
            "GB/T 12345": "GB/T 12345", "Big5": "Big5", "IICore": "IICore", "WGL4": "WGL4", "CP437": "CP437",
            "Basic Latin": "Basic Latin", "Latin-1": "Latin-1", "Latin Ext-A": "Latin Extended-A",
            "Latin Ext-B": "Latin Extended-B"}
SECTION = {"gb": "cn", "prc-lit": "cn", "tw": "tw", "hk": "tw", "jp": "jp", "kr": "kr", "intl": "intl"}


# ---------------------------------------------------------------- helpers
def png(path, width, rows, bits=8):
    """Write a greyscale PNG; rows are bytes-like of length width (8-bit) or packed bits (1-bit)."""
    raw = b"".join(b"\x00" + bytes(r) for r in rows)

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, len(rows), bits, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
    path.write_bytes(data)


def pack_bits(flags):
    out = bytearray((len(flags) + 7) // 8)
    for i, f in enumerate(flags):
        if f:
            out[i >> 3] |= 0x80 >> (i & 7)
    return out


def encode(g):
    """'adv.x.top.w.h.S.hex': top = cell row of the bitmap's first row (row 0 = ascent line)."""
    rows = g["rows"]
    h = len(rows)
    w = len(rows[0]) if h else 0
    top = build.ASCENT - (g["y"] + h) if h else 0
    bits = "".join("1" if c == "#" else "0" for r in rows for c in r)
    bits += "0" * (-len(bits) % 4)
    hx = f"{int(bits, 2):0{len(bits) // 4}x}" if bits else ""
    return f"{g['adv']}.{g['x']}.{top}.{w}.{h}.{STATE_CODE.get(g['state'], 'I')}.{hx}"


def pixels(rows):
    return {(x, y) for y, r in enumerate(rows) for x, c in enumerate(r) if c == "#"}


def table_codepoints(path):
    cps = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if re.fullmatch(r"[0-9A-Fa-f]{4,6}", line):
            cps.add(int(line, 16))
        elif re.fullmatch(r"[0-9A-Fa-f]{4,6}\.\.[0-9A-Fa-f]{4,6}", line):
            lo, hi = (int(p, 16) for p in line.split(".."))
            cps.update(range(lo, hi + 1))
        else:
            cps.update(ord(ch) for ch in line if not ch.isspace())
    return cps


def gb2312_symbols():
    out = set()
    for a in range(0xA1, 0xAA):
        for b in range(0xA1, 0xFF):
            try:
                out.add(ord(bytes([a, b]).decode("gb2312")))
            except UnicodeDecodeError:
                pass
    return out


def read_history(group):
    """history/ai-originals/<group>/ in the glyph file format (same reader as build.read_group)."""
    tmp = {}
    base = ROOT / "history/ai-originals" / group
    for p in sorted(base.glob("*.txt")) if base.exists() else []:
        for block in p.read_text().split("\n\n"):
            lines = [l for l in block.split("\n") if l]
            if not lines or " = " in lines[0]:
                continue
            cp = int(lines[0].split(" ")[0][2:], 16)
            tmp[cp] = {"rows": [l for l in lines[2:] if set(l) <= {".", "#"}], "state": lines[1]}
    return tmp


def read_sources():
    """{group: {cp: entry}} with aliases, as in the glyph files, plus the component links."""
    groups, links = {}, defaultdict(list)
    for group in GROUPS:
        groups[group] = build.read_group(group, ROOT)
        for p in sorted((ROOT / "glyphs" / group).glob("*.txt")):
            for block in p.read_text().split("\n\n"):
                lines = [l for l in block.split("\n") if l]
                if not lines or " = " in lines[0]:
                    continue
                cp = int(lines[0].split(" ")[0][2:], 16)
                for l in lines:
                    if l.startswith("@ ") and not l.startswith("@ mv:"):
                        _, pos, comp, fid = l.split(" ")[:4]
                        links[fid].append((group, cp, comp))
    return groups, links


def read_forms():
    forms = {}
    for block in (ROOT / "forms/forms.txt").read_text().split("\n\n"):
        lines = [l for l in block.split("\n") if l]
        if not lines or not lines[0].startswith("FORM "):
            continue
        head = lines[0].split(" ")
        rows = [l for l in lines[1:] if set(l) <= {".", "#"}]
        forms[head[1]] = {"kind": head[2], "comp": head[3], "region": head[4], "rows": rows}
    return forms


# ---------------------------------------------------------------- parts
def write_shards(faces):
    out = GEN / "g"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    pages = defaultdict(lambda: {"l": [], "c": {}, "_i": {}})
    for cp in sorted(faces["SC"]):
        page = pages[cp >> 8]
        idx = []
        for r in REGIONS:
            g = faces[r][cp]
            key = g.get("src") or f"blank{cp}"
            if key not in page["_i"]:
                page["_i"][key] = len(page["l"])
                page["l"].append(encode(g))
            idx.append(page["_i"][key])
        page["c"][f"{cp:X}"] = idx if len(set(idx)) > 1 else idx[0]
    total = 0
    for p, page in pages.items():
        del page["_i"]
        text = json.dumps(page, separators=(",", ":"))
        (out / f"{p:02X}.json").write_text(text)
        total += len(text)
    return sorted(f"{p:02X}" for p in pages), total


def featured(faces):
    out = []
    for ch in FEATURED:
        cp = ord(ch)
        gs = [faces[r][cp] for r in REGIONS]
        sets = [pixels(g["rows"]) for g in gs]
        diff = len(set.union(*sets) - set.intersection(*sets))
        out.append({"ch": ch, "diff": diff})
    return out


def differing(faces):
    """How many Han characters differ between regions (by pixels)."""
    n = same = 0
    for cp in faces["SC"]:
        if not (0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF or cp > 0xFFFF):
            continue
        sets = [pixels(faces[r][cp]["rows"]) for r in REGIONS]
        n += 1
        if all(s == sets[0] for s in sets):
            same += 1
    return {"han": n, "differ": n - same}


def radical_demo(groups, links, forms):
    """For each radical, the SC form with the most links: its pixels and a dozen linked characters."""
    out = []
    for comp in RADICALS:
        cands = [(fid, [l for l in ls if l[0] == "SC"]) for fid, ls in links.items()
                 if fid in forms and forms[fid]["comp"] == comp and forms[fid]["kind"] == "fixed"]
        if not cands:
            continue
        fid, ls = max(cands, key=lambda t: len(t[1]))
        approved = [(cp) for g, cp, _ in ls if groups[g][cp].get("state") == "approved"]
        others = [cp for g, cp, _ in ls if cp not in approved]
        pick = (approved + others)[:12]
        out.append({"comp": comp, "count": len(ls), "form": forms[fid]["rows"],
                    "chars": "".join(chr(c) for c in pick),
                    "glyphs": ["".join("1" if c == "#" else "0" for c in "".join(groups["SC"][c]["rows"])) for c in pick],
                    "states": [groups["SC"][c]["state"] for c in pick]})
    return out


def review_demo(groups):
    """Approved hanzi whose AI original is kept in history/: before and after."""
    out = []
    for group in ["SC", "TC", "JP"]:
        orig = read_history(group)
        for cp, e in sorted(orig.items()):
            cur = groups[group].get(cp)
            if not cur or cur.get("state") != "approved" or "rows" not in e or len(e["rows"]) != 13:
                continue
            if not (0x4E00 <= cp <= 0x9FFF):
                continue
            a, b = pixels(e["rows"]), pixels(cur["rows"])
            d = len(a ^ b)
            if 6 <= d <= 24:
                out.append((group, cp, d, e["rows"], cur["rows"]))
    # a spread of regions and characters, deterministic
    out.sort(key=lambda t: (-t[2], t[1]))
    seen, pick = set(), []
    for t in out:
        if t[1] in seen:
            continue
        seen.add(t[1])
        pick.append(t)
    step = max(1, len(pick) // 8)
    pick = pick[::step][:8]
    return [{"region": g, "ch": chr(cp), "diff": d,
             "before": "".join("1" if c == "#" else "0" for c in "".join(a)),
             "after": "".join("1" if c == "#" else "0" for c in "".join(b))} for g, cp, d, a, b in pick]


def status_field(groups):
    codes = []
    bands = []
    counts = Counter()
    for group in GROUPS:
        start = len(codes)
        for cp in sorted(groups[group]):
            e = groups[group][cp]
            if "alias" in e:
                continue
            st = e["state"]
            counts[st] += 1
            codes.append(STATUS_ORDER.index(st) + 1 if st in STATUS_ORDER else 4)
        bands.append({"group": group, "start": start, "count": len(codes) - start})
    width = 256
    rows = [bytes(codes[i:i + width]) + bytes(width - len(codes[i:i + width])) for i in range(0, len(codes), width)]
    png(GEN / "status.png", width, rows)
    return {"width": width, "total": len(codes), "bands": bands,
            "counts": {k: counts[k] for k in STATUS_ORDER if counts[k]}, "order": STATUS_ORDER}


def coverage(face_cps):
    covered = [cp in face_cps for cp in range(0x10000)]
    png(GEN / "coverage.png", 256, [pack_bits(covered[y * 256:(y + 1) * 256]) for y in range(256)], bits=1)
    known = {int(l.split("\t")[0], 16) for l in (ROOT / "build-data/coverage-exceptions.txt").read_text(encoding="utf-8").splitlines()
             if l and not l.startswith("#")}
    tables, sprite = [], []
    for line in (ROOT / "build-data/coverage-required.txt").read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        label, path, *flt = line.split("\t")
        cps = table_codepoints(ROOT / "build-data/coverage" / path)
        if flt == ["non-hanzi"]:
            cps = {c for c in cps if not unicodedata.name(chr(c), "").startswith("CJK UNIFIED")}
            if not cps and label == "GB/T 2312 符号":   # gb2312.txt lists only the hanzi: take rows 1-9 from the codec
                cps = gb2312_symbols()
        elif label == "GB/T 2312":
            cps = {c for c in cps if unicodedata.name(chr(c), "").startswith("CJK UNIFIED")}
        cps = {c for c in cps if unicodedata.category(chr(c)) not in ("Cc", "Cs", "Co", "Cn") and c not in known}
        have = len(cps & face_cps)
        zh = "GB/T 2312 汉字" if label == "GB/T 2312" else label
        en = "GB/T 2312 hanzi" if label == "GB/T 2312" else TABLE_EN.get(label, label)
        tid = Path(path).stem + ("-symbols" if flt == ["non-hanzi"] else "")
        tables.append({"id": tid, "zh": zh, "en": en, "section": SECTION[path.split("/")[0]],
                       "count": len(cps), "covered": have, "smp": sum(1 for c in cps if c > 0xFFFF)})
        flags = [cp in cps for cp in range(0x10000)]
        sprite += [pack_bits(flags[y * 256:(y + 1) * 256]) for y in range(256)]
    png(GEN / "tables.png", 256, sprite, bits=1)
    return tables


def favicon(groups):
    rows = groups["SC"][ord("通")]["rows"]
    rects = "".join(f'<rect x="{x + 1}" y="{y + 1}" width="1" height="1"/>' for x, y in sorted(pixels(rows)))
    (GEN / "favicon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 15 15" shape-rendering="crispEdges">'
        '<style>rect{fill:#000}@media(prefers-color-scheme:dark){rect{fill:#fff}}</style>' + rects + "</svg>\n")


def og_image(faces):
    """1200×630 share image drawn from the bitmaps: the name in SC, and 通 in the four regions."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("Pillow missing: no og.png")
        return
    im = Image.new("RGB", (1200, 630), (243, 244, 246))
    d = ImageDraw.Draw(im)
    colors = {"SC": (0, 112, 204), "TC": (209, 0, 106), "JP": (180, 122, 0), "KR": (0, 134, 106)}

    def glyph(cp, region, x0, y0, s, color_of):
        g = faces[region][cp]
        rows = g["rows"]
        top = build.ASCENT - (g["y"] + len(rows)) if rows else 0
        for j, r in enumerate(rows):
            for i, c in enumerate(r):
                if c == "#":
                    col = color_of(g["x"] + i, top + j)
                    d.rectangle([x0 + (g["x"] + i) * s, y0 + (top + j) * s, x0 + (g["x"] + i + 1) * s - 1, y0 + (top + j + 1) * s - 1], fill=col)
        return g["adv"] * s

    x = 72
    for ch in "通格像素黑体":
        x += glyph(ord(ch), "SC", x, 96, 12, lambda a, b: (0, 0, 0))
    x = 72
    for ch in "Tong Pixel Sans":
        x += glyph(ord(ch), "SC", x, 300, 5, lambda a, b: (0, 0, 0)) if ord(ch) in faces["SC"] else 15
    cp = ord("通")
    sets = {r: {(i + faces[r][cp]["x"], j) for j, row in enumerate(faces[r][cp]["rows"]) for i, c in enumerate(row) if c == "#"} for r in REGIONS}
    shared = set.intersection(*sets.values())
    for k, r in enumerate(REGIONS):
        x0 = 72 + k * 270
        glyph(cp, r, x0, 400, 12, lambda a, b, r=r: (0, 0, 0) if (a, b) in shared else colors[r])
    im.save(GEN / "og.png", optimize=True)


# ---------------------------------------------------------------- page text (i18n/*.json)
LANG_FILES = ["zh", "en", "zh-Hant", "ja", "ko", "fr"]
BASE_LANGS = ["zh", "en"]                                   # in the main subset; the others get their own
CJK_RE = "[⺀-⿟ぁ-ヺヽ-ヿ㄀-ㄯㄱ-ㆎㆠ-ㆿㇰ-ㇿ㐀-䶿一-鿿가-힯ᄀ-ᇿ豈-﫿\U00020000-\U0003FFFF]"
LAT_RE = "[A-Za-z0-9À-ɏͰ-ϿЀ-ӿḀ-ỿ]"
THIN = "\u2009"


def autospace(html):
    """Thin space between CJK and Latin letters / digits, looking through inline tags (as assets/autospace.js)."""
    out, prev, skip = [], "", 0
    for part in re.split(r"(<[^>]+>)", html):
        if part.startswith("<"):
            out.append(part)
            if 'class="' in part and "no-space" in part:
                skip += 1
            elif skip and part.startswith("</"):
                skip -= 1
            continue
        if not part or skip:
            out.append(part)
            continue
        text = re.sub(f"({CJK_RE})(?={LAT_RE})|({LAT_RE})(?={CJK_RE})", lambda m: (m.group(1) or m.group(2)) + THIN, part)
        if prev and ((re.match(CJK_RE, prev) and re.match(LAT_RE, text[0])) or (re.match(LAT_RE, prev) and re.match(CJK_RE, text[0]))):
            text = THIN + text
        out.append(text)
        prev = text[-1]
    return "".join(out)


def read_lang(code):
    p = SITE / "i18n" / f"{code}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def lang_text(d):
    """Every character a language file can put on the page."""
    out = []
    for k, v in d.items():
        if k.startswith("_"):
            continue
        out.append("".join(v) if isinstance(v, list) else re.sub(r"<[^>]+>|\{\w+\}", "", v))
    return "".join(out)


def sync_html(stats):
    """Write the Simplified Chinese text into index.html (the page's text before any script runs)."""
    from html import escape
    from html.parser import HTMLParser
    zh, en = read_lang("zh"), read_lang("en")
    page = SITE / "index.html"
    src = page.read_text(encoding="utf-8")
    starts = [0]
    for line in src.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    off = lambda pos: starts[pos[0] - 1] + pos[1]
    edits = []                       # (start, end, new inner html)

    def val(key):
        v = zh.get(key, en.get(key, ""))
        return v

    def stat_fill(html):
        def rep(m):
            k = m.group(2)
            v = stats.get(k)
            return m.group(1) + (f"{v:,}" if isinstance(v, int) else str(v or "")) + m.group(3)
        return re.sub(r'(<(?:b|span) data-stat="(\w+)">)[^<]*(</(?:b|span)>)', lambda m: rep(m), html)

    def fp_fill(html):
        return re.sub(r'<a ([^>]*?)data-fp="([^"]*)"', lambda m: f'<a {m.group(1)}href="https://fontpixel.com/zh{m.group(2)}" data-fp="{m.group(2)}"'
                      if "href=" not in m.group(1) else m.group(0), html)

    class P(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False)
            self.stack = []

        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if tag in ("br", "img", "input", "meta", "link", "hr", "wbr", "source", "col", "area", "base"):
                return
            start = off(self.getpos()) + len(self.get_starttag_text())
            self.stack.append((tag, a, start))

        def handle_startendtag(self, tag, attrs):
            pass

        def handle_endtag(self, tag):
            while self.stack:
                t, a, start = self.stack.pop()
                if t == tag:
                    end = off(self.getpos())
                    new = None
                    if "data-i18n" in a:
                        v = val(a["data-i18n"])
                        new = v if tag == "title" else autospace(stat_fill(fp_fill(v)))
                    elif "data-i18n-list" in a:
                        new = "".join(f"<li>{escape(x)}</li>" for x in val(a["data-i18n-list"]))
                    elif "data-i18n-bi" in a:
                        k = a["data-i18n-bi"]
                        new = f"<span>{escape(val(k))}</span>" + (f'<span class="bi" lang="en">{escape(en[k])}</span>' if en.get(k) and en[k] != val(k) else "")
                    if new is not None:
                        edits.append((start, end, new))
                    break

    p = P()
    p.feed(src)
    out = src
    for start, end, new in sorted(edits, reverse=True):
        out = out[:start] + new + out[end:]
    # attributes
    def attr_rep(m):
        tag = m.group(0)
        spec = re.search(r'data-i18n-attr="([^"]+)"', tag).group(1)
        for pair in spec.split(";"):
            attr, key = pair.split(":")
            v = escape(val(key), quote=True)
            if re.search(rf'\s{attr}="[^"]*"', tag):
                tag = re.sub(rf'(\s{attr}=")[^"]*(")', lambda mm: mm.group(1) + v + mm.group(2), tag)
        return tag
    out = re.sub(r"<[^>]*data-i18n-attr=\"[^\"]+\"[^>]*>", attr_rep, out)
    if out != src:
        page.write_text(out, encoding="utf-8")
        print("index.html: Simplified Chinese text updated")


# ---------------------------------------------------------------- fonts
def page_text(extra):
    text = []
    for p in [SITE / "index.html", *sorted((SITE / "assets").glob("*.js"))]:
        if p.exists():
            text.append(p.read_text(encoding="utf-8"))
    for code in BASE_LANGS:
        text.append(lang_text(read_lang(code)))
    text.append(extra)
    chars = set("".join(text))
    chars |= {chr(c) for c in range(0x20, 0x7F)}
    chars |= set("“”‘’…—–·、。，：；！？（）《》〈〉「」『』【】〔〕％＋－×÷°±←→↑↓■□●○◆◇★☆│─┌┐└┘├┤┬┴┼═║╔╗╚╝▀▄█░▒▓▶▼ 　\u2009")
    chars -= {"\n", "\r", "\t"}
    return sorted(c for c in chars if ord(c) >= 0x20)


def ranges(cps):
    cps = sorted(cps)
    out, start, prev = [], cps[0], cps[0]
    for c in cps[1:]:
        if c == prev + 1:
            prev = c
            continue
        out.append((start, prev))
        start = prev = c
    out.append((start, prev))
    return ", ".join(f"U+{a:X}" if a == b else f"U+{a:X}-{b:X}" for a, b in out)


def make_subset(src, cps, out):
    from fontTools import subset
    from fontTools.ttLib import TTFont
    font = TTFont(src)
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["*"]
    opts.name_IDs = ["*"]
    opts.notdef_outline = True
    opts.drop_tables += ["DSIG"]
    sub = subset.Subsetter(opts)
    sub.populate(unicodes=cps)
    sub.subset(font)
    font.flavor = "woff2"
    font.save(out)
    return out.stat().st_size


def subset_fonts(chars):
    """Per vector font: the full font (loaded only for characters nothing else has), the page subset, and for
    the proportional square font one extra subset per not-yet-base language file (its characters only)."""
    fonts = GEN / "fonts"
    if fonts.exists():
        shutil.rmtree(fonts)
    fonts.mkdir(parents=True)
    css, info = [], {}
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        print("fontTools missing: no font subsets (run with .venv/bin/python)")
        return {}
    base = {ord(c) for c in chars}
    for key, name in VECTOR.items():
        src = SITE / "downloads/ttf" / f"{name}.ttf"          # faster to read than the woff2
        if not src.exists():
            src = SITE / "downloads/woff2" / f"{name}.woff2"
        full = f"../downloads/woff2/{name}.woff2"
        fam = FAMILY[key]
        # The full font first and the subsets after it: for a character in a subset's range the subset is
        # consulted first; any other character falls through to the full font, which loads only then.
        css.append(f'@font-face{{font-family:"{fam}";src:url("{full}") format("woff2");font-display:swap}}')
        if not src.exists():
            print(f"missing {name}: page falls back to the full font only")
            continue
        try:
            cmap = TTFont(src, lazy=True).getBestCmap()
            cps = sorted(c for c in base if c in cmap)
            out = fonts / f"{name}-page.woff2"
            n = make_subset(src, cps, out)
        except Exception as e:                      # e.g. tools/export.py is rewriting the file right now
            print(f"cannot subset {src.name}: {e}")
            continue
        full_size = (SITE / "downloads/woff2" / f"{name}.woff2").stat().st_size if (SITE / "downloads/woff2" / f"{name}.woff2").exists() else 0
        info[key] = {"family": fam, "subset": n, "full": full_size, "fullUrl": f"downloads/woff2/{name}.woff2", "extra": {}}
        css.append(f'@font-face{{font-family:"{fam}";src:url("fonts/{out.name}") format("woff2");'
                   f'font-display:block;unicode-range:{ranges(cps)}}}')
        print(f"{name}: subset {len(cps)} chars, {n:,} bytes")
        if key != "square":
            continue
        for code in LANG_FILES:
            if code in BASE_LANGS:
                continue
            extra = sorted({ord(c) for c in lang_text(read_lang(code))} - base & set(cmap))
            if not extra:
                continue
            out = fonts / f"{name}-{code}.woff2"
            n = make_subset(src, extra, out)
            info[key]["extra"][code] = n
            css.append(f'@font-face{{font-family:"{fam}";src:url("fonts/{out.name}") format("woff2");'
                       f'font-display:block;unicode-range:{ranges(extra)}}}')
            print(f"{name} [{code}]: {len(extra)} more chars, {n:,} bytes")
    (GEN / "fonts.css").write_text("\n".join(css) + "\n")
    return info


# ---------------------------------------------------------------- main
def manifest_version():
    p = SITE / "downloads/manifest.json"
    try:
        return json.loads(p.read_text())["version"]
    except (OSError, ValueError, KeyError):
        return "—"



def main():
    GEN.mkdir(exist_ok=True)
    region_faces = {r: prop for r, prop, _ in build.faces(ROOT)}
    groups, links = read_sources()
    forms = read_forms()
    pages, shard_bytes = write_shards(region_faces)
    print(f"{len(pages)} glyph pages, {shard_bytes:,} bytes")
    face_cps = set(region_faces["SC"])
    latin_prop, _ = build.latin_faces(ROOT)
    tables = coverage(face_cps)
    status = status_field(groups)
    favicon(groups)
    og_image(region_faces)
    data = {
        "stats": {"perRegion": len(region_faces["SC"]), "latin": len(latin_prop), "bmp": sum(1 for c in face_cps if c <= 0xFFFF),
                  "smp": sum(1 for c in face_cps if c > 0xFFFF), "tables": len(tables), **differing(region_faces)},
        "pages": pages,
        "featured": featured(region_faces),
        "radicals": radical_demo(groups, links, forms),
        "review": review_demo(groups),
        "status": status,
        "tables": tables,
    }
    sync_html({"approved": status["counts"].get("approved", 0), "perRegion": data["stats"]["perRegion"],
               "tables": data["stats"]["tables"], "smp": data["stats"]["smp"], "version": manifest_version()})
    extra = "".join(t["zh"] + t["en"] for t in tables) + "".join(r["comp"] + r["chars"] for r in data["radicals"])
    extra += "".join(f["ch"] for f in data["featured"]) + "".join(r["ch"] for r in data["review"])
    chars = page_text(extra)
    data["fonts"] = subset_fonts(chars)
    (GEN / "site.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    print(json.dumps(data["stats"], ensure_ascii=False))
    print("status:", data["status"]["counts"])
    print(f"page characters: {len(chars)}")


if __name__ == "__main__":
    main()
