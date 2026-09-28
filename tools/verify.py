"""Check the sources and the coverage of the fonts built from them.

    python3 tools/verify.py

Sources (glyphs/, forms/forms.txt):
- every block parses; ids are unique, pages sorted, each block on the page of its code point;
- states are known; cells have the right size (regional 13×13; HW/PR/geometric 14 rows, one width per
  glyph; HW 7 columns; GEOMETRIC-FULL 14, GEOMETRIC-HALF 7);
- every alias points at a glyph with its own pixels;
- every link names a form in forms.txt of the same component (or, for a Greek/Cyrillic letter, of the
  Latin letter it is drawn exactly like), a movable form's position keeps it in
  the cell, and the form's black pixels are all black in the glyph (linking never adds a pixel);
- every fixed form is 13×13 with at least one black pixel.
Coverage: the 8 faces tools/build.py makes cover every table in build-data/coverage-required.txt.
Exits with status 1 and a list of problems if anything fails. Needs only the Python standard library.
"""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "editor"))
import build  # noqa: E402
from western import HOMOGLYPHS  # noqa: E402  (Greek/Cyrillic letters that share a Latin letter's form)

STATES = {"approved", "edited", "derived", "ai", "hangul-ai", "hangul-composed", "generated"}
GROUPS = ["SC", "TC", "JP", "KR", "HW", "PR", "GEOMETRIC-FULL", "GEOMETRIC-HALF"]


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


def read_forms():
    out = {}
    for b in (ROOT / "forms/forms.txt").read_text(encoding="utf-8").split("\n\n"):
        lines = [l for l in b.split("\n") if l]
        if lines:
            _, sid, kind, symbol, locale, name = lines[0].split(" ", 5)
            out[sid] = {"kind": kind, "symbol": symbol, "rows": [l for l in lines[1:] if set(l) <= {".", "#"}]}
    return out


def check_sources(problems):
    forms = read_forms()
    for sid, f in forms.items():
        if f["kind"] not in ("fixed", "movable"):
            problems.append(f"form {sid}: kind {f['kind']}")
        if not any("#" in r for r in f["rows"]) or len({len(r) for r in f["rows"]}) != 1:
            problems.append(f"form {sid}: empty or ragged")
        if f["kind"] == "fixed" and (len(f["rows"]) != 13 or len(f["rows"][0]) != 13):
            problems.append(f"form {sid}: fixed form not 13×13")
    groups = {g: build.read_group(g) for g in GROUPS}
    counts = {}
    for g in GROUPS:
        for p in sorted((ROOT / "glyphs" / g).glob("*.txt")):
            blocks = [b for b in p.read_text(encoding="utf-8").split("\n\n") if b.strip()]
            cps = [int(b.split(" ", 1)[0][2:], 16) for b in blocks]
            if cps != sorted(set(cps)):
                problems.append(f"{p.relative_to(ROOT)}: blocks not sorted or duplicated")
            if any(f"{cp >> 8:02X}xx.txt" != p.name for cp in cps):
                problems.append(f"{p.relative_to(ROOT)}: code point on the wrong page")
            for b in blocks:
                lines = b.split("\n")
                bad = [l for l in lines[2:] if not (set(l) <= {".", "#"} or l.startswith(("@ ", "# AI: ", "# 人工: ")))]
                if bad and "=" not in lines[0].split(" ")[2:3]:
                    problems.append(f"{lines[0]}: unknown line {bad[0]!r}")
        for cp, e in groups[g].items():
            gid = f"U+{cp:04X}.{g}"
            if "alias" in e:
                tcp, tg = int(e["alias"][2:].split(".")[0], 16), e["alias"].split(".")[1]
                if "rows" not in groups.get(tg, {}).get(tcp, {}):
                    problems.append(f"{gid}: alias to {e['alias']}, which has no pixels of its own")
                continue
            counts[e["state"]] = counts.get(e["state"], 0) + 1
            if e["state"] not in STATES:
                problems.append(f"{gid}: unknown state {e['state']}")
            rows = e["rows"]
            w, h = (len(rows[0]) if rows else 0), len(rows)
            want = {"HW": (7, 14), "GEOMETRIC-FULL": (14, 14), "GEOMETRIC-HALF": (7, 14)}.get(g, (13, 13) if g in build.REGIONS else None)
            if len({len(r) for r in rows}) != 1 or (want and (w, h) != want) or (g == "PR" and h != 14):
                problems.append(f"{gid}: cell {w}×{h}")
                continue
            for l in links_of(g, cp):
                f = forms.get(l["shape_id"])
                if f is None:
                    problems.append(f"{gid}: link to missing form {l['shape_id']}")
                    continue
                if f["symbol"] != l["symbol"] and HOMOGLYPHS.get(l["symbol"]) != f["symbol"]:
                    problems.append(f"{gid}: link {l['slot']} is {l['symbol']} but form {l['shape_id']} is {f['symbol']}")
                x0, y0 = l.get("x", 0), l.get("y", 0)
                if (f["kind"] == "movable") != ("x" in l):
                    problems.append(f"{gid}: link {l['slot']} position does not match form kind")
                for y, r in enumerate(f["rows"]):
                    for x, v in enumerate(r):
                        if v == "#" and not (0 <= y + y0 < h and 0 <= x + x0 < w and rows[y + y0][x + x0] == "#"):
                            problems.append(f"{gid}: form {l['shape_id']} ({l['symbol']}) has a black pixel the glyph lacks")
                            break
                    else:
                        continue
                    break
    return counts


_LINKS = {}


def links_of(group, cp):
    if group not in _LINKS:
        out = {}
        for p in (ROOT / "glyphs" / group).glob("*.txt"):
            for b in p.read_text(encoding="utf-8").split("\n\n"):
                lines = [l for l in b.split("\n") if l.startswith(("U+", "@ "))]
                if not lines:
                    continue
                c = int(lines[0].split(" ", 1)[0][2:], 16)
                for l in lines[1:]:
                    parts = l.split(" ")
                    link = {"slot": parts[1], "symbol": parts[2], "shape_id": parts[3]}
                    if len(parts) > 4:
                        x, y = parts[4].split(",")
                        link.update(x=int(x), y=int(y))
                    out.setdefault(c, []).append(link)
        _LINKS[group] = out
    return _LINKS[group].get(cp, [])


def check_coverage(problems):
    tables = []
    for line in (ROOT / "build-data/coverage-required.txt").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            label, path, *flt = line.split("\t")
            cps = table_codepoints(ROOT / "build-data/coverage" / path)
            if flt == ["non-hanzi"]:
                cps = {c for c in cps if not unicodedata.name(chr(c), "").startswith("CJK UNIFIED")}
            cps = {c for c in cps if unicodedata.category(chr(c)) not in ("Cc", "Cs", "Co", "Cn")}
            tables.append((label, cps))
    summary = {}
    for region, prop, mono in build.faces():
        for kind, face in (("", prop), ("Mono", mono)):
            name = f"TongPixelSans{kind}{region}"
            for label, cps in tables:
                missing = sorted(cps - set(face))
                if missing:
                    problems.append(f"{name}: {label} misses {len(missing)}: " + " ".join(f"U+{c:04X}" for c in missing[:12]))
            summary[name] = len(face)
    return len(tables), summary


def main():
    problems = []
    counts = check_sources(problems)
    n_tables, faces = check_coverage(problems)
    for p in problems[:100]:
        print(p)
    print(f"glyph states: {counts}")
    print(f"faces: {faces}; required tables: {n_tables}")
    print(f"{len(problems)} problem(s)" if problems else "OK")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
