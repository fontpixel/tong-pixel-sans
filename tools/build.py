"""Build the Tong Pixel Sans BDF fonts from the plain-text glyph sources.

    python tools/build.py [output-dir]      (default: build/)

Two sizes, the same East Asian glyphs (SIZES): "Tong Pixel Sans 14 Large" (the default; western and
other non-CJK scripts drawn larger, 18-px cell: ascent 14, descent 4) and "Tong Pixel Sans 14 Small"
(the compact one, 14-px cell: ascent 11, descent 3). Per size and region (SC, TC, JP, KR) one
proportional face (TongPixelSans14<Size>-<R>.bdf) and one monospace, dual-width face
(TongPixelSansMono14<Size>-<R>.bdf); and two faces without any East Asian glyph (…-Latin.bdf,
latin_faces). Needs only the Python standard library.

Sources (glyphs/<GROUP>/<PAGE>xx.txt, see README.md):
- SC TC JP KR: 13×13 ink in a 14×14 cell (hanzi, kana, bopomofo, Hangul, full-width symbols).
  A code point missing in a region is taken from another region (FALLBACK).
- HW: half-width 7×14 (western letters and symbols, half-width kana); PR: proportional ×14
  (western, Thai, Arabic). adv=auto = ink width + 1 (one blank column), ink from column 0.
- GEOMETRIC-FULL / GEOMETRIC-HALF: box drawing and blocks (full width in the proportional faces),
  braille and Powerline (half width).
- Large size: HW-L, PR-L, GEOMETRIC-FULL-L, GEOMETRIC-HALF-L, the same with 18-row cells (14 rows
  above the baseline). A code point without a large glyph uses the small one on the same baseline
  (half-width kana and Hangul move up with the East Asian glyphs). The 13×13 East Asian ink sits
  2 px below the baseline in Small and 1 px below in Large (as in Source Han Sans).
Rules:
- proportional faces: letters and marks, and punctuation/symbols that the region's Source Han
  Sans draws half-width or proportional (build-data/narrow-width.txt), use the proportional
  western glyph; other punctuation/symbols keep the regional full-width glyph; the half-width
  forms FF61–FF9F are half-width.
- monospace faces: every half-width glyph wins; Thai/Arabic go into 7- or 14-column cells.
- U+2014/U+2015 full-width dashes whose ink spans the ink box fill the blank left column, so
  —— is unbroken. Spaces and zero-width characters are generated.
"""
from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGIONS = ["SC", "TC", "JP", "KR"]
FALLBACK = {"SC": ["SC", "TC", "JP", "KR"], "TC": ["TC", "JP", "SC", "KR"],
            "JP": ["JP", "TC", "SC", "KR"], "KR": ["KR", "TC", "JP", "SC"]}
ASCENT, DESCENT = 11, 3          # the Small cell; tools that draw 14-row cells use these
SIZES = {"Large": {"ascent": 14, "descent": 4, "cjk_below": 1, "suffix": "-L"},
         "Small": {"ascent": ASCENT, "descent": DESCENT, "cjk_below": 2, "suffix": ""}}
WESTERN_GROUPS = ["HW", "PR", "GEOMETRIC-FULL", "GEOMETRIC-HALF"]
LARGE_GROUPS = [g + "-L" for g in WESTERN_GROUPS]
HALFWIDTH_EAST_ASIAN = (0xFF61, 0xFFDC)   # half-width kana and Hangul: placed like the full-width glyphs
JOIN_ACROSS = {0x2014, 0x2015}


# ---------------------------------------------------------------- sources
def read_group(group, root=ROOT):
    """{code point: {'rows', 'state', 'meta', 'alias'}} of one glyph group."""
    out = {}
    for p in sorted((root / "glyphs" / group).glob("*.txt")):
        for block in p.read_text().split("\n\n"):
            lines = [l for l in block.split("\n") if l]
            if not lines:
                continue
            head = lines[0].split(" ")
            cp = int(head[0][2:], 16)
            if len(head) > 3 and head[2] == "=":
                out[cp] = {"alias": head[3]}
                continue
            meta = dict(t.split("=", 1) for t in head[2:])
            rows = [l for l in lines[2:] if set(l) <= {".", "#"}]
            out[cp] = {"rows": rows, "state": lines[1], "meta": meta, "id": f"U+{cp:04X}.{group}"}
    return out


