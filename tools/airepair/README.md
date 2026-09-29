# AI 修字工具

把一批字交给 AI（gpt-6-astra 等，经 Codex 的子代理）在**当前版本**上继续修，结果先看对比图，用户决定后再导入。流程与经验见 `docs/ai-repair.md`，AI 读的经验是 `docs/lessons/worker-lessons.md`。

```bash
PY=.venv/bin/python     # 需要 tools/requirements.txt 的库和 reference-fonts/

# 1. 准备一轮（写 work/airepair/NAME/，不入 git，不改字形）
$PY tools/airepair/prepare.py NAME --representative            # “接下来建议修”清单
$PY tools/airepair/prepare.py NAME --list 清单.txt --ref-round 前一轮NAME --workers 10

# 2. 在 Codex 里以 work/airepair/NAME/ 为工作目录，发送 work/airepair/NAME/PROMPT.md 里的提示词

# 3. 进度与结果
$PY tools/airepair/workflow.py --round NAME status
$PY tools/airepair/compare.py NAME                # work/airepair/NAME/compare/：对比图、排文、摘要

# 4. 用户决定后导入（状态仍为 ai，前一版本存入 history/ai-originals/）
$PY tools/airepair/import_round.py NAME --dry-run
$PY tools/airepair/import_round.py NAME [--exclude 字…] [--only-ids 文件]
```

- 只取状态为 `ai` 的字：用户改过或通过的字不交给 AI；准备之后又被人改过的字，导入时跳过、不覆盖。
- 每字的输入：该地区思源黑体参考（写法依据）、当前点阵、圆石点阵黑 18 号（`data/tumbled-18.bdf`，像素范本）、同部件的已通过字（经部件关联查到，另加已通过的独体字）、同字其他地区的已通过版本，以及 `--ref-round` 指定的前几轮已修的同部件字（保持全库一致）。
- 同一个字的各地区字形在同一批。每批 ≤ 50 字（`--batch-size`）。
- worker 协议和启动提示词由 `templates/` 生成到每轮目录，写明模型、推理强度、并发数。
- `workflow.py`：领取令牌、每 ≤10 字检查点、渲染复看并登记、每字最多两轮、提交时校验齐全；只写本轮目录。
