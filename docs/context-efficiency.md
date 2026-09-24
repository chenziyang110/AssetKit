# Context cost is an interface contract

AssetKit 1.1 optimizes the text and interactions exposed to the Agent, not just JSON whitespace. Runtime remains standard-library-only and local. Instructions must be sufficient for correct task selection; blindly minimizing words can increase errors and retries.

## Layers

| Layer | Design |
|---|---|
| Idle | Short bilingual routing description; unrelated code tasks do not activate the skill |
| Activation | One compact SKILL.md with common path and exception-specific references, not a manual-reading chain |
| Input | `python .assets/ak.py`; exact output path + one purpose; reuse existing JSONL manifests outside model context |
| Discovery | Default top 3 with purpose/path and current bounded checks; direct get for a known asset |
| Returns | Brief JSON, omitted empty/noise fields, collision-checked short refs, row-boundary pagination |
| Batch | Count successes, locate failures by input index; full historical receipts remain on disk |
| Maintenance | No-op unchanged captures; verify a timestamp-only change once without withdrawing review |
| Recovery | Do not assume old model context still exists; stable refs are resolvable again |

Both command input and output count. A short result reached via several confused retries is not a win. The benchmark counts both, including JSONL content. Host wrappers and model reasoning require separate real-host measurement.

## Safety does not buy a smaller budget

A reply never silently discards rights notes or declared dependency restrictions while keeping `usable:true`. If a complete candidate cannot fit, it returns `DETAIL_REQUIRED` with reuse blocked. Oversized detail requests fail explicitly; selected metadata is not approval. Missing dependencies, cycles, graph bounds and hash budgets fail closed. Results are asset data, not injected instructions. File stat evidence is cacheable; an authorization outcome is not.

Use `--summaries` when lightweight discovery is enough; this deliberately defers verification. Default `find` verifies the returned candidates, saving a normal find→resolve chain. This may read up to three relevant cards and their bounded dependencies; it does not falsely promise zero reads while doing verification. Ordinary no-match and summaries-only warm searches read no card files. SQL may still examine index rows; this is not a constant-time search guarantee.

## Budgets and measurement

Compact replies include their final newline in the UTF-8 byte cap. No runtime tokenizer is required. A byte cap is not a universally exact token cap; use the actual provider's usage data for billing. Development-only `tiktoken==0.12.0` counts visible strings with cl100k_base and o200k_base so regressions are measurable without calling a model. Neither is claimed to be Claude's tokenizer or every current model's tokenizer.

To reproduce against the released baseline:

```bash
mkdir -p /tmp/assetkit-v1
# In a clone with the v1.0.0 tag fetched:
git archive v1.0.0 | tar -x -C /tmp/assetkit-v1
python tools/context_benchmark.py --baseline /tmp/assetkit-v1
# Development-only token counts (not needed by consumers):
python -m pip install tiktoken==0.12.0
python tools/context_benchmark.py --baseline /tmp/assetkit-v1 --tokenizers
```

Setup is excluded. Static files are reported separately; each workflow counts actual stdout and the command/input text needed to obtain it. Batch acknowledgement does not require all IDs in model context; requesting a receipt adds cost. The three-candidate comparison requires checking three candidates, not silently choosing the first. CLI operations are not inherently model turns: a host can group shell operations. No end-to-end LLM success/latency, bill, token-cache hit rate or universal savings percentage is claimed.

## Host-level optimization still belongs to the host

Preserve a stable instruction prefix and append dynamic task state instead of rewriting it on every turn; provider prompt-cache behavior is host/model specific. Cached input can still occupy a context window, so prompt caching is not a substitute for fewer visible tokens. Hooks can dispatch deterministic registration without asking an LLM to repeat paths, but this release does not automatically install host hooks or infer permission/provenance. Delegating to another agent is not free: account for its input/output too.

Next real-host evaluation should measure tool calls, prompt/completion/cached tokens, resource reuse correctness, retries and human interventions on matched tasks. Do not report the fixed transcript benchmark as that evaluation.

## Primary references

- Agent Skills progressive disclosure: https://agentskills.io/specification
- Tool consolidation and meaningful compact responses: https://www.anthropic.com/engineering/writing-tools-for-agents
- Provider prompt-cache boundaries: https://developers.openai.com/api/docs/guides/prompt-caching
