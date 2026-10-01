"""The Large size's geometric characters (GEOMETRIC-FULL-L, GEOMETRIC-HALF-L, 18-row cells), made from the
14-row ones so that they still join in a terminal:

    .venv/bin/python tools/editor/large_geometric.py [--dry-run]

- box drawing (U+2500–257F): four rows repeated where almost no box glyph changes (rows 0, 2, 10, 13), so
  the lines stay one pixel wide and the horizontal ones move to the middle row; the diagonals are redrawn;
- blocks (U+2580–259F): eighths by their fraction of 18 rows, shades repeat their pattern, the rest
  (halves, quadrants, vertical bars) is resampled to the nearest row;
- braille (U+2800–28FF): the same 2×2-pixel dots, re-spaced (rows 2–3, 6–7, 10–11, 14–15);
- Powerline (U+E0A0–E0BF): the full-height triangles and half circles resampled, the icons centred.
State `generated`; existing large glyphs are left alone. Changes no 14-row glyph.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]
import build  # noqa: E402
from store import Store  # noqa: E402

H = 18
BOX_REPEAT = (0, 2, 10, 13)            # rows of the 14-row cell repeated, top to bottom
BRAILLE_ROWS = {1: 2, 2: 3, 4: 6, 5: 7, 7: 10, 8: 11, 10: 14, 11: 15}
EIGHTHS_LOWER = range(0x2581, 0x2588)  # ▁ … ▇: the lower k/8
EIGHTHS_UPPER = {0x2594: 1}            # ▔: the upper 1/8


def repeat_rows(rows, repeat):
    out = []
    for y, r in enumerate(rows):
        out += [r, r] if y in repeat else [r]
    return out


def nearest(rows):
    return [rows[int((y + 0.5) * len(rows) / H)] for y in range(H)]


def diagonal(w, rising):
    """One-pixel diagonal from corner to corner of a w×18 cell."""
    out = []
    for y in range(H):
        x = int((y + 0.5) * w / H)
        x = w - 1 - x if rising else x
        out.append("".join("#" if c == x else "." for c in range(w)))
    return out


def large(cp, rows):
    w = len(rows[0])
    if cp in (0x2571, 0x2572, 0x2573):        # ╱ ╲ ╳
        a, b = diagonal(w, True), diagonal(w, False)
        if cp == 0x2571:
            return a
        if cp == 0x2572:
            return b
        return ["".join("#" if "#" in (p, q) else "." for p, q in zip(ra, rb)) for ra, rb in zip(a, b)]
    if 0x2500 <= cp <= 0x257F:
        return repeat_rows(rows, BOX_REPEAT)
    if cp in EIGHTHS_LOWER or cp in EIGHTHS_UPPER:
        k = cp - 0x2580 if cp in EIGHTHS_LOWER else EIGHTHS_UPPER[cp]
        n = int(H * k / 8 + 0.5)
        full, blank = "#" * w, "." * w
        return ([blank] * (H - n) + [full] * n) if cp in EIGHTHS_LOWER else ([full] * n + [blank] * (H - n))
    if 0x2591 <= cp <= 0x2593:               # shades: repeat the pattern's period
        p = next(p for p in range(1, len(rows)) if all(rows[y] == rows[y + p] for y in range(len(rows) - p)))
        return [rows[y % p] for y in range(H)]
    if 0x2580 <= cp <= 0x259F:
        return nearest(rows)
    if 0x2800 <= cp <= 0x28FF:
        out = ["." * w] * H
        for y, r in enumerate(rows):
            if "#" in r:
                out[BRAILLE_ROWS[y]] = r
        return out
    if 0xE0B0 <= cp <= 0xE0BF:
        return nearest(rows)
    pad = (H - len(rows)) // 2                 # Powerline icons: centred
    return ["." * w] * pad + rows + ["." * w] * (H - len(rows) - pad)


def main():
    s = Store(HERE.parent.parent)
    new = []
    for small, big in (("GEOMETRIC-FULL", "GEOMETRIC-FULL-L"), ("GEOMETRIC-HALF", "GEOMETRIC-HALF-L")):
        for cp, e in sorted(build.read_group(small, s.root).items()):
            if f"U+{cp:04X}.{big}" in s.records or "rows" not in e:
                continue
            rows = large(cp, e["rows"])
            assert len(rows) == H and len({len(r) for r in rows}) == 1, hex(cp)
            new.append({"group": big, "cp": cp, "rows": rows, "state": "generated", "metrics": []})
    print(f"{len(new)} large geometric glyphs")
    if "--dry-run" not in sys.argv:
        s.add_glyphs(new)


if __name__ == "__main__":
    main()
