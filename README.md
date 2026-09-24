# AssetKit

**让 Agent 在创建资源前想起复用，在交付资源后完成登记。**

AssetKit 是一个可安装的 Agent Skill，把项目资产管理变成固定工作流：
先检索 → 判断可复用性 → 规范存放 → 增量登记/更新 → 校验。
适用于文档、图片、视频、音频、3D/机器学习模型、数据集、设计稿和模板。

## 安装：使用 skills.sh 的官方 CLI

在**目标项目根目录**执行，不需要先 clone AssetKit，也不需要运行我们的复制安装器：

```bash
npx skills add chenziyang110/AssetKit --skill assetkit
```

按交互提示选择 Agent。需要明确指定客户端时：

```bash
# Codex
npx skills add chenziyang110/AssetKit --skill assetkit --agent codex --yes

# Claude Code
npx skills add chenziyang110/AssetKit --skill assetkit --agent claude-code --yes

# 同时安装给两个客户端
npx skills add chenziyang110/AssetKit --skill assetkit --agent codex claude-code --yes

# 只发现、不安装：应该找到一个 assetkit
npx skills add chenziyang110/AssetKit --list
```

CLI 由 skills.sh / vercel-labs 维护，通过 npm 的 `skills` 包运行；AssetKit 是 GitHub 源仓库，不是另一个 npm 包。
安装需要 Node.js、Git 与网络；安装后的资产工具需要 Python 3.10+，只用标准库，不联网。
默认链接安装和 `--copy` 均支持，不再要求 `--copy`。

### 首次在项目中使用

**安装 Skill**和**初始化项目账本**是两个独立步骤；`skills add` 不会自动执行项目初始化脚本。
安装后可以直接让 Agent 执行：

> 使用 assetkit 接入当前项目。先读取接入手册，在目标项目运行 bootstrap，合并实际客户端使用的项目入口；保留现有规则和资源路径，不批量入库。

也可以手动执行一次：

```bash
# Codex 项目
python .agents/skills/assetkit/scripts/bootstrap.py --project . --entry AGENTS.md

# Claude Code 项目
python .claude/skills/assetkit/scripts/bootstrap.py --project . --entry CLAUDE.md

# 同时使用两个客户端时，选 --entry both；预览则添加 --dry-run
```

`bootstrap.py` 不复制、不升级、不修改已安装 Skill；它只初始化目标项目的 `.assets/`，
向选定的 `AGENTS.md` / `CLAUDE.md` 和 `.gitignore` 合并带标记的规则，保留其他内容。
重复执行保留项目 ID、已有卡片和业务文件。初始化支持读取已安装 Skill 的符号链接，
但仍拒绝把项目账本或规则写入符号链接目标。文件级原子替换不等于整个项目的事务。

### 全局安装与更新

```bash
npx skills add chenziyang110/AssetKit --skill assetkit --agent codex --global --yes
npx skills update
```

全局安装的 `SKILL_DIR` 位于客户端全局目录。每个项目分别运行
`python <实际SKILL_DIR>/scripts/bootstrap.py --project <实际项目根目录> --entry AGENTS.md`。
全局初始化入口记录真实安装路径；换机器需重新 bootstrap，不应直接沿用其他机器的绝对路径。
Skill 更新不把项目 `.assets/records/` 当成安装内容；升级前仍应备份自定义 Skill 文件。

旧的 `scripts/install.py` 保留用于已下载包的离线复制安装，不再是主安装方式；
**不要在 skills CLI 的符号链接安装后运行旧复制安装器**。详见 [接入手册](skills/assetkit/references/integration.md)。

## 给 Agent 的调用

在已接入的项目中直接说：

> 使用 assetkit。先检索项目已有的首页主视觉、产品介绍和模型，能复用就复用；本次新建且需要保留的资源按规范存放并增量登记，最后只报告相关资产 ID 和校验结果。

首次整理存量资源：

> 使用 assetkit 整理当前项目的可复用资源。先小批量盘点高频资产，保持现有文件路径不变；未知来源和许可标为 candidate，不要把全部账本读入上下文，也不要自动重命名整个项目。

SKILL.md 的 description 负责匹配任务，项目入口负责提醒。宿主仍可能漏触发；Skill 本身不是强制执行或权限边界。

## 结构与数据归属

