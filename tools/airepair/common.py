"""Shared pieces of the AI repair tools: paths, Tumbled glyphs, Source Han (and Plangothic) references, drawing."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
FONTS = ROOT / "reference-fonts"
ROUNDS = ROOT / "work/airepair"
REGIONS = ("SC", "TC", "JP", "KR")
# what Source Han Sans lacks (static fonts): Han characters, then symbols; as tools/editor/draft.py
FALLBACK_FONTS = ["PlangothicP1-Regular.ttf", "NotoSansSymbols2-Regular.ttf", "NotoSansSymbols-Regular.ttf", "NotoSansMath-Regular.ttf"]
sys.path.insert(0, str(ROOT / "tools/editor"))


def read_json(path, default=None):
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


# ---------------------------------------------------------------- Tumbled Bitmap 18
_tumbled = None


def tumbled():
    """{code point: 14 rows × 13 columns} of TUMBLED 18's glyphs (its Han ink box; ours is 13 × 13)."""
    global _tumbled
    if _tumbled is None:
        out, rows, cur = {}, [], None
        for line in open(HERE / "data/tumbled-18.bdf", encoding="latin-1"):
            s = line.split()
            if not s:
                continue
            if s[0] == "ENCODING":
                cp = int(s[1])
            elif s[0] == "BBX":
                w, h, x, y = map(int, s[1:5])
            elif s[0] == "BITMAP":
                rows, cur = [], True
            elif s[0] == "ENDCHAR":
                bits = [bin(int(r, 16))[2:].zfill(len(r) * 4)[:w] for r in rows]
                grid = [["."] * 13 for _ in range(14)]
                top = 14 - h
                for yy, r in enumerate(bits):
                    for xx, v in enumerate(r):
                        X = x + xx
                        if v == "1" and 0 <= X < 13 and 0 <= top + yy < 14:
                            grid[top + yy][X] = "#"
                out[cp] = ["".join(r) for r in grid]
                cur = None
            elif cur:
                rows.append(s[0])
        _tumbled = out
    return _tumbled


# ---------------------------------------------------------------- Source Han
_faces = {}


