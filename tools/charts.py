"""Character charts of the non-Han categories, from the built glyph data (as the BDFs render them).

    python3 tools/charts.py [output-dir] [--region SC|TC|JP|KR|Latin] [--root REPO] [--all]      (default: build/charts/; needs Pillow)

For each category of tools/editor/make_symbol_lists.py (by default: punctuation, digits, Latin, IPA,
and the common symbol categories 18–26) writes chart-NN-<name>.png: 16 code points a row, each cell
the monospace glyph and the proportional glyph at 3×, on the baseline, the cell tinted by review state
(green approved, yellow draft, white AI). Also specimen.png: sample lines at 1:1 and 3×.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(HERE), str(HERE / "editor")]
from build import ASCENT, crop, faces  # noqa: E402
from make_symbol_lists import CATEGORIES  # noqa: E402

DEFAULT = ("02", "03", "04", "05", "18", "19", "20", "21", "22", "23", "24", "25", "26")
TINT = {"approved": (214, 240, 214), "draft": (250, 240, 200)}
SPECIMEN = ["The quick brown fox jumps over the lazy dog. 0123456789",
            "Sphinx of black quartz, judge my vow! (1+2)×3 ≠ 4 ≤ 5 ≥ ±6 ÷ 7 ≈ 8 ∞",
            "Façade naïve café Ærø Łódź Ștefan Đà Nẵng Ǆ œ ß ẞ ĳ",
            "“Quotes” ‘single’ «guillemets» — dash – en … ‰ † ‡ • § ¶ © ® ™",
            "$ ¢ £ ¥ € ₹ ₽ ₺ ₩ ₪ ₫ ₿ ¹²³ ⁴⁵ ₀₁₂ ½ ⅓ ¾ ⅛ Ⅰ Ⅱ Ⅻ ⅰ ⅱ",
            "← ↑ → ↓ ↔ ⇐ ⇒ ⇔ ⟵ ⟶ ↩ ↪ ↺ ↻ ⌘ ⌥ ⌃ ⇧ ⌫ ⏎ ⎋ ␣",
            "∀x ∈ ℝ: ∃y ∉ ∅, ∑ ∏ √ ∫ ∂ ∇ ⊂ ⊃ ⊆ ⊕ ⊗ ⊥ ∧ ∨ ¬ ∴ ∵",
            "① ② ③ ⑳ Ⓐ Ⓑ ❶ ❷ ★ ☆ ○ ● ◎ □ ■ △ ▲ ◇ ◆ ♠ ♥ ♦ ♣ ☀ ☁ ☂ ✔ ✗",
            "IPA: /ˈfəʊnətɪk/ [ʃ ʒ θ ð ŋ ɑ ɔ ɛ ɪ ʊ ʌ æ ʔ ʰ ː]"]


def draw(d, g, x, base, sc, fill=(0, 0, 0)):
    g = crop(g)
    ox, oy = x + g["x"], base - g["y"] - len(g["rows"])
    for yy, r in enumerate(g["rows"]):
        for xx, v in enumerate(r):
            if v == "#":
                d.rectangle(((ox + xx) * sc, (oy + yy) * sc, (ox + xx + 1) * sc - 1, (oy + yy + 1) * sc - 1), fill=fill)


def chart(name, cps, prop, mono, path):
    from PIL import Image, ImageDraw, ImageFont
    fnt = ImageFont.truetype(str(ROOT / "reference-fonts/SourceHanSansSC-VF.otf"), 12)
    big = ImageFont.truetype(str(ROOT / "reference-fonts/SourceHanSansSC-VF.otf"), 20)
    sc, cw, ch = 3, 2 * 16 * 3 + 10, 16 * 3 + 22
    cols = 16
    rows = (len(cps) + cols - 1) // cols
    im = Image.new("RGB", (cols * cw + 70, rows * ch + 44), "white")
    d = ImageDraw.Draw(im)
    d.text((10, 8), f"{name} · {len(cps)} 个 · 每格左为等宽、右为比例（3 倍） · 绿=已通过 黄=底稿 白=AI", font=big, fill=(0, 0, 0))
    for i, cp in enumerate(cps):
        X, Y = 64 + (i % cols) * cw, 40 + (i // cols) * ch
        if i % cols == 0:
            d.text((6, Y + 18), f"{cp:04X}", font=fnt, fill=(120, 120, 120))
        g = prop.get(cp) or mono.get(cp)
        state = (g or {}).get("state", "")
        d.rectangle((X, Y, X + cw - 4, Y + ch - 4), fill=TINT.get(state, (255, 255, 255)), outline=(220, 220, 220))
        d.line((X, Y + (2 + ASCENT) * sc, X + cw - 4, Y + (2 + ASCENT) * sc), fill=(235, 190, 190))
        for k, face in enumerate((mono, prop)):
            if cp in face:
                sub = Image.new("RGB", (16 * sc, 16 * sc), TINT.get(state, (255, 255, 255)))
                draw(ImageDraw.Draw(sub), face[cp], 1, 2 + ASCENT, sc)
                im.paste(sub, (X + 2 + k * (16 * sc + 4), Y + 2))
        d.text((X + 2, Y + 16 * sc + 4), f"{cp:04X} {chr(cp) if chr(cp).isprintable() else ''}", font=fnt, fill=(90, 90, 90))
    im.save(path)


def specimen(prop, path):
    from PIL import Image, ImageDraw
    parts = []
    for sc in (1, 3):
        width = max(sum(prop[ord(c)]["adv"] if ord(c) in prop else 14 for c in line) for line in SPECIMEN)
        im = Image.new("L", ((width + 8) * sc, (len(SPECIMEN) * 16 + 8) * sc), 255)
        d = ImageDraw.Draw(im)
        for li, line in enumerate(SPECIMEN):
            x = 4
            for c in line:
                g = prop.get(ord(c))
                if g is None:
                    d.rectangle(((x + 2) * sc, (4 + li * 16 + 2) * sc, (x + 11) * sc, (4 + li * 16 + 11) * sc), outline=160)
                    x += 14
                    continue
                draw(d, g, x, 4 + li * 16 + ASCENT, sc, fill=0)
                x += g["adv"]
        parts.append(im)
    sheet = Image.new("L", (max(p.width for p in parts), sum(p.height for p in parts) + 10), 255)
    y = 0
    for p in parts:
        sheet.paste(p, (0, y))
        y += p.height + 10
    sheet.save(path)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    region = sys.argv[sys.argv.index("--region") + 1] if "--region" in sys.argv else "SC"
    root = Path(sys.argv[sys.argv.index("--root") + 1]) if "--root" in sys.argv else ROOT
    args = [x for x in args if x not in (region, str(root))]
    out = Path(args[0]) if args else ROOT / "build/charts"
    out.mkdir(parents=True, exist_ok=True)
    if region == "Latin":
        from build import latin_faces
        prop, mono = latin_faces(root)
    else:
        prop, mono = next((p, m) for r, p, m in faces(root) if r == region)
    for name, ranges in CATEGORIES:
        if "--all" not in sys.argv and name[:2] not in DEFAULT:
            continue
        cps = sorted({cp for a, b in ranges for cp in range(a, b + 1) if cp in prop or cp in mono})
        if cps:
            chart(name, cps, prop, mono, out / f"chart-{name.replace(' ', '-')}.png")
            print(name, len(cps))
    specimen(prop, out / "specimen.png")
    print("written to", out)


if __name__ == "__main__":
    main()
