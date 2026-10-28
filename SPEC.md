# 知识库规范（轻量版）

一句话：**提问 → 归档成一篇笔记 → 下次问同样的问题直接从笔记里答。**

索引页（`INDEX.md` / `TAGS.md` / `search.html` 等）是让笔记能被找回来的副产品，不是目的。所以这套库只有一件事是核心：**问题落成文档的路径**和**再次提问时的检索路径**。

换机器时照本文做即可；已经建好的，可以拿「六、验收」当检查清单。

---

## 一、最小文件集

```
knowledge-base/
├── scripts/build_index.py            索引生成，唯一脚本
├── .claude/settings.json             注册 Stop Hook
├── .claude/hooks/rebuild-index.sh    会话结束重建索引
├── .claude/hooks/archive-pending.sh  会话结束检查待归档暂存区
├── .claude/pending_archive.md        待归档暂存区（含格式说明）
├── TEMPLATE.md                       新笔记模板
├── CLAUDE.md                         给 Claude Code 的行为约定
└── README.md                         给人看的说明
```

**不拷**：`INDEX.md` / `CATEGORIES.md` / `TAGS.md` / `TIMELINE.md` / `search.html` / `feed.xml` / `related.json` / `backlinks.json`（首次运行就生成）、`scripts/__pycache__/`、`.claude/settings.local.json`（本机权限，含绝对路径）。

**可选**：`scripts/report.py`（周报）与 `.gitattributes`（CSV 换行）。不做周报就整个不拷，与核心流程无关。

**新增任何仓库根的手写文件（如 `CHANGELOG.md`），必须加进 `build_index.py` 顶部的 `HANDWRITTEN`**，否则会被当成没有 frontmatter 的笔记收进索引。

---

## 二、笔记格式

### 文件位置与命名

- 放进分类目录，命名 `YYYY-MM-DD-简短标题.md`（日期前缀保证同目录内按时间排序）。
- **目录路径 == `category` 值**：`tech/linux/x.md` 的 `category` 就是 `tech/linux`。不一致会标 ⚠️，但仍按 frontmatter 归类。
- 分类默认两级（`tech/linux`、`ops/tools`）。三级只在「长期折腾 + 中间层有明确归类意义」时用，如 `tech/proxy/clash`。新建目录自动生效，不用改代码，但要同步 `README.md` 的分类表。
- **别用 `README.md` / `TEMPLATE.md` / `ABOUT.md` / `CLAUDE.md` 当笔记名**——这四个按文件名全局跳过，同名笔记会静默不进索引，不报错。

### frontmatter

```yaml
---
title: 磁盘满了怎么排查          # 必填
date: 2026-09-23                # 必填
category: tech/linux            # 必填，单值，层级用 / 分隔
tags: [磁盘, 排查]               # 行内数组
status: open                    # 必填，open 未解决 / resolved 有结论
---
```

可选字段：`top` 置顶、`hide` 隐藏、`password` 加密。

**解析器只认两种写法：`key: value` 和 `key: [a, b]`。块状列表会被静默丢弃**——`tags:` 下面换行写 `- 磁盘`，标签全空且不报 ⚠️，这是全套规范里最容易踩的坑。

### 正文骨架

```markdown
## 问题        原始疑问 + 当时上下文（什么场景、试过什么）
## 结论        一句话答案；没搞清楚写「暂无」并保持 status: open
## 详细分析    推理、验证、命令、踩过的坑；内部用 ### 编号小节
## 参考资料    外部链接
## 一句话总结  固定收尾，一到两句
```

**末尾的「一句话总结」固定保留。** 它和开头的「结论」不是重复：结论是给赶时间的人的直接答案，收口是讲完全部细节之后的回扣——这份东西讲清了什么、边界在哪。一两句为上限，别照抄结论。

排错类在「详细分析」里按 **现象 → 排查步骤 → 修复命令 → 验证方案** 四段走，回看时能直接跳到需要的那段。

---

## 三、写：一个问题怎么变成笔记

**先查重，再决定新开还是补充：**

```bash
grep -ri 关键词 . --include='*.md' | grep -v '/\.git/'
```

或者翻 `TAGS.md` / `INDEX.md`。

判断是否同一主题用**读者视角**：*有人搜到这个词时，想要的是不是同一份答案？* 是 → 补进原笔记；不是 → 新开一篇。

同一主题**不设篇幅上限**，写到一千行也不拆——拆开之后每个文件都只讲一半，索引里两篇都沾边，反而更难找。补充时按层级选：能安一个 `###` 就用 `###`，侧面已有独立分量（完整配置清单、一整套实测）才升成 `##`。

