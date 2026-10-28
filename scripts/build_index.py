#!/usr/bin/env python3
"""扫描知识库里的笔记，重新生成四个索引页。

    INDEX.md       首页：待解决 + 最新文章 + 分类/标签概览
    CATEGORIES.md  分类页：分类树（默认两级，专项目录可再深若干层）
    TAGS.md        标签页：标签 -> 文章
    TIMELINE.md    时间线：按年月倒序

用法：
    python3 scripts/build_index.py

只读取每篇笔记开头 `---` 之间的 frontmatter，不解析正文，不依赖第三方库。
"""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent


def code_dirs() -> set[Path]:
    """源码副本目录：内含 .git 的子目录视为克隆进来的仓库，整体跳过。

    学习专项目录（如 tech/proxy/clash/mihomo/）里放着源码副本，
    里面的 .md（说明、LICENSE、报告）不是笔记，也不该进索引。仓库根目录
    自己的 .git 要排除，否则全库都会被跳过。
    """
    found = set()
    for git in ROOT.rglob(".git"):
        parent = git.parent
        if parent != ROOT:
            found.add(parent)
    return found


CLONE_DIRS = code_dirs()

# ---------------------------------------------------------------- 字段名
# 与 VanBlog 的导入格式对齐，这样以后要把内容发成博客时不用重排字段。
# 已对照官方文档核实（2026-09-23，https://vanblog.mereith.com/features/article.html）：
#   导入时识别的键：title / date / category / tags / top / hide / password
#   别名：category 亦可写 categories，hide 亦可写 hidden；多分类只取第一个
#   不在导入映射表里的：draft（草稿是应用内状态，不从 frontmatter 导入）
F_TITLE = "title"
F_DATE = "date"
F_CATEGORY = "category"
F_TAGS = "tags"
F_TOP = "top"
F_HIDE = "hide"
F_PASSWORD = "password"

# 知识库自有，博客侧没有对应概念（导入时会被忽略）
F_STATUS = "status"

REQUIRED = (F_TITLE, F_DATE, F_CATEGORY, F_STATUS)

# 手写的文件，不参与索引
HANDWRITTEN = {"README.md", "TEMPLATE.md", "ABOUT.md", "CLAUDE.md", "SPEC.md", "AGENTS.md", "VERIFY.md"}
# 本脚本的生成物，不当作笔记
GENERATED = {
    "INDEX.md", "CATEGORIES.md", "TAGS.md", "TIMELINE.md",
    "search.html", "feed.xml", "related.json", "backlinks.json",
}

# 首页「最新文章」列几篇
LATEST_COUNT = 10

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


# ---------------------------------------------------------------- 解析
def parse_frontmatter(text: str) -> dict[str, str]:
    """极简 YAML 解析：只认 `key: value`，值原样保留（含 [] 和逗号）。"""
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}

    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip().strip('"').strip("'")
    return fields


def as_list(value: str) -> list[str]:
    """`[a, b]` / `a, b` / `a` -> ['a', 'b'] / ['a'] / []"""
    if not value:
        return []
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    # 处理引号内的逗号
    parts = []
    current = ""
    in_quotes = False
    for char in value:
        if char in '"\'':
            in_quotes = not in_quotes
        elif char == "," and not in_quotes:
            parts.append(current.strip())
            current = ""
            continue
        current += char
    if current.strip():
        parts.append(current.strip())
    return [p for p in parts if p]


