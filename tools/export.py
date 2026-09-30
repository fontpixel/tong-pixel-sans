"""Export the download formats: BDF and PCF per face, and vector OpenType fonts with every region in one font.

    python3 tools/export.py [out-dir] [--only square|dot] [--skip-otf]      (default: site/downloads/)

Writes (out-dir is not in git):
  bdf/  the ten BDFs (as tools/build.py makes them)
  pcf/  the same ten as PCF (bdftopcf; PCF has no room for code points above U+FFFF, so those are left out)
  ttf/ otf/ woff2/  vector fonts, one per shape and spacing:
        TongPixelSans-Square, TongPixelSansMono-Square    every pixel a square; touching pixels merged
        TongPixelSans-Dot, TongPixelSansMono-Dot          every pixel a round dot
  manifest.json  file sizes and glyph counts, for the download table

Vector fonts: 100 units per pixel (1,400 per em), ascent 1,100, descent 300, so 14 px and its
multiples land on whole pixels. The default glyphs are the Simplified Chinese face; the OpenType
`locl` feature switches to the Traditional (ZHT, ZHH), Japanese (JAN) and Korean (KOR) glyphs,
and in Latin, Greek and Cyrillic runs to the western glyphs of the Latin faces (narrow quotation
marks and ellipsis), so one font serves every region. Square outlines trace the boundary of each
connected run of pixels (holes included, touching corners kept apart), with points only where the
outline turns; dots are one shared circle placed by composite glyphs (TrueType) or one subroutine
(CFF). The outline tracing follows fontpixel's opf/vectorize.py (MIT, same author).
"""
from __future__ import annotations

import datetime
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import build  # noqa: E402

UNIT, UPM = 100, 1400
ASCENT, DESCENT = build.ASCENT, build.DESCENT
DOT_DIAMETER = 90                       # a little gap between dots
REGIONS = ["SC", "TC", "JP", "KR"]
LANGS = {"TC": ["ZHT ", "ZHH "], "JP": ["JAN "], "KR": ["KOR "]}
CJK_SCRIPTS = ["DFLT", "hani", "kana", "hang", "bopo"]
WESTERN_SCRIPTS = ["latn", "grek", "cyrl"]
FAMILY = {"prop": "Tong Pixel Sans", "mono": "Tong Pixel Sans Mono"}


# ---------------------------------------------------------------- outlines
def contours(rows):
    """Closed polygons around every connected run of lit pixels (bitmap coordinates, y down)."""
    h, w = len(rows), len(rows[0]) if rows else 0
    lit = lambda x, y: 0 <= x < w and 0 <= y < h and rows[y][x] == "#"
    edges = {}
    for y in range(h):
        for x in range(w):
            if rows[y][x] != "#":
                continue
            if not lit(x, y - 1):
                edges.setdefault((x, y), []).append((x + 1, y))
            if not lit(x + 1, y):
                edges.setdefault((x + 1, y), []).append((x + 1, y + 1))
            if not lit(x, y + 1):
                edges.setdefault((x + 1, y + 1), []).append((x, y + 1))
            if not lit(x - 1, y):
                edges.setdefault((x, y + 1), []).append((x, y))
    out = []
    while edges:
        start = next(iter(edges))
        pt, poly, prev = start, [], None
        while True:
            outgoing = edges.get(pt)
            if not outgoing:
                break
            if len(outgoing) == 1 or prev is None:
                nxt = outgoing[0]
            else:        # turn towards the ink first, so touching corners stay two loops
                px, py = prev
                order = [(-py, px), (px, py), (py, -px)]
                nxt = min(outgoing, key=lambda e: order.index((e[0] - pt[0], e[1] - pt[1]))
                          if (e[0] - pt[0], e[1] - pt[1]) in order else 3)
            outgoing.remove(nxt)
            if not outgoing:
                del edges[pt]
            d = (nxt[0] - pt[0], nxt[1] - pt[1])
            if d != prev:
                poly.append(pt)
            prev, pt = d, nxt
            if pt == start:
                break
        if len(poly) > 2:
            first = (poly[1][0] - poly[0][0], poly[1][1] - poly[0][1])
            first = ((first[0] > 0) - (first[0] < 0), (first[1] > 0) - (first[1] < 0))
            if first == prev:
                poly.pop(0)
            out.append(poly)
    return out


def area2(poly):
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]))


