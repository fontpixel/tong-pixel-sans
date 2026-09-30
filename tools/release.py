"""Build the release: the BDF fonts, their licences and a short readme in dist/, and a zip of them.

    python3 tools/release.py [version]      (default version: today's date, e.g. 2026.09.30)

Runs the build, then writes dist/ (not in git) flat, as tools of other projects read it (the
fontpixel catalogue's `make import-tong` takes the eight regional BDFs and OFL.txt, OFL-SourceSans3.md,
OFL-Noto.txt from here): the ten BDFs, OFL.txt (this font's licence), every upstream licence from
licenses/, README.txt; and dist/tong-pixel-sans-VERSION.zip with the same files in a folder.
"""
from __future__ import annotations

import datetime
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FACES = [f"TongPixelSans{k}{r}-14.bdf" for r in ("SC", "TC", "JP", "KR", "Latin") for k in ("", "Mono")]

README = """Tong Pixel Sans (通格像素黑体) {version}

A 14-pixel pan-CJK bitmap sans. Unfinished: the glyphs were rasterised from Source Han Sans and
other OFL fonts and retouched by AI; {approved} glyphs have been reviewed by hand so far.

Files (BDF, 14 px, ascent 11, descent 3):
  TongPixelSansSC-14.bdf / TC / JP / KR       proportional, with that region's glyph forms
  TongPixelSansMonoSC-14.bdf / TC / JP / KR   monospace (half and full width)
  TongPixelSansLatin-14.bdf, TongPixelSansMonoLatin-14.bdf
                                              western scripts only, no East Asian glyphs
                                              (quotation marks and ellipsis always narrow)

Licence: SIL Open Font License 1.1 (OFL.txt). The bitmaps are drawn after Source Han Sans,
Source Sans 3, the Noto fonts and Plangothic, and part of the Han bitmaps draw on TUMBLED by
TsFreddie; their licences are the other OFL-* files. Reserved font names of those fonts
("Source", "Plangothic", "遍黑") are not used in this font's name.

Built from commit {commit} on {date}.
"""


def main():
    version = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().strftime("%Y.%m.%d")
    build = ROOT / "build"
    subprocess.run([sys.executable, str(ROOT / "tools/build.py"), str(build)], check=True, stdout=subprocess.DEVNULL)
    dist = ROOT / "dist"
    if dist.exists():
        shutil.rmtree(dist)
    dist.mkdir()
    files = []
    for name in FACES:
        shutil.copy2(build / name, dist / name)
        files.append(name)
    shutil.copy2(ROOT / "OFL.txt", dist / "OFL.txt")
    files.append("OFL.txt")
    for lic in sorted((ROOT / "licenses").iterdir()):
        shutil.copy2(lic, dist / lic.name)
        files.append(lic.name)
    commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    approved = sum(1 for p in (ROOT / "glyphs").glob("*/*.txt") for block in p.read_text(encoding="utf-8").split("\n\n")
                   if block.split("\n")[1:2] == ["approved"])
    (dist / "README.txt").write_text(README.format(version=version, approved=f"{approved:,}", commit=commit,
                                                   date=datetime.date.today().isoformat()), encoding="utf-8")
    files.append("README.txt")
    folder = f"tong-pixel-sans-{version}"
    with zipfile.ZipFile(dist / f"{folder}.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for name in files:
            z.write(dist / name, f"{folder}/{name}")
    print(f"dist/: {len(files)} files; dist/{folder}.zip")


if __name__ == "__main__":
    main()
