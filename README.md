# 知识库模板

一个可以直接 clone 使用的 Markdown 技术知识库：**零依赖、纯 Python 标准库、按 frontmatter 自动生成索引**。

它解决两件事：

1. **问答沉淀**——问过的技术问题自动整理成一篇笔记，不再散落在聊天记录里。
2. **问第二遍直接答**——同样的问题再问，先查库，命中就直接给答案和文件路径，没有再补充。

## 把仓库丢给 AI

把仓库克隆到新机器，然后对那个机器上的 AI 说一句「按 AGENTS.md 干活」就够了：

- **[AGENTS.md](AGENTS.md)** —— 给所有 AI 的入口：查库顺序、写笔记规则、什么该问、什么不能做
- **[CLAUDE.md](CLAUDE.md)** —— Claude Code 的行为约定，里面是同一套规则的完整版
- **[SPEC.md](SPEC.md)** —— 这套库的规范，换机器重建照它做
- **[VERIFY.md](VERIFY.md)** —— 装完后丢给 AI 的验收提示词，逐项自检并给出结论

Claude Code 会自动读 `CLAUDE.md` 并加载 `.claude/` 下的 Hook（会话结束自动重建索引）。其他工具读 `AGENTS.md`，索引需要手动重建。

## 快速开始

```bash
git clone https://github.com/gyc0109/knowledge-base-template.git ~/knowledge-base
cd ~/knowledge-base

python3 scripts/build_index.py     # 生成索引，无输出即成功
```

打开 `INDEX.md` 开始。**没有依赖要装，没有数据库，不联网**，有 `python3` 就能跑。

> Windows 上通常没有 `python3` 这个名字，用 `py -3 scripts/build_index.py` 代替；`.claude/hooks/` 里的 Hook 会自动探测 `python3 / python / py -3`，不用改。
> 装完想确认一切正常：把 [VERIFY.md](VERIFY.md) 第一节整段丢给 AI 跑一遍。

写第一篇笔记：

```bash
cp TEMPLATE.md tech/linux/2026-10-28-磁盘满了怎么排查.md
rm tech/linux/2026-01-01-示例笔记-这个文件演示笔记格式.md   # 示例用完删掉
```

## 开箱有什么

```
knowledge-base/
├── AGENTS.md                    AI 入口（任何工具都读这个）
├── CLAUDE.md                    Claude Code 行为约定
├── SPEC.md                      这套库的规范
├── TEMPLATE.md                  新笔记模板
├── ABOUT.md                     这个库为什么这么组织
├── scripts/build_index.py       索引生成，唯一脚本
├── .claude/settings.json        注册两个 Stop Hook
├── .claude/hooks/               会话结束重建索引 / 检查待归档暂存区
├── .claude/pending_archive.md   待归档暂存区
└── tech/ ops/ misc/             分类目录（随便改）
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

## 自定义

- 换分类：直接 `mkdir tech/rust`，再同步改 README 的分类表（自动发现，不用改代码）
- 换样式：渲染逻辑都在 `scripts/build_index.py` 里，纯标准库
- 不要往核心流程里加报表类功能（周报、统计看板）——回顾用 `git log` 就够了

## 许可

未附带许可证文件，按需自行添加。