def square_polys(g):
    """Font-unit polygons of a glyph record, clockwise outer contours (TrueType and CFF both accept it)."""
    rows = g["rows"]
    if not rows:
        return []
    top = g["y"] + len(rows)
    polys = [[((g["x"] + x) * UNIT, (top - y) * UNIT) for x, y in p] for p in contours(rows)]
    if sum(area2(p) for p in polys) > 0:
        polys = [p[::-1] for p in polys]
    return polys


def dots(g):
    """Lower-left corners (font units) of the lit pixels."""
    rows = g["rows"]
    top = g["y"] + len(rows)
    return [((g["x"] + x) * UNIT, (top - y - 1) * UNIT) for y, r in enumerate(rows) for x, v in enumerate(r) if v == "#"]


# ---------------------------------------------------------------- glyph plan
def signature(g):
    return (tuple(g["rows"]), g["adv"], g["x"], g["y"])


def gname(cp):
    return f"uni{cp:04X}" if cp <= 0xFFFF else f"u{cp:05X}"


def plan(spacing):
    """(glyph order, {name: record}, cmap, {region: {default name: variant name}})."""
    faces = {r: (p if spacing == "prop" else m) for r, p, m in build.faces(ROOT)}
    lp, lm = build.latin_faces(ROOT)
    faces["Latin"] = lp if spacing == "prop" else lm
    base = faces["SC"]
    glyphs, cmap = {}, {}
    for cp in sorted(base):
        cmap[cp] = gname(cp)
        glyphs[cmap[cp]] = base[cp]
    subs, by_sig = {}, {}
    for region in ["TC", "JP", "KR", "Latin"]:
        subs[region] = {}
        for cp in sorted(faces[region]):
            g = faces[region][cp]
            if cp not in cmap:                 # only in this face: its own default glyph
                cmap[cp] = gname(cp)
                glyphs[cmap[cp]] = g
                continue
            if signature(g) == signature(glyphs[cmap[cp]]):
                continue
            name = by_sig.setdefault(signature(g), f"{gname(cp)}.{region.lower()}")
            glyphs[name] = g
            subs[region][cmap[cp]] = name
    order = [".notdef"] + sorted(glyphs, key=lambda n: (n.split(".")[0], n))
    return order, glyphs, cmap, subs


def feature_text(subs):
    lines = ["languagesystem DFLT dflt;"]
    for s in CJK_SCRIPTS + WESTERN_SCRIPTS:
        if s != "DFLT":
            lines.append(f"languagesystem {s} dflt;")
        for tags in LANGS.values():
            for t in tags:
                lines.append(f"languagesystem {s} {t.strip()};")
    for region, table in subs.items():
        if table:
            lines.append(f"lookup L_{region} {{")
            lines += [f"  sub \\{a} by \\{b};" for a, b in table.items()]
            lines.append(f"}} L_{region};")
    lines.append("feature locl {")
    for s in CJK_SCRIPTS:
        lines.append(f"  script {s};")
        for region, tags in LANGS.items():
            for t in tags:
                lines.append(f"  language {t.strip()} exclude_dflt;")
                if subs.get(region):
                    lines.append(f"    lookup L_{region};")
    for s in WESTERN_SCRIPTS:           # western runs: narrow western punctuation, whatever the language
        lines.append(f"  script {s};")
        if subs.get("Latin"):
            lines.append("    lookup L_Latin;")
        for tags in LANGS.values():
            for t in tags:
                lines.append(f"  language {t.strip()} include_dflt;")
    lines.append("} locl;")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- fonts
def names(family, style, version):
    return {"familyName": family, "styleName": "Regular", "uniqueFontIdentifier": f"{family} {style} {version}",
            "fullName": f"{family} {style}", "psName": f"{family.replace(' ', '')}-{style}",
            "version": f"Version {version}", "copyright": "Tong Pixel Sans. Derived from Source Han Sans (Adobe), Source Sans 3 "
            "(Adobe), the Noto fonts (Google), Plangothic P1; Han bitmaps partly after TUMBLED (TsFreddie).",
            "licenseDescription": "This Font Software is licensed under the SIL Open Font License, Version 1.1.",
            "licenseInfoURL": "https://openfontlicense.org", "typographicFamily": family,
            "typographicSubfamily": style}


