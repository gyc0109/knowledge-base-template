#!/usr/bin/env bash
# Stop Hook：检查待归档暂存区，非空就顶回对话。
#
# 边界：只做**检测**，不做归档。语义判断（值不值得写、归哪个分类、
# 和旧笔记什么关系）只有模型能做，bash 写出来的笔记半年后自己都看不懂。
#
# 机制：Stop hook 的输出会回灌给模型，退出码 2 让内容浮到对话里而不是被吞掉。
# 模型据此完成归档或向用户确认，然后清空本文件。
#
# 防循环：同一会话只升级一次。模型清空 pending 后本 hook 自然静默；
# 万一它没清空，标记文件会挡住下一次——否则「忘记清空」会变成每轮都打断的死循环。
#
# 标记文件由模型清空 pending 时一并删除。若删除后 pending 再次变非空，会重新触发，
# 这是期望行为：暂存区非空本来就是需要处理的状态。

set -uo pipefail

root="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
pending="$root/.claude/pending_archive.md"
flag="$root/.claude/.pending_hook_fired"

# 本会话已升级过，静默退出
[ -f "$flag" ] && exit 0

# 文件不存在，视为空
[ -f "$pending" ] || exit 0

# 剥掉 HTML 注释和空行后还有内容，才算真的有东西要处理。
# 纯 bash 实现，不调 sed / grep——Windows 的 Git Bash 上不一定有这两个命令。
body=""
in_comment=0
while IFS= read -r line || [ -n "$line" ]; do
    if [ "$in_comment" -eq 1 ]; then
        case "$line" in
            *"-->"*) in_comment=0; line="${line#*-->}" ;;
            *) continue ;;
        esac
    fi
    while :; do
        case "$line" in
            *"<!--"*)
                pre="${line%%<!--*}"
                rest="${line#*<!--}"
                case "$rest" in
                    *"-->"*) line="$pre${rest#*-->}" ;;
                    *) line="$pre"; in_comment=1; break ;;
                esac
                ;;
            *) break ;;
        esac
    done
    case "$line" in
        *[![:space:]]*) body="${body}${line}"$'\n' ;;
    esac
done < "$pending"

[ -z "$body" ] && exit 0

touch "$flag"

echo "待归档暂存区有内容（.claude/pending_archive.md）：" >&2
echo "$body" >&2
echo "" >&2
echo "请处理上述条目：确认归档分类后写成笔记，或向用户确认是否值得留存。" >&2
echo "处理完清空 .claude/pending_archive.md（保留 HTML 注释说明即可），" >&2
echo "并删除 .claude/.pending_hook_fired。" >&2
exit 2
