# Changelog

## 1.1.0 — 2026-09-24

- Add a short project launcher and agent-first find/get/put/check interface. Existing assetctl commands remain available.
- Fuse bounded candidate discovery and usage checks; add collision-checked short refs and field projection.
- Default to compact bounded replies, summary-only batch acknowledgements, stdin JSONL and pageable historical receipts.
- Keep safety fields intact or fail closed when the response budget cannot fit them.
- Preserve review/revision for timestamp-only changes; cache verified file signatures, not authorization decisions.
- Verify declared cross-card dependencies with node/depth/file limits and cycle detection, including legacy resolve.
- Add byte-budget/safety/launcher/receipt tests and a reproducible visible-token transcript comparison with v1.0.0.
- No new runtime dependency, LLM call, telemetry, cloud service, hook auto-installation or license policy is introduced.

## 1.0.0 — 2026-09-24

Stable local-workspace release. Add multi-project profile detection, original-path capture, JSONL batches, stat-based no-op capture, bounded find, native usage resolution, Git-scoped inventory, omission/integrity gate, diagnostics and metadata backups. Preserve schema 1 and all existing low-level CLI operations.

Add explicit CPU/I/O/context budgets, custom discovery policy, known sidecar/glTF/image-set grouping, pointer awareness, stricter metadata/asset-path safety and recovery tests. Publish the measured synthetic benchmark, operating contract, contribution/security policies and release packaging workflow. Native engine runtime certification and distributed services are explicitly outside this release.


## 0.3.0 — 2026-09-24

- Make `npx skills add chenziyang110/AssetKit --skill assetkit` the primary install path.
- Preserve the Anthropic-style `skills/assetkit/SKILL.md` layout and add optional marketplace grouping.
- Add an independent bootstrap command for default symlink, copy and global installations; do not rewrite installed skills.
- Keep legacy offline copy installation for compatibility. Preserve project state and existing entry rules.
- Add eight bootstrap/packaging tests and real skills CLI discovery/install/ledger smoke tests in CI.
- Document installation versus initialization versus skills.sh leaderboard indexing.


## 0.2.0

- 将原资产规范包封装为独立的 `assetkit` Agent Skill。
- 增加短 SKILL.md、6 份按需参考、请求/入口模板与 UI 元信息。
- 增加项目级安装器，支持预览、非破坏式入口合并和相同内容的重复安装。
- 保留 JSON 卡片事实源和 SQLite 派生索引，项目状态与 Skill 安装目录分离。
- CLI 增加 --version、--patch-file，以及对关键元数据路径的符号链接拒绝。
- 增加安装/包装测试与跨平台 CI 配置；不将配置存在等同于运行已通过。
