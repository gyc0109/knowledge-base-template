# 验收检查

模板装好之后，把这页第一节整段复制给那台机器上的 AI，它会逐项跑完并给出结论。第二节是预期结果，人工也能照着核。

---

## 一、给 AI 的提示词

````text
我在新机器上把这个仓库部署成了技术知识库（仓库：knowledge-base-template）。
现在请你做一次安装验收。

规则：
- 只做检查和只读操作。第 6 项会临时改动 .claude/pending_archive.md，测完必须原样恢复。
- 不要修改任何笔记内容，不要 git commit / push。
- 每一项都要跑真实的命令，用命令输出当证据，不要凭文件存在就下结论。
- 失败项给出具体的修复命令，等我确认后再执行。

逐项检查：

1) 文件齐全
for f in AGENTS.md CLAUDE.md SPEC.md TEMPLATE.md README.md ABOUT.md \
         scripts/build_index.py .claude/settings.json \
         .claude/hooks/rebuild-index.sh .claude/hooks/archive-pending.sh \
         .claude/pending_archive.md; do
  [ -f "$f" ] && echo "OK   $f" || echo "MISS $f"
done
ls -l .claude/hooks/*.sh    # 两个 hook 必须是可执行位

2) 脚本能跑
python3 -VV
python3 scripts/build_index.py; echo "exit=$?"

3) 输出幂等
md5sum INDEX.md CATEGORIES.md TAGS.md TIMELINE.md search.html feed.xml \
       related.json backlinks.json > /tmp/kb.md5
python3 scripts/build_index.py >/dev/null && md5sum -c /tmp/kb.md5

4) 生成物是合法 JSON / XML
python3 - <<'EOF'
import json, xml.etree.ElementTree as ET
for f in ("related.json", "backlinks.json"):
    json.load(open(f, encoding="utf-8")); print("OK", f)
ET.parse("feed.xml"); print("OK feed.xml")
EOF

5) 索引把对了文件
python3 - <<'EOF'
import sys; sys.path.insert(0, 'scripts')
import build_index as b
notes = b.collect_notes()
print("笔记数:", len(notes))
print("缺字段:", [(n['path'], n['missing']) for n in notes if n['missing']] or "无")
print("目录不符:", [(n['path'], n['category']) for n in notes if n['mismatch']] or "无")
bad = [n['path'] for n in notes if n['path'].rsplit('/', 1)[-1] in
       ("AGENTS.md", "CLAUDE.md", "SPEC.md", "README.md", "TEMPLATE.md", "ABOUT.md")]
print("手写文档被误收:", bad or "无")
EOF

6) Stop Hook 三态（测完恢复原状）
cp .claude/pending_archive.md /tmp/pending.bak
bash .claude/hooks/archive-pending.sh; echo "空暂存区 exit=$?（应为 0）"
printf '\n## 验收测试条目\n- category: 待定\n' >> .claude/pending_archive.md
bash .claude/hooks/archive-pending.sh; echo "有内容 exit=$?（应为 2）"
bash .claude/hooks/archive-pending.sh; echo "标记后 exit=$?（应为 0）"
cp /tmp/pending.bak .claude/pending_archive.md
rm -f .claude/.pending_hook_fired
bash .claude/hooks/archive-pending.sh; echo "恢复后 exit=$?（应为 0）"

7) 问答闭环能走通：检索要能命中已有笔记
grep -rn "示例" --include='*.md' . | grep -v '/\.git/' | head -5
# 命中就说明「先查库、命中直接答」这条路径是通的

8) 没有残留的机器专属路径或已删除的功能
grep -rn "/root/Labs\|scripts/report.py" --include='*.md' --include='*.sh' . \
  | grep -v '/\.git/' | grep -v 'VERIFY.md' || echo "无残留"

输出格式：
给一张表 —— 检查项 | 结果(PASS/FAIL) | 证据（命令输出的关键行）。
最后回答三句话：
1. 这套知识库现在能不能用？
2. 有没有必须修的地方？有就给命令。
3. 我下一步该做什么？
````

---

## 二、预期结果

| 项 | 通过标准 |
| --- | --- |
| 1 文件齐全 | 10 个文件全部 `OK`；两个 hook 有可执行位（`-rwx`） |
| 2 能跑 | `exit=0`，输出「共 N 篇」，N 等于实际笔记数（示例笔记还在就是 1） |
| 3 幂等 | 8 个生成物全部 `OK`，没有 `FAILED` |
| 4 合法性 | 三行 `OK`，无异常栈 |
| 5 索引对 | `缺字段: 无`、`目录不符: 无`、`手写文档被误收: 无` |
| 6 Hook | `0 / 2 / 0 / 0` 四个退出码依次正确 |
| 7 检索 | grep 能返回笔记路径（示例笔记未删时必有） |
| 8 残留 | 输出 `无残留` |

## 三、常见失败与修法

| 现象 | 原因 | 修法 |
| --- | --- | --- |
| 手写文档被误收 | 新增了根目录手写文件但没登记 | 加进 `scripts/build_index.py` 顶部的 `HANDWRITTEN` |
| 笔记数比预期多出几百 | 放了源码副本但没保留 `.git` | 保留 `.git`，或在 `code_dirs()` 里加排除 |
| Hook 退出码不对 | 脚本没有可执行位 / 没经过 bash 调用 | `chmod +x .claude/hooks/*.sh` |
| 索引没随笔记更新 | Hook 只在会话启动时加载 | 重开会话，或手动 `python3 scripts/build_index.py` |
| `feed.xml` 解析失败 | 标题里有未转义的 `<` `&` | 改标题；转义由脚本负责，检查是否改了渲染逻辑 |
