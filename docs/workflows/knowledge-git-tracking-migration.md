# Knowledge Git-Tracking Migration (FRESH-001)

> Added: 2026-08-14 (FRESH-001 — source-freshness / fact-freshness system)
> Companion docs: [knowledge-bundle-recovery.md](knowledge-bundle-recovery.md), [freshness-and-bounded-regen.md](freshness-and-bounded-regen.md)

## Why

`knowledge/` was entirely gitignored (`.gitignore:20`, `/knowledge/*`, except the
pre-existing `/knowledge/_overrides` carve-out). This meant no generated fact bundle
(`model.yaml`, `api_surface.json`, `formats.md`, `claims.json`) had any git history,
diffability, blame, or cross-session/cross-machine durability — the structural root
cause behind the cells/net stale-facts incident and behind every compensating
workaround this mission found (`data/upstream_baselines.json`, `data/knowledge_state.json`,
`baseline_ledger.jsonl`, the whole `stale_since` mechanism). Those workarounds are
symptoms; the missing durable substrate is the disease.

`knowledge/{family}/{platform}/merged/` (the actual fact bundle — the source-of-truth
hierarchy's priorities 2–5 per AGENTS.md §2a) is now git-tracked. `_vectors/`
(regenerable embeddings, 627M measured 2026-08-14 — 78% of `knowledge/` by itself),
`scout/` (intermediate/pre-merge, regenerable by rerunning `scout.py` at the pinned
commit), and local run-bookkeeping stay gitignored.

## Classification policy

`scripts/pipeline/config/knowledge_tracking_policy.yaml` — every KEEP/DROP decision is
a declarative glob pattern, not logic buried in a script, so it can be corrected with
evidence without a code change. `scripts/pipeline/commands/ops/knowledge_git_migration.py`
enforces it and is the **only** thing that should ever add/remove `knowledge/` file
patterns to/from `.gitignore` (keep the two in sync manually when the policy changes —
there is no automated sync between them, by design, to keep `.gitignore` reviewable in
a normal diff).

**Fail-closed**: any file matching neither `keep_patterns` nor `drop_patterns` is
reported as `UNCLASSIFIED` and left **completely untouched** — never silently tracked,
never deleted. `audit` exits 1 if any unclassified files are found. This caught 22 real
unclassified files (7 products: `merged/format_delta.json`, `merged/manifest_delta.json`,
`merged/conflict_receipts.jsonl`, `merged/merge_conflicts.json`/`.md`,
`merged/workarounds.json`, `merged/test_context.md`) during the 2026-08-14 fleet audit —
the policy was updated to classify them (all DROP; see the policy file's own comments
for the reasoning per file) before relying on the audit fleet-wide.

**Never deletes anything.** "Clean up" means narrowing what's tracked *going forward*,
not removing files from disk — a DROP classification leaves a file exactly where it is
(already gitignored today, so this is a strict no-op for DROP items). Genuine on-disk
deletion of confirmed-redundant files is a separate, explicit, DGR-governed step per
AGENTS.md §11a — not bundled into this migration.

## CLI

```bash
# Dry-run classification report across every product with local knowledge/ present:
python scripts/pipeline/commands/ops/knowledge_git_migration.py audit
python scripts/pipeline/commands/ops/knowledge_git_migration.py audit --products cells/net,cells/go
python scripts/pipeline/commands/ops/knowledge_git_migration.py audit --json --out report.md

# git add (never commit) the KEEP-classified files for named products only:
python scripts/pipeline/commands/ops/knowledge_git_migration.py apply --products cells/net,cells/go,font/python
```

`apply`'s `git add` calls retry with backoff (5 attempts, 0.2s × attempt) — a real
transient failure (AV/indexer handle contention on a freshly-written file) was observed
live during the 2026-08-14 pilot and silently dropped 4 of 100 snippet files from the
first `apply` pass before this was added.

## Fleet numbers (measured 2026-08-14, all 31 active products, after policy fix)

- Would newly track: **71,657,993 bytes (~71.7 MB)**
- Stays gitignored: **99,967,032 bytes (~100.0 MB)**
- Unclassified: **0 files** (policy fully covers the observed fleet)

For scale: `.git` was 843M (689.65 MiB packed) before this migration — the tracked
addition is a meaningful but proportionate increase, not a multiplier, once vectors and
scout/ are correctly excluded.

## Rollout status (as of 2026-08-14)

**Applied** (staged, not committed — see the FRESH-001 mission's confirmed session
scope) for the 3 pilot products: `cells/net`, `cells/go`, `font/python` (160 files,
123,854 insertions). These were also the 3 products regenerated end-to-end this
session — see [freshness-and-bounded-regen.md](freshness-and-bounded-regen.md) and the
FRESH-001 mission's final report for the full proof (STALE → locked/atomic regen →
`bundle_manifest.json` COMPLETE → `freshness_guard(mode="strict")` CURRENT).

**Not yet applied** for the remaining 28 products. This is a deliberate, bounded scope
decision (the mission's own cost/time realism framing), not an oversight — the
migration mechanism is generic and already proven correct across the full fleet in
dry-run (`audit`, 0 unclassified across all 31). Rolling out `apply` to the remaining
28 is a mechanical follow-up:

```bash
python scripts/pipeline/commands/ops/knowledge_git_migration.py apply \
  --products 3d/java,3d/net,3d/python,3d/typescript,barcode/python,cells/cpp,cells/java,\
cells/python,cells/rust,cells/typescript,email/cpp,email/net,email/python,html/python,\
note/python,page/python,pdf/cpp,pdf/go,pdf/java,pdf/net,pdf/python,slides/cpp,slides/java,\
slides/net,slides/python,tex/python,words/net,words/python
```

Run this **after** each product's knowledge is confirmed `CURRENT`
(`freshness_guard.check_freshness(mode="strict")`) — tracking a bundle that is already
known-stale just commits stale data with a false sense of durability. The 15 products
the 2026-08-14 fleet audit found genuinely `STALE` are filed as `backlog/inbox.md`
rows `SW-025` through `SW-039` — regenerate via `/knowledge-update` first, confirm
`CURRENT`, then apply the migration for that product.

## What was deliberately NOT unified

The write-*paths* of `data/upstream_baselines.json` / `data/knowledge_state.json` /
`baseline_ledger.jsonl` are unchanged — only their *read order* (see
`freshness_guard.resolve_baseline()` in
[freshness-and-bounded-regen.md](freshness-and-bounded-regen.md)). `promote.py`'s
existing MT030 dual-write choke point is left as-is at the write layer; only its
*consumer* (`regen_baseline_projections.rebuild_one()`, called from the same choke
point) changed. Full write-path consolidation is a larger, riskier refactor explicitly
out of scope for this pass.