def resolve(groups, group, cp, seen=()):
    e = groups[group][cp]
    if "alias" not in e:
        return e
    tid = e["alias"]
    tcp, tgroup = int(tid[2:].split(".")[0], 16), tid.split(".")[1]
    if (tgroup, tcp) in seen:
        raise ValueError(f"alias loop at {tid}")
    return resolve(groups, tgroup, tcp, seen + ((group, cp),))


def read_narrow(root=ROOT):
    out = {}
    for line in (root / "build-data/narrow-width.txt").read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        region, *parts = line.split()
        cps = set()
        for part in parts:
            a, _, b = part.partition("..")
            cps.update(range(int(a, 16), int(b or a, 16) + 1))
        out[region] = cps
    return out


def read_constants(root=ROOT):
    out = {}
    for line in (root / "build-data/constants.txt").read_text().splitlines():
        if line and not line.startswith("#"):
            k, v = line.split()
            out[k] = int(v)
    return out


# ---------------------------------------------------------------- glyph records
def G(rows, adv, x, y, state):
    return {"rows": rows, "adv": adv, "x": x, "y": y, "state": state}


def cjk(rows, state, below=2):
    assert len(rows) == 13 and all(len(r) == 13 for r in rows)
    return G(rows, 14, 1, -below, state)


def joined(rows, state, below=2):
    assert len(rows) == 13 and all(len(r) == 13 for r in rows)
    return G([("#" if r == "#" * 13 else ".") + r for r in rows], 14, 0, -below, state)


def cell(rows, adv, x_offset, state, descent=DESCENT, height=14):
    assert len(rows) == height and len({len(r) for r in rows}) == 1
    return G(rows, adv, x_offset, -descent, state)


def western(e, descent=DESCENT, height=14):
    rows, meta, st = e["rows"], e["meta"], e["state"]
    if meta.get("adv") == "auto":
        cols = [x for r in rows for x, v in enumerate(r) if v == "#"]
        x0, x1 = min(cols), max(cols)
        return cell([r[x0:x1 + 1] for r in rows], x1 - x0 + 2, 0, st, descent, height)
    return cell(rows, int(meta["adv"]), int(meta.get("x", 0)), st, descent, height)


def crop(g):
    rows = g["rows"]
    ys = [y for y, r in enumerate(rows) if "#" in r]
    if not ys:
        return {**g, "rows": [], "x": 0, "y": 0}
    xs = [x for r in rows for x, v in enumerate(r) if v == "#"]
    x0, x1, y0, y1 = min(xs), max(xs) + 1, ys[0], ys[-1] + 1
    return {**g, "rows": [r[x0:x1] for r in rows[y0:y1]], "x": g["x"] + x0, "y": g["y"] + len(rows) - y1}


def blanks(space_pr):
    fixed = {0x0020: (space_pr, 7), 0x00A0: (space_pr, 7), 0x3000: (14, 14), 0x3164: (14, 14),
             0x2000: (7, 7), 0x2001: (14, 14), 0x2002: (7, 7), 0x2003: (14, 14), 0x2004: (5, 7), 0x2005: (4, 7),
             0x2006: (2, 7), 0x2007: (7, 7), 0x2008: (space_pr, 7), 0x2009: (3, 7), 0x200A: (1, 7),
             0x202F: (3, 7), 0x205F: (3, 7)}
    zero = [0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x2028, 0x2029, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
            0x2060, 0x2061, 0x2062, 0x2063, 0x2064, 0xFEFF, 0x061C]
    prop = {cp: G([], a, 0, 0, "blank") for cp, (a, _) in fixed.items()}
    mono = {cp: G([], a, 0, 0, "blank") for cp, (_, a) in fixed.items()}
    for cp in zero:
        prop[cp] = mono[cp] = G([], 0, 0, 0, "blank")
    return prop, mono


def to_mono(g):
    if g["adv"] == 0:
        return g, False
    w = len(g["rows"][0])
    target = 7 if w <= 7 else 14
    if w > target:
        return {**g, "adv": target}, True
    pad = (target - w) // 2
    return {**g, "rows": ["." * pad + r + "." * (target - w - pad) for r in g["rows"]], "adv": target}, target == 14


def letter(cp):
    return unicodedata.category(chr(cp))[0] in "LM"


