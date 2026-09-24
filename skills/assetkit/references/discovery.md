# 检索与渐进式披露

> 1.0 日常路径：优先 `find → resolve → capture`，参见 [快速流程](workflows.md)。下文的 `search/add` 是保留的低层操作。原生工程路径优先于受管导出命名规则；capture 默认原位登记。


目标是控制模型读取量，不禁止程序扫描磁盘。卡片是一项可引用资产版本的结构化说明，SQLite 是派生索引。
禁止 `cat .assets/records/*.json`、读取整张数据库表、维护巨型 Markdown 账本。

按四层读取：Skill 元信息 → 当前规则章节 → 每次最多 5 条搜索摘要 → 1～3 张相关卡片的必要字段/正文。
CLI 的硬上限是每页 20 条；`next_offset` 用于继续分页，不应不加选择地把所有页展开。

用用途、业务域和类型搜索。例如先搜“首页”并加 `--type image`，再尝试“hero”或“主视觉”。
`search` 是 Unicode casefold 后的子串 AND 匹配；不会自动进行中文语义分词、同义词扩展或向量排序。
多个空格分隔词必须全部出现；零命中先减少词数再尝试别名，不要立即重新生成资源。
结果排序为 logical_key、内容版本降序、ID，不代表语义质量评分，也不是只返回最新版。

默认 `--status ready`。没有合适 ready 时显式查看 candidate 或 all，区分“存在但待审核”和“不存在”。
`deprecated`、`archived` 只用于历史追溯，不能无审查地用于新交付。

命中之后先 `show --fields id,revision,summary,use_when,restrictions,status,files,source,rights`。
核实文件可用性、版本、用途与约束，再按需要读预览或正文。搜索摘要本身不是复用许可。
未知来源和许可不能凭搜索命中变成已确认。未执行搜索不能说无资产；索引错误不能当作零结果。

`summary` 解释内容和作用；`use_when` 表达任务触发场景；`aliases` 承接不同说法；`restrictions` 解释不适用场景。
不要把全文放进卡片。摘要最多 240 字符，use_when 1～3 项，卡片最多 64 KiB。

每次旧式 `search` 会在程序内检查卡片 stat，解析变化文件并同步索引；这是 O(N) 元数据检查，不是常数时间检索承诺。
`show` 直接读取指定卡片，不需要全库同步。全量校验与重建也只把有限结果交给模型。
需要跨库语义检索时可另建派生索引；不要引入第二个可独立编辑的元数据事实源。