def lsb(g):
    xs = [x for r in g["rows"] for x, v in enumerate(r) if v == "#"]
    return (g["x"] + min(xs)) * UNIT if xs else 0


def font_builder(order, cmap, glyph_records, family, style, version, tt):
    from fontTools.fontBuilder import FontBuilder
    assert not any(n in family for n in ("Source", "Plangothic", "遍黑"))
    fb = FontBuilder(UPM, isTTF=tt)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap({cp: n for cp, n in cmap.items()})
    return fb


def finish(fb, order, glyph_records, subs, family, style, version, dot=False):
    from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
    metrics = {".notdef": (UPM // 2, UNIT)}
    for n in order[1:]:
        g = glyph_records[n]
        metrics[n] = (g["adv"] * UNIT, lsb(g) + ((UNIT - DOT_DIAMETER) // 2 if dot and g["rows"] else 0))
    if "dot" in order:
        metrics["dot"] = (UNIT, (UNIT - DOT_DIAMETER) // 2)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=ASCENT * UNIT, descent=-DESCENT * UNIT)
    fb.setupNameTable(names(family, style, version))
    fb.setupOS2(sTypoAscender=ASCENT * UNIT, sTypoDescender=-DESCENT * UNIT, sTypoLineGap=0,
                usWinAscent=ASCENT * UNIT, usWinDescent=DESCENT * UNIT, fsType=0, achVendID="TONG",
                usWeightClass=400, fsSelection=0x40)
    fb.setupPost(keepGlyphNames=False)
    addOpenTypeFeaturesFromString(fb.font, feature_text(subs))
    fb.font["OS/2"].recalcUnicodeRanges(fb.font)
    return fb.font


def notdef_pen(pen):
    for x0, y0, x1, y1 in ((UNIT, 0, 6 * UNIT, 10 * UNIT), (2 * UNIT, UNIT, 5 * UNIT, 9 * UNIT)):
        pts = [(x0, y0), (x0, y1), (x1, y1), (x1, y0)]
        if x0 == 2 * UNIT:
            pts = pts[::-1]
        pen.moveTo(pts[0])
        for p in pts[1:]:
            pen.lineTo(p)
        pen.closePath()


def build_ttf(spacing, shape, version, plan_):
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    order, glyph_records, cmap, subs = plan_
    order = order + (["dot"] if shape == "dot" else [])
    family, style = FAMILY[spacing], shape.capitalize()
    fb = font_builder(order, cmap, glyph_records, family, style, version, True)
    glyf = {}
    pen = TTGlyphPen(None)
    notdef_pen(pen)
    glyf[".notdef"] = pen.glyph()
    if shape == "dot":
        r, c = DOT_DIAMETER / 2, 0.9142135623730951 * DOT_DIAMETER / 2
        o = UNIT / 2
        pen = TTGlyphPen(None)
        pen.moveTo((o + r, o))
        pen.qCurveTo((o + c, o + c), (o, o + r))
        pen.qCurveTo((o - c, o + c), (o - r, o))
        pen.qCurveTo((o - c, o - c), (o, o - r))
        pen.qCurveTo((o + c, o - c), (o + r, o))
        pen.closePath()
        glyf["dot"] = pen.glyph()
    components = {"dot": glyf.get("dot")}        # the pen checks a component's name against a glyph set
    for n in order[1:]:
        if n == "dot":
            continue
        g = glyph_records[n]
        pen = TTGlyphPen(components)
        if shape == "square":
            for poly in square_polys(g):
                pen.moveTo(poly[0])
                for p in poly[1:]:
                    pen.lineTo(p)
                pen.closePath()
        else:
            for x, y in dots(g):
                pen.addComponent("dot", (1, 0, 0, 1, x, y))
        glyf[n] = pen.glyph()
    fb.setupGlyf(glyf)
    return finish(fb, order, glyph_records, subs, family, style, version, dot=shape == "dot")


def build_otf(spacing, shape, version, plan_):
    from fontTools.misc.psCharStrings import T2CharString
    from fontTools.pens.t2CharStringPen import T2CharStringPen
    order, glyph_records, cmap, subs = plan_
    family, style = FAMILY[spacing], shape.capitalize()
    fb = font_builder(order, cmap, glyph_records, family, style, version, False)
    charstrings = {}
    pen = T2CharStringPen(UPM // 2, None)
    notdef_pen(pen)
    charstrings[".notdef"] = pen.getCharString()
    r = DOT_DIAMETER / 2
    k = 0.5522847498 * r
    # the shared dot, drawn from its rightmost point, relative moves only (a global subroutine)
    circle = [0, k, -(r - k), r - k, -k, 0, "rrcurveto", -k, 0, -(r - k), -(r - k), 0, -k, "rrcurveto",
              0, -k, r - k, -(r - k), k, 0, "rrcurveto", k, 0, r - k, r - k, 0, k, "rrcurveto", "return"]
    for n in order[1:]:
        g = glyph_records[n]
        w = g["adv"] * UNIT
        if shape == "square":
            pen = T2CharStringPen(w, None)
            for poly in square_polys(g):
                pen.moveTo(poly[0])
                for p in poly[1:]:
                    pen.lineTo(p)
                pen.closePath()
            charstrings[n] = pen.getCharString()
        else:
            prog, cx, cy = [w], 0, 0
            for x, y in dots(g):
                tx, ty = x + UNIT / 2 + r, y + UNIT / 2      # rightmost point of this dot
                prog += [tx - cx, ty - cy, "rmoveto", -107, "callgsubr"]
                cx, cy = tx, ty
            prog.append("endchar")
            charstrings[n] = T2CharString(program=prog)
    fb.setupCFF(FAMILY[spacing].replace(" ", "") + "-" + style, {"FullName": f"{family} {style}"}, charstrings,
                {"defaultWidthX": 0, "nominalWidthX": 0})
    cff = fb.font["CFF "].cff
    if shape == "dot":
        cff.GlobalSubrs.append(T2CharString(program=circle))
        top = cff.topDictIndex[0]
        for cs in top.CharStrings.values():
            cs.globalSubrs = cff.GlobalSubrs
    return finish(fb, order, glyph_records, subs, family, style, version, dot=shape == "dot")


# ---------------------------------------------------------------- main
def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = Path(args[0]) if args else ROOT / "site/downloads"
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    version = datetime.date.today().strftime("%Y.%m.%d")
    for d in ("bdf", "pcf", "ttf", "otf", "woff2"):
        (out / d).mkdir(parents=True, exist_ok=True)
    manifest = {"version": version, "files": {}}
    tmp = ROOT / "build"
    subprocess.run([sys.executable, str(HERE / "build.py"), str(tmp)], check=True, stdout=subprocess.DEVNULL)
    faces = [f"TongPixelSans{k}{r}-14" for r in REGIONS + ["Latin"] for k in ("", "Mono")]
    for f in faces:
        shutil.copy2(tmp / f"{f}.bdf", out / "bdf" / f"{f}.bdf")
        # PCF encodes 16-bit code points only: bdftopcf skips the supplementary-plane glyphs (extension B …)
        r = subprocess.run(["bdftopcf", "-o", str(out / "pcf" / f"{f}.pcf"), str(tmp / f"{f}.bdf")],
                           check=True, capture_output=True, text=True)
        manifest.setdefault("pcf_skipped", {})[f] = r.stderr.count("encoding too large")
        for kind in ("bdf", "pcf"):
            p = out / kind / f"{f}.{kind}"
            manifest["files"][f"{kind}/{p.name}"] = p.stat().st_size
    print("bdf, pcf:", len(faces), "each")
    for spacing in ("prop", "mono"):
        plan_ = plan(spacing)
        print(spacing, "glyphs", len(plan_[0]), "locl", {r: len(t) for r, t in plan_[3].items()})
        for shape in ("square", "dot"):
            if only and shape != only:
                continue
            stem = f"{FAMILY[spacing].replace(' ', '')}-{shape.capitalize()}"
            tt = build_ttf(spacing, shape, version, plan_)
            tt.save(out / "ttf" / f"{stem}.ttf")
            tt.flavor = "woff2"
            tt.save(out / "woff2" / f"{stem}.woff2")
            if "--skip-otf" not in sys.argv:
                build_otf(spacing, shape, version, plan_).save(out / "otf" / f"{stem}.otf")
            for kind in ("ttf", "woff2", "otf"):
                p = out / kind / f"{stem}.{kind}"
                if p.exists():
                    manifest["files"][f"{kind}/{p.name}"] = p.stat().st_size
            print(stem, {k: manifest["files"].get(f"{k}/{stem}.{k}") for k in ("ttf", "woff2", "otf")})
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