**归档还是不归档，三选一，每轮重新判断**（一次会话连问五件事，每件独立判断）：

| 情况 | 动作 |
| --- | --- |
| 纯技术知识点（命令、报错、原理、配置） | **直接写**，不问 |
| 涉及用户自身环境/账号/拓扑、工作内容、拿不准值不值得留、拿不准归哪个分类 | **先问一句**再写 |
| 想写但本轮做不完（要先确认分类、先查重） | **追加到 `.claude/pending_archive.md`** |

暂存区不是可选项：**只留在对话里等于没写**，对话结束就没了。Hook 会在会话结束时把非空暂存区顶回对话。

---

## 四、读：同一个问题被问第二遍时

按这个顺序找，命中就**直接给答案 + 指路文件**，不要重新推导一遍：

| 顺序 | 方法 | 适用 |
| --- | --- | --- |
| 1 | `grep -ri 关键词 . --include='*.md'` | 记得关键字 |
| 2 | 翻 `TAGS.md` | 记得大概方向 |
| 3 | 翻 `INDEX.md` 待解决区 | 上次没搞定的 |
| 4 | 浏览器打开 `search.html` 全文搜 | 关键词不确定 |

命中之后：

- **直接引用已有结论**，补一句「详见 `tech/linux/xxx.md`」。
- 如果新问题多出一个侧面，按第三节补进原笔记，**不要新开一篇**。
- 只有结论变了才改原文——旧的错误结论留在库里比没有更糟。

「同一个问题」不看字面，看意图：`curl 怎么发 POST` 和 `curl 传 JSON` 是同一份答案；`curl 常用参数` 和 `HTTP 报文结构` 不是。

---

## 五、写法

- **标题要能概括住内容。** `title` 和各级小节是索引/搜索/订阅源里唯一露出来的东西，读者全靠它判断「这篇有没有我要的」。写 `### 三、最小可用：一服务端一客户端`，不写 `### 三、最小可用`；不用「详解」「说明」「原理」「浅谈」。
- **写法中立，不写「我在这台机器上怎么样」。** 笔记是给半年后在另一台机器上排查的自己看的。不出现「本机是 Debian 13」「本机未安装 X」「未实测，仅供参考」。有环境差异的**按条件分列**：

  - ✅ 「Debian 系把脚本放 `/etc/rc.local.d/`；RHEL 系放 `/etc/rc.local`。」
  - ❌ 「本机是 Debian 系，所以 RHEL 的写法未能验证。」

  命令该给就给，用条件句提醒而不是免责声明：「在有 systemd 的系统上，`nc -l` 要加 `-p`」。
- **相对链接写准层级。** 同目录直接 `[x](y.md)`；跨分类 `[x](../../linux/y.md)`。多写一层 `../` **不会报错**，只是反向链接静默为空。
- **讲完收口。** 回答完一个问题、写完一篇笔记，最后用一句话概括，最多两句。不要「综上所述」这类空起头，直接把话说出来。
- **生成物不手改。** 见第一节的文件清单，下次运行整个覆盖。

---

## 六、验收

```bash
# ① 跑通，且确认没有笔记被落下
python3 scripts/build_index.py; echo "exit=$?"

# ② 幂等：重复跑逐字节一致
md5sum INDEX.md CATEGORIES.md TAGS.md TIMELINE.md search.html feed.xml \
       related.json backlinks.json > /tmp/idx.md5
python3 scripts/build_index.py && md5sum -c /tmp/idx.md5

# ③ 必填字段齐、category 与目录一致
python3 - <<'EOF'
import sys; sys.path.insert(0, 'scripts')
import build_index as b
notes = b.collect_notes()
print(f"{len(notes)} 篇笔记")
print("字段缺失:", [(n['path'], n['missing']) for n in notes if n['missing']] or "无")
print("目录不符:", [(n['path'], n['category']) for n in notes if n['mismatch']] or "无")
EOF

# ④ Hook 三态：暂存区空 → 0；有内容 → 2；标记文件存在 → 0
bash .claude/hooks/archive-pending.sh; echo "exit=$?"
```

---

## 七、clone 之后要改的一处

| 位置 | 改什么 |
| --- | --- |
| `README.md` 的分类表 | 按实际 `mkdir` 了哪些分类填写 |

建好分类目录后同步改这张表——它和实际目录是两份要人工对齐的东西。

另：**Stop Hook 只在会话启动时该文件已存在的情况下加载。** 第一次打开会话说索引没自动更新，就打开一次 `/hooks` 菜单或重启会话。
