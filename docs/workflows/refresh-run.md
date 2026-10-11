# Run-Bound Product Refresh

`scripts/pipeline/commands/ops/refresh_run.py` is the sole production control
plane for S-84. It turns a product refresh into one locked, resumable run whose
inputs and evidence cannot be inferred from another execution.

## Commands

```bash
.venv/Scripts/python scripts/pipeline/commands/ops/refresh_run.py start FAMILY PLATFORM \
  --mode upstream|remediation|combined [--scope-manifest PATH] [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/ops/refresh_run.py run --run-id ID
.venv/Scripts/python scripts/pipeline/commands/ops/refresh_run.py resume --run-id ID
.venv/Scripts/python scripts/pipeline/commands/ops/refresh_run.py status --run-id ID
.venv/Scripts/python scripts/pipeline/commands/ops/refresh_run.py verify --run-id ID
.venv/Scripts/python scripts/pipeline/commands/ops/refresh_run.py recover \
  --run-id ID --reason TEXT
.venv/Scripts/python scripts/pipeline/commands/ops/refresh_run.py bind-commit \
  --run-id ID --commit SHA
.venv/Scripts/python scripts/pipeline/commands/ops/refresh_run.py abandon \
  --run-id ID --reason TEXT
```

Mutation requires a session identity. Resolution order is explicit
`--session-id`, `AGENT_SESSION_ID`, then `CODEX_THREAD_ID`; absence or ownership
ambiguity blocks.

## State model

```text
CREATED -> INPUTS_PINNED -> PLANNED -> APPLYING
        -> VALIDATING -> READY_TO_COMMIT -> COMMITTED
```

Any non-terminal state can enter `BLOCKED` with a durable `resume_state`.
`ABANDONED` is terminal. The product lock and `ACTIVE.json` pointer prevent two
live runs for the same family/platform. Resume rechecks scoped working-file
hashes. Each writer stages its final candidate, validates the factual gates,
and emits an immutable receipt plus page decision before changing the real
content path. A crash therefore leaves either the pinned input bytes or
receipt-bound output bytes; resume accepts those two states and rejects every
other hash. `recover` is explicit and hash-gated: it accepts only paths still
matching the run output (or already restored during an interrupted recovery),
restores base bytes atomically, verifies the pinned input hashes, and
terminates the run as `ABANDONED`. It refuses to delete paths absent from the
base.

## Run artifacts

Artifacts live under:

```text
reports/refresh_runs/{family}/{platform}/{run_id}/
  manifest.json
  events.jsonl
  scope.json
  planning/{family}/{platform}/
  staging/content/
  page_decisions.jsonl
  receipts/
  stages/*.result.json
  stages/*.stdout.log
  stages/*.stderr.log
  validation.json
  validation/attempt-NN/
```

Reports are local operational state, not content truth. The manifest pins the
Git base and source/model SHAs. Writers record intent and evidence. Commit
readiness is independently derived from Git body/frontmatter comparison, the
pinned source revision, current deterministic knowledge, and blocking
validators. The validation stage runs exact-run post-refresh verification,
S-23 content audit, scoped link validation, the refresh oracle, triage
confirmation, and SEO stability. Any non-PASS result blocks commit readiness.
Every page decision contains exactly three required validator results:
`receipt`, `forbidden_claims`, and `regrounding`. The stage and validation
result files, their redacted logs, and all result/log digests are manifest
bound; missing, extra, duplicate, or altered attempt evidence blocks readiness.

Schema-v2 and older manifests, migrated product-level `page_decisions.json`,
and historical receipts are `legacy_unbound`. They may be used with an explicit
`post_refresh_verify --base REF` forensic analysis, but never for a commit
verdict. `migrate_schema_version.py --apply` and the old partial
`refresh_run_manifest.py` writer are disabled; changing legacy artifact shape
does not make its meaning trustworthy.

## Commit contract

One run owns one product and one content commit. Pipeline-code changes land
separately. The content commit must include every run decision that claims a
file change and may contain only paths in the pinned run scope
and must include:

```text
Refresh-Run: ID
Refresh-Base: SHA
Refresh-Source-SHA: SHA
```

Each required trailer must occur exactly once in the final Git trailer block;
matching subject/body prose is not accepted. `bind-commit` compares the
checkout-filtered committed bytes to the receipt's raw `new_hash` as well as
the normalized body and frontmatter hashes. After the local commit, use
`bind-commit`. Do not push from S-84. Roll back an already committed refresh
with `git revert`; never reset.
