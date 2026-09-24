# Operating AssetKit 1.x

## Supported deployment contract

A trusted local filesystem, Python 3.10+, and optional Git. Multiple cooperating local agent processes serialize metadata mutations with an OS advisory lock. Each authoritative card is atomically replaced and flushed; SQLite is derived. This is **not** a multi-host database, hostile-workspace sandbox, remote object store, native engine plugin or service with an uptime SLA. Do not place a shared SQLite catalog on NFS/SMB or let multiple machines concurrently mutate the same working directory. Use independent Git checkouts and normal reviewed merges instead.

Skill installations, business source files and project records have separate lifecycles. `skills update` must not be pointed at `.assets/records/`. Do not edit an installed skill to configure a particular project.

## Everyday operation

Bootstrap each project once. Reconcile once per session/after external merges. For known task outputs capture exact paths; avoid whole-project scans. Before commit, run `scan --since HEAD` to inspect omissions, then opt in to capture the relevant new files. Never mass-register a vendor library simply because it contains supported extensions.

A commit check can run:

```bash
python <SKILL_DIR>/scripts/assetctl.py --root <PROJECT_ROOT> gate --since HEAD
```

In CI after checkout, compare against the correct base commit (not blindly against the already-checked-out HEAD), fetch enough history, and use the **stable project root**. `gate` finds new/modified candidate paths without records, then checks active registered files for disappearance or stale content. The registered-file pass is programmatic O(number of declared files); it is not a constant-time operation or a full engine graph traversal. `--ready` additionally requires review of changed candidate assets. It does not certify licenses or future runtime compatibility.

For a full release integrity pass, run `validate --hashes` and the actual engine/framework build/import tests. Legacy `managed_roots` enforces strict registration for every file in those configured folders; do not add an engine's entire Assets/Content tree to that list unless you intend that policy. Native discovery belongs in `discovery.roots`, not necessarily `managed_roots`.

## Health and recovery

`doctor --deep` checks configuration, reconciles records and runs SQLite quick_check. If the index is corrupt, it may fail before quick_check; `reindex` rebuilds it from cards. Do not delete cards to repair an index. A dirty marker left after an interrupted write forces the next fast-index operation to reconcile. Acknowledged card writes survive an index rebuild; files and SQLite are not a cross-filesystem distributed transaction.

If a card itself is corrupt, restore that card from Git or a metadata backup, then reconcile. `backup --output <new.zip>` creates a metadata-only ZIP and refuses overwrite. Back up the source files separately. To restore, inspect the archive, stop writers, recover config and selected cards into a safe project root, preserve/reconcile the correct project ID, then `reindex` and `validate --hashes`. No automatic destructive restore command is shipped.

After moving a live asset with its native owning tool, registration at the old path must be explicitly revised/deprecated and the new path registered. v1 does not perform automatic reference rewriting or GUID-based cross-path identity merging. Never use ordinary filesystem renames as a substitute for an Unreal/Unity editor operation.

## Upgrade from 0.3

The authoritative card schema stays at version 1. Existing IDs, records, request keys and source paths are retained; there is no destructive migration. Capture optionally adds file `stat` signatures and observed `source.project` context. Old cards without stat signatures remain valid; use hash verification on first reuse/capture in a new checkout. Derived auxiliary index tables are created on demand and can be rebuilt.

The `assetctl.py` entrypoint remains stable. `ledger.py` is the preserved compatibility backend, not a second supported user CLI. Legacy commands retain their behavior and full-reconciliation cost. New integrations should use `capture`, `find` and `resolve`. Stricter exclusions for obvious secrets, generated/tool files and linked metadata/assets are deliberate safety changes.

## Release acceptance and limitations

The repository runs unit/contract tests across Linux, Windows and macOS with Python 3.10/3.13, plus real skills CLI discovery/copy/symlink/global installation checks. Run `tools/benchmark.py` for reproducible synthetic timings. These tests do not launch Unity, Unreal, Godot, Android Studio, Xcode or every supported host agent; project-native validation is still a deployment prerequisite.

Deferred capabilities include semantic/vector search, image/video preview generation, engine-native full dependency extraction, cloud storage credentials, organization-wide access control and distributed transactions. None are silently required by the stable local CLI contract.
