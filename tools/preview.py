"""Sample sheets typeset from the built glyph data (same advances and offsets as the BDFs).

    python3 tools/preview.py [output-dir]      (default: build/; needs Pillow)

Writes <face>-preview.png for the 10 faces, and docs/images/sample.png (SC, TC, JP, KR proportional,
first lines) when run with --readme. No shaping: Arabic appears in logical order with isolated forms,
as a plain BDF renders it.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from build import ASCENT, crop, faces  # noqa: E402

SAMPLES = {
    "SC": ["永和九年，岁在癸丑。国语、骨、直、说。", "「标点」（括号）《书名》——省略……", "The quick brown fox jumps over 0123456789!",
           "Łódź Ærøskøbing Ștefan Đà Nẵng ǅ Ǳ", "αβγ ΑΒΓ Ωμέγα абв Жизнь ①②③ ㈠㈡ ℃ ¥ ※ →",
           "สวัสดีครับ ภาษาไทย ๑๒๓", "مرحبا بالعالم ١٢٣", "┌──┬──┐ ▁▂▃▄▅▆▇█ ⣿⠿⡇ ", "한국어 텍스트, 日本語のテキスト。ｱｲｳｴｵ"],
    "TC": ["永和九年，歲在癸丑。國語、骨、直、說。", "「標點」（括號）《書名》——刪節……", "The quick brown fox jumps over 0123456789!",
           "Łódź Ærøskøbing Ștefan Đà Nẵng ǅ Ǳ", "ㄅㄆㄇㄈ αβγ ΑΒΓ абв ①②③ ℃ ※ →",
           "สวัสดีครับ ภาษาไทย ๑๒๓", "مرحبا بالعالم ١٢٣", "┌──┬──┐ ▁▂▃▄▅▆▇█ ⣿⠿⡇ ", "한국어 텍스트, 日本語のテキスト。ｱｲｳｴｵ"],
    "JP": ["いろはにほへと ちりぬるを。骨、直、糸、辻。", "「句読点」（括弧）『二重』……", "The quick brown fox jumps over 0123456789!",
           "Łódź Ærøskøbing Ștefan Đà Nẵng ǅ Ǳ", "カタカナ ァィゥ ｶﾀｶﾅ ﾊﾟﾋﾟ αβγ ①②③ ※ →",
           "สวัสดีครับ ภาษาไทย ๑๒๓", "مرحبا بالعالم ١٢٣", "┌──┬──┐ ▁▂▃▄▅▆▇█ ⣿⠿⡇ ", "한국어 텍스트, 中文文本。"],
    "KR": ["다람쥐 헌 쳇바퀴에 타고파. 한글 ㄱㄴㄷ ㅏㅑ", "「문장 부호」（괄호）……", "The quick brown fox jumps over 0123456789!",
           "Łódź Ærøskøbing Ștefan Đà Nẵng ǅ Ǳ", "㉠㉡㉢ ㈀㈁ ①②③ αβγ абв ※ →",
           "สวัสดีครับ ภาษาไทย ๑๒๓", "مرحبا بالعالم ١٢٣", "┌──┬──┐ ▁▂▃▄▅▆▇█ ⣿⠿⡇ ", "漢字 骨 直, 日本語のテキスト。ｱｲｳｴｵ"],
}


def preview(face, path, lines, scale=3):
    """Typeset sample lines from the exported glyph data (advances and offsets as in the BDF).
    No shaping: Arabic is shown in logical order with isolated forms, as a plain BDF renders it."""
    from PIL import Image, ImageDraw
    width = max(sum(face[ord(c)]["adv"] if ord(c) in face else 14 for c in line) for line in lines)
    im = Image.new("L", ((width + 8) * scale, (len(lines) * 16 + 8) * scale), 255)
    d = ImageDraw.Draw(im)
    for li, line in enumerate(lines):
        x, top = 4, 4 + li * 16
        base = top + ASCENT  # y of the baseline
        for c in line:
            g = face.get(ord(c))
            if g is None:
                d.rectangle(((x + 2) * scale, (top + 2) * scale, (x + 11) * scale, (top + 11) * scale), outline=180); x += 14; continue
            g = crop(g)
            ox, oy = x + g["x"], base - g["y"] - len(g["rows"])
            for yy, r in enumerate(g["rows"]):
                for xx, v in enumerate(r):
                    if v == "#":
                        d.rectangle(((ox + xx) * scale, (oy + yy) * scale, (ox + xx + 1) * scale - 1, (oy + yy + 1) * scale - 1), fill=0)
            x += g["adv"]
    im.save(path)




LATIN = ["The quick brown fox jumps over the lazy dog. 0123456789", "“Quotes” ‘single’ «guillemets» — dash – en … ‰ † § ©",
         "Façade naïve café Ærø Łódź Ștefan Đà Nẵng ǅ œ ß ẞ", "αβγ ΑΒΓ Ωμέγα абв Жизнь ← → ≠ ≤ ≥ ∞ ± × ÷ ℃ € ₹",
         "שלום עולם · Გამარჯობა · Բարեւ · ສະບາຍດີ · สวัสดี", "┌──┬──┐ ▁▂▃▄▅▆▇█ ⣿⠿⡇"]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = Path(args[0]) if args else ROOT / "build"
    out.mkdir(parents=True, exist_ok=True)
    readme = []
    for region, prop, mono in faces():
        for kind, face in (("", prop), ("Mono", mono)):
            preview(face, out / f"TongPixelSans{kind}{region}-preview.png", SAMPLES[region])
        readme.append((region, prop))
    from build import latin_faces
    prop, mono = latin_faces()
    for kind, face in (("", prop), ("Mono", mono)):
        preview(face, out / f"TongPixelSans{kind}Latin-preview.png", LATIN)
    if "--readme" in sys.argv:
        from PIL import Image
        parts = []
        for region, face in readme:
            p = out / f"readme-{region}.png"
            preview(face, p, SAMPLES[region][:5], scale=2)
            parts.append(Image.open(p))
        w = max(im.width for im in parts)
        sheet = Image.new("L", (w, sum(im.height for im in parts)), 255)
        y = 0
        for im in parts:
            sheet.paste(im, (0, y)); y += im.height
        (ROOT / "docs/images").mkdir(parents=True, exist_ok=True)
        sheet.save(ROOT / "docs/images/sample.png")
    print("previews in", out)


if __name__ == "__main__":
    main()
