# 参考字体

字形由下列 OFL 字体点阵化后修整而来。构建字体**不需要**它们；只有编辑器的参考轮廓和相位底稿、以后生成新字的底稿，以及重新量取 `build-data/` 的数据时才需要。

字体放在仓库根目录的 `reference-fonts/`（已在 `.gitignore` 中，不入库，约 120 MB），文件名必须与下表一致。放好后校验：

```bash
cd reference-fonts && sha256sum -c ../build-data/reference-fonts.sha256
```

| 文件名 | 字体与版本 | 用途 | 来源 |
|---|---|---|---|
| `SourceHanSansSC-VF.otf` | Source Han Sans SC VF 2.004 | 简体字形 | Adobe [source-han-sans](https://github.com/adobe-fonts/source-han-sans) 2.004R，`Variable/OTF/SourceHanSansSC-VF.otf`（最初取自本机旧实验，校验值与发布版一致与否未另行核对） |
| `SourceHanSansTC-VF.otf` | Source Han Sans TC VF 2.004 | 繁体字形 | [2.004R，提交 a8b073b 的 `Variable/OTF/SourceHanSansTC-VF.otf`](https://raw.githubusercontent.com/adobe-fonts/source-han-sans/a8b073bbf80f7226af03abeeb31e27017d5e3f67/Variable/OTF/SourceHanSansTC-VF.otf) |
| `SourceHanSansJP-VF.otf` | Source Han Sans VF 2.004（日文默认） | 日文字形、半角假名、部分西文 | [同一提交的 `Variable/OTF/SourceHanSans-VF.otf`](https://raw.githubusercontent.com/adobe-fonts/source-han-sans/a8b073bbf80f7226af03abeeb31e27017d5e3f67/Variable/OTF/SourceHanSans-VF.otf)，改名 |
| `SourceHanSansKR-VF.otf` | Source Han Sans K VF 2.004（韩文默认） | 韩文字形 | [同一提交的 `Variable/OTF/SourceHanSansK-VF.otf`](https://raw.githubusercontent.com/adobe-fonts/source-han-sans/a8b073bbf80f7226af03abeeb31e27017d5e3f67/Variable/OTF/SourceHanSansK-VF.otf)，改名 |
| `SourceSans3-VF.otf` | Source Sans 3 VF 3.052 | 西文 | Adobe [source-sans](https://github.com/adobe-fonts/source-sans) 3.052 可变字体（直立），改名 |
| `SourceCodePro-VF.otf` | Source Code Pro VF 1.026（Upright） | 等宽版西文（2026-10-01 起） | Adobe [source-code-pro](https://github.com/adobe-fonts/source-code-pro) 发布 2.042R-u/1.062R-i/1.026R-vf 的 `VF-source-code-VF-1.026R.zip` 里的 `SourceCodeVF-Upright.otf`，改名 |
| `NotoSans-VF.ttf` | Noto Sans 2.015 | Source Sans 3 没有的西文 | [notofonts](https://github.com/notofonts/latin-greek-cyrillic) / Google Fonts 可变字体，改名 |
| `NotoSansThai-VF.ttf` | Noto Sans Thai 2.001 | 泰文 | [notofonts/thai](https://github.com/notofonts/thai) 可变字体，改名 |
| `NotoSansArabic-VF.ttf` | Noto Sans Arabic 2.013 | 阿拉伯文 | [notofonts/arabic](https://github.com/notofonts/arabic) 可变字体，改名 |
| `NotoSansMath-Regular.ttf` | Noto Sans Math 2.001（静态，只有常规体） | 以上字体都没有的数学符号（如 ∼ U+223C） | [notofonts/math](https://github.com/notofonts/math)；本机取自 Ubuntu 的 fonts-noto-core |
| `NotoSansSymbols-Regular.ttf` | Noto Sans Symbols 2.001（静态） | 以上字体都没有的符号（⌘ 类技术符号、罗马数字 Ⅼ–ⅿ、⚙ 等） | [notofonts/symbols](https://github.com/notofonts/symbols)；本机取自 Ubuntu 的 fonts-noto-core |
| `NotoSansSymbols2-Regular.ttf` | Noto Sans Symbols 2 2.003（静态） | 同上（几何图形、播放键 ⏩ ⏸、☀ ☔ 等） | 同上 |
| `NotoSansHebrew-Regular.ttf`、`NotoSansGeorgian-Regular.ttf`、`NotoSansArmenian-Regular.ttf`、`NotoSansLao-Regular.ttf` | Noto Sans Hebrew / Georgian / Armenian / Lao（静态常规体） | 希伯来、格鲁吉亚、亚美尼亚、老挝文（2026-09-30） | [notofonts](https://github.com/notofonts)；本机取自 Ubuntu 的 fonts-noto-core |
| `PlangothicP1-Regular.ttf` | 遍黑体 Plangothic P1 6.400（项目版本 V2.9.5795，静态，只有常规体） | 思源黑体各地区都没有的汉字（扩展 B 区及以后） | [Plangothic_Project](https://github.com/Fitzgerald-Porthmouth-Koenigsegg/Plangothic_Project/releases/tag/V2.9.5795) 发布附件 `PlangothicP1-Regular.ttf`（2026-09-29 取得） |

各字体的精确 SHA-256 见 `build-data/reference-fonts.sha256`。表中只有思源黑体 TC / JP / KR 的下载地址有原始记录；其余字体以版本号和校验值为准，重新下载后请核对校验值。

许可原文：`licenses/OFL-SourceHanSans.txt`、`licenses/OFL-SourceSans3.md`、`licenses/OFL-SourceCodePro.md`、`licenses/OFL-Noto.txt`、`licenses/OFL-Plangothic.txt`。遍黑体的保留字体名是 “Plangothic” 和 “遍黑”，本字体的名字不能含有它们（思源的保留名 “Source” 同理）。

## 用到的参数

- **汉字、全角字形的底稿**：WorkBench（FreeType 单色渲染，`FT_LOAD_TARGET_MONO`，FreeType 2.13.2，关闭 stem darkening），wght 320，字面 14×13（“囗”全包围字与独体“口”13×13）。见 `archive/tong/docs/DESIGN.md`。思源黑体没有的汉字改用遍黑体 P1（只有常规体，相当于 wght 400，笔画比 w320 粗），参考图、叠加轮廓也用它。
- **全角符号和西文底稿**：同样的渲染，另加 1/16 像素横向相位搜索：每字试 16 种亚像素平移，选对称、少黑块、不断笔的一种（`archive/tong-ext-v5/scripts/phase.py`、`varraster.py`）。
- **参考图 / 叠加轮廓**：汉字用该地区思源黑体 wght 400，em = 14 像素，右移 0.5 像素、基线在字格顶下 11.8 像素，使轮廓以 13×13 墨迹框（第 1–13 列、第 0–12 行）为中心（按已通过汉字实测：墨迹框比轮廓偏右 0.47、偏上 0.18 像素）；西文用底稿所用字体（wght 320）和底稿字号，水平对齐底稿的最左墨迹列（`tools/editor/data/reference-western.txt`）。
- `build-data/narrow-width.txt`：各地区思源黑体中步进 ≤ 700/1000 的码位。
- `build-data/constants.txt`：比例版空格 = max(3, round(Source Sans 3 空格步进 × 13 / 1000))。
