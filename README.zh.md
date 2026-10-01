# 通格像素黑体 · Tong Pixel Sans

[English](README.md) · **中文**

一套 14 像素的泛中日韩点阵字体：简体中文、繁体中文、日文、韩文各一版，每版有比例和等宽两种。

![样张：简体、繁体、日文、韩文各一段](docs/images/sample.png)

## 特点

- **地区字形**：同一个字在简、繁、日、韩里写法不同时分别绘制（如 骨、直、说），各版本按本地区习惯取字形，标点位置也跟随地区习惯。
- **覆盖面广**：每个字体约 3 万字，完整覆盖 GB/T 2312、《通用规范汉字表》、Big5、台湾常用与次常用国字、JIS X 0208 第一水準、全部现代韩文音节，以及注音、假名、拉丁（含越南文）、希腊、西里尔、泰文、阿拉伯文、制表符、方块元素和盲文。
- **清晰的小字号**：汉字墨迹 13×13 像素，笔画一像素宽；西文比例字字距一像素，降部完整。
- **终端友好**：等宽版为全角 14 / 半角 7 像素双宽，制表符和方块元素可无缝拼接。

## 字体文件

| 文件 | 用途 |
|---|---|
| `TongPixelSansSC-14.bdf` `TongPixelSansTC-14.bdf` `TongPixelSansJP-14.bdf` `TongPixelSansKR-14.bdf` | 比例版（排版、界面） |
| `TongPixelSansMonoSC-14.bdf` … `TongPixelSansMonoKR-14.bdf` | 等宽版（终端、代码） |
| `TongPixelSansLatin-14.bdf` `TongPixelSansMonoLatin-14.bdf` | 只含西文等非东亚文字（引号、省略号、破折号总是窄的西文版） |

字体名分别为 “Tong Pixel Sans SC” 与 “Tong Pixel Sans Mono SC” 等。目前提供 BDF 格式。

## 从源文件生成

只需要 Python 3，不需要安装其他东西：

```bash
python3 tools/build.py      # 生成 build/ 下 8 个 BDF
python3 tools/verify.py     # 检查源文件和字表覆盖
```

## 现状

**这是草稿版本。** 字形先由程序从思源黑体等字体点阵化，再由 AI 逐字修整，目前约 700 个字经人工审核通过，其余仍待审核。欢迎试用和反馈。

## 参与修字

每个字都是 `glyphs/` 下的纯文本点阵，可以直接编辑，也可以用自带的网页编辑器（`python3 tools/editor/server.py`）。详见 [文档](docs/README.md)。

## 许可

[SIL Open Font License 1.1](OFL.txt)。点阵参照 Source Han Sans（思源黑体）、Source Sans 3、Source Code Pro、Noto Sans、Noto Sans Thai、Noto Sans Arabic、Hebrew、Georgian、Armenian、Lao、Math、Symbols、Symbols 2 绘制，思源黑体没有的汉字参照[遍黑体（Plangothic）](https://github.com/Fitzgerald-Porthmouth-Koenigsegg/Plangothic_Project) P1，部分汉字点阵借鉴了 TsFreddie 的[圆石点阵黑（TUMBLED）](https://github.com/TsFreddie/TUMBLED)；这些字体均以 OFL 发布，许可原文见 [licenses/](licenses/)。