def collect_notes() -> list[dict]:
    notes = []
    for path in sorted(ROOT.rglob("*.md")):
        rel = path.relative_to(ROOT)
        if path.name in HANDWRITTEN or path.name in GENERATED:
            continue
        if SCRIPTS_DIR in path.parents:
            continue
        if any(path.is_relative_to(d) for d in CLONE_DIRS):
            continue
        if any(part.startswith(".") for part in rel.parts):
            continue
        if "reports" in rel.parts:
            continue

        meta = parse_frontmatter(path.read_text(encoding="utf-8"))
        rel_dir = rel.parent.as_posix()
        rel_dir = "" if rel_dir == "." else rel_dir
        category = meta.get(F_CATEGORY, "")

        notes.append(
            {
                "title": meta.get(F_TITLE) or path.stem,
                "date": meta.get(F_DATE, ""),
                "category": category,
                "tags": as_list(meta.get(F_TAGS, "")),
                "status": meta.get(F_STATUS, ""),
                "path": rel.as_posix(),
                "dir": rel_dir,
                "missing": [f for f in REQUIRED if not meta.get(f)],
                # category 与所在目录不一致：同一件事写在了两个地方，会漂移
                "mismatch": bool(rel_dir) and bool(category) and rel_dir != category,
            }
        )
    return notes


def sort_notes(notes: list[dict]) -> list[dict]:
    """日期倒序（新的在前），无日期的沉底；同日期按标题升序。"""
    ordered = sorted(notes, key=lambda n: n["title"])
    ordered.sort(key=lambda n: n["date"], reverse=True)
    return ordered


def group_key(category: str) -> str:
    """取一级分类。`tech/linux` -> `tech`；`misc` -> `misc`。"""
    return category.split("/")[0] if category else "(未分类)"


def sub_label(category: str, group: str) -> str:
    """去掉一级分类前缀，`tech/proxy/clash` -> `proxy/clash`。

    默认分类是两级，专项目录（如 tech/proxy/clash）会更深；
    展示时统一去掉大类前缀，避免子标题把 `tech` 也带出来。
    """
    prefix = f"{group}/"
    return category[len(prefix):] if category.startswith(prefix) else category


def warn(note: dict) -> str:
    """标题后面的告警标记。"""
    if note["missing"] or note["mismatch"]:
        return " ⚠️"
    return ""


# ---------------------------------------------------------------- 渲染
def header(title: str, notes: list[dict], extra: str = "") -> list[str]:
    return [
        f"# {title}",
        "",
        f"> 由 `python3 scripts/build_index.py` 自动生成，最后更新 {date.today().isoformat()}，"
        f"共 {len(notes)} 篇。**不要手工编辑本文件。**",
        "",
    ] + ([extra] if extra else [])


def render_home(notes: list[dict]) -> str:
    unresolved = [n for n in notes if n["status"] != "resolved"]
    lines = header("首页", notes)

    lines += [f"## 待解决：{len(unresolved)} 篇", ""]
    if unresolved:
        lines += ["_没搞清楚的都挂在这，相当于一份自动维护的待办。_", ""]
        for note in sort_notes(unresolved):
            lines.append(f"- [{note['title']}]({note['path']}) — `{note['category'] or '—'}`")
    else:
        lines.append("_全部有结论了。_")
    lines.append("")

    lines += ["## 最新", ""]
    latest = sort_notes([n for n in notes if n["date"]])[:LATEST_COUNT]
    if latest:
        for note in latest:
            tags = f" · {' '.join('`' + t + '`' for t in note['tags'])}" if note["tags"] else ""
            lines.append(
                f"- **{note['date']}** [{note['title']}]({note['path']}){warn(note)}"
                f" — `{note['category'] or '—'}`{tags}"
            )
    else:
        lines.append("_还没有带日期的笔记。_")
    lines.append("")

    lines += ["## 分类", ""]
    groups: dict[str, list[dict]] = defaultdict(list)
    for note in notes:
        groups[group_key(note["category"])].append(note)
    if groups:
        lines += ["| 大类 | 篇数 | 子类 |", "| --- | --- | --- |"]
        for name in sorted(groups, key=lambda g: (-len(groups[g]), g)):
            subs = Counter(n["category"] or "(未分类)" for n in groups[name])
            if len(subs) == 1 and next(iter(subs)) == name:
                sub_text = "—（单级）"
            else:
                sub_text = "、".join(
                    f"{sub_label(s, name)} ({c})" for s, c in sorted(subs.items())
                )
            lines.append(f"| **{name}** | {len(groups[name])} | {sub_text} |")
    else:
        lines.append("_还没有笔记。_")
    lines.append("")

    lines += ["## 标签", ""]
    tag_counts = Counter(t for n in notes for t in n["tags"])
    if tag_counts:
        lines.append(
            " ".join(f"`{t}`({c})" for t, c in sorted(tag_counts.items(), key=lambda kv: (-kv[1], kv[0])))
        )
    else:
        lines.append("_还没有标签。_")
    lines.append("")

    return "\n".join(lines)


