# CLI 契约

运行 `python <SKILL_DIR>/scripts/assetctl.py --root <PROJECT_ROOT> <command>`。
Python 3.10+，无额外包，无网络调用。路径参数加引号；manifest/patch-file 相对进程当前目录或使用绝对路径，
而请求中的 files.path 始终相对 PROJECT_ROOT。

| 命令 | 契约 |
|---|---|
| `init` | 创建配置、卡片目录、索引，不覆盖原配置，不自动改项目指令 |
| `search "词" --type image --status ready --limit 5 --offset 0` | 返回有限摘要、total、next_offset；默认 ready，最大 20 条 |
| `show <ID> --fields id,revision,summary,files` | 只读指定卡片和顶层字段；省略 fields 会返回整张卡片 |
| `add --manifest <JSON> --request-key <KEY>` | 文件先存在；每次只新增一张卡片；同键幂等 |
| `patch <ID> --expect-revision N --patch-file <JSON>` | 指定顶层字段替换；也支持 `--patch '<JSON>'`，两者互斥 |
| `refresh <ID> --expect-revision N --summary "摘要" --use-when '["适用场景"]'` | 仅 live；刷新哈希并撤销旧审核 |
| `sync` | 程序检查卡片 stat，只解析变化记录 |
| `reindex` | 删除并完整重建派生索引，不修改卡片或业务文件 |
| `validate --hashes --max-issues 20` | 验证卡片、关系、文件指纹和受管目录漏登记；输出有限问题 |
| `--version` | 输出 AssetKit 版本 |

成功输出 JSON 到 stdout；业务/输入错误输出 `{ "ok": false, "error": "..." }` 到 stderr。
退出码 0 成功，1 校验发现错误，2 操作失败；argparse 用法错误是文本，不保证 JSON。
`--version` 输出文本。以退出码和成功回执为准，不从“命令已经执行”推断写入成功。

重要默认：新增 candidate、snapshot、版本 1、managed；live 未指定版本时用 0。
source/rights 缺省 unknown。每卡最多 512 个文件，卡片/请求/补丁文件最大 64 KiB。
`add` 流式计算文件哈希；大文件仍需读完其内容，不存在“零 I/O 登记”的承诺。

检查到 REVISION_CONFLICT 时只重读该条记录。request-key 冲突时核实是重试还是新内容。
路径不存在、命名不符或未知字段时修正本次请求，不绕开验证直接改数据库。
数据库损坏可 reindex；卡片损坏须定位并修复来源记录，不能用重建掩盖。

原子替换以单个卡片文件为单位；文件与 SQLite 不是跨系统原子事务，先写卡片再写索引，sync 可恢复缓存。
进程锁只协调同一机器上遵守该锁的工具进程。外部编辑和跨主机写入不受保护，不适用于共享网络盘并发。
`validate` 的 managed_roots 默认只包含 assets；不会证明其他目录没有漏登记资源，不校验模型兼容性或真实授权。
