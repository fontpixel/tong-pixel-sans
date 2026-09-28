"""Read the character tables in build-data/coverage/ (one code point, range XXXX..YYYY or literal
characters per line; # starts a comment)."""
import re


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
