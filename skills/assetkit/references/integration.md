# 安装、项目接入与存量迁移

Skill 本体和项目状态分开：安装目录放 SKILL.md、手册和脚本；目标项目根目录存 `.assets/`。
全局安装尤其必须显式指定项目根目录，不得把不同项目的记录混进全局技能目录。

## 首选：skills CLI 安装

在目标项目运行：

```bash
npx skills add chenziyang110/AssetKit --skill assetkit
# 指定客户端可加 --agent codex 或 --agent claude-code；非交互加 --yes
# 只发现：npx skills add chenziyang110/AssetKit --list
```

默认链接安装、`--copy`、`--global` 都可用。不要在这些安装之后调用旧 `install.py` 复制自身。
安装不会自动运行项目初始化或修改项目规则，也不表示已经被 skills.sh 排名收录。
确认客户端确实能发现 assetkit；客户端激活行为不由 CLI 安装测试证明。

## 项目初始化：只写目标项目

确认用户授权接入、项目根目录以及实际客户端入口后，从已安装的 Skill 运行：

```bash
python <SKILL_DIR>/scripts/bootstrap.py --project <PROJECT_ROOT> --entry AGENTS.md
# Claude Code 使用 --entry CLAUDE.md；两者都使用则 --entry both
# 仅账本和 .gitignore，不添加项目指令：--entry none
# 只检查计划：加 --dry-run
```

`SKILL_DIR` 是当前 SKILL.md 的真实目录；不依赖当前工作目录或并不存在的客户端环境变量。
项目级常见入口为 `.agents/skills/assetkit` 或 `.claude/skills/assetkit`，实际以客户端提供路径为准。
全局安装允许从项目外读取 Skill，但 `.assets/` 永远写入指定项目；全局入口使用真实绝对路径，换机器重新接入。

Bootstrap 不复制或改写 Skill，支持从符号链接启动。它会初始化 `.assets/`，
在所选 AGENTS.md / CLAUDE.md 及 .gitignore 中合并带标记的最小规则，保留其他内容。
已有项目 ID 和卡片不重置。错误或重复的入口标记先报错，不盲目重写。
仍拒绝向符号链接形式的项目元数据和入口文件写入，防止重定向；只适用于可信本地工作区，不提供竞态隔离。
按文件原子写入，不是整个项目的事务；失败后以实际文件和错误回执为准。

纯查找任务遇到尚无账本时，说明未初始化，不擅自修改项目；获准接入或正式保留资产时才初始化。
提交 `.assets/config.json` 和 records；不提交 cache、.lock 或临时目录。

## 可选：旧式离线复制安装

已下载包、没有 Node.js 或网络时可以运行：

```bash
python <已下载SKILL_DIR>/scripts/install.py --project <PROJECT_ROOT> --client codex --bootstrap
# Claude Code 使用 --client claude；预览加 --dry-run
```

该工具只管理普通目录的复制，拒绝符号链接目的地；与 skills CLI 管理的安装不混用。
遇到已有不同文件会中止，不静默覆盖。新用户优先走上面的标准 CLI。
升级安装目录前备份和审查自定义内容，不删除 `.assets/records/`。

## 存量整理

先用程序枚举获准目录，排除依赖、缓存、构建产物。分批选取高复用资源，再阅读必要内容写卡片。
按可复用单元组织组合资源，不是每个分片各记一条。使用 in-place，不自动搬动 docs/public 等依赖路径。
待确认信息保持 unknown；不要为了完成整理伪造用途和审批。

## 检查与恢复

项目提交检查可运行 `python <SKILL_DIR>/scripts/assetctl.py --root <PROJECT_ROOT> validate --hashes --max-issues 20`。
这只检查卡片与 managed_roots。要发现全仓乱放资源，还需审查 Git 新增文件与允许路径；当前 CLI 不自带该门禁。
索引损坏用 reindex；卡片与业务文件从版本控制/备份恢复，不能把缓存当唯一备份。
多机高并发、对象存储、LFS/DVC、自动媒体预览和向量索引需要另行集成，当前版本未实现。
