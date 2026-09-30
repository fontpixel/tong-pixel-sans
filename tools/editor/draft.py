"""Phase-searched drafts (“相位底稿”), computed on demand from the reference fonts. Nothing is stored.

The rasterisation is WorkBench's: FreeType monochrome (FT_LOAD_TARGET_MONO) with stem darkening off,
at a fixed face size and weight. The outline is additionally shifted right by k/16 px (k = 0…15;
k = 0 is WorkBench's own result) and the best candidate is kept:

  3 × mirror mismatch (only if the outline itself is mirror-symmetric, IoU ≥ 0.85)
  + 2 × solid 2×2 blocks where the outline is not solid
  + 4 × difference in connected strokes from the grey rendering (broken strokes)
  + 0.5 × |mono − grey coverage|   (fidelity: strokes are not moved far)

Regional glyphs (SC TC JP KR): the region's Source Han Sans at weight 320, face 14×13 (13×13 for the
fully enclosed 囗 characters and 口), falling back to smaller faces when the ink does not fit 13×13;
the ink is centred horizontally in the 13×13 box as the original drafts were. Characters that no
Source Han Sans has (extension B and later) come from Plangothic P1 (遍黑体, a static weight-400 font).
.HW / .PR glyphs: the font of their original draft (data/reference-western.txt) at weight 320, on
the real baseline (rows 0–10 above, 11–13 below); the face size is searched as the original drafts
were (half-width: narrowest face whose ink fits 6 columns; western proportional: ink from column 0,
one blank column after it).

Ported from the draft packages (archive/tong-ext-v5/scripts/phase.py, varraster.py and
archive/tong/scripts/prepare.py). Needs freetype-py, numpy and fontTools (tools/requirements.txt).
"""
from __future__ import annotations

import math
import os
import threading
from functools import lru_cache
from pathlib import Path

# Must be set before FreeType is loaded, exactly as in the draft packages.
os.environ["FREETYPE_PROPERTIES"] = "cff:no-stem-darkening=1 autofitter:no-stem-darkening=1"

HERE = Path(__file__).resolve().parent
FONTS = HERE.parent.parent / "reference-fonts"
STEPS, SYMMETRIC = 16, 0.85
H, BASELINE_ROW = 14, 11
# User decision 2026-09-16: fully enclosed 囗 characters and the standalone 口 use a 13×13 face.
SQUARE = set("口囗囚四囝回囟因囡团囤囪囫园困囱围囵囹固国图囿圃圄圆圈圉圊國圍園圓圖團圜")
REGIONAL_FACES = [(14, 13), (13, 13), (12, 13), (12, 12), (11, 11), (10, 10)]
# label in data/reference-western.txt -> (font file, variation coordinates as the drafts used them);
# a label is matched by its prefix, so the longer names come first
WESTERN_FONTS = {"Source Sans 3": ("SourceSans3-VF.otf", (320,)), "Noto Sans Thai": ("NotoSansThai-VF.ttf", (320, 100)),
                 "Noto Sans Arabic": ("NotoSansArabic-VF.ttf", (320, 100)), "Noto Sans Math": ("NotoSansMath-Regular.ttf", ()),
                 "Noto Sans Symbols 2": ("NotoSansSymbols2-Regular.ttf", ()), "Noto Sans Symbols": ("NotoSansSymbols-Regular.ttf", ()),
                 "Noto Sans Hebrew": ("NotoSansHebrew-Regular.ttf", ()), "Noto Sans Georgian": ("NotoSansGeorgian-Regular.ttf", ()),
                 "Noto Sans Armenian": ("NotoSansArmenian-Regular.ttf", ()), "Noto Sans Lao": ("NotoSansLao-Regular.ttf", ()),
                 "Noto Sans": ("NotoSans-VF.ttf", (320, 100)), "思源 JP": ("SourceHanSansJP-VF.otf", (320,))}
# Han characters beyond Source Han Sans (extension B and later): static, weight 400 only
EXTENSION = ("PlangothicP1-Regular.ttf", "遍黑体 P1")
# full-width glyphs no Source Han Sans has, in this order: Han characters, then symbols (all static)
REGIONAL_FALLBACK = [EXTENSION, ("NotoSansSymbols2-Regular.ttf", "Noto Sans Symbols 2"),
                     ("NotoSansSymbols-Regular.ttf", "Noto Sans Symbols"), ("NotoSansMath-Regular.ttf", "Noto Sans Math")]
