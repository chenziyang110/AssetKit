# 存储、命名与可复用单元

> 1.0 日常路径：优先 `find → resolve → capture`，参见 [快速流程](workflows.md)。下文的 `search/add` 是保留的低层操作。原生工程路径优先于受管导出命名规则；capture 默认原位登记。


仅独立受管导出资源采用 `assets/<type>/<domain>/<slug>/<version>/`，主入口命名为 `<slug>--<variant>--<version>.<ext>`。
`domain`、`slug`、`variant` 使用小写 kebab-case；中文标题、用途与别名写入卡片。
`snapshot` 的目录为 `v001` 等，`live` 的目录为 `working`。不要使用“最终版2”“new-image”等文件名。
状态放在卡片中；candidate 变 ready 不应搬家。

`type` 可用值：`document`、`image`、`video`、`audio`、`model-3d`、`model-ml`、`dataset`、`design`、`template`、`other`。
例如 `assets/model-3d/product/robot/v002/robot--web--v002.glb`。
`logical_key` 通常为 `<domain>/<slug>`；工具对同一 logical_key 和内容版本拒绝重复登记。

现有 `docs/`、`public/`、`src/assets/` 不强制迁移。登记时使用 `storage_policy: in-place`；
正式迁移须先检查代码、构建和文档引用，并明确授权。此工具不自动搬迁或修复引用。
所有登记路径必须是项目内的规范相对路径；拒绝绝对路径、`..` 和逃逸项目的符号链接。

一个资产代表一个可独立复用单元，不一定只有一个文件。每张卡片必须且只能有一个 `primary`。
配套文件角色包括 `source`、`preview`、`transcript`、`config`、`dependency`、`readme`。
例如 3D 模型应同时登记入口、纹理、材质；模型权重应说明配置、分片和运行环境。
超过 512 个文件的集合使用清单和入口；清单内容及其引用文件仍需类型专属工具验证。

文档先读摘要/目录；图片先读缩略图与已验证属性；视频先读关键帧/分段转录；模型先读预览和运行要求。
CLI 不自动生成预览。1.0 resolve 仅对 PNG 做有界文件头尺寸提示，不代表完整解码校验；其他未测得的属性不要猜。
源文件与交付文件可以组合登记；不同用途或独立发布的派生版本使用 `derived_from` 建立关系。

中间产物放 `.work/<task-id>/`；待分类资源可以放 `assets/_inbox/`，不默认为可复用。
缓存、依赖、构建输出、失败生成不默认入库。Skill 自带 `assets/` 是模板目录，不是项目业务资产存储区。
