---
name: change-sweep
id: S-94
description: >
  Run a batch SHA comparison across all active launched products to detect upstream repository changes with HIGH/MEDIUM/LOW impact classification and produce a structured sweep report.
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-94: Change Sweep -- Batch SHA Comparison

<!-- CONTRACT
purpose: Batch SHA comparison across all active launched products; detect upstream changes with impact classification
preconditions:
  - data/products.json exists with active launched products
  - Clone cache populated (runs/.clone_cache/) or network available to fetch
  - MT074 fleet step only: GitHub API access (GH_TOKEN) or --offline fixtures; no clones needed
postcondition: reports/discovery/sweep_report.json created; reports/discovery/history/ updated;
  MT074 fleet step also writes reports/fleet/drift_ledger.json|md and, with --update-state, only the
  DRIFT fields of data/content_propagation_state.json (never a propagation field); with --file-issues,
  one keyed FLEET-PROPAGATE-{family}-{platform} issue per drifted product
idempotent: yes (sweep itself only fetches upstream clones; the fleet step is deterministic and a
  re-run with unchanged upstream produces no state diff and no new issues)
verified: '2026-10-07'
-->

## Purpose

Run a batch SHA comparison across all active launched products to detect upstream repository changes with HIGH/MEDIUM/LOW impact classification and produce a structured sweep report.

## When to use

Run weekly or before a knowledge refresh session to identify which products have upstream
changes that require documentation updates.

## Steps

1. Run the sweep:
   ```bash
   PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/diagnostics/repo_patrol.py sweep
   ```
   This fetches upstream for all active launched products and compares SHAs.

2. Read the report:
   ```bash
   cat reports/discovery/sweep_report.json
   ```
   Or generate the markdown summary:
   ```bash
   PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/diagnostics/repo_patrol.py report
   cat reports/discovery/combined_report.md
   ```

3. Route findings using /discovery-triage (S-95).

## MT074: Fleet drift step (clone-free) and discovery stages L1-L4

Added by mission MT074 (the existing steps above are unchanged). `repo_patrol.py sweep` clones every
product; the fleet step answers the same question without cloning anything and also records it in
tracked state, so drift cannot disappear after a knowledge-only refresh.

### F1. Fleet drift (L1, clone-free) -- run this first

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/diagnostics/fleet_drift.py \
  [--products F/P ...] --json-out reports/fleet/drift_ledger.json --md-out reports/fleet/drift_ledger.md \
  --sweep-out reports/discovery/sweep_report.json --check-projections --update-state
```

- **What it does:** for every active product in `data/products.json`: `git ls-remote` HEAD, the GitHub compare API from the knowledge SHA (paginated; a truncated compare forces deep analysis), and the release state from `data/package_registry.json` (add `--probe-registry` for a live registry probe). Tiers: `NO_CHANGE | NON_SOURCE | SOURCE | API_TOUCHED | UNKNOWN`, decided by the per-language path rules in `scripts/pipeline/config/language_api_paths.yaml`. `UNKNOWN` is the safe default (unknown platform, truncation with no API file in view, orphaned baseline, rate limit or auth failure). Never guess a tier.
- **Outputs:** `reports/fleet/drift_ledger.json|md` (working copies, gitignored; volatile timestamps live under a `volatile` key), and a `sweep_report.json`-compatible file via `--sweep-out` so S-95 can consume it unchanged.
- **State updates:** `--update-state` writes the drift fields (and only those) of `data/content_propagation_state.json` through `content_propagation_state.record_drift`. The step never writes a propagation field; that belongs to `capability_surface_gate.py` at the close of S-84. A product with no record is `UNRECORDED`, which counts as drift.
- **Keyed issues:** `--file-issues --repo OWNER/REPO [--max-issues-per-run N]` files or updates one deduplicated GitHub issue per product, titled `FLEET-PROPAGATE-{family}-{platform}` (the upstream SHA goes in the body), and closes it when the product reaches `PROPAGATED`. Offline runs (`--offline DIR`) and `--dry-run` never touch issues or state.
- **Release trigger:** `--release-trigger F/P` refreshes one product's `release_state` from the already-updated registry and files or updates its issue. The registry-watch workflow calls it after a version bump or first publish; run it by hand after a release lands. A release-triggered candidate outranks a main-only one.
- **Exit codes:** 0 ok, 1 an issue operation failed, 2 configuration error. A product that is `UNKNOWN` is reported, never skipped silently.

### F2. Discovery stages L2-L4 (read-only; for products whose knowledge is NOT refreshed)

Run only after F1, and only for the products it flagged `API_TOUCHED`/`SOURCE` with a content gap worth checking, or when asked to rank the fleet.

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/diagnostics/propagation_analyze.py analyze \
  --out-dir reports/fleet/analysis [--products F/P ...] [--max-repos 8]
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/diagnostics/propagation_analyze.py rank \
  --analysis-dir reports/fleet/analysis --json-out reports/fleet/candidates.json --md-out reports/fleet/candidates.md
```

- **L2** deep analysis: capability units added since the baseline, computed from a pinned base and head with the shallow read-only path (a ground-truth tier `GT-1` from a language adapter, else `GT-2` file-level evidence, always shown). At most `--max-repos` products are analysed per run; the rest are recorded `DEFERRED`, never dropped.
- **L3** content-presence scan: English content only; a unit whose symbols are absent from docs, kb, blog and products is a content gap.
- **L4** ranking: release-triggered first, then `API_TOUCHED`, then unit count descending, then `family/platform` lexicographic. Deterministic: a re-run is byte-identical.
- The analysis never writes the propagation state, never checks anything out in a clone, and never refreshes knowledge. The matching criteria live in `scripts/pipeline/config/discovery_criteria.yaml` once frozen; never tune them in the same commit as a run.

Route the results with `/discovery-triage` (S-95). This skill still does NOT invoke S-84.

## Output

- reports/discovery/sweep_report.json -- structured JSON with impact classification
- reports/discovery/history/YYYY-MM-DD-sweep.json -- archived snapshot
- Impact levels: HIGH (source files changed), MEDIUM (undetermined), LOW (non-source only)

## Notes

- Sweep is read-only apart from the MT074 fleet step's own report/state/issue outputs. It does NOT set stale_since -- that is S-12 responsibility. Only `capability_surface_gate.py` (S-84 close step) can mark a product `PROPAGATED`.
- S-95 routes HIGH/MEDIUM findings to backlog items. LOW findings are logged only.
- This skill does NOT invoke S-84 (refresh). Route findings to S-95 first.
