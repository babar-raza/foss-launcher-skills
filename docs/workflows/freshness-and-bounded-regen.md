# Freshness Guard & Bounded Automatic Regeneration (FRESH-001)

> Added: 2026-08-14 (FRESH-001 — source-freshness / fact-freshness system, following the
> cells/net stale-facts incident: local clone cache 2 commits behind live upstream,
> generated facts (`formats.md`, `api_surface.json`) stale for ~1 month with no detection)
> Companion docs: [knowledge-bundle-recovery.md](knowledge-bundle-recovery.md), [knowledge-git-tracking-migration.md](knowledge-git-tracking-migration.md)

## Root cause this fixes

Every consumer of `knowledge/{family}/{platform}/merged/` independently read
`model.yaml["stale_since"]` and treated `None` as "safe to use" — a cached boolean
only ever updated by a human/agent remembering to run `/knowledge-diff`. The one
mechanism that *did* automatically detect drift (`upstream-monitor.yml`, weekly cron)
correctly fired for 11 consecutive Mondays but filed a generic, undifferentiated,
non-deduplicated issue that never named the affected product — alert fatigue, not a
real gate. See the FRESH-001 mission's final report for the full root-cause taxonomy
(symptom vs. root cause vs. structural weaknesses).

## `freshness_guard.py` — the single source of truth

`scripts/pipeline/lib/freshness_guard.py`. Every gate that used to read `stale_since`
directly now calls this instead: `batch_reference.py`, `refresh_run.py`
(`_model_state()`), `launch_gate.py` (L-01/L-06), `readiness_gate.py` (G-04).

### States

| State | Meaning |
|---|---|
| `CURRENT` | Resolved baseline matches (mode-dependent: durable sources agree, or live upstream) |
| `STALE` | A local `stale_since` flag is set (degraded), or the live upstream HEAD differs (strict) |
| `REFRESHING` | A `knowledge_regen_lock` is currently held for this product |
| `REFRESH_FAILED` | A previous regen attempt failed after acquiring the lock (`.regen_failed` marker) |
| `UPSTREAM_UNAVAILABLE` | Strict mode's live `git ls-remote` failed (network/auth/timeout) — **never** silently downgrades to a stale-local comparison |
| `PROVENANCE_MISSING` | No `merged/model.yaml`, or no baseline SHA resolvable from any source |
| `CORRUPT` | The durable baseline sources disagree with each other, or `bundle_manifest.json` fails self-verification |
| `LAST_KNOWN_GOOD` | Explicit opt-in fallback (see below) |

### Modes

- **`strict`**: requires `bundle_manifest.json` present with `status: COMPLETE`; requires
  the durable sources (`model.yaml`, `data/upstream_baselines.json`,
  `data/knowledge_state.json`) to *agree* (disagreement → `CORRUPT`, never "pick one" —
  the direct fix for a real, confirmed bug class: `migrate_baseline_ledger.py`'s backfill
  once wrote a fabricated placeholder timestamp for cells/net instead of consulting the
  real value sitting next to it). Does one cheap read-only `git ls-remote {repo_url} HEAD`
  against live upstream (no clone/fetch).
- **`degraded`** (the default for generation-time callers): same as strict minus the live
  network call. Resolves purely from durable/local source agreement plus the local
  `stale_since` flag. Bounds network cost for high-volume callers.
- **`offline`**: `resolve_baseline()` only, no cross-source check, no network. For
  read-only status/reporting CLIs that must never fail or hang.

### `resolve_baseline()` — the collapsed single-writer model

`merged/model.yaml` is now git-tracked (see
[knowledge-git-tracking-migration.md](knowledge-git-tracking-migration.md)) and is the
**one canonical writer** of "accepted baseline SHA". `data/upstream_baselines.json` and
`data/knowledge_state.json` are **regenerated projections**
(`scripts/pipeline/commands/ops/regen_baseline_projections.py`), not independent
beliefs — `rebuild_one()` runs at `promote.py`'s acceptance choke point (replacing the
old ad hoc MT030 dual-write), and `rebuild_all()`/`check-staleness` are the standalone
full-fleet reconciliation path. Because the projections are *derived*, they cannot
disagree with the source by construction — only be *stale relative to it*, which is
trivially detected and fixed.

Resolution order: `model.yaml.repo_sha` → `data/upstream_baselines.json` →
`data/knowledge_state.json` → local `baseline_ledger_head.json` → `evidence.model_sha`
sampled from committed content frontmatter (last resort, reused from
`baseline_resolver.py`, for products that predate this mechanism).

### `LAST_KNOWN_GOOD` — the one intentional stale-fallback

`is_generation_allowed(..., allow_last_known_good=True)` permits falling back to the
last successfully-generated bundle when the state is `UPSTREAM_UNAVAILABLE` or
`REFRESH_FAILED` and a prior bundle exists. **Opt-in only** (default `False`). Every
use is appended to `reports/freshness_guard/last_known_good.log.jsonl` for audit.
**Launch and readiness gates are hard-configured to never pass this flag.**

