# 修字经验

从人工修改中归纳的经验，给 AI 修字（和人）参考。用户确认的规则不在这里，在 [../design-rules.md](../design-rules.md)。

| 文件 | 内容 |
|---|---|
| [worker-lessons.md](worker-lessons.md) | **当前读本**：下一轮 AI 修字要读的候选规律（L023–L054）与自检清单（C001–C017） |
| [2026-09-30-phone-review.md](2026-09-30-phone-review.md) | 手机修字 150 字及编辑器修改：L051–L054 |
| [2026-09-29-phase1-review.md](2026-09-29-phase1-review.md) | 第一期代表字导入后，人工又改了什么：L044–L048 |
| [2026-09-29-pass2-review.md](2026-09-29-pass2-review.md) | 常用百字二次修字（借鉴圆石）后，人工又改了什么：数字、L037–L043 |
| `data/2026-09-28-pass2-tumbled.json` | 常用百字 189 个字形的第一轮 AI、二次修字、人工版和圆石点阵 |

更早的分析（2026-09-17 至 2026-09-26，L001–L036）在旧包存档 `archive/tong-review-v1/knowledge/` 和 `data/proposals/`（不在公开仓库中，由作者另存）。

## 怎样做一次新的总结

1. 选定要分析的字（通常是一批刚人工修完、审核通过的字），取出 AI 版（`history/ai-originals/`、git 历史或试验数据）和人工版。
2. 生成逐字对比图（思源参考 | 圆石 | AI 版 | 人工版，标出增删像素），实际看完；再算统计（改动量、边缘位置、黑块、与圆石的距离等）。
3. 写一份报告 `YYYY-MM-DD-主题.md`，新规律接着编号（L044…、C013…），注明证据字和修订了哪些旧规律。
4. 更新 `worker-lessons.md`，让下一轮 AI 读到的永远是合并后的最新版本。用户确认的规律再写入 `docs/design-rules.md`。
