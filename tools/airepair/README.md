# AI 修字工具

把一批字交给 AI（gpt-6-astra 等，经 Codex 的子代理）在**当前版本**上继续修，结果先看对比图，用户决定后再导入。流程与经验见 `docs/ai-repair.md`，AI 读的经验是 `docs/lessons/worker-lessons.md`。

```bash
PY=.venv/bin/python     # 需要 tools/requirements.txt 的库和 reference-fonts/

# 1. 准备一轮（写 work/airepair/NAME/，不入 git，不改字形）
$PY tools/airepair/prepare.py NAME --representative            # “接下来建议修”清单
$PY tools/airepair/prepare.py NAME --list 清单.txt --ref-round 前一轮NAME --workers 10
$PY tools/airepair/prepare.py NAME --list 清单.txt --masters-only …       # 只修各字的母版
$PY tools/airepair/prepare.py NAME --derive --ref-round 前几轮NAME …        # 地区派生轮

# 2. 在 Codex 里以 work/airepair/NAME/ 为工作目录，发送 work/airepair/NAME/PROMPT.md 里的提示词

# 3. 进度与结果
$PY tools/airepair/workflow.py --round NAME status
$PY tools/airepair/compare.py NAME                # work/airepair/NAME/compare/：对比图、排文、摘要

# 4. 用户决定后导入（状态仍为 ai，前一版本存入 history/ai-originals/）
$PY tools/airepair/import_round.py NAME --dry-run
$PY tools/airepair/import_round.py NAME [--exclude 字…] [--only-ids 文件] [--masters-only] [--alias-identical]
```

- **母版与派生**（`docs/design-rules.md` 第 2 节）：同一个字的地区版本以一个为母版（已通过的，其次改过的，否则按 简 → 繁 → 日 → 韩 的第一个）。修字轮用 `--masters-only` 只修母版；派生轮 `--derive` 取其他地区的 AI 版和底稿，“当前”是母版的逐像素副本（母版未审核时取 `--ref-round` 里最新的结果），AI 只改两地写法不同的笔画。导入时先导母版轮（`--masters-only` 跳过非母版），最后导派生轮（`--alias-identical`：与母版像素相同的改为别名）。
- 复看图和 `common.wide_gaps` 标出左右并排部件之间空 2 列以上的字（L049；按编辑器的 IDS 分割推断）。

- 只取状态为 `ai` 的字：用户改过或通过的字不交给 AI；准备之后又被人改过的字，导入时跳过、不覆盖。
- 每字的输入：该地区思源黑体参考（写法依据）、当前点阵、圆石点阵黑 18 号（`data/tumbled-18.bdf`，像素范本）、同部件的已通过字（经部件关联查到，另加已通过的独体字）、同字其他地区的已通过版本，以及 `--ref-round` 指定的前几轮已修的同部件字（保持全库一致）。
- 同一个字的各地区字形在同一批。每批 ≤ 50 字（`--batch-size`）。
- worker 协议和启动提示词由 `templates/` 生成到每轮目录，写明模型、推理强度、并发数。
- `workflow.py`：领取令牌、每 ≤10 字检查点、渲染复看并登记、每字最多两轮、提交时校验齐全；只写本轮目录。
- `add_glyphs.py`：新增字写成底稿（状态 `draft`，之后可交给 AI 修）。默认补齐必需字表里还没有的字；`--symbols data/symbols-2026-09-29.txt` 补清单里的符号（按思源黑体的有无和宽窄，决定画全角地区版还是等宽 / 比例版，报告写到 `reports/add-symbols.md`）。