_lock = threading.RLock()
_faces = {}


def available():
    try:
        import freetype  # noqa: F401
        import numpy  # noqa: F401
        import fontTools  # noqa: F401
    except ImportError:
        return False
    return FONTS.exists()


# ---------------------------------------------------------------- scoring (phase.py)
def _np():
    import numpy as np
    return np


def bitmap_array(bm):
    import freetype
    np = _np()
    buffer, pitch = bm.buffer, bm.pitch
    if bm.pixel_mode == freetype.FT_PIXEL_MODE_MONO:
        return np.array([[bool(buffer[y * pitch + x // 8] & (0x80 >> (x % 8))) for x in range(bm.width)]
                         for y in range(bm.rows)], dtype=bool)
    return np.array([[buffer[y * pitch + x] for x in range(bm.width)] for y in range(bm.rows)], dtype=np.uint8)


def components(b):
    np = _np()
    seen = np.zeros_like(b, dtype=bool); n = 0
    for y, x in zip(*np.nonzero(b)):
        if seen[y, x]:
            continue
        n += 1; stack = [(y, x)]; seen[y, x] = True
        while stack:
            cy, cx = stack.pop()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    yy, xx = cy + dy, cx + dx
                    if 0 <= yy < b.shape[0] and 0 <= xx < b.shape[1] and b[yy, xx] and not seen[yy, xx]:
                        seen[yy, xx] = True; stack.append((yy, xx))
    return n


def spurious_blocks(B, G):
    if B.shape[0] < 2 or B.shape[1] < 2:
        return 0
    blk = B[:-1, :-1] & B[1:, :-1] & B[:-1, 1:] & B[1:, 1:]
    cover = (G[:-1, :-1] + G[1:, :-1] + G[:-1, 1:] + G[1:, 1:]) / 4
    return int((blk & (cover < 0.6)).sum())


def mirror_mismatch(b):
    np = _np()
    ys, xs = np.nonzero(b)
    if not len(xs):
        return 0
    c = b[:, xs.min():xs.max() + 1]
    return int((c ^ c[:, ::-1]).sum())


class Face:
    """One font at one face size and variation, rendering a character at 16 sub-pixel phases."""

    def __init__(self, path, face_w, face_h, coords, symmetry_transform):
        import freetype
        from fontTools.ttLib import TTFont
        self.face = freetype.Face(str(path))
        self.face.set_pixel_sizes(face_w, face_h)
        if coords:
            self.face.set_var_design_coords(tuple(coords))
        tt = TTFont(str(path))
        tags = [a.axisTag for a in tt["fvar"].axes] if "fvar" in tt else []
        self.glyphs = tt.getGlyphSet(location=dict(zip(tags, coords)) if tags else None)
        self.cmap = tt.getBestCmap()
        self.sym_transform = symmetry_transform

    def load(self, ch, dx64, mono):
        import freetype
        flags = (freetype.FT_LOAD_TARGET_MONO | freetype.FT_LOAD_RENDER) if mono else \
            (freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
        self.face.set_transform(freetype.Matrix(0x10000, 0, 0, 0x10000), freetype.Vector(dx64, 0))
        try:
            self.face.load_char(ch, flags)
            g = self.face.glyph
            return bitmap_array(g.bitmap), g.bitmap_left, g.bitmap_top, g.advance.x / 64
        finally:
            self.face.set_transform(freetype.Matrix(0x10000, 0, 0, 0x10000), freetype.Vector(0, 0))

    def symmetry(self, ch):
        from fontTools.pens.freetypePen import FreeTypePen
        np = _np()
        name = self.cmap.get(ord(ch))
        if name is None:
            return 0.0
        pen = FreeTypePen(self.glyphs); self.glyphs[name].draw(pen)
        a = pen.array(width=256, height=256, transform=self.sym_transform, contain=True) > 0.5
        ys, xs = np.nonzero(a)
        if not len(xs):
            return 0.0
        c = a[:, xs.min():xs.max() + 1]
        return float((c & c[:, ::-1]).sum() / max((c | c[:, ::-1]).sum(), 1))

    def best(self, ch, phases=True, broken_both_ways=False):
        """Best phase: {'b' (bool bitmap), 'left', 'top', 'advance', 'k', scores}; None if empty."""
        np = _np()
        if ord(ch) not in self.cmap:
            return None
        symmetric = self.symmetry(ch) >= SYMMETRIC
        best = None
        for k in (range(STEPS) if phases else [0]):
            dx = k * 64 // STEPS
            b, bl, bt, adv = self.load(ch, dx, True)
            b = b.astype(bool)
            if not b.any():
                continue
            g, gl, gt, _ = self.load(ch, dx, False)
            g = g.astype(float) / 255
            x0, y0 = min(bl, gl), min(-bt, -gt)
            x1 = max(bl + b.shape[1], gl + g.shape[1]); y1 = max(-bt + b.shape[0], -gt + g.shape[0])
            B = np.zeros((y1 - y0, x1 - x0), bool); G = np.zeros_like(B, dtype=float)
            B[-bt - y0:-bt - y0 + b.shape[0], bl - x0:bl - x0 + b.shape[1]] = b
            G[-gt - y0:-gt - y0 + g.shape[0], gl - x0:gl - x0 + g.shape[1]] = g
            sym = mirror_mismatch(B) if symmetric else 0
            spurious = spurious_blocks(B, G)
            diff = components(B) - components(G > 0.35)
            broken = abs(diff) if broken_both_ways else max(0, diff)
            score = 3 * sym + 2 * spurious + 4 * broken + 0.5 * float(np.abs(B - G).sum())
            if best is None or score < best["score"]:
                best = {"score": score, "k": k, "b": b, "left": bl, "top": bt, "advance": adv,
                        "symmetric_outline": symmetric}
        return best


def _face(path, fw, fh, coords, transform):
    key = (str(path), fw, fh, tuple(coords), transform)
    if key not in _faces:
        _faces[key] = Face(path, fw, fh, coords, transform)
    return _faces[key]


def rows_of(b):
    return ["".join("#" if v else "." for v in r) for r in b]


def crop(b):
    np = _np()
    ys, xs = np.nonzero(b)
    return b[ys.min():ys.max() + 1, xs.min():xs.max() + 1], int(ys.min()), int(xs.min())


# ---------------------------------------------------------------- regional 13×13 (phase.py + prepare.place)
@lru_cache(maxsize=None)
def _cmap(path):
    from fontTools.ttLib import TTFont
    return set(TTFont(str(path)).getBestCmap())


def regional_font(char, region):
    """(font path, variation coordinates, label): the region's Source Han Sans, or for what it lacks
    the first of REGIONAL_FALLBACK that has the character (Plangothic P1 for Han characters)."""
    font = FONTS / f"SourceHanSans{region}-VF.otf"
    if ord(char) not in _cmap(font):
        for name, label in REGIONAL_FALLBACK:
            if (FONTS / name).exists() and ord(char) in _cmap(FONTS / name):
                return FONTS / name, (), label
    return font, (320,), f"思源 {region} w320"


def regional(char, region, font=None):
    """13×13 draft; `font` = (path, variation coordinates, label) overrides the region's font (e.g. a
    full-width symbol from Noto Sans Symbols 2 that no Source Han Sans has)."""
    np = _np()
    font, coords, label = font or regional_font(char, region)
    faces = [(13, 13)] + [f for f in REGIONAL_FACES if f != (13, 13)] if char in SQUARE else REGIONAL_FACES
    for fw, fh in faces:
        r = _face(font, fw, fh, coords, (0.2, 0, 0, 0.2, 0, 40)).best(char, broken_both_ways=True)
        if r is None:
            break
        b, bl, bt = r["b"], r["left"], r["top"]
        native_y = min(13 - max(bt, 0) - 1, 13 - b.shape[0])
        ink, top, left = crop(b)
        h, w = ink.shape
        if w > 13 or h > 13:
            continue
        x, y = max(0, math.ceil((14 - w) / 2) - 1), min(max(native_y + top, 0), 13 - h)
        out = np.zeros((13, 13), dtype=bool)
        out[y:y + h, x:x + w] = ink
        return {"rows": rows_of(out), "phase_k": r["k"], "face": [fw, fh], "label": label,
                "symmetric_outline": r["symmetric_outline"]}
    raise ValueError("无法生成相位底稿（参考字体没有此字，或墨迹放不进 13×13）")


# ---------------------------------------------------------------- .HW / .PR (varraster.py)
def _place(r, cell_w, x, rows_used=H):
    np = _np()
    ink, oy, ox = crop(r["b"])
    h, w = ink.shape
    if h > rows_used or x + w > cell_w or x < 0:
        return None, None
    top_row = BASELINE_ROW - (r["top"] - oy)
    y = min(max(top_row, 0), rows_used - h)
    grid = np.zeros((H, cell_w), bool)
    grid[y:y + h, x:x + w] = ink
    return rows_of(grid), y - top_row


def half_width(path, coords, ch, max_ink=6, cell_w=7, rows_used=H):
    """Narrowest face whose ink fits max_ink columns; a smaller face height before a vertical shift."""
    fallback = None
    for fh in (13, 12, 11, 10):
        for fw in range(13, 3, -1):
            r = _face(path, fw, fh, coords, (0.2, 0, 0, 0.2, 40, 60)).best(ch)
            if r is None:
                return None
            ink, _, _ = crop(r["b"])
            if ink.shape[1] <= max_ink or (fw <= 7 and ink.shape[1] <= cell_w) or fw == 4:
                x = (cell_w - ink.shape[1]) // 2 if ink.shape[1] <= cell_w else 0
                rows, shift = _place(r, cell_w, max(x, 0), rows_used)
                if rows is None:
                    break
                out = {"rows": rows, "phase_k": r["k"], "face": [fw, fh], "shift": shift}
                if not shift:
                    return out
                if fallback is None or abs(shift) < abs(fallback["shift"]):
                    fallback = out
                break
    return fallback


def proportional(path, coords, ch, tight):
    """The font's own advance (tight: ink from column 0 and one blank column after it)."""
    fallback = None
    for fw, fh in ((13, 13), (12, 12), (11, 11), (10, 10)):
        r = _face(path, fw, fh, coords, (0.2, 0, 0, 0.2, 40, 60)).best(ch)
        if r is None:
            return None
        ink, oy, ox = crop(r["b"])
        advance = int(round(r["advance"]))
        x_offset = 0
        if advance and tight:
            cell_w = ink.shape[1] + 1
            rows, shift = _place(r, cell_w, 0)
        elif advance == 0:              # combining mark: its own box, drawn relative to the pen position
            cell_w = ink.shape[1]
            x_offset = r["left"] + ox
            rows, shift = _place(r, cell_w, 0)
        else:
            x = max(r["left"] + ox, 0)
            cell_w = max(advance, x + ink.shape[1] + 1)
            rows, shift = _place(r, cell_w, x)
        if rows is None:
            continue
        out = {"rows": rows, "phase_k": r["k"], "face": [fw, fh], "shift": shift,
               "advance": cell_w if advance else 0, "x_offset": x_offset}
        if not shift:
            return out
        if fallback is None or abs(shift) < abs(fallback["shift"]):
            fallback = out
    return fallback


def western(gid, char, label, script):
    key = next((k for k in WESTERN_FONTS if label.startswith(k)), None)
    if key is None:
        raise ValueError("没有这个字的参考字体记录")
    name, coords = WESTERN_FONTS[key]
    path = FONTS / name
    if gid.endswith(".HW"):
        kana = script == "kana"
        r = half_width(path, coords, char, max_ink=7 if kana else 6, rows_used=13 if kana else H)
    else:
        r = proportional(path, coords, char, tight=script == "western")
    if r is None:
        raise ValueError("无法生成相位底稿（放不进 14 行字格）")
    return {**r, "label": label}


def compute(gid, char, group, label="", script=""):
    """Rows of the phase-searched draft for one glyph."""
    with _lock:
        if group in ("SC", "TC", "JP", "KR"):
            return regional(char, group)
        if group in ("HW", "PR"):
            return western(gid, char, label, script)
    raise ValueError("这个分组没有相位底稿（几何字符由规则生成）")