def render_categories(notes: list[dict]) -> str:
    lines = header("分类", notes)
    groups: dict[str, list[dict]] = defaultdict(list)
    for note in notes:
        groups[group_key(note["category"])].append(note)

    if not groups:
        lines += ["_还没有笔记。从 `cp TEMPLATE.md tech/linux/2026-09-23-标题.md` 开始。_", ""]
        return "\n".join(lines)

    for name in sorted(groups, key=lambda g: (-len(groups[g]), g)):
        group = groups[name]
        lines += [f"## {name} ({len(group)})", ""]

        subs: dict[str, list[dict]] = defaultdict(list)
        for note in group:
            subs[note["category"] or "(未分类)"].append(note)

        # 单级分类（category 就是大类名）不再套一层多余的子标题
        flat = len(subs) == 1 and next(iter(subs)) == name

        for sub in sorted(subs, key=lambda s: (-len(subs[s]), s)):
            if not flat:
                lines += [f"### {sub_label(sub, name)} ({len(subs[sub])})", ""]
            lines += ["| 日期 | 标题 | 状态 | 标签 |", "| --- | --- | --- | --- |"]
            for note in sort_notes(subs[sub]):
                lines.append(
                    f"| {note['date'] or '—'} | [{note['title']}]({note['path']}){warn(note)} "
                    f"| {note['status'] or '—'} | {' '.join(note['tags']) or '—'} |"
                )
            lines.append("")

    return "\n".join(lines)


def render_tags(notes: list[dict]) -> str:
    lines = header("标签", notes)
    by_tag: dict[str, list[dict]] = defaultdict(list)
    for note in notes:
        for tag in note["tags"]:
            by_tag[tag].append(note)

    if not by_tag:
        lines += ["_还没有标签。_", ""]
        return "\n".join(lines)

    for tag in sorted(by_tag, key=lambda t: (-len(by_tag[t]), t)):
        tagged = by_tag[tag]
        lines += [f"## {tag} ({len(tagged)})", ""]
        for note in sort_notes(tagged):
            lines.append(
                f"- **{note['date'] or '—'}** [{note['title']}]({note['path']}){warn(note)}"
                f" — `{note['category'] or '—'}`"
            )
        lines.append("")

    return "\n".join(lines)


def render_timeline(notes: list[dict]) -> str:
    lines = header("时间线", notes)
    dated = [n for n in notes if n["date"]]
    if not dated:
        lines += ["_还没有带日期的笔记。_", ""]
        return "\n".join(lines)

    by_month: dict[str, list[dict]] = defaultdict(list)
    for note in dated:
        by_month[note["date"][:7]].append(note)

    for month in sorted(by_month, reverse=True):
        lines += [f"## {month} ({len(by_month[month])})", ""]
        for note in sort_notes(by_month[month]):
            day = note["date"][8:10] or note["date"]
            lines.append(
                f"- **{day}日** [{note['title']}]({note['path']}){warn(note)}"
                f" — `{note['category'] or '—'}` · {note['status'] or '—'}"
            )
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------- 搜索 / 相关 / 反向链接 / 热力图
def build_search_data(notes: list[dict]) -> list[dict]:
    """每篇笔记的搜索数据：title/path/date/category/tags/content 摘要。"""
    data = []
    for n in notes:
        content = ""
        note_path = ROOT / n["path"]
        if note_path.exists():
            text = note_path.read_text(encoding="utf-8")
            # 取 frontmatter 之后的正文，前 200 字
            if "---" in text:
                parts = text.split("---", 2)
                content = parts[2].strip()[:200] if len(parts) > 2 else ""
            else:
                content = text.strip()[:200]
        data.append({
            "title": n["title"],
            "path": n["path"],
            "date": n["date"],
            "category": n["category"],
            "tags": n["tags"],
            "content": content,
        })
    return data


