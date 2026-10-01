# AI 修字 worker 协议（{NAME}）

仅在用户明确启动后执行。模型 {MODEL}，reasoning_effort={EFFORT}。一次独立会话只处理协调者分配的一批（最多 {BATCH_SIZE} 字）。不要再创建子代理，不处理第二批。

你会收到 BATCH、TOKEN、OWNER。以下 `WF` 指 `{PY} {WF} --round {KIT}`。KIT 是本轮目录：{KIT}

## 任务

Tong Pixel Sans 是 14 像素泛中日韩点阵字体。全角符号的墨迹 13×13（放在 14×14 字格中，左列和底行为固定留白，由程序处理，你的 13×13 数组不需要另留白）；等宽符号 7 宽 × 14 高；比例符号宽度可变、14 高。{TASK}

## 依据（按优先顺序）

1. **参考图是写法依据**：全角符号是该地区思源黑体，等宽 / 比例符号是底稿所用的西文字体（inputs.txt 的底稿说明写了是哪一个）。
2. **同族已有字形**（`examples-*.png`，✓ 为用户已通过）：同一族的圆圈、括号、箭头头部、上下标高度等要与它们逐像素一致；同一码位在其他分组已通过的字形（inputs.txt 的“同码位已通过”）也照它。
3. **LESSONS.md**：用户确认的规则（全角标点、西文、几何字符）和符号修字要点、自检清单 S1–S4。

不要为了“显得改过”而改；也不要为了与同族一致而牺牲可读性。

## 步骤

1. `WF context --batch BATCH --token TOKEN`：查看进度。恢复任务时保留已保存的字和已完成的复看，只做未完成的部分。
2. 读 KIT/LESSONS.md 和 `KIT/batches/BATCH/inputs.txt`，并**实际查看** context 列出的全部 input 和 example 图片（detail=original）。文件存在不等于看过。
3. 逐字修，每完成至多 10 字就写一个增量文件（如 `KIT/work/BATCH/delta-001.json`）并运行 `WF checkpoint --batch BATCH --token TOKEN --file 文件路径`。格式严格如下：

   ```json
   {"glyphs": [{"id": "U+5B57.SC", "changes": {"4": "#############"}, "note": "", "tumbled": "未借鉴"}]}
   ```

   - `changes`：键为行号字符串（全角 0–12，等宽 / 比例 0–13），值为该行完整的一行 `.` / `#`，宽度与“当前”相同（比例符号可以改宽度，但这时要把所有行都写出、宽度一致）；**始终相对 inputs.txt 里的“当前”版本**（第二轮也是）；不改就写 `{}`，但必须列出该字。
   - `tumbled`：符号轮一律写 `未借鉴`。
   - `reuse`：逐像素复用的已通过部件，如 `宀←U+5B87.SC`；没有就省略或写 `[]`。
   - `note`：仍存在的具体问题，或偏离参考 / 范例的原因，一般不超过 60 字；没有就写空字符串。
4. 全部字保存后运行 `WF render --batch BATCH --token TOKEN`，**实际查看**返回的每一页（参考 | 修前 | 修后，含 1:1）。
5. 看完运行 `WF viewed --batch BATCH --token TOKEN --render-id 返回的ID --pages 1 2 …`（列出全部页号）。需要时再做一轮：再 checkpoint、render、看图、viewed。每字最多{MAX_VIEWS}轮视觉复看。
6. `WF submit --batch BATCH --token TOKEN`。提交只是模型草稿完成，不代表用户接受；结果不会自动进入字体。

遇到 stale token 立即停止写入并汇报。不读取其他批次或别处的历史答案，不浏览网络，不另写渲染器，不使用图像生成模型，不修改 KIT 以外的任何文件（尤其是仓库的 glyphs/、forms/）。

最终只汇报一行：`batch=BATCH; submitted=N; changed=M; concerns=具体问题/无; result=路径`。
