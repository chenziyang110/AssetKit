# 安装、项目接入与存量迁移

Skill 本体和项目状态分开：安装目录放 SKILL.md、手册和脚本；目标项目根目录存 `.assets/`。
全局安装尤其必须显式指定 `--root`，不得把不同项目的记录混进全局技能目录。

## 内置安装器

从已下载的 Skill 目录运行：

```bash
python <SKILL_DIR>/scripts/install.py --project <PROJECT_ROOT> --client codex --bootstrap
# Claude Code 使用 --client claude
```

codex 目标为 `.agents/skills/assetkit`；claude 目标为 `.claude/skills/assetkit`。
不加 bootstrap 时只复制 Skill；加上后初始化账本，并在 AGENTS.md 或 CLAUDE.md 及 .gitignore 合并带标记的资产片段。
其他规则保留。`--dry-run` 仅输出计划。相同内容重复安装不重复追加；不同内容的现有 Skill 文件会导致中止，
不会静默覆盖。升级前自行备份并审查旧 Skill，仅替换安装目录，不删除 `.assets/records/`。
安装按文件写入，不是整个项目的事务；执行失败后以错误信息和实际文件为准。

安装器拒绝符号链接目标，避免写到错误项目。外部安装器建立的链接可直接用于运行 CLI；
使用本安装器前改用经过确认的普通目录安装，例如外部 CLI 的 `--copy` 模式。

## 手工接入或已由其他工具安装

在目标项目运行 `python <SKILL_DIR>/scripts/assetctl.py --root <PROJECT_ROOT> init`。
将 `assets/project-entry.md` 中的占位符替换为真实 Skill 路径，再合并进客户端实际加载的项目指令；
将 `assets/gitignore-snippet.txt` 合并进 .gitignore。不要覆盖既有文件。
提交 `.assets/config.json` 和 records；不提交 cache、.lock 或临时工作目录。
确认客户端能够发现 assetkit；名称匹配并不保证每次隐式触发，关键项目规则仍需常驻入口。

给 Agent 的首次调用：

> 使用 assetkit 接入当前项目。先检查已有指令和账本，再补充最小入口；已有文件原位登记，不批量重命名，未知来源保留 candidate。不要把所有卡片读入上下文。

## 存量整理

先用程序枚举获准目录，排除依赖、缓存、构建产物。分批选取高复用资源，再阅读必要内容写卡片。
按可复用单元组织组合资源，不是每个分片各记一条。使用 in-place，不自动搬动 docs/public 等依赖路径。
待确认信息保持 unknown；不要为了“完成整理”伪造用途和审批。

## 检查与恢复

项目提交检查可运行 `python <SKILL_DIR>/scripts/assetctl.py --root . validate --hashes --max-issues 20`。
这只检查卡片与 managed_roots。要发现全仓乱放资源，还需审查 Git 新增文件与允许路径；当前 CLI 不自带该门禁。
索引损坏用 reindex；卡片与业务文件从版本控制/备份恢复，不能把缓存当唯一备份。
多机高并发、对象存储、LFS/DVC、自动媒体预览和向量索引需要另行集成，当前版本未实现。
