# 给 AI 代理的工作规则

本仓库是 Tong Pixel Sans（通格像素黑体）的源文件。先读 `docs/README.md`；格式见 `docs/format.md`，画字规则见 `docs/design-rules.md`。

## 必须遵守

- 用用户最近一条消息的语言回复（用户通常用中文）。
- `glyphs/`、`forms/forms.txt`、`history/` 只通过 `tools/editor/store.py`（编辑器、`tools/western/` 脚本都用它）或保持格式不变的方式修改；改完运行 `python3 tools/verify.py`。不手工打乱排序、状态行和关联行。
- 部件关联永远不改变像素。拿不准的一律列出来给用户审核，不自动处理。
- 程序或 AI 写的字形永远不标为 `approved`；只有用户能审核通过。脚本写的像素状态为 `derived`。
- 不改用户画过或通过的字（状态 `edited` / `approved`），除非用户明确点名。
- 修改构建逻辑后，确认 `tools/build.py` 输出与修改前一致，或向用户说明差异。
- 字形来源只能是 OFL 参考字体（思源黑体、Source Sans 3、Noto）。GB/T 37023、中易宋体等授权点阵只能参考、绝不能作为基础，不给修字者看它们的同字点阵。
- 不使用图像生成模型；看图用现有工具（编辑器、`tools/preview.py`）生成的真实点阵。
- 不在用户没有明确要求时启动 AI 批量修字；修字只用用户指定的模型和推理强度，不可用时如实报告，不静默替代。
- 产物名不含 “Source”（思源的保留字体名）。
- 测试只用临时目录里的合成数据（见 `tools/editor/test_store.py`），不改真实源文件。
- 提交、推送、删除文件等不可逆或对外的操作先征得用户同意。

## 目录速查

- `tools/build.py`：构建；`tools/verify.py`：检查；`tools/preview.py`：样张。
- `tools/editor/`：修字编辑器（`server.py`、`store.py`、`forms.py`）。
- `tools/western/`：西文连带更新（`docs/western-tools.md`）。
- `archive/`：旧修字包的代码、提示词和报告，只读，供参考。
