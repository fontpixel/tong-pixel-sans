# 启动提示词（审读，用户在 Codex 中发送）

```text
开始审读：{NAME}。只列问题，不修改任何字形。用 {WORKERS} 个 subagent 并发，模型 gpt-6-astra，reasoning_effort xhigh，不要 fast mode。
环境：python3 -m pip install -r tools/requirements.txt（只需看图，不需要参考字体）
KIT={KIT}
共 {N} 批（b001–{LAST}），{PAGES} 页，{GLYPHS} 个字形。你是协调者，不自己审读：
1. 已完成的批次 = KIT/results/bNNN.tsv 存在且最后一行以 “# done” 开头。列出未完成的批次。
2. 每次为一批启动一个 subagent 作为 worker（model gpt-6-astra，reasoning_effort xhigh，不带聊天记录），只传下面的 worker 消息（填好 BATCH）。
3. 同时最多 {WORKERS} 个 worker。一个结束后确认它的 results 文件已写完（有 “# done”），再派下一批；没写完就重新派这一批（覆盖旧文件）。
4. 额度用完或中断时先保存进度；用户会重新发起同一个任务，只派未完成的批次。只要还有额度就一直派下去，不要中途停下来汇报。
5. 全部完成后：汇报完成批数和问题总数（按类型统计），以及启动 worker 用的模型参数。先尝试把 KIT/results/ 提交并推送到当前分支；推送不了就把 KIT/results/ 打成 zip 交给用户。
只改 KIT/results/ 以内的文件。

worker 消息：
本批 AI 审读已获用户授权。模型必须 gpt-6-astra，effort xhigh。只列问题，不修改任何字形。
KIT={KIT}
BATCH=…
请先读 KIT/PROTOCOL.md 并严格照做；实际查看 KIT/batches/BATCH/ 下的每一页（detail=original），对照 pages.tsv，把明显的错误写进 KIT/results/BATCH.tsv，看完后加 “# done 页数”。
不要再开代理，不审读第二批，不读其他批次的结果，不改 KIT/results/BATCH.tsv 以外的文件。
```
