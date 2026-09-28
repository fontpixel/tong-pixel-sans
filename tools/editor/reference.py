"""Reference outlines for the editor, drawn from the reference fonts in reference-fonts/ (not in git;
see docs/reference-fonts.md). Needs fontTools; without it or without the fonts the editor simply
shows no reference.

- regional glyphs (SC TC JP KR): that region's Source Han Sans at weight 400, em = 14 px, baseline
  12 px below the top of the 14×14 cell (the geometry the drafts were made with);
- .HW/.PR glyphs: the font and face size of their draft (tools/editor/data/reference-western.txt),
  on the baseline (row 11), left edge aligned to the draft's leftmost ink column.
"""
from __future__ import annotations

import threading
from functools import lru_cache
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
FONTS = HERE.parent.parent / "reference-fonts"
REGIONAL = {r: (f"SourceHanSans{r}-VF.otf", (("wght", 400),)) for r in ("SC", "TC", "JP", "KR")}
WESTERN = {"Source Sans 3": ("SourceSans3-VF.otf", (("wght", 320),)),
           "Noto Sans Thai": ("NotoSansThai-VF.ttf", (("wdth", 100), ("wght", 320))),
           "Noto Sans Arabic": ("NotoSansArabic-VF.ttf", (("wdth", 100), ("wght", 320))),
           "Noto Sans": ("NotoSans-VF.ttf", (("wdth", 100), ("wght", 320))),
           "思源 JP": ("SourceHanSansJP-VF.otf", (("wght", 320),))}
_lock = threading.RLock()


def _table():
    out = {}
    for line in (HERE / "data/reference-western.txt").read_text(encoding="utf-8").splitlines():
        if line.startswith("U+"):
            gid, label, fw, fh, left = line.split("\t")
            out[gid] = (label, int(fw), int(fh), int(left))
    return out


WESTERN_REF = _table()


@lru_cache(maxsize=12)
def _face(name, location):
    from fontTools.ttLib import TTFont
    font = TTFont(str(FONTS / name))
    return font, font.getGlyphSet(location=dict(location))


def available(gid):
    group = gid.rsplit(".", 1)[-1]
    if group in REGIONAL:
        name = REGIONAL[group][0]
    elif gid in WESTERN_REF:
        label = WESTERN_REF[gid][0]
        name = next((WESTERN[k][0] for k in WESTERN if label.startswith(k)), None)
    else:
        return False
    try:
        import fontTools  # noqa: F401
    except ImportError:
        return False
    return bool(name) and (FONTS / name).exists()


def label(gid):
    return WESTERN_REF.get(gid, ("",))[0]


def svg(gid, char, cell_w, cell_h, fill="#009ec0"):
    """The outline as an SVG in cell pixel units (viewBox = the glyph's cell)."""
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.pens.svgPathPen import SVGPathPen
    group = gid.rsplit(".", 1)[-1]
    with _lock:
        if group in REGIONAL:
            font, glyphs = _face(*REGIONAL[group])
            upem = font["head"].unitsPerEm
            sx = sy = 14 / upem
            dx, base = 0, 12
        else:
            lab, fw, fh, left = WESTERN_REF[gid]
            key = next(k for k in WESTERN if lab.startswith(k))
            font, glyphs = _face(*WESTERN[key])
            upem = font["head"].unitsPerEm
            sx, sy = fw / upem, fh / upem
            base = 11
        name = font.getBestCmap().get(ord(char))
        if name is None:
            raise ValueError("参考字体没有此字")
        pen = SVGPathPen(glyphs)
        glyphs[name].draw(pen)
        if group not in REGIONAL:
            bp = BoundsPen(glyphs)
            glyphs[name].draw(bp)
            dx = left - bp.bounds[0] * sx if bp.bounds else 0
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {cell_w} {cell_h}">'
            f'<path fill="{fill}" transform="translate({dx} {base}) scale({sx} {-sy})" '
            f'd="{escape(pen.getCommands(), quote=True)}"/></svg>').encode()
