---
name: baseline-ledger-writer
id: S-111
description: >
  Maintain the append-only baseline SHA ledger for a product and resolve a git-reachable baseline for a refresh, implementing the real orphaned-SHA walkback. Replaces the single mutable model.yaml.repo_sha scalar with durable history.
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-111: Baseline Ledger Writer — Append-Only Baseline SHA History

<!-- CONTRACT
purpose: Append-only baseline SHA history per product + git-reachable baseline resolution with real orphaned-SHA walkback
inputs: family, platform; new_repo_sha + sha_source + run_id (append); the FOSS clone path (resolve)
outputs: knowledge/{family}/{platform}/merged/baseline_ledger.jsonl (append-only) + baseline_ledger_head.json (O(1) cache); a resolved (sha, source) or an explicit ORPHANED_BASELINE
preconditions:
  - knowledge/{family}/{platform}/merged/ exists (or is creatable)
  - schema 5a (validate_baseline_ledger_entry) governs every appended row
postcondition: exactly one new ledger row per accepted SHA change (zero if unchanged); head cache updated
forbidden_paths: does NOT edit model.yaml, content/, or any page; ledger rows are never mutated or reordered (append-only, CI-enforced)
deterministic_or_llm: fully deterministic (no LLM)
idempotent: yes (re-appending the current accepted head is a no-op)
evidence: baseline_ledger.jsonl rows; provenance report (reports/baseline_migration/provenance.json for backfill)
stop_conditions: OrphanedBaselineError (no reachable baseline) — surface, never a silent empty diff
downstream: S-12 knowledge-diff (consumes resolve_baseline_sha); truth-merge/S-14 promote.py (appends on promote)
verified: '2026-07-17'
-->

## Purpose

Give every product a durable, append-only baseline SHA history instead of the single mutable
`model.yaml.repo_sha` scalar (which `promote.py` overwrites every run). Resolve the baseline a
refresh should diff against, including the **real** orphaned-SHA recovery for the force-push/rebase
case (previously documented but never implemented — plan §2.3 found 0 implementations).

## When to use

- On every knowledge promotion (`truth-merge`/S-14 calls the ledger before the `model.yaml` rewrite).
- Before a `knowledge-diff` (S-12) run, to resolve which baseline SHA to compare current HEAD against.
- Once per product, at migration time, to backfill history that predates the ledger (see Steps 3).

## Steps

1. **Append a baseline row** (deterministic, schema-validated):
   ```python
   from lib.baseline_ledger import BaselineLedger
   BaselineLedger(family, platform).append(
       run_id=..., new_repo_sha=..., sha_source="scout"|"manual-recovery"|"orphaned-recovered",
       status="accepted", accepted_at=<iso8601>, prior_repo_sha=<previous head or None>)
   ```
   Re-appending the current accepted head is a no-op. Every row is validated by
   `validate_baseline_ledger_entry` (schema 5a) before write; an invalid row is refused, not written.

2. **Resolve a baseline SHA** for a refresh (real orphaned-SHA walkback):
   ```python
   from lib.baseline_resolver import resolve_baseline_sha, git_reachable, OrphanedBaselineError
   res = resolve_baseline_sha(family, platform, reachable=git_reachable(clone_path),
                              model_repo_sha=<pre-migration fallback>)
   # res.source: "ledger" | "model-yaml" | "orphaned-recovered"
   ```
   Or the CLI: `.venv/Scripts/python scripts/pipeline/lib/baseline_resolver.py {family} {platform} --repo-path <clone>`
   (exit 3 = ORPHANED_BASELINE). Never treat an unresolvable baseline as "no changes".

3. **Backfill** (one-time, for products predating the ledger):
   ```bash
   python scripts/pipeline/commands/knowledge/migrate_baseline_ledger.py [--apply]
   ```
   Classifies each active product CONFIRMED / RECONSTRUCTED / UNCERTAIN / NO_BASELINE — never
   silently CONFIRMED (plan §13). Default is dry-run; `--apply` writes rows.

## Output

- `knowledge/{family}/{platform}/merged/baseline_ledger.jsonl` — append-only history (schema 5a).
- `baseline_ledger_head.json` — O(1) current-head cache.
- `reports/baseline_migration/provenance.json` — backfill provenance classification.

## Notes

- Concurrency: `append()` takes a real exclusive lock (`O_CREAT|O_EXCL` sidecar, stale-lock steal) —
  the first working concurrency-control primitive in this pipeline (plan §2.5 SW-1).
- Append-only is CI-enforced: a diff that removes or reorders a prior row fails the pre-commit gate.
- Backing code: `scripts/pipeline/lib/baseline_ledger.py`, `baseline_resolver.py`,
  `commands/knowledge/migrate_baseline_ledger.py` (all registered, tested).
