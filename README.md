# AssetKit

**让 Agent 在创建资源前想起复用，在交付资源后完成登记。**

AssetKit 是一个可安装的 Agent Skill，把项目资产管理变成固定工作流：
先检索 → 判断可复用性 → 规范存放 → 增量登记/更新 → 校验。
适用于文档、图片、视频、音频、3D/机器学习模型、数据集、设计稿和模板。

## 安装

运行环境：Python 3.10+，仅标准库；账本操作不联网。安装器提供 Codex 和 Claude Code 项目级路径。
这是命令行 Skill，需要客户端具有文件访问和脚本执行能力；不是单纯上传一份提示词就拥有数据库服务。

### 方式一：内置 Python 安装器

```bash
git clone https://github.com/chenziyang110/AssetKit.git

# 将 /path/to/project 替换为实际且已存在的目标项目根目录
python AssetKit/skills/assetkit/scripts/install.py \
  --project /path/to/project --client codex --bootstrap

# Claude Code 改用 --client claude
```

`--bootstrap` 会初始化项目账本，并向现有 AGENTS.md / CLAUDE.md 和 .gitignore 合并带标记的最小规则，保留其他内容。
不带它则只安装 Skill。添加 `--dry-run` 可预览且不写入。重复安装相同文件不会重复追加规则；
遇到不同内容的旧 Skill 文件时停止，不静默覆盖。需要升级时先备份审查旧 Skill，只替换安装目录，不删项目账本。

| 客户端 | Skill 安装位置 | 常驻入口 |
|---|---|---|
| Codex | `.agents/skills/assetkit/` | `AGENTS.md` |
| Claude Code | `.claude/skills/assetkit/` | `CLAUDE.md` |

### 方式二：Skills CLI

仓库采用 `skills/<name>/SKILL.md` 发现结构，可用外部 Skills CLI 安装：

```bash
npx skills add chenziyang110/AssetKit --skill assetkit --agent codex --copy
# 或 --agent claude-code
```

这一步安装 Skill，不初始化项目账本。以 Codex 为例，再在目标项目根目录运行：

```bash
python .agents/skills/assetkit/scripts/install.py --project . --client codex --bootstrap
```

Claude Code 对应 `.claude/skills/assetkit/scripts/install.py --client claude`。
外部 CLI 需要 Node.js 和网络；安装器拒绝符号链接目标，所以示例明确使用 `--copy`。
Skills CLI 的网络安装与模型隐式触发未作为本地 Python 测试的验证结论。

## 给 Agent 的调用

在已接入的项目中直接说：

> 使用 assetkit。先检索项目已有的首页主视觉、产品介绍和模型，能复用就复用；本次新建且需要保留的资源按规范存放并增量登记，最后只报告相关资产 ID 和校验结果。

首次整理存量资源：

> 使用 assetkit 整理当前项目的可复用资源。先小批量盘点高频资产，保持现有文件路径不变；未知来源和许可标为 candidate，不要把全部账本读入上下文，也不要自动重命名整个项目。

SKILL.md 的 description 负责匹配任务，项目入口负责提醒。宿主仍可能漏触发；Skill 本身不是强制执行或权限边界。

## 结构与数据归属

```text
AssetKit/                           # 这个仓库：分发 Skill
├── skills/assetkit/
│   ├── SKILL.md                    # 短入口和任务路由
│   ├── references/                 # 6 个按需手册
│   ├── scripts/assetctl.py          # 增量账本 CLI
│   ├── scripts/install.py          # 安装、预览、项目接入
│   ├── assets/                     # 卡片 schema、请求示例、入口模板
│   └── agents/openai.yaml          # 可选 UI 元信息
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
CI 配置覆盖 Linux/Windows 与 Python 3.10/3.13；配置存在不等于这些环境已经通过运行。

当前没有：自动媒体预览/转录、向量搜索、对象存储连接、真实审批认证、分布式锁、自动迁移/删除和全仓引用检查。
只适用于可信本地工作区。validate 默认只检查已登记卡片和 assets 受管目录；不能证明全仓没有遗漏资源。
本仓库 CI 测试 Skill 自身，不会自动给目标项目安装 CI。需要强制门禁时接入目标项目的提交/CI 流程。

## 规范参考

- [Agent Skills 格式与渐进披露](https://agentskills.io/specification)
- [Codex Skills 官方说明](https://developers.openai.com/codex/skills/)
- [Skills CLI 官方仓库：安装选项与发现路径](https://github.com/vercel-labs/skills)

版本：0.2.0。沿用原资产方案的 schema_version 1。许可证尚未指定。