def build_related(notes: list[dict]) -> dict[str, list[str]]:
    """基于标签共现计算相关笔记。返回 {path: [related_paths]}。"""
    result = {}
    for n in notes:
        tag_set = set(n["tags"])
        scored = []
        for m in notes:
            if m["path"] == n["path"]:
                continue
            common = tag_set & set(m["tags"])
            if common:
                scored.append((len(common), m["date"], m["path"]))
        # 共同标签数降序，同数量时日期降序
        scored.sort(key=lambda x: (-x[0], -int(x[1].replace("-", "") if x[1] else "0")))
        result[n["path"]] = [p for _, _, p in scored[:5]]
    return result


def build_backlinks(notes: list[dict]) -> dict[str, list[dict]]:
    """解析笔记间 Markdown 链接，返回 {path: [{from, text}]}。"""
    link_re = re.compile(r"\[([^\]]+)\]\(([^)]+\.md)\)")
    result: dict[str, list[dict]] = {n["path"]: [] for n in notes}
    for n in notes:
        note_path = ROOT / n["path"]
        if not note_path.exists():
            continue
        text = note_path.read_text(encoding="utf-8")
        note_dir = note_path.parent
        for m in link_re.finditer(text):
            link_text = m.group(1)
            link_target = m.group(2)
            # 解析相对路径
            try:
                target_path = (note_dir / link_target).resolve().relative_to(ROOT).as_posix()
            except ValueError:
                # 链接指向知识库外，跳过
                continue
            if target_path in result:
                result[target_path].append({"from": n["path"], "text": link_text})
    return result


def build_heatmap(notes: list[dict]) -> dict[str, int]:
    """按天统计笔记数量。返回 {date: count}。"""
    counts = Counter(n["date"] for n in notes if n["date"])
    return dict(sorted(counts.items()))


