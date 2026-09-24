# 登记、更新、审核与版本

> 1.0 日常路径：优先 `find → resolve → capture`，参见 [快速流程](workflows.md)。下文的 `search/add` 是保留的低层操作。原生工程路径优先于受管导出命名规则；capture 默认原位登记。


`.assets/records/<id>.json` 是元数据事实源；`.assets/cache/catalog.sqlite` 可删除重建。
通过 CLI 更新卡片。不要手工维护数据库或另造全量总表。Git 审查、合并卡片后由工具同步索引。

## 新增

正式文件先落到获准位置，然后构造本次请求并调用 `add --manifest ... --request-key ...`。
请求至少提供 type、domain、logical_key、title、summary、use_when、files；其他默认值见 CLI。
有真实来源和使用权依据时填写 source、rights。工具生成 ID、时间、revision、文件大小和 SHA-256。
不要手填工具管理字段；不要把 API 密钥、临时签名 URL、完整生成日志写入卡片。

同一项目和 request-key 生成稳定 ID；完全相同的请求重试返回原登记回执。
同键但请求/文件内容变更会报错。换键不允许绕过重复 logical_key + content_version 检查。
工具不移动文件：没有 add 成功回执时，可能仍存在待登记文件，应排查后重试，不能声称完成。

## 两种内容模式

`snapshot` 用于发布图片、视频、模型、数据或可复现文档。content_version >= 1。
内容变更必须新建版本和路径，产生新 ID；用 `supersedes` 指向旧版本，旧文件继续保留。
同一 logical_key 串起版本。snapshot 的“不覆盖”由工作流和哈希校验约束，不是文件系统写保护。

`live` 用于持续编辑的需求/架构说明，content_version 固定为 0，ID 和路径保持稳定。
修改文件后执行 `refresh --expect-revision ... --summary ... --use-when ...`。
工具刷新指纹并改为 candidate，删除旧审核字段。预览与转录不会自动更新，必须另外核实。
live 不代表可复现历史快照；需固定交付时另建 snapshot。

## 元数据补丁与审核

先读目标字段和 revision，再使用 `patch --expect-revision N --patch-file ...`。
只替换指定顶层字段，不是递归合并，也不是 RFC 6902。
修改 `rights`、`source`、`tags` 等对象或数组时提交该字段的完整新值，但不需读整本账本。
不能用 patch 修改路径、哈希、内容版本、类型和 logical_key。

初始状态 candidate。标为 ready 必须具备非 unknown 的来源/使用权、reviewed_by 和 review_evidence。
这些字段只提供结构约束，不认证身份或授权真实性。Agent 不得捏造审批人和证据。
复用权限/用途发生实质变化时先撤为 candidate，再按真实流程审阅；CLI 不自动判断语义变化。
过期或停止使用时 patch 为 deprecated/archived；状态变化不会删除文件。

`revision` 是卡片修改次数，不是内容版本。冲突时重读该卡片，重新判断补丁，不盲目重试旧结论。
`derived_from` 表示派生，`depends_on` 表示依赖，`supersedes` 表示替代；目标须存在且不能是自身。
当前工具不做关系环检测，也不自动停用被替代项。
