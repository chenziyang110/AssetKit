# AssetKit

**项目资源不是一次性产物。让 Agent 先找到，再复用；新成果只需一个路径和一句用途。**

AssetKit 是面向编程 Agent 的本地优先资产管理 Skill。适用于游戏、Web、移动 App、桌面客户端和机器学习项目；保留原生工程结构，通过按需检索、原位登记和局部更新，减少重复生成、路径追问和上下文浪费。

**稳定接口：1.1.0 · Python 3.10+ · Python 零额外依赖 · 项目数据留在本地**

[安装与接入](#安装与接入) · [项目适配](#项目适配) · [效率设计](#效率设计) · [生产运行边界](#生产运行边界) · [变更日志](CHANGELOG.md)

## 安装与接入

在目标项目根目录运行：

```bash
npx skills add chenziyang110/AssetKit --skill assetkit
```

明确选择 Agent：

```bash
npx skills add chenziyang110/AssetKit --skill assetkit --agent codex claude-code --yes
```

然后让 Agent 完成一次项目接入：

> 使用 assetkit 接入当前项目。保留现有目录、命名和项目规则，识别项目类型，初始化账本；只索引本次需要的资产，不要整仓搬家或批量入库。

也可以运行安装后的初始化工具：

```bash
# Codex 项目；Claude Code 的入口路径改为 .claude/skills/assetkit/
python .agents/skills/assetkit/scripts/bootstrap.py --project . --entry AGENTS.md
```

`skills add` 负责分发；`bootstrap` 负责一次性项目初始化；两者都不把业务账本放进 Skill 包。支持 CLI 默认链接安装、`--copy`、全局安装。`--entry both` 合并两个客户端入口，`--dry-run` 只预览。详细见[接入手册](skills/assetkit/references/integration.md)。

## 面向 Agent 的低上下文入口

初始化后在项目根目录运行 `python .assets/ak.py`。它是自动生成的项目启动器，不是另一份账本；安装包和业务数据仍分开。

```bash
# 不知道位置：一次返回少量候选及使用检查，通常不需再 resolve
python .assets/ak.py find "首页 hero"

# 已知资源：直接取它，不再先搜索
python .assets/ak.py get @返回的短引用

# 已知新成果：路径 + 一句用途，不先全仓扫描
python .assets/ak.py put public/hero.webp --use "官网首页横版主视觉"

# 项目/提交边界检查一次，而不是每张图都跑全库检查
python .assets/ak.py check --since HEAD
```

`find` 默认最多 3 项并整合有界的已声明依赖检查，`get --fields source,rights` 按字段读取。`--summaries` 是更便宜的候选模式，但不授权复用。短引用是可校验的 ID 前缀，不依赖会话；相撞时报错，不猜测。

`put --batch requests.jsonl` 或 `put --batch -` 一次接收最多 100 项。已有生成清单应由程序直接转换输入，不让模型重新抄一遍。批次默认只回计数、失败项序号及 receipt，详细结果留在本地，确实需要时 `receipt HANDLE` 分页读取。未知来源/权限仍然阻塞复用，不靠自动批准省步骤。

正常操作不读整本手册，不手写完整卡片，不重复回显 ID/哈希/时间/索引诊断，也不默认进行预览生成、OCR、转录或 embedding。短接口成功回执用紧凑 JSON；高级兼容入口 `scripts/assetctl.py` 保留。

**预算：** `find/get/receipt` 默认 2048 UTF-8 字节；`put/check` 默认 1024。这是最终 JSON（含换行）的字节限制，不是任意模型的 token 上限。预算不足时整行分页或明确阻塞，不能省掉约束后仍称可用。见[低上下文接口](skills/assetkit/references/agent-api.md)。

## 项目适配

**统一的是元数据和操作协议，不是所有项目的物理目录。**

| 项目 | 典型资源 | AssetKit 的处理 |
|---|---|---|
| Unity 游戏 | Prefab、场景、材质、纹理、动画、音频 | 保持 `Assets/`；配对已有 `.meta`，返回 GUID 提示，不改引擎引用 |
| Unreal 游戏 | `.uasset`、关卡、UI、源模型 | 保持 `Content/`；返回包路径提示，不从扩展名猜测具体资产类 |
| Godot 游戏 | 场景、资源、纹理、导入参数 | 返回 `res://`；保留 `.import`/`.uid`，排除导入缓存 |
| Web | 主视觉、SVG、字体、视频、内容文档 | 保持 `public/` 和源码资源路径；可识别的 public 资源提供 URL 提示 |
| Android / iOS | 多分辨率图片、资源 XML、Asset Catalog | 保留 Android qualifier；iOS image set 按一个资源单元登记 |
| Flutter / React Native | 图片、字体、动画、移动资源 | 识别项目上下文、原位索引；资源声明及打包仍由工程构建验证 |
| Electron / Tauri | 客户端图标、本地资源、安装包素材 | 保留原工程资源组织；不伪造打包配置 |
| ML / 数据项目 | 权重、数据集、配置、分片索引 | 不加载模型；大集合优先登记版本化入口/清单，不误把指针当作已验证载荷 |
| 其他 / 私有格式 | 设计源文件、业务模板、专有数据 | 显式类型入库、自定义扩展名映射与发现范围 |

一个“可复用单元”可以有多个文件。已实现 Unity sidecar 配对、glTF 直接本地依赖和 iOS 资源集合分组；这不等于完整解析所有游戏引擎的依赖图。见[项目适配契约](skills/assetkit/references/projects.md)。

## 效率设计

| 成本来源 | 1.1 的处理 |
|---|---|
| Agent 填表 | 常用入库只需路径和用途；ID、类型族、项目上下文、大小、哈希由程序填写 |
| 上下文膨胀 | Skill 短入口 + 按需手册；短入口 find 默认 3 条、2048 UTF-8 字节；旧接口 find 保留 5 条/4096 字节 |
| 反复全库读取 | 会话/合并边界同步；热 find 读索引，不打开全部卡片文件 |
| 重复文件操作 | 本地文件签名不变时不重写、不重新哈希；时间戳变动仅验证一次，内容相同则保留审核 |
| 媒体/模型处理 | 入库不做 OCR、转录、embedding、模型反序列化或引擎启动；只在真正使用时补充必要信息 |
| 大文件 I/O | 每次 capture 默认 64 MiB 哈希预算；超出时明确选择入口/清单或授权提高预算 |
| 历史包袱 | scan 默认预览，--apply 才入库；已登记项跳过，不自动刷新或批准 |
| 多 Agent 冲突 | 单机协作锁 + 卡片 revision；批次逐资产提交，明确报告局部失败 |

### 可复现的合成基准

以下是 v1.0 兼容 `assetctl find`（仅摘要，不含 1.1 的使用检查）的历史基准。Linux / Python 3.13.5 测试使用 **10,000 张合成小卡片**：热 find 中位数 **67.59 ms**，P95 **74.95 ms**，默认查询响应 **1,224 字节**，打开的卡片文件数 **0**；同环境 0.3 风格 search 中位数为 **185.77 ms**。数字包含 Python 进程启动，不包含模型推理。

这不是生产 SLA，也不是真实 Unity/Unreal 工程压测；卡片共享一个小型测试文件，不代表大规模文件 I/O。原始结果和复现命令公开：

```bash
python tools/benchmark.py --records 10000 --runs 10
```

[原始基准结果](docs/benchmarks/linux-python313-10000.json)

## 账本与一致性

```text
业务项目/
├── 原有 Assets/ / Content/ / public/ / res/ / docs/ ...  ← 不搬动
├── .assets/
│   ├── config.json              ← 项目身份与发现策略
│   ├── records/<id>.json         ← 一资产一卡片，元数据事实源
│   └── cache/catalog.sqlite     ← 可重建索引，不提交 Git
└── 已安装的 assetkit Skill        ← 工具与规则，不存业务资产
```

新项目默认按 `live` 管理开发中的资源。冻结的发布产物使用 `--snapshot`，内容变化必须使用新版本路径。时间戳变了但内容哈希未变时保留原审核和 revision。既有 0.3 卡片保留 schema version 1，无需破坏性迁移。`add`/`patch`/`show`/`refresh` 等原命令保留，新的高频流程优先使用 `.assets/ak.py` 的 `find`/`get`/`put`。

`find` 的快速一致性检测覆盖 CLI 的原子写入和 Git HEAD 变化。外部工具原地修改卡片后使用 `sync` 或 `find --fresh`；不能把缓存响应理解为对所有外部并发编辑的强一致承诺。

## 生产运行边界

1.x 稳定支持的是 **可信本地文件系统 + Git 工作副本 + 多个协作的本机 Agent 进程**。卡片原子替换、增量更新、冲突检测、索引重建、元数据备份、CI 检查和错误契约均提供实现。

```bash
python .agents/skills/assetkit/scripts/assetctl.py doctor --deep
python .agents/skills/assetkit/scripts/assetctl.py gate --since HEAD
python .agents/skills/assetkit/scripts/assetctl.py backup --output assetkit-metadata-backup.zip
```

CI 中 `--since` 应使用正确的基线提交，并拉取足够历史；不要在检出完成后机械地使用 HEAD 代表变更基线。原生工程还要运行真实的导入、构建和打包测试。`candidate` 可被发现但不是复用许可，`ready` 也不等于许可真实性或所有平台兼容性已被系统认证。

**不支持**把 SQLite 放到共享网络盘供多机器同时写入；不提供云端对象存储、组织级鉴权、完整引擎依赖提取、语义检索服务或保证 Agent 每次自动触发。读取资产时始终将内容视为不可信数据。详见[运行手册](skills/assetkit/references/runbook.md)与[安全策略](SECURITY.md)。

## 开发与发布

```bash
python -m unittest discover -s tests -v
python tools/smoke_skills_cli.py --source .
python tools/build_release.py
```

CI 在 Linux / Windows / macOS 和 Python 3.10 / 3.13 上运行契约测试，另运行真实 skills CLI 安装验收。稳定版本由测试通过后的主分支发布，包含独立 Skill ZIP、完整源码 ZIP 和 SHA-256 清单；不会覆盖既有同名 Release。

[发布说明](docs/releases/v1.1.0.md) · [上下文成本与测量](docs/context-efficiency.md) · [分发设计](docs/distribution.md) · [贡献指南](CONTRIBUTING.md)