def xml_escape(text: str) -> str:
    """XML 转义。"""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def render_feed(notes: list[dict]) -> str:
    """Atom feed，最新 20 篇。"""
    latest = sort_notes([n for n in notes if n["date"]])[:20]
    entries = ""
    for n in latest:
        entries += f"""  <entry>
    <title>{xml_escape(n['title'])}</title>
    <link href="{n['path']}"/>
    <id>{n['path']}</id>
    <updated>{n['date']}T00:00:00Z</updated>
    <category term="{xml_escape(n['category'])}"/>
    <summary>{xml_escape(', '.join(n['tags']))}</summary>
  </entry>
"""
    return f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>知识库</title>
  <link href="."/>
  <updated>{date.today().isoformat()}T00:00:00Z</updated>
  <id>knowledge-base</id>
{entries}</feed>
"""


def render_search_html(notes: list[dict]) -> str:
    """自包含搜索页面（内联 JSON + vanilla JS）。"""
    import json
    data = build_search_data(notes)
    data_json = json.dumps(data, ensure_ascii=False)
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>搜索 · 知识库</title>
<style>
:root {{ --bg: #fff; --fg: #1a1a2e; --muted: #6b7280; --border: #e5e7eb; --accent: #3b82f6; --accent-light: #eff6ff; }}
[data-theme="dark"] {{ --bg: #1a1a2e; --fg: #e5e7eb; --muted: #9ca3af; --border: #374151; --accent: #60a5fa; --accent-light: #1e3a5f; }}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans SC", sans-serif; background: var(--bg); color: var(--fg); padding: 2rem 1rem; }}
.container {{ max-width: 800px; margin: 0 auto; }}
h1 {{ font-size: 1.5rem; margin-bottom: 1rem; }}
input {{ width: 100%; padding: 0.75rem 1rem; font-size: 1rem; border: 1px solid var(--border); border-radius: 8px; background: var(--bg); color: var(--fg); margin-bottom: 1.5rem; }}
input:focus {{ outline: 2px solid var(--accent); border-color: var(--accent); }}
.results {{ list-style: none; }}
.results li {{ padding: 0.75rem; border-bottom: 1px solid var(--border); }}
.results li:last-child {{ border-bottom: none; }}
.results a {{ color: var(--accent); text-decoration: none; font-weight: 500; }}
.results a:hover {{ text-decoration: underline; }}
.results .meta {{ color: var(--muted); font-size: 0.8125rem; margin-top: 0.25rem; }}
.results .snippet {{ color: var(--muted); font-size: 0.875rem; margin-top: 0.25rem; }}
.no-results {{ color: var(--muted); text-align: center; padding: 2rem; }}
</style>
</head>
<body>
<div class="container">
  <h1>搜索知识库</h1>
  <input type="text" id="q" placeholder="输入关键词搜索..." autofocus>
  <ul class="results" id="results"></ul>
</div>
<script>
const DATA = {data_json};
const q = document.getElementById('q');
const results = document.getElementById('results');
function search() {{
  const term = q.value.toLowerCase().trim();
  if (!term) {{ results.innerHTML = ''; return; }}
  const matched = DATA.filter(n =>
    n.title.toLowerCase().includes(term) ||
    n.tags.some(t => t.toLowerCase().includes(term)) ||
    n.content.toLowerCase().includes(term)
  );
  if (matched.length === 0) {{
    results.innerHTML = '<li class="no-results">没有匹配的笔记</li>';
    return;
  }}
  results.innerHTML = matched.map(n => {{
    const title = n.title.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const category = (n.category || '—').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const tags = n.tags.map(t => '#' + t).join(' ');
    const snippet = n.content.slice(0, 100).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    return `
    <li>
      <a href="${{n.path}}">${{title}}</a>
      <div class="meta">${{n.date}} · ${{category}} · ${{tags}}</div>
      <div class="snippet">${{snippet}}...</div>
    </li>`;
  }}).join('');
}}
q.addEventListener('input', search);
</script>
</body>
</html>
'''


# ---------------------------------------------------------------- 主流程
PAGES = {
    "INDEX.md": render_home,
    "CATEGORIES.md": render_categories,
    "TAGS.md": render_tags,
    "TIMELINE.md": render_timeline,
}


def write_if_changed(path: Path, content: str) -> bool:
    """内容没变就不写。避免无谓刷新 mtime——Stop Hook 每轮都会跑本脚本。"""
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def main() -> int:
    import json

    notes = collect_notes()
    changed = [name for name, render in PAGES.items() if write_if_changed(ROOT / name, render(notes))]

    # 新增生成物
    if write_if_changed(ROOT / "search.html", render_search_html(notes)):
        changed.append("search.html")
    if write_if_changed(ROOT / "feed.xml", render_feed(notes)):
        changed.append("feed.xml")
    related = build_related(notes)
    if write_if_changed(ROOT / "related.json", json.dumps(related, ensure_ascii=False, indent=2)):
        changed.append("related.json")
    backlinks = build_backlinks(notes)
    if write_if_changed(ROOT / "backlinks.json", json.dumps(backlinks, ensure_ascii=False, indent=2)):
        changed.append("backlinks.json")

    if changed:
        print(f"已更新 {'、'.join(changed)}（{len(notes)} 篇笔记）")
    else:
        print(f"索引无变化（{len(notes)} 篇笔记）")

    flagged = [n for n in notes if n["missing"] or n["mismatch"]]
    if flagged:
        print("以下笔记有问题（索引中已标 ⚠️）：", file=sys.stderr)
        for note in flagged:
            reasons = []
            if note["missing"]:
                reasons.append("缺少 " + "、".join(note["missing"]))
            if note["mismatch"]:
                reasons.append(f"category `{note['category']}` 与目录 `{note['dir']}/` 不符")
            print(f"  - {note['path']}：{'；'.join(reasons)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
