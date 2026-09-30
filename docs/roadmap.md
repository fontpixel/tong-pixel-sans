# 待办与未决问题

更新于 2026-09-29。

## 进行中：AI 修字队列

三步，提示词在 `work/airepair/STEP1-PROMPT.md`、`STEP2-PROMPT.md`、`STEP3-PROMPT.md`（不入库），用户在 Codex 中发送（50 个并发）：

1. 汉字母版：phase2a-v2（764 字）、phase2b-v3（2,272 字）、phase3-v3（445 字）、recheck-v1（466 字，按 L049 / L052 / L053 回头修）。
2. 符号：symbols-v2（1,012 字）。
3. 地区派生：derive-v1（约 10,500 字），第一步全部提交后才生成。

跑完之后：`compare.py` 出对比图，用户决定是否导入。导入顺序见 `work/airepair/QUEUE-PROMPT.md`。

## 待决定

- 第二期前半已交的 4,976 字：暂不导入（2026-09-29 决定）。
- 部件间距的几个已通过字：见 [todo-user.md](todo-user.md)。
- GBK、JIS X 0208 第二水準缺的字暂不补（2026-09-29 决定）。补的话 GBK 缺 4,396 字，JIS 第二水準缺的 423 字都在 GBK 里。

## 手机修字

- 手机编辑器：`tools/mobile/`（选字 `select_glyphs.py`、数据 `build_data.py`、页面 `template.html`、导入 `import_edits.py`）。
- 2026-09-29 的 150 字清单 `tools/editor/data/lists/手机修字150.txt` 已全部通过（2026-09-30）。

## 西文

- `reports/link-western.md`：221 个字没能自动关联形态（画法与标准写法不同，或变音符冲突），需要人工逐个看。
- `tools/western/propagate_family.py --group HW` 仍会更新少数字（如 Ự 套用 Ư 的角）。
- 比例版中还有偏窄的希腊、西里尔和特殊字母，可能需要按 Source Sans 3 加宽（候选：Λ Τ Φ φ Ψ ψ ω Д Ж ж М Т Ф ф Ш ш Щ щ Ъ Ы Ю ю Љ љ Њ њ 及二合字母等）。
- 其他同形字母（如西里尔 В 与拉丁 B）是否统一共用形态，待定。

## 韩文

- 拼合后仍有 32 个拼合音节和 11 个 AI 音节的部件相邻（多为三横初声 + ㅛ / ㅠ + 三横终声，13 行放不下）。
- 拼合工具在 `archive/tong-hangul-v1/`，依赖旧包的 AI 结果和思源黑体 KR 轮廓。若要在改了常用音节后重新拼合，需要把它改成从 `glyphs/KR/` 读取。

## 其他

- Powerline 装饰图形 E0C0–E0D4（21 个）尚未做；生成器在 `archive/tong-geometric-v1/generate.py`。
- 韩文字体里的汉字借用繁体字形，尚无韩国汉字字形。
- 只输出 BDF；单文件 OpenType（用 locl 切换地区字形）尚未实现。
- 人工审核进度：通过 1,229，改过未通过 330（其中约 200 个只是随共享形态同步变化）。

## 已完成（2026-09-29–30）

- 必需字表 39 张全部覆盖。扩展 B 区 23 字和 ∼ 取自遍黑体 P1、Noto Sans Math，`build-data/coverage-exceptions.txt` 已清空。
- 补充符号 653 个（与缝合像素对比的第一、二档，清单在 `tools/airepair/data/symbols-2026-09-29.txt`）。
- 同字各地区从母版派生、像素相同的改为别名；编辑器可以拆开别名、把像素相同的同字字形改为别名。
- 香港字形算作繁体（TC），不另设地区。
- 当前地区写法与借用字形不同的，建了自己的底稿：日文 2,248 个（JIS 第二水準）、简体 4,249 个（GBK，如 麵），待派生轮修。
- 手机修字 95 个已导入并自动关联部件。
