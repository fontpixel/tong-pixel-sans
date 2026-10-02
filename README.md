# Tong Pixel Sans · 通格像素黑体

**English** · [中文](README.zh.md)

A 14-pixel pan-CJK bitmap font with separate versions for Simplified Chinese, Traditional Chinese, Japanese and Korean, each available as a proportional and a monospace font, in two sizes of western text.

![Sample text in the Simplified Chinese, Traditional Chinese, Japanese and Korean versions](docs/images/sample.png)

## Features

- **Regional glyphs**: characters written differently in China, Taiwan, Japan and Korea (such as 骨, 直, 说) are drawn separately for each version, and punctuation sits where each region expects it.
- **Wide coverage**: about 39,000 characters per font, with complete coverage of GB/T 2312, GBK, the Table of General Standard Chinese Characters (通用规范汉字表), Big5, Taiwan's common and less-common standard characters, JIS X 0208 levels 1–2 and JIS X 0213 levels 3–4, KS X 1001, and all modern Hangul syllables. Also covers Bopomofo, kana, Latin (including Vietnamese), Greek, Cyrillic, Thai, Arabic, box drawing, block elements and Braille.
- **Clear at small sizes**: CJK characters use 13×13 pixels of ink with one-pixel strokes. Proportional Latin has one-pixel spacing and full descenders.
- **Terminal-friendly**: the monospace fonts use a dual width of 14 px (full width) and 7 px (half width), and box-drawing and block characters join seamlessly.

## Two sizes

Both sizes share the same 13×13 East Asian glyphs; they differ in the western and other non-CJK scripts:

- **Tong Pixel Sans 14 Large** (the default): capitals 10 px, x-height 7, accents never squeezed; 18-px line (ascent 14, descent 4).
- **Tong Pixel Sans 14 Small**: compact, capitals 9 px, x-height 6; 14-px line (ascent 11, descent 3).

## Font files

`<Size>` is `Large` or `Small`:

| Files | Use |
|---|---|
| `TongPixelSans14<Size>-SC.bdf` `-TC` `-JP` `-KR` | Proportional (text, user interfaces) |
| `TongPixelSansMono14<Size>-SC.bdf` … `-KR` | Monospace (terminals, code) |
| `TongPixelSans14<Size>-Latin.bdf` `TongPixelSansMono14<Size>-Latin.bdf` | Western scripts only, no East Asian glyphs (quotation marks, ellipsis and dashes always narrow) |

The family names are “Tong Pixel Sans 14 Large SC”, “Tong Pixel Sans Mono 14 Small JP” and so on. `tools/export.py` also makes PCF and vector (TTF, OTF, WOFF2) versions.

## Building from source

Only Python 3 is needed; nothing else has to be installed:

```bash
python3 tools/build.py      # writes the 20 BDF files to build/
python3 tools/verify.py     # checks the sources and character coverage
```

## Status

**This is a draft.** The glyphs were first rasterised from Source Han Sans and other fonts, then retouched character by character by AI. About 1,300 glyphs have been reviewed by hand so far; the rest still await review. Feedback is welcome.

## Contributing

Every glyph is a plain-text bitmap under `glyphs/`. You can edit it directly or use the built-in web editor (`python3 tools/editor/server.py`). The documentation (in Chinese) is in [docs/](docs/README.md).

## License

[SIL Open Font License 1.1](OFL.txt). The bitmaps are drawn after Source Han Sans, Source Sans 3, Source Code Pro, Noto Sans, Noto Sans Thai, Noto Sans Arabic, Hebrew, Georgian, Armenian, Lao, Math, Symbols and Symbols 2, with the Han characters Source Han Sans lacks drawn after [Plangothic](https://github.com/Fitzgerald-Porthmouth-Koenigsegg/Plangothic_Project) P1, and part of the Han bitmaps draw on [TUMBLED](https://github.com/TsFreddie/TUMBLED) by TsFreddie; all are released under the OFL, and their license texts are in [licenses/](licenses/).
