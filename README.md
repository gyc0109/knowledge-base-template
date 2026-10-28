# 知识库模板

一个可以直接 clone 使用的 Markdown 知识库骨架：**零依赖、纯 Python 标准库、按 frontmatter 自动生成索引**。

用途是把日常的技术问答沉淀成可检索的笔记——一个问题一篇，分类 + 标签 + 时间线三个维度都能找回来。配合 Claude Code 使用时，问答会被自动归档、同样的问题会被直接从库里答。

## 快速开始

```bash
git clone https://github.com/gyc0109/knowledge-base-template.git ~/knowledge-base
cd ~/knowledge-base

python3 scripts/build_index.py     # 生成索引，无输出即成功
```

然后打开 `INDEX.md` 开始写。**没有依赖要装，没有数据库，不联网**，有 `python3` 就能跑。

第一次写笔记：复制 `TEMPLATE.md` 到分类目录，改个名。

```bash
cp TEMPLATE.md tech/linux/2026-10-28-磁盘满了怎么排查.md
```

## 开箱有什么

```
knowledge-base/
├── scripts/build_index.py      索引生成，唯一必需脚本
├── scripts/report.py           周报（可选，不用可以删）
├── .claude/                    接入 Claude Code 的配置与 Hook
│   ├── settings.json           注册两个 Stop Hook
│   ├── hooks/rebuild-index.sh  会话结束重建索引
│   ├── hooks/archive-pending.sh 会话结束检查待归档暂存区
│   └── pending_archive.md      待归档暂存区
├── CLAUDE.md                   给 Claude Code 的行为约定
├── SPEC.md                     这套库的规范（换机器重建照它做）
├── TEMPLATE.md                 新笔记模板
├── ABOUT.md                    这个库为什么这么组织
└── tech/ ops/ misc/            分类目录（随便改）
```

`INDEX.md` / `CATEGORIES.md` / `TAGS.md` / `TIMELINE.md` / `search.html` / `feed.xml` / `related.json` / `backlinks.json` 都是**自动生成**的，不要手改，下次运行整个覆盖。

## 目录与分类

分类就是目录路径，默认两级（`tech/linux`、`ops/tools`）。笔记的 `category` 字段要和所在目录一致：

```yaml
---
title: 磁盘满了怎么排查
date: 2026-10-28
category: tech/linux
tags: [磁盘, 排查]
status: resolved
---
```

必填 `title` / `date` / `category` / `status`。完整规则见 `SPEC.md`，最要紧的一条：

> **frontmatter 只认 `key: value` 和 `key: [a, b]` 两种写法**，块状列表（`tags:` 下面换行写 `- 磁盘`）会被**静默丢弃**，标签为空且不报错。

## 可选：周报

`scripts/report.py` 按周统计新增笔记、待解决项和标签趋势，产物落在 `reports/`。不需要就整个删掉，不影响索引。

## 自定义

- 换分类：直接 `mkdir tech/rust`，并同步改 `README.md` 的分类表（自动发现，不用改代码）
- 换样式：所有渲染逻辑都在 `scripts/build_index.py` 顶部几个函数里
- 已有 Claude Code：`.claude/settings.json` 里的 Hook 开箱即用，会话结束自动重建索引

## 许可

未附带许可证文件，按需自行添加。