## Locking: `knowledge_regen_lock.py`

`scripts/pipeline/lib/knowledge_regen_lock.py` — a thin, owner-labelled wrapper over
the existing, tested `advisory_lock.FileLock`. Lock path:
`knowledge/{family}/{platform}/merged/.regen.lock` (gitignored). Guards the **whole**
scout→enrich→promote→index chain, wired into `refresh_knowledge.py`'s `refresh()` —
the single convergence point every caller (manual `/knowledge-update`, `refresh_run.py`
subprocess, S-90's skill-level invocation, the scheduled bounded-auto-regen path) goes
through. **Fixed acquisition order** (documented to prevent deadlock): this lock is
always acquired before `refresh_run.py`'s own content-refresh lock, never the reverse.

## Closed-loop scheduled detection: `upstream-monitor.yml`

Weekly cron (Monday 08:00 UTC) + `workflow_dispatch`. Rewritten flow:

1. `check_upstream_drift.py` — cheap, GitHub-API-only detection (no clone-cache
   touch). Issue filing is now **testable Python** (`--file-issues`), not inline
   workflow JS: one issue **per** `(family, platform)`, deduped by label pair
   (`upstream-drift` + `product:{family}-{platform}`) — a repeat finding comments on
   the existing issue instead of creating a duplicate. `data/upstream_drift_state.json`
   (git-tracked) persists per-product level/SHAs/`consecutive_weeks_flagged`.
2. On drift: `repo_patrol.py sweep` (existing S-94 mechanism, unchanged internals) —
   now actually scheduled, not just "run weekly" in a SKILL.md nobody enforces.
3. `bounded_auto_regen.py select` — the bounded selector (see below).
4. **`data/fleet_freshness_snapshot.json`** (git-tracked) persists the sweep's compact
   per-product SHA table, committed via `git_plumb_commit.py` (this repo's sanctioned
   CI-safe, non-interactive, isolated-index commit path — never raw `git commit`).

## Bounded automatic regeneration policy

`scripts/pipeline/commands/ops/bounded_auto_regen.py`. The reason full automation felt
unsafe before this mission is exactly the root cause above: automating writes to a
gitignored local cache that vanishes per-session is genuinely unsafe and unauditable.
**Once `knowledge/merged/` is git-tracked, automatic regeneration becomes safe to fully
automate, because every automated write is a normal, diffable, revertable git commit.**

Selection rules (`select_candidates()`, pure function, fully unit-tested):
- **HIGH impact never auto-regenerates.** Always routes to the named, deduped issue —
  that is precisely where a wrong published claim is costliest and where LLM
  enrichment spend is largest.
- LOW/MEDIUM impact only, capped at `MAX_AUTO_REGEN_PER_RUN = 3` per scheduled run,
  **oldest-flagged-first** (highest `consecutive_weeks_flagged`) so a long-drifting
  product isn't perpetually starved by newer findings.
- Regen-lock contention **skips** the product for this run (never blocks).

`run()`'s regen/lock/commit callables are injectable — tests never invoke the real
S-12→S-14 chain or `git_plumb_commit.py`.

### Rollout status (as of 2026-08-14 — read this before assuming it is live)

The **selector** (`bounded_auto_regen.py select`) runs in the scheduled workflow today
in **observability-only mode** — its JSON selection decision is printed to the workflow
log, but wiring `select`'s output into a live regen-and-commit loop inside
`upstream-monitor.yml` is **intentionally deferred**, pending explicit maintainer
sign-off, until the pilot (see
[knowledge-git-tracking-migration.md](knowledge-git-tracking-migration.md)'s pilot
section) has run and been reviewed at least once. This is not a hedge walking back the
design — the design's own dependency ordering says the closed loop should only go live
"after the pilot has proven the chain end-to-end under human supervision first," and
that pilot ran this session (cells/net, cells/go, font/python — see the FRESH-001
mission's final report for the full proof). Enabling the live loop is a follow-up PR.

## Migration status of the 4 gate call sites

Migrated low-to-high blast radius, each with a behavioral-equivalence test
(`test_freshness_guard_migration.py`) before the next: `batch_reference.py` →
`refresh_run.py` → `launch_gate.py` → `readiness_gate.py`. All four now call
`freshness_guard.is_generation_allowed(mode="degraded")` (matching each site's
pre-existing no-network-call behavior) rather than reading `stale_since` directly.

## Honest limitation: LLM enrichment determinism

`enrich.py` calls an LLM. Even pinned to the exact same source commit, exact wording
of enriched claims can vary between reruns. This mechanism makes the **structural**
parts fully deterministic and provable (which source commit was used, whether the
bundle is internally self-consistent, whether validation passed) — it does not, and
cannot without a much larger separate investment (pinned model version, temperature=0,
fixed prompt hash), guarantee bit-identical enriched-claim prose across reruns at the
same commit. The pilot runs this session used `--skip-enrich` specifically to keep the
proof scoped to the freshness/atomicity/locking mechanism itself, not enrichment
quality.