def grey(char, region, ppem=104, weight=400):
    """Grey rendering (uint8 array) of the character in that region's Source Han Sans, or in the
    first of FALLBACK_FONTS that has it (Plangothic P1 for Han characters; weight 400 only)."""
    import freetype
    import numpy as np
    key = (region, ppem, weight)
    if key not in _faces:
        f = freetype.Face(str(FONTS / f"SourceHanSans{region}-VF.otf"))
        f.set_pixel_sizes(ppem, ppem)
        f.set_var_design_coords((weight,))
        _faces[key] = f
    f = _faces[key]
    for name in FALLBACK_FONTS:
        if f.get_char_index(ord(char)) or not (FONTS / name).exists():
            continue
        if (name, ppem) not in _faces:
            _faces[name, ppem] = freetype.Face(str(FONTS / name))
            _faces[name, ppem].set_pixel_sizes(ppem, ppem)
        f = _faces[name, ppem]
    f.load_char(char, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
    bm = f.glyph.bitmap
    if not bm.rows:
        return np.zeros((1, 1), np.uint8)
    return np.array(bm.buffer, dtype=np.uint8).reshape(bm.rows, bm.pitch)[:, :bm.width]


def reference_png(char, region, path):
    from PIL import Image
    a = grey(char, region)
    ref = Image.fromarray(255 - a)
    canvas = Image.new("L", (128, 128), 255)
    canvas.paste(ref, ((128 - ref.width) // 2, (128 - ref.height) // 2))
    canvas.save(path)


def _norm(a, n=48):
    import numpy as np
    from PIL import Image
    ys, xs = np.nonzero(a > (a.max() / 2 if a.max() else 1))
    if not len(xs):
        return np.zeros((n, n))
    c = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(float)
    c = c / c.max()
    return np.asarray(Image.fromarray((c * 255).astype("uint8")).resize((n, n), Image.BILINEAR), dtype=float) / 255


def region_match(char, region, tum_rows):
    """Does Tumbled draw this character like this region's Source Han? An automatic hint only."""
    import numpy as np
    t = _norm(np.array([[255 if v == "#" else 0 for v in r] for r in tum_rows], dtype=np.uint8)) > 0.5
    refs = {}
    for r in REGIONS:
        try:
            refs[r] = _norm(grey(char, r, ppem=96)) > 0.5
        except Exception:
            continue
    iou = lambda a, b: float((a & b).sum() / max((a | b).sum(), 1))
    same = {r: iou(t, a) for r, a in refs.items()}
    if region not in same:
        return "难以判断"
    best = max(same, key=same.get)
    if best == region or iou(refs[region], refs[best]) >= 0.85 or same[region] >= same[best] - 0.04:
        return "一致"
    return f"可能不一致（自动判断，像 {best}，需核对）"


# ---------------------------------------------------------------- drawing
def font(size):
    from PIL import ImageFont
    return ImageFont.truetype(str(FONTS / "SourceHanSansSC-VF.otf"), size)


def draw_bits(d, rows, x, y, sc, x_off=1, box=(14, 14), label=None, fnt=None, colors=None):
    """A bitmap on a light grid; colors: optional {(x, y): fill} overrides (for marking changes)."""
    d.rectangle((x - 1, y - 1, x + box[0] * sc, y + box[1] * sc), outline=(190, 190, 190))
    for yy in range(box[1] + 1):
        d.line((x, y + yy * sc, x + box[0] * sc - 1, y + yy * sc), fill=(235, 235, 235))
    for xx in range(box[0] + 1):
        d.line((x + xx * sc, y, x + xx * sc, y + box[1] * sc - 1), fill=(235, 235, 235))
    for yy, r in enumerate(rows):
        for xx, v in enumerate(r):
            fill = (colors or {}).get((xx, yy), (0, 0, 0) if v == "#" else None)
            if fill:
                d.rectangle((x + (xx + x_off) * sc, y + yy * sc, x + (xx + x_off + 1) * sc - 1, y + (yy + 1) * sc - 1), fill=fill)
    if label:
        d.text((x, y + box[1] * sc + 2), label, font=fnt, fill=(90, 90, 90))


def diff_colors(before, after):
    """Colours for `after`: removed pixels red, added blue (unchanged black)."""
    out = {}
    for y, (a, b) in enumerate(zip(before, after)):
        for x, (p, q) in enumerate(zip(a, b)):
            if p == "#" and q != "#":
                out[(x, y)] = (215, 40, 40)
            elif q == "#" and p != "#":
                out[(x, y)] = (40, 90, 230)
    return out


def one_to_one(im, rows_list, x, y, gap=18):
    for k, rows in enumerate(rows_list):
        for yy, r in enumerate(rows):
            for xx, v in enumerate(r):
                if v == "#":
                    im.putpixel((x + 1 + xx + k * gap, y + yy), (0, 0, 0))


# ---------------------------------------------------------------- checks
def wide_gaps(char, region, rows, limit=2):
    """Side-by-side components (⿰ ⿲, also inside ⿱ …) whose ink boxes leave `limit` or more blank
    columns between them: [(left symbol, right symbol, blank columns)]. Uses the IDS segmentation of
    the editor (an inference; strokes the segmentation cannot place are ignored)."""
    import segment
    try:
        node, found, _ = segment.segment(char, region, rows)
    except Exception:
        return []

    def mask(n):
        if n is None:
            return set()
        if "op" in n:
            return set().union(*(mask(c) for c in n["children"]))
        return set(found.get(n["slot"], ()))

    def name(n):
        return "?" if n is None else n["symbol"] if "symbol" in n else "".join(name(c) for c in n["children"])

    out = []

    def visit(n, depth):
        if n is None or depth > 3:
            return
        if "op" in n:
            if n["op"] in ("⿰", "⿲"):
                ms = [mask(c) for c in n["children"]]
                for (a, ca), (b, cb) in zip(zip(ms, n["children"]), zip(ms[1:], n["children"][1:])):
                    if a and b:
                        gap = min(x for x, _ in b) - max(x for x, _ in a) - 1
                        if gap >= limit:
                            out.append((name(ca), name(cb), gap))
            for c in n["children"]:
                visit(c, depth + 1)
        else:
            visit(n["sub"], depth + 1)

    visit(node, 0)
    return out
