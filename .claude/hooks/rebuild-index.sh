#!/usr/bin/env bash
# Stop Hook：会话结束时重建索引页。
#
# 边界：只负责「重建索引」，不判断笔记内容对不对——语义判断留给人和 CLAUDE.md 的约定。
#
# 成功时完全静默：Stop hook 的输出会回灌给模型，无条件打印「已更新…」会触发
# 没意义的后续动作。失败时才出声，并以退出码 2 结束，让错误浮到对话里而不是被吞掉。
#
# 脚本本身幂等且内容未变时不写文件，所以每轮都跑没有副作用。

set -uo pipefail

root="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$root" || exit 0

# 找可用的 Python：Linux / macOS 与多数发行版是 python3，
# Windows 上（Git Bash / Claude Code）常见的是 python 或 py -3。
if command -v python3 >/dev/null 2>&1; then
    PY=(python3)
elif command -v python >/dev/null 2>&1; then
    PY=(python)
elif command -v py >/dev/null 2>&1; then
    PY=(py -3)
else
    echo "索引重建失败：PATH 里找不到 python3 / python / py -3" >&2
    exit 2
fi

if ! out=$("${PY[@]}" scripts/build_index.py 2>&1); then
    echo "索引重建失败（scripts/build_index.py）：" >&2
    echo "$out" >&2
    exit 2
fi

exit 0
