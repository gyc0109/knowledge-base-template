#!/usr/bin/env python3
"""生成知识库周报：HTML 展示 + MD 留档。

用法：
    python3 scripts/report.py            # 生成到 reports/ 目录
    python3 scripts/report.py --print    # 同时打印到终端

输出：
    reports/<ISO周>.md      留档
    reports/<ISO周>.html    展示
    reports/index.html      始终指向最新

只读 frontmatter，不解析正文，纯标准库。
"""

from __future__ import annotations

import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_index import collect_notes, sort_notes, build_backlinks  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "reports"

# 笔记路径是仓库根相对的（tech/network/xxx.md），而周报产物落在 reports/ 下。
# 直接把根相对路径写进链接，渲染器会从 reports/ 往上解析，得到 reports/tech/... 这种不存在的路径。
# 所以渲染链接时统一加一层 ../；JSON / CSV 导出是数据不是链接，保持原样。
LINK_PREFIX = "../"


# ---------------------------------------------------------------- 工具函数
def esc(text: str) -> str:
    """HTML 转义。"""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# ---------------------------------------------------------------- 日期工具
def parse_day(value: str) -> date | None:
    """`2026-09-26` -> date；空值或格式不对返回 None。"""
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def window(notes: list[dict], start: date, end: date) -> list[dict]:
    """闭区间 [start, end] 内的笔记，日期倒序。"""
    return sort_notes([n for n in notes if (d := parse_day(n["date"])) and start <= d <= end])


def last_week(today: date) -> tuple[date, date]:
    """上周一到上周日。"""
    this_monday = today - timedelta(days=today.weekday())
    return this_monday - timedelta(days=7), this_monday - timedelta(days=1)


