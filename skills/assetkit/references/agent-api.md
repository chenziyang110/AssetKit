# Agent command contract (1.1)

Use `python .assets/ak.py` from the project root. Bootstrap generates this short launcher without changing installed Skill files. Direct equivalent: `python <SKILL_DIR>/scripts/agent.py --root <PROJECT_ROOT>`. `assetctl.py` remains the detailed v1 compatibility interface.

## Decision path

Known asset path/ID: `get`; unknown location: `find`; retained known output: `put`; task/commit boundary: `check`. No separate `detect`, `sync`, `show`, or validation call is required before each operation. `find --fresh` folds external reconciliation into the lookup; use once after manual card edits or when resuming uncertain state. Do not cache `usable` decisions across changes.

`find "keywords"` returns at most 3 candidates, including purpose, path, revision, declared-dependency checks, nonempty restrictions/rights and native reference hints. The selected card and up to 32 dependency nodes (depth <=8, <=2048 files) are checked. This saves find→resolve round trips, not semantic selection: the Agent must still select an appropriate resource. Use `--scope`, `--type`, `--profile` to narrow; `--match all` requires all keywords. `--summaries` returns metadata only and opens no cards on a warm index; call `get` before using those candidates. `--offset` follows the returned `next` cursor.

`get @ref` also accepts a full asset ID or exact project-relative file path. Short refs are collision-checked ID prefixes, not sequential IDs or session state. A later collision fails closed; use the full ID, not a guessed suffix. `get @ref --fields source,rights` projects selected authoritative metadata without asserting usability. It does not run an approval workflow.

## Cost and safety budgets

`find/get/receipt` default to 2048 UTF-8 bytes; `put/check` default to 1024. `--budget` accepts 384..65536 and counts final compact JSON plus newline. This is a byte limit, not a universal tokenizer estimate. JSON is escaped normally; no cryptic column encodings or hidden safety fields.

Results stop at complete row boundaries. An oversized first search row becomes `usable:false` with `DETAIL_REQUIRED`; use a larger `get --budget` or targeted metadata. Oversized `get` fails without claiming success. Rights notes and dependency restrictions are never silently truncated while returning `usable:true`. Explicit `blocked`, `blocker_count` and pagination fields must be respected.

`--verify auto` stats files and hashes only absent/stale local evidence within a shared 64 MiB read budget. `--verify hash` bypasses cached signatures. `--hash-budget-mib 0` explicitly removes the read cap. The cache stores file evidence, NEVER review/authorization outcomes; current relevant cards and files are checked again on reuse. Native hints do not prove full engine dependency closure or runtime compatibility. Passing checks are not legal authority; apply all restrictions and project approval requirements.

## Writes without verbose receipts

`put PATH --use "short purpose"` records observable fields; it never approves a resource. Existing changed files require `--expect-revision N`. A byte-identical touch/checkout preserves revision and review; only cached local signatures are refreshed. The original JSON card is not rewritten. Snapshot payload changes remain forbidden. Source/rights/purpose changes still require review.

`put --batch requests.jsonl` or `put --batch -` accepts the same small JSONL capture requests as assetctl (<=100; input <=512 KiB):

```jsonl
{"path":"public/hero.webp","use":"Homepage hero"}
{"path":"docs/design.md","use":"Current design decisions","expect_revision":2}
```

Reuse an existing tool-output manifest when available instead of making the model emit paths again. Runtime validation rejects unknown request fields; do not pipe arbitrary tool schemas without mapping them outside the LLM.

One input returns ref/rev/action/status. Batches return created/updated/unchanged counts, indexed errors, and a local receipt handle. Full path/ID results are kept outside context. `input` is the zero-based input ordinal. `--details` opts into full rows, still under the byte budget. Only retry failed entries; successful writes are not undone by another failure. A transport/error after writing is ambiguous: inspect the path, never blindly replay an update.

`receipt HANDLE --offset N --limit 5` pages historical outcomes, NOT current approval. Receipts are content-addressed, local, under `.assets/cache/receipts/`, capped at 128 files of <=1 MiB. They can be pruned or lost with cache deletion. They are not an audit log, asset store, or permissions source. Keep durable IDs in the actual records/Git, not only in receipts.

## Completion and errors

`check --since <BASE>` executes the existing omission/staleness gate and returns only `{"ok":true}` on success. Use a real base commit and sufficient Git history in CI. Failures return counts, up to 3 errors and a receipt; a truncated gate receipt is explicitly marked. A separate full release integrity/build check remains required. Never run this O(all registered files) gate once per capture.

Recoverable errors use a short code and message, not full tracebacks/usage dumps. `REVISION_REQUIRED/CONFLICT`: get current metadata; `NOT_INITIALIZED`: bootstrap; `INDEX_ERROR`: reindex; `HASH_BUDGET`: narrow or authorize the read; `DETAIL_REQUIRED/OUTPUT_BUDGET`: request necessary details; `DEPENDENCY_LIMIT/CYCLE`: resolve the relationship problem, do not bypass the guard.

## Token accounting

`tools/context_benchmark.py` compares fixed workflows with v1.0.0. It counts commands, JSONL inputs, tool responses and static text separately; optional pinned tiktoken counts are development-only. No tokenizer/model/API dependency is added to project usage. The benchmark is not a measured LLM task-success rate or provider bill. No silent response suppression is based on assumed model memory: after compaction, relevant results remain retrievable.
