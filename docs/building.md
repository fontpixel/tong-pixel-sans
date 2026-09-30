# 构建与检查

```bash
python3 tools/build.py [输出目录]   # 默认 build/，约 10 秒
python3 tools/verify.py            # 源文件检查 + 8 个地区字体的字表覆盖
python3 tools/release.py [版本]      # 构建并在 dist/（不入库）放发布文件：10 个 BDF、全部许可证、README.txt，另打 zip；版本默认为当天日期
python3 tools/preview.py           # 每个字体的样张 build/*-preview.png（需要 Pillow）
python3 tools/preview.py --readme  # 同时更新 docs/images/sample.png
```

`build.py` 和 `verify.py` 只用 Python 标准库。

## 产物

| 文件 | 字体名（FAMILY_NAME） | 本地区缺字时依次借用 |
|---|---|---|
| `TongPixelSansSC-14.bdf` / `TongPixelSansMonoSC-14.bdf` | Tong Pixel Sans SC / Tong Pixel Sans Mono SC | SC → TC → JP → KR |
| `TongPixelSansTC-14.bdf` / `TongPixelSansMonoTC-14.bdf` | … TC | TC → JP → SC → KR |
| `TongPixelSansJP-14.bdf` / `TongPixelSansMonoJP-14.bdf` | … JP | JP → TC → SC → KR |
| `TongPixelSansKR-14.bdf` / `TongPixelSansMonoKR-14.bdf` | … KR | KR → TC → JP → SC |
| `TongPixelSansLatin-14.bdf` / `TongPixelSansMonoLatin-14.bdf` | Tong Pixel Sans Latin / Tong Pixel Sans Mono Latin | 不含东亚字形：只用比例（PR）、等宽（HW）和半宽几何字形；引号、省略号、破折号总是窄的西文版（简、繁字体里这些跟思源为全角）。2026-09-30 |

- 14 像素：PIXEL_SIZE 14，FONT_ASCENT 11，FONT_DESCENT 3，75 dpi，WEIGHT_NAME Medium，FOUNDRY Tong。
- 汉字 13×13 墨迹放在字格的第 1–13 列、第 0–12 行，底边在基线下 2 像素，接近思源黑体原设计。
- 每个字形只写出墨迹外框（BBX），SWIDTH = 步进 × 1000 ÷ 14。
- 目前每个字体 30,267 个字形。
- 韩文字体里的汉字借用繁体字形（尚无韩国汉字字形）。

## 比例版的组成

1. 地区字形：本地区的 13×13 字形，缺的按上表借用其他地区。U+2014、U+2015 两个全角破折号如果墨迹横贯整行，就把左侧空列也补黑，这样 `——` 能连成一线。
2. 西文比例字形（`PR`）覆盖以下码位：
   - 字母和附加符号（Unicode 类别 L*、M*）；
   - 该地区思源黑体画成半角或比例宽的码位（`build-data/narrow-width.txt`），如日文的 “ ”、韩文的 · ¡ ®；
   - 地区字形没有的码位。
   其余标点符号（“” … — · × 等在简繁中的全角写法）保留地区全角字形。
3. 半角字形（`HW`）：半角片假名等 U+FF61–FF9F 一律用半角；其他 HW 只补比例版缺的码位。
4. 几何字符：制表符、方块元素（U+25A0 以前）用全宽，盲文和 Powerline 用半宽，只补缺的码位。
5. 空白字符由脚本生成：空格、NBSP、U+2008 用比例空格宽度（`build-data/constants.txt`，当前 3 像素）；全角空格 14；U+2000–200A 等按各自规定宽度；零宽字符（U+200B–200F、2028–202E、2060–2064、FEFF、061C）步进 0。
6. 软连字符 U+00AD 显示为连字符。

## 等宽版的组成

终端用：全角 14、半角 7 像素两种宽度。

1. 地区字形同上。
2. 凡有半角形（`HW`）的码位一律用半角，包括全部西文、半角假名；几何字符全部用半宽版。这与终端“歧义宽度按窄”的默认一致。
3. 泰文、阿拉伯文只有比例形：墨迹不超过 7 列的居中放进 7 列，否则放进 14 列；步进为 0 的组合符号保持 0。
4. 空白字符：空格类都是 7 或 14。

## `verify.py` 检查什么

- 每段字形都能解析；ID 不重复；每页按码位排序、码位在正确的页里；状态是已知值。
- 字格大小：地区字形 13×13，HW 7×14，PR 14 行，几何 14×14 / 7×14。
- 别名都指向有自己点阵的字形。
- 部件关联：形态存在，部件与形态一致（希腊、西里尔字母可以共用同形拉丁字母的形态），可移动形态位置在字格内，形态的每个黑点在字里都是黑的。
- 固定形态都是 13×13、不空。
- 8 个字体对 `build-data/coverage-required.txt` 里 28 张字表全部 100% 覆盖（控制字符、代理、私用区和未分配码位不计）。

检查通过只说明数据完整，不说明字形好看。

## 注意

- 转成 PCF（`bdftopcf`）时，码位大于 U+FFFF 的扩展 B 区汉字会被丢掉（PCF 只支持 16 位编码），BDF 本身包含它们。
- 阿拉伯文：BDF 不做字形连接和从右到左排版；字体包含表现形 U+FE70–FEFC，需要应用自行选形。
- 同一码位的地区差异无法放进同一个 BDF（没有 locl），所以每个地区一个文件。