def quarter_start(today: date) -> date:
    """本季第一天。"""
    return date(today.year, (today.month - 1) // 3 * 3 + 1, 1)


def iso_week_label(d: date) -> str:
    """`2026-W39`。"""
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


# ---------------------------------------------------------------- 数据收集
def _week_stats(d: dict) -> dict:
    """observations() 和 ai_template() 共享的上周数据统计。"""
    week = d["last_week_notes"]
    if not week:
        return {}
    cats = Counter(n["category"] or "(未分类)" for n in week)
    top_cat, top_count = cats.most_common(1)[0]
    open_week = [n for n in week if n["status"] != "resolved"]
    oldest = min(open_week, key=lambda n: n["date"]) if open_week else None
    days = (d["today"] - parse_day(oldest["date"])).days if oldest else 0
    all_tags = [t for n in week for t in n["tags"]]
    top_tags = Counter(all_tags).most_common(3)
    return {
        "cats": cats,
        "top_cat": top_cat,
        "top_count": top_count,
        "open_week": open_week,
        "oldest": oldest,
        "days": days,
        "top_tags": top_tags,
    }


def gather(today: date) -> dict:
    """收集所有时间窗口的数据。"""
    notes = collect_notes()
    lw_start, lw_end = last_week(today)
    qs = quarter_start(today)
    ys = date(today.year, 1, 1)
    ms = today.replace(day=1)

    last_week_notes = window(notes, lw_start, lw_end)
    month = window(notes, ms, today)
    quarter = window(notes, qs, today)
    year = window(notes, ys, today)
    open_notes = sort_notes([n for n in notes if n["status"] != "resolved"])

    # 月度趋势
    monthly = Counter(n["date"][:7] for n in notes if n["date"])
    monthly_trend = dict(sorted(monthly.items()))

    # 每周趋势（ISO 周）
    weekly = Counter()
    for n in notes:
        if n["date"]:
            d = parse_day(n["date"])
            if d:
                iso = d.isocalendar()
                weekly[f"{iso.year}-W{iso.week:02d}"] += 1
    weekly_trend = dict(sorted(weekly.items()))

    # GitHub 风格贡献图数据：按周和天分组
    # 返回 [(week_index, weekday, count), ...]
    from datetime import timedelta as td
    contrib = []
    if notes:
        dated_notes = [n for n in notes if n["date"]]
        if dated_notes:
            dates = [parse_day(n["date"]) for n in dated_notes]
            min_date = min(dates)
            max_date = max(dates)
            # 对齐到周一
            start = min_date - td(days=min_date.weekday())
            # 按 (week_index, weekday) 分组
            day_counts = Counter()
            for d in dates:
                week_idx = (d - start).days // 7
                weekday = d.weekday()  # 0=Mon
                day_counts[(week_idx, weekday)] += 1
            # 生成完整的网格（包括没有笔记的天）
            total_weeks = (max_date - start).days // 7 + 1
            for w in range(total_weeks):
                for day in range(7):
                    count = day_counts.get((w, day), 0)
                    contrib.append((w, day, count))

    # 过期笔记（open 超过 30 天）
    stale_notes = []
    for n in open_notes:
        d = parse_day(n["date"])
        if d and (today - d).days > 30:
            stale_notes.append((n, (today - d).days))
    stale_notes.sort(key=lambda x: -x[1])

    # 标签趋势（上周 vs 上上周）
    prev_week_start = lw_start - timedelta(days=7)
    prev_week_end = lw_start - timedelta(days=1)
    prev_week = window(notes, prev_week_start, prev_week_end)
    prev_tags = Counter(t for n in prev_week for t in n["tags"])
    curr_tags = Counter(t for n in last_week_notes for t in n["tags"])
    tag_trends = {}
    all_tags = set(prev_tags.keys()) | set(curr_tags.keys())
    for t in all_tags:
        tag_trends[t] = (prev_tags.get(t, 0), curr_tags.get(t, 0))

    # 知识缺口（笔记数少于 3 篇的分类）
    cat_counts = Counter(n["category"] or "(未分类)" for n in notes)
    knowledge_gaps = [(cat, count) for cat, count in cat_counts.items() if count < 3]

    # 笔记质量评分
    backlinks = build_backlinks(notes)
    quality_scores = []
    for n in notes:
        score = 0
        reasons = []
        # 状态
        if n["status"] == "resolved":
            score += 30
            reasons.append("已解决")
        # 标签
        if n["tags"]:
            score += min(len(n["tags"]) * 5, 20)
            reasons.append(f"{len(n['tags'])} 个标签")
        # 交叉链接
        if backlinks.get(n["path"]):
            score += min(len(backlinks[n["path"]]) * 10, 30)
            reasons.append(f"{len(backlinks[n['path']])} 个反向链接")
        # 正文长度
        note_path = ROOT / n["path"]
        if note_path.exists():
            text = note_path.read_text(encoding="utf-8")
            content = text.split("---", 2)[-1].strip() if "---" in text else text
            if len(content) > 500:
                score += 20
                reasons.append("内容详实")
            elif len(content) > 200:
                score += 10
                reasons.append("内容适中")
        quality_scores.append((n, score, reasons))
    quality_scores.sort(key=lambda x: -x[1])

    return {
        "today": today,
        "notes": notes,
        "last_week_notes": last_week_notes,
        "week_range": (lw_start, lw_end),
        "month": month,
        "month_range": (ms, today),
        "quarter": quarter,
        "quarter_range": (qs, today),
        "year": year,
        "year_range": (ys, today),
        "open_notes": open_notes,
        "heatmap": dict(sorted(Counter(n["date"] for n in notes if n["date"]).items())),
        "monthly_trend": monthly_trend,
        "weekly_trend": weekly_trend,
        "contrib": contrib,
        "related": related_notes({"notes": notes}),
        "stale_notes": stale_notes,
        "tag_trends": tag_trends,
        "knowledge_gaps": knowledge_gaps,
        "quality_scores": quality_scores,
    }


# ---------------------------------------------------------------- MD 渲染
def render_markdown(d: dict) -> str:
    """渲染 Markdown 留档。"""
    today = d["today"]
    lw_start, lw_end = d["week_range"]
    wk_label = iso_week_label(lw_start)
    lines = [
        f"# 知识库周报 · {wk_label}（{lw_start:%m-%d} ~ {lw_end:%m-%d}）",
        "",
        f"> 由 `python3 scripts/report.py` 自动生成，生成日期 {today}。",
        f"> 全库 {len(d['notes'])} 篇。",
        "",
        "## 时间窗口",
        "",
    ]
    for label, subset, (s, e) in [
        ("上周", d["last_week_notes"], d["week_range"]),
        ("本月", d["month"], d["month_range"]),
        ("本季", d["quarter"], d["quarter_range"]),
        ("本年", d["year"], d["year_range"]),
    ]:
        lines.append(f"- **{label}** {s:%m-%d} ~ {e:%m-%d}：{len(subset)} 篇")
    lines.append("")

    # 每日分布
    if d["last_week_notes"]:
        lines += [f"## 上周每日分布（{lw_start:%m-%d} ~ {lw_end:%m-%d}）", ""]
        per_day = Counter(n["date"] for n in d["last_week_notes"])
        top = max(per_day.values())
        for day, count in sorted(per_day.items()):
            bar = "█" * round(count / top * 20)
            lines.append(f"- `{day}` {bar} {count}")
        lines.append("")

    # 新增清单
    lines += [f"## 上周新增（{len(d['last_week_notes'])} 篇）", ""]
    if d["last_week_notes"]:
        for n in d["last_week_notes"]:
            status = " ✅" if n["status"] == "resolved" else ""
            lines.append(f"- **{n['date']}** [{n['title']}]({LINK_PREFIX}{n['path']}) — `{n['category'] or '—'}`{status}")
    else:
        lines.append("- _上周无新增。_")
    lines.append("")

    # 待解决
    lines += [f"## 待解决（{len(d['open_notes'])} 篇）", ""]
    if d["open_notes"]:
        for n in d["open_notes"]:
            lines.append(f"- **{n['date']}** [{n['title']}]({LINK_PREFIX}{n['path']}) — `{n['category'] or '—'}`")
    else:
        lines.append("- _全部有结论了。_")
    lines.append("")

    # 数据观察
    lines += ["## 数据观察", ""]
    lines += observations(d)
    lines.append("")

    # AI 分析
    lines += ["## AI 分析", ""]
    lines += ["> 本节由 AI 填写，脚本不生成内容。", ""]
    lines += ai_template(d)

    return "\n".join(lines).rstrip() + "\n"


def observations(d: dict) -> list[str]:
    """规则驱动的数据观察。"""
    out = []
    stats = _week_stats(d)
    if not stats:
        out.append("- 上周无新增笔记。")
        return out

    week = d["last_week_notes"]
    out.append(f"- 上周新增集中在 `{stats['top_cat']}`（{stats['top_count']}/{len(week)} 篇）。")

    if stats["open_week"]:
        out.append(f"- 上周新增中 {len(stats['open_week'])} 篇待解决，最早 `{stats['oldest']['date']}` 已挂 {stats['days']} 天。")
    else:
        out.append("- 上周新增全部已有结论。")

    if stats["top_tags"]:
        tag_str = "、".join(f"`{t}`({c})" for t, c in stats["top_tags"])
        out.append(f"- 高频标签：{tag_str}。")

    return out


def ai_template(d: dict) -> list[str]:
    """AI 分析：基于数据生成模板化分析文字。"""
    stats = _week_stats(d)
    if not stats:
        return ["_上周无数据，无需分析。_"]

    week = d["last_week_notes"]
    lines = [f"**本周主题**：新增集中在 `{stats['top_cat']}`（{stats['top_count']}/{len(week)} 篇）。"]

    # 趋势
    if len(stats["cats"]) > 1:
        others = [f"`{c}`({n})" for c, n in stats["cats"].most_common()[1:]]
        lines.append(f"**趋势**：其余分布在 {'、'.join(others)}。")

    # 标签
    if stats["top_tags"]:
        tag_str = "、".join(f"`{t}`({c})" for t, c in stats["top_tags"])
        lines.append(f"**高频标签**：{tag_str}。")

    # 建议
    lines.append("")
    lines.append("**建议**：")
    if stats["open_week"]:
        lines.append(f"- 优先处理 `{stats['oldest']['title']}`（`{stats['oldest']['date']}`，已挂 {stats['days']} 天）")
        if len(stats["open_week"]) > 1:
            lines.append(f"- 还有 {len(stats['open_week']) - 1} 篇待解决，建议本周内跟进")
    else:
        lines.append("- 上周新增全部已有结论，保持节奏")

    # 交叉链接建议
    related = d["related"]
    no_link = [n for n in week if not related.get(n["path"])]
    if no_link and len(week) > 1:
        titles = "、".join(f"`{n['title']}`" for n in no_link[:2])
        lines.append(f"- {titles} 等笔记暂无相关笔记，建议补充交叉链接")

    lines.append("")
    return lines


def related_notes(d: dict, top: int = 5) -> dict[str, list[dict]]:
    """基于标签共现计算相关笔记。返回 {path: [related_notes]}。"""
    notes = d["notes"]
    result = {}
    for n in notes:
        tag_set = set(n["tags"])
        scored = []
        for m in notes:
            if m["path"] == n["path"]:
                continue
            common = tag_set & set(m["tags"])
            if common:
                scored.append((len(common), m["date"], m))
        # 共同标签数降序，同数量时日期降序
        scored.sort(key=lambda x: (-x[0], -int(x[1].replace("-", "") if x[1] else "0")))
        result[n["path"]] = [m for _, _, m in scored[:top]]
    return result


# ---------------------------------------------------------------- HTML 渲染
def line_chart_svg(data: dict[str, int], width: int = 700, height: int = 200) -> str:
    """生成 SVG 折线图。"""
    if not data:
        return ""
    labels = list(data.keys())
    values = list(data.values())
    max_val = max(values) if values else 1
    if max_val == 0:
        max_val = 1

    padding = 40
    chart_w = width - padding * 2
    chart_h = height - padding * 2

    # 计算点坐标
    points = []
    for i, v in enumerate(values):
        x = padding + (i / max(len(values) - 1, 1)) * chart_w
        y = padding + chart_h - (v / max_val) * chart_h
        points.append((x, y))

    # SVG 路径
    path_d = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in points)

    # 数据点
    dots = ""
    for x, y in points:
        dots += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="var(--accent)"/>\n'

    # 数值标签
    value_labels = ""
    for i, (x, y) in enumerate(points):
        value_labels += f'<text x="{x:.1f}" y="{y - 8:.1f}" text-anchor="middle" font-size="10" fill="var(--muted)">{values[i]}</text>\n'

    # X 轴标签
    x_labels = ""
    step = max(1, len(labels) // 6)
    for i, label in enumerate(labels):
        if i % step == 0 or i == len(labels) - 1:
            x = padding + (i / max(len(values) - 1, 1)) * chart_w
            x_labels += f'<text x="{x:.1f}" y="{height - 10}" text-anchor="middle" font-size="9" fill="var(--muted)">{label}</text>\n'

    # 网格线
    grid = ""
    for i in range(5):
        y = padding + (i / 4) * chart_h
        grid += f'<line x1="{padding}" y1="{y:.1f}" x2="{width - padding}" y2="{y:.1f}" stroke="var(--border)" stroke-width="0.5"/>\n'

    return f'''<svg class="chart-svg" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">
{grid}<path d="{path_d}" fill="none" stroke="var(--accent)" stroke-width="2"/>{dots}{value_labels}{x_labels}</svg>'''


def render_html(d: dict) -> str:
    """渲染自包含 HTML 报告。遵循 effective-html skill 规范。"""
    today = d["today"]
    lw_start, lw_end = d["week_range"]
    wk_label = iso_week_label(lw_start)
    week = d["last_week_notes"]

    # 每日分布条形图
    daily_bars = ""
    if week:
        per_day = Counter(n["date"] for n in week)
        top = max(per_day.values())
        for day, count in sorted(per_day.items()):
            pct = round(count / top * 100)
            daily_bars += f'''    <div class="bar-row">
      <span class="bar-label">{day}</span>
      <div class="bar-track"><div class="bar-fill" style="width:{pct}%"></div></div>
      <span class="bar-count">{count}</span>
    </div>
'''

    # 新增清单
    week_items = ""
    if week:
        for n in week:
            status_icon = "✅" if n["status"] == "resolved" else "⬜"
            week_items += f'''    <li>
      <span class="item-date">{n["date"]}</span>
      <span class="item-title">{esc(n["title"])}</span>
      <span class="item-cat">{esc(n["category"] or "—")}</span>
      <span class="item-status">{status_icon}</span>
    </li>
'''
    else:
        week_items = '    <li class="empty">上周无新增。</li>\n'

    # 待解决清单
    open_items = ""
    if d["open_notes"]:
        for n in d["open_notes"]:
            open_items += f'''    <li>
      <span class="item-date">{n["date"]}</span>
      <span class="item-title">{esc(n["title"])}</span>
      <span class="item-cat">{esc(n["category"] or "—")}</span>
    </li>
'''
    else:
        open_items = '    <li class="empty">全部有结论了。</li>\n'

    # 数据观察
    obs_items = ""
    for line in observations(d):
        text = line.lstrip("- ").strip()
        obs_items += f"    <li>{esc(text)}</li>\n"

    # AI 分析
    ai_lines = ai_template(d)
    ai_html = ""
    for line in ai_lines:
        if line.startswith("**") and line.endswith("**"):
            ai_html += f"    <h3>{esc(line.strip('*'))}</h3>\n"
        elif line.startswith("- "):
            ai_html += f"    <li>{esc(line[2:])}</li>\n"
        elif line.strip().startswith("_") and line.strip().endswith("_"):
            ai_html += f'    <p class="placeholder">{esc(line.strip("_"))}</p>\n'
        elif line.strip():
            ai_html += f"    <p>{esc(line)}</p>\n"

    # 活跃度热力图
    heatmap_html = ""
    if d["heatmap"]:
        max_count = max(d["heatmap"].values())
        cells = ""
        for day, count in d["heatmap"].items():
            opacity = count / max_count if max_count > 0 else 0
            cells += f'      <div class="heat-cell" style="opacity:{opacity:.2f}" title="{day}: {count} 篇"></div>\n'
        heatmap_html = f'''  <section>
    <h2>活跃度热力图</h2>
    <div class="heatmap">
{cells}    </div>
    <p class="meta">共 {len(d["heatmap"])} 天有笔记，最多 {max_count} 篇/天</p>
  </section>

'''

    # 相关笔记
    related = d["related"]
    related_html = ""
    if week:
        rel_items = ""
        for n in week:
            rels = related.get(n["path"], [])
            if rels:
                rel_links = "、".join(
                    f'<a href="{LINK_PREFIX}{r["path"]}">{esc(r["title"])}</a>' for r in rels[:3]
                )
                rel_items += f'    <li><strong>{esc(n["title"])}</strong> → {rel_links}</li>\n'
        if rel_items:
            related_html = f'''  <section>
    <h2>相关笔记</h2>
    <ul>
{rel_items}    </ul>
  </section>

'''

    # 折线图
    monthly_chart = ""
    if d["monthly_trend"]:
        monthly_chart = f'''  <section>
    <h2>月度趋势</h2>
    <div class="chart-container">
      {line_chart_svg(d["monthly_trend"])}
    </div>
  </section>

'''

    weekly_chart = ""
    if d["weekly_trend"]:
        weekly_chart = f'''  <section>
    <h2>每周活跃度</h2>
    <div class="chart-container">
      {line_chart_svg(d["weekly_trend"])}
    </div>
  </section>

'''

    # GitHub 风格贡献图
    contrib_html = ""
    if d["contrib"]:
        max_count = max(c for _, _, c in d["contrib"]) if d["contrib"] else 0
        cells = ""
        for w, day, count in d["contrib"]:
            if count == 0:
                level = 0
            elif max_count <= 1:
                level = 1
            elif count <= max_count * 0.25:
                level = 1
            elif count <= max_count * 0.5:
                level = 2
            elif count <= max_count * 0.75:
                level = 3
            else:
                level = 4
            cells += f'      <div class="contrib-cell" data-level="{level}" title="周{w+1} 周{day+1}: {count} 篇"></div>\n'
        contrib_html = f'''  <section>
    <h2>贡献图</h2>
    <div class="contrib-graph">
{cells}    </div>
    <div class="contrib-legend">
      <span>少</span>
      <div class="contrib-cell" data-level="0"></div>
      <div class="contrib-cell" data-level="1"></div>
      <div class="contrib-cell" data-level="2"></div>
      <div class="contrib-cell" data-level="3"></div>
      <div class="contrib-cell" data-level="4"></div>
      <span>多</span>
    </div>
  </section>

'''

    # KPI 卡片
    total = len(d["notes"])
    week_count = len(week)
    open_count = len(d["open_notes"])
    tag_count = len(set(t for n in d["notes"] for t in n["tags"]))
    kpi_html = f'''  <section>
    <h2>概览</h2>
    <div class="kpi-grid">
      <div class="kpi-card"><div class="kpi-value">{total}</div><div class="kpi-label">总篇数</div></div>
      <div class="kpi-card"><div class="kpi-value">{week_count}</div><div class="kpi-label">上周新增</div></div>
      <div class="kpi-card"><div class="kpi-value">{open_count}</div><div class="kpi-label">待解决</div></div>
      <div class="kpi-card"><div class="kpi-value">{tag_count}</div><div class="kpi-label">标签数</div></div>
    </div>
  </section>

'''

    # 分类分布
    cat_dist = ""
    cats = Counter(n["category"] or "(未分类)" for n in d["notes"])
    if cats:
        top_cat_count = cats.most_common(1)[0][1]
        for cat, count in cats.most_common():
            pct = round(count / top_cat_count * 100)
            cat_dist += f'''    <div class="dist-bar">
      <span class="dist-label">{esc(cat)}</span>
      <div class="dist-track"><div class="dist-fill" style="width:{pct}%"></div></div>
      <span class="dist-count">{count}</span>
    </div>
'''
    cat_html = f'''  <section>
    <h2>分类分布</h2>
{cat_dist}  </section>

'''

    # 标签云
    tag_cloud = ""
    all_tags = [t for n in d["notes"] for t in n["tags"]]
    if all_tags:
        tag_counts = Counter(all_tags)
        max_tag = tag_counts.most_common(1)[0][1]
        tags_sorted = sorted(tag_counts.items(), key=lambda x: (-x[1], x[0]))
        for tag, count in tags_sorted:
            size = 0.75 + (count / max_tag) * 0.5
            tag_cloud += f'      <a href="#" style="font-size:{size:.2f}rem">{esc(tag)}</a>\n'
    tag_html = f'''  <section>
    <h2>标签云</h2>
    <div class="tag-cloud">
{tag_cloud}    </div>
  </section>

'''

    # 状态分布
    status_html = ""
    if total > 0:
        resolved = total - open_count
        res_pct = round(resolved / total * 100)
        open_pct = 100 - res_pct
        status_html = f'''  <section>
    <h2>状态分布</h2>
    <div class="status-bar">
      <div class="status-resolved" style="width:{res_pct}%"></div>
      <div class="status-open" style="width:{open_pct}%"></div>
    </div>
    <div class="status-labels">
      <span>✅ 已解决 {resolved} 篇（{res_pct}%）</span>
      <span>⬜ 待解决 {open_count} 篇（{open_pct}%）</span>
    </div>
  </section>

'''

    # 过期笔记提醒
    stale_html = ""
    if d["stale_notes"]:
        stale_items = ""
        for n, days in d["stale_notes"]:
            stale_items += f'    <li><span class="item-date">{n["date"]}</span><span class="item-title">{esc(n["title"])}</span><span class="item-cat">{esc(n["category"] or "—")}</span><span class="stale-days">{days} 天</span></li>\n'
        stale_html = f'''  <section>
    <h2>⚠️ 过期笔记（{len(d["stale_notes"])} 篇）</h2>
    <p class="meta">以下笔记待解决超过 30 天，建议优先处理或关闭：</p>
    <ul>
{stale_items}    </ul>
  </section>

'''

    # 标签趋势
    tag_trend_html = ""
    if d["tag_trends"]:
        trend_items = ""
        # 排序键必须完全确定：tag_trends 的键来自 set，迭代顺序随进程哈希种子变化，
        # 而「标签增减量」大量并列，仅靠增量的稳定排序会保留那个随机顺序，导致周报 HTML 不幂等。
        # 用标签名做次级键兜底。
        for tag, (prev, curr) in sorted(d["tag_trends"].items(), key=lambda x: (-(x[1][1] - x[1][0]), x[0])):
            diff = curr - prev
            if diff > 0:
                trend = f'<span class="trend-up">+{diff}</span>'
            elif diff < 0:
                trend = f'<span class="trend-down">{diff}</span>'
            else:
                trend = '<span class="trend-flat">0</span>'
            trend_items += f'    <li><span class="tag-name">{esc(tag)}</span><span class="trend-prev">{prev}</span><span class="trend-arrow">→</span><span class="trend-curr">{curr}</span><span class="trend-diff">{trend}</span></li>\n'
        tag_trend_html = f'''  <section>
    <h2>标签趋势（上周 vs 上上周）</h2>
    <ul class="tag-trend-list">
{trend_items}    </ul>
  </section>

'''

    # 知识缺口
    gap_html = ""
    if d["knowledge_gaps"]:
        gap_items = ""
        for cat, count in d["knowledge_gaps"]:
            gap_items += f'    <li><span class="gap-cat">{esc(cat)}</span><span class="gap-count">{count} 篇</span><span class="gap-hint">建议补充</span></li>\n'
        gap_html = f'''  <section>
    <h2>知识缺口</h2>
    <p class="meta">以下分类笔记数少于 3 篇，建议补充：</p>
    <ul>
{gap_items}    </ul>
  </section>

'''

    # 笔记质量评分
    quality_html = ""
    if d["quality_scores"]:
        quality_items = ""
        for n, score, reasons in d["quality_scores"][:5]:
            quality_items += f'    <li><span class="quality-score">{score}</span><span class="item-title">{esc(n["title"])}</span><span class="quality-reasons">{esc(", ".join(reasons))}</span></li>\n'
        quality_html = f'''  <section>
    <h2>笔记质量评分（Top 5）</h2>
    <ul>
{quality_items}    </ul>
  </section>

'''

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>知识库周报 · {wk_label}</title>
<style>
:root {{
  --bg: #ffffff;
  --fg: #1a1a2e;
  --muted: #6b7280;
  --border: #e5e7eb;
  --accent: #3b82f6;
  --accent-light: #eff6ff;
  --success: #10b981;
  --warning: #f59e0b;
  --radius: 8px;
  --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans SC", sans-serif;
  --mono: "SF Mono", "Fira Code", "Consolas", monospace;
}}
[data-theme="dark"] {{
  --bg: #1a1a2e;
  --fg: #e5e7eb;
  --muted: #9ca3af;
  --border: #374151;
  --accent: #60a5fa;
  --accent-light: #1e3a5f;
  --success: #34d399;
  --warning: #fbbf24;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: var(--font);
  color: var(--fg);
  background: var(--bg);
  line-height: 1.6;
  padding: 2rem 1rem;
}}
.container {{ max-width: 800px; margin: 0 auto; }}
header {{
  border-bottom: 2px solid var(--border);
  padding-bottom: 1.5rem;
  margin-bottom: 2rem;
}}
h1 {{ font-size: 1.75rem; font-weight: 700; margin-bottom: 0.5rem; }}
.header-row {{ display: flex; align-items: center; justify-content: space-between; }}
.theme-toggle {{
  background: none;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 0.375rem 0.75rem;
  font-size: 1.25rem;
  cursor: pointer;
  color: var(--fg);
}}
.theme-toggle:hover {{ background: var(--accent-light); }}
.meta {{ color: var(--muted); font-size: 0.875rem; }}
section {{
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1.5rem;
  margin-bottom: 1.5rem;
}}
h2 {{
  font-size: 1.125rem;
  font-weight: 600;
  margin-bottom: 1rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid var(--border);
}}
h3 {{ font-size: 1rem; font-weight: 600; margin: 0.75rem 0 0.5rem; }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ padding: 0.5rem 0.75rem; text-align: left; border-bottom: 1px solid var(--border); }}
th {{ font-weight: 600; color: var(--muted); font-size: 0.875rem; }}
td {{ font-size: 0.9375rem; }}
tr:last-child td {{ border-bottom: none; }}
.bar-row {{
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
}}
.bar-label {{ font-family: var(--mono); font-size: 0.8125rem; width: 6rem; flex-shrink: 0; }}
.bar-track {{
  flex: 1;
  height: 20px;
  background: var(--accent-light);
  border-radius: 4px;
  overflow: hidden;
}}
.bar-fill {{
  height: 100%;
  background: var(--accent);
  border-radius: 4px;
  transition: width 0.3s ease;
}}
.bar-count {{ font-family: var(--mono); font-size: 0.8125rem; width: 2rem; text-align: right; flex-shrink: 0; }}
ul {{ list-style: none; }}
li {{
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--border);
  font-size: 0.9375rem;
}}
li:last-child {{ border-bottom: none; }}
li.empty {{ color: var(--muted); font-style: italic; }}
.item-date {{ font-family: var(--mono); font-size: 0.8125rem; color: var(--muted); flex-shrink: 0; }}
.item-title {{ flex: 1; }}
.item-cat {{
  font-family: var(--mono);
  font-size: 0.75rem;
  background: var(--accent-light);
  color: var(--accent);
  padding: 0.125rem 0.5rem;
  border-radius: 4px;
  flex-shrink: 0;
}}
.item-status {{ flex-shrink: 0; }}
.placeholder {{
  color: var(--muted);
  font-style: italic;
  padding: 0.75rem;
  background: #f9fafb;
  border-radius: var(--radius);
  border: 1px dashed var(--border);
}}
footer {{
  text-align: center;
  color: var(--muted);
  font-size: 0.8125rem;
  margin-top: 2rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border);
}}
@media (max-width: 600px) {{
  body {{ padding: 1rem 0.5rem; }}
  li {{ flex-wrap: wrap; }}
  .item-cat {{ display: none; }}
}}
.heatmap {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(20px, 1fr));
  gap: 3px;
  margin-bottom: 0.75rem;
}}
.heat-cell {{
  aspect-ratio: 1;
  background: var(--accent);
  border-radius: 2px;
  min-width: 12px;
}}
.kpi-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 1rem;
  margin-bottom: 0;
}}
.kpi-card {{
  text-align: center;
  padding: 1rem;
  background: var(--accent-light);
  border-radius: var(--radius);
}}
.kpi-value {{ font-size: 2rem; font-weight: 700; color: var(--accent); }}
.kpi-label {{ font-size: 0.8125rem; color: var(--muted); margin-top: 0.25rem; }}
.tag-cloud {{
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
}}
.tag-cloud a {{
  color: var(--accent);
  text-decoration: none;
  padding: 0.125rem 0.5rem;
  border-radius: 4px;
  background: var(--accent-light);
}}
.tag-cloud a:hover {{ opacity: 0.8; }}
.dist-bar {{
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
}}
.dist-label {{ font-family: var(--mono); font-size: 0.8125rem; width: 10rem; flex-shrink: 0; }}
.dist-track {{ flex: 1; height: 16px; background: var(--accent-light); border-radius: 4px; overflow: hidden; }}
.dist-fill {{ height: 100%; background: var(--accent); border-radius: 4px; }}
.dist-count {{ font-family: var(--mono); font-size: 0.8125rem; width: 3rem; text-align: right; flex-shrink: 0; }}
.status-bar {{
  display: flex;
  height: 24px;
  border-radius: var(--radius);
  overflow: hidden;
  margin-bottom: 0.5rem;
}}
.status-resolved {{ background: var(--success); }}
.status-open {{ background: var(--warning); }}
.status-labels {{
  display: flex;
  justify-content: space-between;
  font-size: 0.8125rem;
  color: var(--muted);
}}
.chart-container {{
  position: relative;
  margin: 1rem 0;
}}
.chart-svg {{
  width: 100%;
  height: auto;
  display: block;
}}
.contrib-graph {{
  display: grid;
  grid-template-rows: repeat(7, 1fr);
  grid-auto-flow: column;
  gap: 3px;
  overflow-x: auto;
  padding-bottom: 0.5rem;
}}
.contrib-cell {{
  width: 14px;
  height: 14px;
  border-radius: 3px;
  background: #ebedf0;
  border: 1px solid #d1d5db;
}}
.contrib-cell[data-level="1"] {{ background: #9be9a8; border-color: #9be9a8; }}
.contrib-cell[data-level="2"] {{ background: #40c463; border-color: #40c463; }}
.contrib-cell[data-level="3"] {{ background: #30a14e; border-color: #30a14e; }}
.contrib-cell[data-level="4"] {{ background: #216e39; border-color: #216e39; }}
[data-theme="dark"] .contrib-cell {{ background: #161b22; border-color: #30363d; }}
[data-theme="dark"] .contrib-cell[data-level="1"] {{ background: #0e4429; border-color: #0e4429; }}
[data-theme="dark"] .contrib-cell[data-level="2"] {{ background: #006d32; border-color: #006d32; }}
[data-theme="dark"] .contrib-cell[data-level="3"] {{ background: #26a641; border-color: #26a641; }}
[data-theme="dark"] .contrib-cell[data-level="4"] {{ background: #39d353; border-color: #39d353; }}
.contrib-legend {{
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.75rem;
  color: var(--muted);
  margin-top: 0.5rem;
}}
.contrib-legend .contrib-cell {{
  width: 12px;
  height: 12px;
}}
.stale-days {{
  font-family: var(--mono);
  font-size: 0.75rem;
  color: var(--warning);
  flex-shrink: 0;
}}
.tag-trend-list li {{
  display: flex;
  align-items: center;
  gap: 0.5rem;
}}
.tag-name {{
  font-family: var(--mono);
  font-size: 0.8125rem;
  min-width: 6rem;
}}
.trend-prev, .trend-curr {{
  font-family: var(--mono);
  font-size: 0.8125rem;
  width: 2rem;
  text-align: center;
}}
.trend-arrow {{
  color: var(--muted);
}}
.trend-diff {{
  font-family: var(--mono);
  font-size: 0.8125rem;
  margin-left: 0.5rem;
}}
.trend-up {{ color: var(--success); }}
.trend-down {{ color: var(--warning); }}
.trend-flat {{ color: var(--muted); }}
.gap-cat {{
  font-family: var(--mono);
  font-size: 0.8125rem;
  min-width: 8rem;
}}
.gap-count {{
  font-family: var(--mono);
  font-size: 0.8125rem;
  color: var(--warning);
}}
.gap-hint {{
  font-size: 0.75rem;
  color: var(--muted);
  margin-left: auto;
}}
.quality-score {{
  font-family: var(--mono);
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--accent);
  width: 3rem;
  text-align: center;
  flex-shrink: 0;
}}
.quality-reasons {{
  font-size: 0.75rem;
  color: var(--muted);
  margin-left: auto;
}}
@media print {{
  body {{ padding: 0; }}
  section {{ break-inside: avoid; }}
}}
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="header-row">
      <h1>知识库周报 · {wk_label}</h1>
      <button class="theme-toggle" onclick="toggleTheme()" title="切换主题">🌙</button>
    </div>
    <p class="meta">{lw_start:%Y-%m-%d} ~ {lw_end:%Y-%m-%d} · 全库 {len(d["notes"])} 篇 · 生成于 {today}</p>
  </header>

{kpi_html}{cat_html}{tag_html}{status_html}{monthly_chart}{weekly_chart}{contrib_html}
  <section>
    <h2>时间窗口</h2>
    <table>
      <thead><tr><th>窗口</th><th>范围</th><th>篇数</th></tr></thead>
      <tbody>
        <tr><td><strong>上周</strong></td><td>{d["week_range"][0]:%m-%d} ~ {d["week_range"][1]:%m-%d}</td><td>{len(d["last_week_notes"])}</td></tr>
        <tr><td>本月</td><td>{d["month_range"][0]:%m-%d} ~ {d["month_range"][1]:%m-%d}</td><td>{len(d["month"])}</td></tr>
        <tr><td>本季</td><td>{d["quarter_range"][0]:%m-%d} ~ {d["quarter_range"][1]:%m-%d}</td><td>{len(d["quarter"])}</td></tr>
        <tr><td>本年</td><td>{d["year_range"][0]:%m-%d} ~ {d["year_range"][1]:%m-%d}</td><td>{len(d["year"])}</td></tr>
      </tbody>
    </table>
  </section>

  <section>
    <h2>上周每日分布</h2>
{daily_bars}  </section>

  <section>
    <h2>上周新增（{len(week)} 篇）</h2>
    <ul>
{week_items}    </ul>
  </section>

  <section>
    <h2>待解决（{len(d["open_notes"])} 篇）</h2>
    <ul>
{open_items}    </ul>
  </section>

  <section>
    <h2>数据观察</h2>
    <ul>
{obs_items}    </ul>
  </section>

  <section>
    <h2>AI 分析</h2>
{ai_html}  </section>

{heatmap_html}{related_html}{stale_html}{tag_trend_html}{gap_html}{quality_html}  <footer>
    由 <code>python3 scripts/report.py</code> 自动生成
  </footer>
</div>
<script>
  const saved = localStorage.getItem('theme');
  if (saved) document.documentElement.dataset.theme = saved;
  function toggleTheme() {{
    const next = document.documentElement.dataset.theme === 'dark' ? '' : 'dark';
    document.documentElement.dataset.theme = next;
    localStorage.setItem('theme', next);
  }}
</script>
</body>
</html>
'''


# ---------------------------------------------------------------- 主流程
def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="生成知识库周报")
    parser.add_argument("--print", action="store_true", help="同时打印到终端")
    args = parser.parse_args()

    today = date.today()
    d = gather(today)
    lw_start, _ = d["week_range"]
    wk_label = iso_week_label(lw_start)

    # 渲染
    md = render_markdown(d)
    html = render_html(d)

    # 写入文件
    REPORTS_DIR.mkdir(exist_ok=True)
    md_path = REPORTS_DIR / f"{wk_label}.md"
    html_path = REPORTS_DIR / f"{wk_label}.html"
    index_path = REPORTS_DIR / "index.html"

    try:
        md_path.write_text(md, encoding="utf-8")
        html_path.write_text(html, encoding="utf-8")
        index_path.write_text(html, encoding="utf-8")
    except OSError as e:
        print(f"写入文件失败: {e}", file=sys.stderr)
        return 1

    # 导出 JSON
    import json
    export_data = {
        "week": wk_label,
        "generated": today.isoformat(),
        "total_notes": len(d["notes"]),
        "last_week_notes": len(d["last_week_notes"]),
        "open_notes": len(d["open_notes"]),
        "stale_notes": len(d["stale_notes"]),
        "knowledge_gaps": len(d["knowledge_gaps"]),
        "notes": [{"title": n["title"], "date": n["date"], "category": n["category"], "tags": n["tags"], "status": n["status"], "path": n["path"]} for n in d["notes"]],
    }
    json_path = REPORTS_DIR / f"{wk_label}.json"
    try:
        json_path.write_text(json.dumps(export_data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        print(f"导出 JSON 失败: {e}", file=sys.stderr)

    # 导出 CSV
    csv_path = REPORTS_DIR / f"{wk_label}.csv"
    try:
        import csv
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["title", "date", "category", "tags", "status", "path"])
            for n in d["notes"]:
                writer.writerow([n["title"], n["date"], n["category"], "|".join(n["tags"]), n["status"], n["path"]])
    except OSError as e:
        print(f"导出 CSV 失败: {e}", file=sys.stderr)

    print(f"已生成 {md_path.relative_to(ROOT)}")
    print(f"已生成 {html_path.relative_to(ROOT)}")
    print(f"已更新 {index_path.relative_to(ROOT)}")
    print(f"已导出 {json_path.relative_to(ROOT)}")
    print(f"已导出 {csv_path.relative_to(ROOT)}")

    if args.print:
        print("\n" + md)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
