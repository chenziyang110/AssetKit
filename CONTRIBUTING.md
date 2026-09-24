# Contributing

Keep the canonical skill self-contained under `skills/assetkit/`. Runtime dependencies must remain Python 3.10+ standard library unless a reviewed design change explicitly changes the contract. Do not initialize a business ledger in this distribution repository.

Before proposing a change, run unit tests, check relative SKILL.md links, run the real skills CLI smoke test when network access is available, and benchmark material query changes. Add fixtures for both supported behavior and failure paths. Synthetic project markers test our adapters, not the corresponding engines or host agents.

New adapters must document detection evidence, canonical paths, sidecars, disposable caches, native reference generation and unsupported dependency semantics. Do not infer a complex asset class from a package suffix. Never rename native assets as part of discovery.

Card schema changes need compatibility tests and a reversible migration plan. Keep cache formats replaceable and project IDs stable. Avoid new always-loaded text in SKILL.md: route to a reference for uncommon operations. Benchmark claims must include fixture size, environment, whether interpreter startup is included, and the measured operation.

Stable releases use semantic versions in `VERSION`, Skill metadata and marketplace metadata. Update release notes and tests together. CI publishes only from a tested main commit, never overwrites an existing release, and emits ZIP archives plus a SHA-256 checksum manifest. Changes to licensing, permissions, remote storage or organizational policy require the repository owner's explicit decision rather than a silent default.
