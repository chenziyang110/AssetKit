# Skill 分发设计

## 对照 Anthropic

核对日期：2026-09-24。上游参考：

- [skills.sh 的 Anthropic 作者页](https://www.skills.sh/anthropics)：展示页，不是需要复制的安装目录。
- [anthropics/skills](https://github.com/anthropics/skills)：`.claude-plugin/`、`skills/`、`spec/`、`template/` 以及根 README。
- [上游 marketplace.json](https://github.com/anthropics/skills/blob/main/.claude-plugin/marketplace.json)：使用 source、strict 和 skills 对技能做插件分组。
- [Skills CLI 源码](https://github.com/vercel-labs/skills/blob/main/src/skills.ts)：检查 SKILL.md 的 name / description，扫描 skills 等已知目录。
- [CLI 安装参数](https://github.com/vercel-labs/skills#install-a-skill)、[skills.sh FAQ](https://skills.sh/docs/faq)。

AssetKit 采用同样的“一仓库可包含多个 Skill，每个 Skill 独立成包”原则：

```text
AssetKit/
├── .claude-plugin/marketplace.json  # 可选：Claude 插件分组
├── skills/
│   └── assetkit/                    # 唯一可安装 Skill，运行时内容自包含
│       ├── SKILL.md                 # 必须：YAML 元信息和短流程
│       ├── references/              # 按需手册
│       ├── scripts/                 # 账本、独立初始化、旧式离线安装
│       ├── assets/                  # schema 和模板，不是业务资产
│       └── agents/openai.yaml       # 可选客户端信息，不是 CLI 发现入口
├── docs/                            # 仓库维护说明；运行时不能依赖它
├── tools/                           # 仓库级验收工具；不随 Skill 安装
├── tests/
└── README.md
```

不为模仿目录而复制上游 spec/template 或其技能实现。本项目只有一个 Skill，也不拆成多个缺乏独立用途的微技能。
不在仓库根目录放重复 SKILL.md，避免根 Skill 优先发现而改变子技能选择。
新增可复用技能时再增加 `skills/<other-name>/SKILL.md`，并确保名称唯一。
模板若需要 SKILL 示例，使用 `SKILL.md.example` 等非入口名称，避免误被发现。

## CLI 需要什么，不需要什么

`skills/assetkit/SKILL.md` 的 YAML frontmatter 提供字符串类型的 `name: assetkit` 和非空 description；
所有运行时依赖均在该 Skill 目录内，链接相对该目录。无需发布名为 AssetKit 的 npm 包，也无需 package.json 或 install hook。
本仓库保留的 marketplace.json 只是可选插件分组，不是 skills CLI 安装的必要条件。
没有把 Claude 原生插件客户端的激活行为当成已验证事实；当前验收对象是 skills CLI 和 Python 工具。

```bash
npx skills add chenziyang110/AssetKit --list
npx skills add chenziyang110/AssetKit --skill assetkit
```

CLI 负责下载和管理 Skill；bootstrap 负责在被授权时初始化项目账本。把二者拆开才能支持默认符号链接、复制、全局安装，
并避免升级 Skill 时碰到业务记录。旧 install.py 仅保留作离线复制兼容入口。

## 安装、初始化、网站收录是三件事

仓库能被 CLI 安装不要求已经出现在 skills.sh 搜索结果中。
FAQ 说明网站榜单通过真实安装遥测形成；不是向网站推送目录或先提交一个 npm 包。
CI 设置 `DISABLE_TELEMETRY=1` 与 `DO_NOT_TRACK=1`，不以自动化安装制造榜单计数。
本项目不承诺网站立即收录，也不把自动化测试当成真实用户使用。

## 验收

```bash
python -m unittest discover -s tests -v
# 以下使用真实外部 CLI，需 Node.js、Git、网络
python tools/smoke_skills_cli.py --source /absolute/path/to/AssetKit
python tools/smoke_skills_cli.py --source chenziyang110/AssetKit
# 复现某次日志中的版本可附加 --cli-version <version>
```

Smoke 测试隔离 HOME 和项目目录，覆盖唯一技能发现、默认项目安装、--copy、全局安装；
验证 Codex 和 Claude Code 的安装内容完整，安装本身不建账本；再执行幂等初始化、登记、中文检索与哈希校验。
本地源测试用于 pull request；公开 owner/repo 测试仅在 main push 执行，检查安装内容与当前提交一致。
以对应提交的 GitHub Actions 运行结果为准。工具安装成功不等于语言模型每次都能正确触发 Skill。
