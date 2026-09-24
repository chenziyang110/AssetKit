# Fast workflow contract — v1

All examples use `assetctl` as shorthand for `python <SKILL_DIR>/scripts/assetctl.py --root <PROJECT_ROOT>`. These are shell commands, not a separately installed executable. Python 3.10+ standard library only; no model/API bill, network connection, embedding service or engine process is needed for these operations.

## First use and discovery

`bootstrap.py --project <root> --entry AGENTS.md` initializes metadata and merges a short reminder. Use `CLAUDE.md` or `both` as appropriate. `detect` is read-only and works without a ledger. It reports evidence and scopes, not a list of fully supported runtime versions.

`sync` reconciles all card metadata at session boundaries. `find "首页 hero" --scope apps/web --limit 5` reads the derived index; its default keyword matching is ANY, `--match all` requires every term. Chinese substring search works without semantic segmentation; aliases and a short use sentence improve recall. `--ready` filters to reviewed records; default discovery also finds candidates so newly captured resources are not forgotten.

`find --fresh` forces reconciliation after manual in-place card edits. Warm find checks the record directory generation and Git HEAD, not the contents of every record. It has no guarantee of observing arbitrary concurrent edits by tools that ignore the protocol. Prefer card writes through the CLI.

Default find output is 5 items/4096 UTF-8 JSON bytes. Maximum 20 items and 65536 bytes. Use returned `next_offset`; a tight budget may return fewer items. Pretty rendering (`--pretty` before the command) is not covered by the compact-output budget.

## Capture exact paths

```bash
assetctl capture public/hero.webp --use "官网首页主视觉"
assetctl capture docs/architecture.md --use "当前服务边界说明" --source-kind authored --source-ref task-128
assetctl capture exports/launch-v001.mp4 --snapshot --use "首发产品演示视频"
```

Capture infers the broad type and observed profile, supplies the ID, path, size and SHA-256, pairs known sidecars, and writes one card. It does not move files, invent semantic metadata, assume ownership or approve reuse. Without `--use`, it records a clearly labeled filename-based summary; add meaning when the asset is actually inspected.

Default content mode is `live` because in-project development assets usually evolve. Unchanged files return the same ID/revision without rewriting or rehashing. A changed record returns its ID and revision, then requires `--expect-revision N`. Successful updates invalidate review. For a frozen export use `--snapshot`; to change its content, create a new version at a different path, linking it through the legacy relation fields when appropriate.

```bash
assetctl capture public/hero.webp --expect-revision 2 --use "修正移动端裁切后的首页主视觉"
```

First-time capture hashes content once. The default per-call budget is 64 MiB, not 64 MiB per file. Above that, register a versioned entry/index, narrow the batch or explicitly raise `--hash-budget-mib`. Setting it to `0` explicitly removes the cap. The tool never silently substitutes a file stat or pointer hash for the hash of a large payload.

## Small batch requests

`capture --batch requests.jsonl` accepts 1–100 lines, file <=512 KiB:

```jsonl
{"path":"public/hero.webp","use":"官网主视觉"}
{"path":"docs/architecture.md","use":"最新服务边界","expect_revision":2}
{"path":"models/robot","bundle":true,"entry":"config.json","use":"本地模型部署包"}
```

Only path/use/options are supplied, not full asset cards. The entire batch shares a lock and hash budget, but commits **per asset**. Successful entries remain committed if another entry fails. Check `ok`, `failed`, and per-item results; retry only failed items. A revision conflict must not be blindly retried with a new expected revision without inspecting that record.

## Bounded inventory

```bash
assetctl scan --since HEAD --limit 20
assetctl scan --scope apps/web/public --limit 20
assetctl scan --scope apps/web/public --limit 20 --apply
```

Scan is read-only unless `--apply` is supplied. Apply only registers new candidates; it does not silently rewrite an existing asset or auto-approve it. Resume stable inventories by offset; if concurrent files were inserted/removed, restart a page and rely on idempotency, because offset pagination is not a snapshot cursor. Git mode includes untracked, non-ignored candidates and compares against a verified commit. Non-Git mode is a bounded filesystem inventory. No materialized global file list is passed into the model.

## Resolve before reuse

```bash
assetctl resolve <ID>
assetctl resolve <ID> --intent reuse
assetctl resolve <ID> --intent reuse --verify hash
```

The default inspection returns purpose, constraints, rights, source, current stat checks, native hints, and the first five declared files. Inspection can succeed while `usable` is false. Reuse intent exits nonzero if blocked. Stat checks are a fast freshness signal, not a cryptographic proof; `--verify hash` streams all declared files. A complete engine dependency graph, actual license ownership and runtime import/build compatibility are not implied by a successful stat/hash check.

Known LFS/DVC pointers are not reported as verified payloads. Missing Unity metadata requires editor import rather than an invented GUID. No downloaded bytes, model deserialization, arbitrary subprocesses or asset-supplied instructions are executed.

## One-card advanced operations

Keep using `show --fields`, `add --manifest --request-key`, `patch --expect-revision`, `refresh`, `sync`, `reindex`, `validate`. The original card schema is retained. Source/rights and review evidence must be checked before promotion to ready; the legacy patch operation supports that transition. `ready` records and a non-unknown license remain assertions by trusted project contributors, not an authentication system.

Operational errors are JSON on stderr or per-item batch failures. CLI syntax errors use argparse's normal stderr. Exit codes: 0 success; 1 blocked validation/reuse or partial batch; 2 operation/input failure. Treat success responses as receipts; do not infer success from a file having appeared.