# ---------------------------------------------------------------- BDF
def bdf(glyphs, family, mono, size="Small"):
    assert not any(n in family for n in ("Source", "Plangothic", "遍黑"))
    props = [f'FAMILY_NAME "{family}"', 'FOUNDRY "Tong"', 'WEIGHT_NAME "Medium"', 'SLANT "R"', 'SETWIDTH_NAME "Normal"',
             'PIXEL_SIZE 14', 'POINT_SIZE 140', 'RESOLUTION_X 75', 'RESOLUTION_Y 75', 'SPACING "P"',
             f'FONT_ASCENT {SIZES[size]["ascent"]}', f'FONT_DESCENT {SIZES[size]["descent"]}', 'CHARSET_REGISTRY "ISO10646"', 'CHARSET_ENCODING "1"',
             'COPYRIGHT "Derived from Source Han Sans (Adobe), Source Sans 3, Source Code Pro (Adobe), Noto Sans, Noto Sans Thai, '
             'Noto Sans Arabic, Hebrew, Georgian, Armenian, Lao, Math, Symbols, Symbols 2 (Google), Plangothic P1 (Plangothic Project), '
             'with Han bitmaps drawing on TUMBLED (TsFreddie); '
             'SIL Open Font License 1.1; Reserved Font Names Source, Plangothic"']
    if mono:
        props.append('AVERAGE_WIDTH 70')
    body, box = [], [0, 0, 0, 0]
    for cp, g in sorted(glyphs.items()):
        g = crop(g)
        if g["rows"]:
            box = [min(box[0], g["x"]), min(box[1], g["y"]), max(box[2], g["x"] + len(g["rows"][0])),
                   max(box[3], g["y"] + len(g["rows"]))]
        w, h = (len(g["rows"][0]), len(g["rows"])) if g["rows"] else (0, 0)
        nbytes = max(1, (w + 7) // 8)
        body += [f"STARTCHAR U+{cp:04X}", f"ENCODING {cp}", f"SWIDTH {g['adv'] * 1000 // 14} 0", f"DWIDTH {g['adv']} 0",
                 f"BBX {w} {h} {g['x']} {g['y']}", "BITMAP"]
        for r in g["rows"]:
            bits = r.replace(".", "0").replace("#", "1").ljust(nbytes * 8, "0")
            body.append(f"{int(bits, 2):0{nbytes * 2}X}")
        body.append("ENDCHAR")
    head = ["STARTFONT 2.1", "COMMENT SIL Open Font License 1.1; see OFL.txt",
            "COMMENT DRAFT: not fully human-reviewed; see README.md and report.json",
            f"FONT -tong-{family}-medium-r-normal--14-140-75-75-{'c' if mono else 'p'}-{70 if mono else 140}-iso10646-1",
            "SIZE 14 75 75", f"FONTBOUNDINGBOX {box[2] - box[0]} {box[3] - box[1]} {box[0]} {box[1]}",
            f"STARTPROPERTIES {len(props)}", *props, "ENDPROPERTIES", f"CHARS {len(glyphs)}"]
    return "\n".join(head + body + ["ENDFONT"]) + "\n"


# ---------------------------------------------------------------- faces
def western_groups(groups, size):
    """(proportional, half-width, full geometric, half geometric) western glyphs of a size: in Large, the
    -L groups override the small glyphs, which otherwise stay on the same baseline."""
    pr = {cp: {**western(e), "src": e["id"]} for cp in groups["PR"] for e in [resolve(groups, "PR", cp)]}
    hw = {cp: {**western(e), "src": e["id"]} for cp in groups["HW"] for e in [resolve(groups, "HW", cp)]}
    full = {cp: {**cell(e["rows"], 14, 0, "generated"), "src": e["id"]} for cp, e in groups["GEOMETRIC-FULL"].items()}
    half = {cp: {**cell(e["rows"], 7, 0, "generated"), "src": e["id"]} for cp, e in groups["GEOMETRIC-HALF"].items()}
    if size == "Large":
        d, h = SIZES["Large"]["descent"], SIZES["Large"]["ascent"] + SIZES["Large"]["descent"]
        lo, hi = HALFWIDTH_EAST_ASIAN
        for cp, g in hw.items():
            if lo <= cp <= hi:
                hw[cp] = {**g, "y": g["y"] + SIZES["Small"]["cjk_below"] - SIZES["Large"]["cjk_below"]}
        for name, face in (("PR-L", pr), ("HW-L", hw)):
            for cp in groups.get(name, {}):
                e = resolve(groups, name, cp)
                face[cp] = {**western(e, d, h), "src": e["id"]}
        for name, face, w in (("GEOMETRIC-FULL-L", full, 14), ("GEOMETRIC-HALF-L", half, 7)):
            for cp, e in groups.get(name, {}).items():
                face[cp] = {**cell(e["rows"], w, 0, "generated", d, h), "src": e["id"]}
    return pr, hw, full, half


def faces(root=ROOT, size="Small"):
    """(region, proportional face, monospace face) for each region; a face maps code point -> glyph,
    and each glyph's "src" names the source glyph it was made from (None for generated blanks)."""
    groups = {g: read_group(g, root) for g in REGIONS + WESTERN_GROUPS + (LARGE_GROUPS if size == "Large" else [])}
    below = SIZES[size]["cjk_below"]
    by_region = {}
    for r in REGIONS:
        d = {}
        for cp in groups[r]:
            e = resolve(groups, r, cp)
            d[cp] = {**(joined(e["rows"], e["state"], below) if cp in JOIN_ACROSS else cjk(e["rows"], e["state"], below)),
                     "src": e["id"]}
        by_region[r] = d
    union = set().union(*(set(d) for d in by_region.values()))
    pr, hw, full, half = western_groups(groups, size)
    geo_prop = {cp: (full[cp] if cp < 0x25A0 else half[cp]) for cp in full}
    blank_prop, blank_mono = blanks(read_constants(root)["space_advance_proportional"])
    narrow = read_narrow(root)
    for region in REGIONS:
        base = {}
        for cp in union:
            src = next(loc for loc in FALLBACK[region] if cp in by_region[loc])
            base[cp] = by_region[src][cp]
        prop = dict(base)
        for cp, g in pr.items():
            if cp not in prop or letter(cp) or cp in narrow[region]:
                prop[cp] = g
        for cp, g in hw.items():
            if 0xFF61 <= cp <= 0xFF9F:
                prop[cp] = g
            else:
                prop.setdefault(cp, g)
        for cp, g in {**geo_prop, **blank_prop}.items():
            prop.setdefault(cp, g)
        mono = dict(base)
        mono.update(hw)
        mono.update(half)
        for cp, g in pr.items():
            if cp not in mono:
                mono[cp], _ = to_mono(g)
        for cp, g in blank_mono.items():
            mono.setdefault(cp, g)
        yield region, prop, mono


def east_asian(cp):
    """Han, kana, Hangul and the full-width / half-width forms: left out of the Latin faces."""
    return any(a <= cp <= b for a, b in ((0x1100, 0x11FF), (0x2E80, 0x9FFF), (0xA960, 0xA97F), (0xAC00, 0xD7FF),
                                         (0xF900, 0xFAFF), (0xFE10, 0xFE1F), (0xFE30, 0xFE4F), (0xFF00, 0xFFEF),
                                         (0x1B000, 0x1B16F), (0x1F200, 0x1F2FF), (0x20000, 0x3FFFF)))


def latin_faces(root=ROOT, size="Small"):
    """(proportional face, monospace face) without any East Asian glyph: the western proportional (PR)
    and half-width (HW) glyphs, half-width geometric characters and the non-CJK spaces. Here the
    quotation marks, ellipsis and dashes are always the narrow western ones (in the SC / TC faces they
    follow Source Han Sans and are full-width)."""
    groups = {g: read_group(g, root) for g in WESTERN_GROUPS + (LARGE_GROUPS if size == "Large" else [])}
    pr, hw, _, half = western_groups(groups, size)
    pr = {cp: g for cp, g in pr.items() if not east_asian(cp)}
    hw = {cp: g for cp, g in hw.items() if not east_asian(cp)}
    blank_prop, blank_mono = blanks(read_constants(root)["space_advance_proportional"])
    prop = {**{cp: g for cp, g in blank_prop.items() if not east_asian(cp) and cp not in (0x3164,)}, **half, **hw, **pr}
    mono = {**{cp: g for cp, g in blank_mono.items() if not east_asian(cp) and cp not in (0x3164,)}, **half, **hw}
    for cp, g in pr.items():
        if cp not in mono:
            mono[cp], _ = to_mono(g)
    return prop, mono


def face_name(size, region, mono):
    """(file stem, family name), e.g. ("TongPixelSansMono14Large-SC", "Tong Pixel Sans Mono 14 Large SC")."""
    kind = "Mono" if mono else ""
    return (f"TongPixelSans{kind}14{size}-{region}",
            " ".join(["Tong Pixel Sans"] + ([kind] if kind else []) + ["14", size, region]))


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "build"
    out.mkdir(parents=True, exist_ok=True)
    for size in SIZES:
        for region, prop, mono in [*faces(size=size), ("Latin", *latin_faces(size=size))]:
            for is_mono, face in ((False, prop), (True, mono)):
                stem, family = face_name(size, region, is_mono)
                (out / f"{stem}.bdf").write_text(bdf(face, family, is_mono, size))
                print(stem, len(face))


if __name__ == "__main__":
    main()