```text
AssetKit/                           # 这个仓库：分发 Skill
├── .claude-plugin/marketplace.json # 可选插件分组，参考 Anthropic
├── skills/assetkit/
│   ├── SKILL.md                    # 短入口和任务路由
│   ├── references/                 # 6 个按需手册
│   ├── scripts/assetctl.py          # 增量账本 CLI
│   ├── scripts/bootstrap.py        # 安装后初始化项目；不复制 Skill
│   ├── scripts/install.py          # 可选的旧式离线复制安装器
│   ├── assets/                     # 卡片 schema、请求示例、入口模板
│   └── agents/openai.yaml          # 可选 UI 元信息
├── docs/distribution.md            # 分发结构与上游参考
├── tools/smoke_skills_cli.py        # 真实 skills CLI 安装验收
└── tests/

目标项目/
├── .agents/skills/assetkit/         # 或 .claude/skills/assetkit/
├── .assets/config.json             # 项目 ID 和受管目录配置，提交 Git
├── .assets/records/<id>.json        # 一资产版本一卡片，元数据事实源
├── .assets/cache/catalog.sqlite    # 可重建索引，不提交 Git
├── assets/                         # 新建正式业务资源
└── .work/<task-id>/                 # 临时产物，不提交 Git
```

既有 docs/public/src/assets 等可以原位登记。Skill 自带的 assets/ 只放模板，不是项目资源仓库。
每次新增只写一张卡片；每次修改只替换目标卡片中的指定顶层字段。索引可重建，不维护第二份可手改的总表。

## CLI

以下在已经安装的 Codex 项目根目录运行；Claude Code 将脚本路径改为 `.claude/skills/assetkit/scripts/assetctl.py`。

```bash
# 检索默认只返回 ready；候选资产加 --status candidate
python .agents/skills/assetkit/scripts/assetctl.py --root . search "首页" --type image --limit 5

# 读取少量字段，用工具返回的真实 ID 替换 <ID>
python .agents/skills/assetkit/scripts/assetctl.py --root . show <ID> --fields id,revision,summary,use_when,restrictions,files,rights

# 文件必须已在正式位置；request.json 只包含本次登记请求
python .agents/skills/assetkit/scripts/assetctl.py --root . add --manifest request.json --request-key task-018.hero.v1

# patch.json 例如 {"tags":["首页","hero"]}；用实际 revision 替换 1
python .agents/skills/assetkit/scripts/assetctl.py --root . patch <ID> --expect-revision 1 --patch-file patch.json

python .agents/skills/assetkit/scripts/assetctl.py --root . validate --hashes --max-issues 20
```

完整参数及错误处理见 [CLI 契约](skills/assetkit/references/cli.md)。
示例请求见 [登记模板](skills/assetkit/assets/register-document.request.json)；示例内容不是实际业务资产。

`request-key` 防重复登记；`revision` 防止覆盖并发修改。snapshot 内容改动必须新版本；live 修改后 refresh，撤销旧审核。
“增量”指不把全库读入模型上下文：程序仍会检查卡片 stat；搜索为中英文子串匹配，不是语义检索，也不是 O(1) 全链路操作。

## 验证与边界

```bash
python -m unittest discover -s tests -v
```

测试涵盖账本读写、幂等、冲突、检索、路径、哈希、live 刷新、并发登记和 Skill 安装。
CI 覆盖 Linux/Windows 与 Python 3.10/3.13 的单元测试；另在 Ubuntu + Node.js 22 中运行真正的 `skills@latest`。
安装验收覆盖仓库发现、项目默认链接/复制、全局安装、初始化、登记、中文检索和哈希校验；
main push 还会测试公开的 `chenziyang110/AssetKit` 源。日志输出实际 CLI 版本；测试关闭遥测，不制造安装排名。
具体结果以对应提交的 Actions 运行记录为准，不把配置存在当成测试通过。

当前没有：自动媒体预览/转录、向量搜索、对象存储连接、真实审批认证、分布式锁、自动迁移/删除和全仓引用检查。
只适用于可信本地工作区。validate 默认只检查已登记卡片和 assets 受管目录；不能证明全仓没有遗漏资源。
本仓库 CI 测试 Skill 自身，不会自动给目标项目安装 CI。需要强制门禁时接入目标项目的提交/CI 流程。

## 规范参考

- [Anthropic 的技能仓库结构](https://github.com/anthropics/skills)
- [skills.sh 安装与收录说明](https://skills.sh/docs/faq)
- [本仓库的分发设计](docs/distribution.md)
- [Agent Skills 格式与渐进披露](https://agentskills.io/specification)
- [Codex Skills 官方说明](https://developers.openai.com/codex/skills/)
- [Skills CLI 官方仓库：安装选项与发现路径](https://github.com/vercel-labs/skills)

版本：0.3.0。沿用原资产方案的 schema_version 1。许可证尚未指定。
