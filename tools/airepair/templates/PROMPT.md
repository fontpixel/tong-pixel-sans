# 启动提示词（用户在 Codex 中发送）

在 Codex 里、以本轮目录 `{KIT}` 为工作目录发送：

```text
开始修字：{NAME}。用 {WORKERS} 个 subagent 并发，模型 {MODEL}，reasoning_effort {EFFORT}，不要 fast mode。
KIT={KIT}
WF={PY} {WF} --round {KIT}
共 {N} 批（b001–{LAST}），每批最多 {BATCH_SIZE} 字。你是协调者，不自己修字：
1. 运行 `$WF status`。
2. 每次为一个 worker 领取一批：`$WF claim --owner 唯一名称`（如 日期时间+序号），得到 batch 和 token。
3. 用 collaboration.spawn_agent 启动 worker：model="{MODEL}", reasoning_effort="{EFFORT}", fork_turns="none"。只传下面这段 worker 消息（填好 BATCH、TOKEN、OWNER），不要传聊天记录或别的批次。然后 `$WF register-agent --batch B --token T --agent-id 实际agentID`。
4. 同时最多 {WORKERS} 个 worker。一个结束后查 `$WF status`，只有 submitted 才算完成；再领下一批，直到全部 submitted。worker 失败时先确认它已停止，`$WF release --batch B --token T --reason 原因` 后重新领取，已保存的检查点会保留。
5. 全部提交后汇报 status。不要改 KIT 以外的文件。

worker 消息：
本批 AI 修字已获用户授权。模型必须 {MODEL}，effort {EFFORT}。
KIT={KIT}
WF={PY} {WF} --round {KIT}
BATCH=…
TOKEN=…
OWNER=…
请先读 KIT/PROTOCOL.md 并严格照做（其中写明本批的任务、写法依据和输出格式）；遵守 KIT/LESSONS.md 的规则与自检清单。
先运行 `$WF context --batch BATCH --token TOKEN`；读 LESSONS.md、本批 inputs.txt，实际查看 context 列出的全部图片。
每至多 10 字 checkpoint，全部保存后 render、实际看完每页、viewed，最多{MAX_VIEWS}轮，然后 submit。
不要再开代理，不处理第二批，不读其他批次，不改 KIT 以外的文件。
```
