# 文档

| 文档 | 内容 |
|---|---|
| [format.md](format.md) | 源文件格式：目录、分组、字形块、状态、形态库 |
| [building.md](building.md) | 构建与检查：产物、比例版 / 等宽版如何组成、`verify.py` |
| [editor.md](editor.md) | 修字编辑器的用法 |
| [design-rules.md](design-rules.md) | 画字规则：已确定的字形决定 |
| [western-tools.md](western-tools.md) | 西文字族连带更新脚本 |
| [reference-fonts.md](reference-fonts.md) | 参考字体、版本、校验值、点阵化参数 |
| [ai-repair.md](ai-repair.md) | AI 修字的流程与经验 |
| [lessons/](lessons/README.md) | 从人工修改中归纳的修字经验；`lessons/worker-lessons.md` 是 AI 修字的当前读本 |
| [history.md](history.md) | 字形来历、转换记录 |
| [roadmap.md](roadmap.md) | 待办与未决问题 |

## 常用命令

```bash
python3 tools/build.py              # 构建 8 个 BDF 到 build/
python3 tools/verify.py             # 检查源文件和字表覆盖
python3 tools/editor/server.py      # 修字编辑器 http://127.0.0.1:8791/
python3 tools/editor/test_store.py  # 编辑器存储层测试
python3 tools/preview.py            # 样张（需要 Pillow）
```

`tools/build.py`、`tools/verify.py` 和编辑器核心只需要 Python 3 标准库。参考轮廓需要 fontTools，样张和西文脚本的对比图需要 Pillow：

```bash
python3 -m venv .venv && .venv/bin/pip install -r tools/requirements.txt
.venv/bin/python tools/editor/server.py
```
