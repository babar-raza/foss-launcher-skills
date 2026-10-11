# Evidence Bundle — readme-refresh-audit-baseline-pinning-hardening-2026-09-03

Mission contract: `mission_authority.yaml` (this directory)
Taskcards (schema 5f): `taskcards.jsonl` (this directory)
Backlog: ST-181 (corrected in place), ST-182 (this mission's own item, status `in-progress`),
ST-183 (deferred follow-on, filed) — all in `backlog/inbox.md`
Governing plan (assessment + design): `<local-plan-cache>/perform-a-deep-first-principles-sparkling-scroll.md`
Repository: `d:\onedrive\Documents\GitHub\aspose.org`, branch `main`
Baseline HEAD: `b46b08f583b13a9276d82d35bb5c21ea14b8869d` (unchanged throughout — nothing committed)

## Baseline (captured before any change)

- `git status --porcelain=v1 -uall` at session start: 21 pre-existing dirty files (data/keywords/
  knowledge state files, `scripts/pipeline/config/mission-ids.jsonl`, plus untracked SEO workflow
  files and `knowledge/html/python/merged/bundle_manifest.json`) — all pre-existing, unrelated to
  this mission, left untouched throughout.
- 3 other active sessions reported by the SessionStart hook (`8771024d`, `9d8aa2aa`, `bf995473`);
  `9d8aa2aa` is the recorded author of the parent mission
  `readme-refresh-pdf-typescript-scale-hardening-2026-09-03`'s hand-authored mission record —
  this mission's `allowed_paths` do not overlap any in-flight work observed in git status.
- Baseline test run, before any code change: `pytest scripts/pipeline/tests/test_readme_refresh_run.py -q`
  → **195 passed, 0 failed** (203.96s).

## Root-cause assessment (governing plan, produced this session, prior turn)

Independently re-investigated ST-181's own stated root cause (a flaky live-publication network
probe) and refuted it by direct code tracing (`publication_probe.py` is not in the failing call
path) and live PyPI re-verification. Traced the real mechanism to `_readme_matches_published_
upstream()`'s live, unpinned read of `clone_cache/README.md`, `pin_old_readme_baseline()` existing
but never invoked automatically, and `classify_target_authority()`'s mirror verdict being computed
and discarded once inline inside `push()`. Full assessment, evidence citations (file:line), and
target design in the governing plan file above. Backlog ST-181 corrected in place same session;
ST-182 filed with the corrected root cause and pointer to the design.

## Implementation (this session)

`scripts/pipeline/commands/foss/readme_refresh_run.py`:
- `_target_authority_path` / `_persist_target_authority` / `_load_persisted_target_authority` —
  persist `classify_target_authority()`'s verdict per product.
- `_auto_pin_old_readme_baseline_at_push` — automatic pin at `push()`'s `PUSHED` transition, keyed
  to `manifest["pinned_inputs"]["clone_cache_head"]`.
- `_BASELINE_COVERAGE_*` constants, `_latest_pushed_run_manifest`, `_ever_receipted_as_mirror`,
  `_classify_baseline_coverage`, `backfill_old_readme_baseline`, `audit_baseline_coverage` — the
  survey/backfill machinery (RRABP-01/05/06).
- `audit_portfolio` — new `verification_status` / `fully_verified` / `result_schema_version`
  fields, new `indeterminate` state, `disposition_tracking` kept as a deprecated alias.
- New CLI verbs `audit-baseline-coverage` and `backfill-old-readme-baseline`, wired into `main()`.
- `push()` — persists the authority verdict, auto-pins after `PUSHED`, records the auto-pin result
  onto the manifest.

`skills/readme-refresh.md` — CLI contract block updated (2 new verbs), new prose section
documenting the incident and the fix (matches this file's own established per-incident
convention). Provider mirrors (`.agents/skills/readme-refresh/SKILL.md`,
`.claude/commands/readme-refresh.md`, `.kilocode/skills/readme-refresh/SKILL.md`) synced via
`scripts/pipeline/commands/ops/sync_providers.py` — confirmed zero drift afterward
(`sync_providers.py --check` clean for readme-refresh).

`scripts/pipeline/tests/test_readme_refresh_run.py` — 19 new tests (14 covering the core
mechanism + 5 added after the independent review below, covering its findings specifically).

## Independent verification (adversarial, did not author the implementation)

Ran `/code-review high` (8 parallel finder agents: simplification, reuse, efficiency, angle-A
line-by-line diff, angle-B removed-behavior audit, altitude/architecture, conventions/governance,
angle-C cross-file trace) plus a manual live-execution discovery of my own (running the new
`audit-baseline-coverage` tool against the real portfolio surfaced a real gap independently of the
code-review pass). Findings and disposition:

| # | Finding | Severity | Disposition |
|---|---------|----------|--------------|
| 1 | `_auto_pin_old_readme_baseline_at_push` only caught `ReadmeRefreshRunError`, not the `OSError` family `pin_old_readme_baseline`'s own `mkdir`/`write_text`/`git show` calls can raise — could let a raw exception escape after `PUSHED` was already durably saved, making a successful push appear to fail | Real correctness bug, confirmed independently by 3 finder agents | **Fixed** — now catches `(ReadmeRefreshRunError, OSError)`, plus an outer `except OSError` guard |
| 2 | A corrupted/unreadable `old-readme-baseline.json` was misclassified as a protected manual pin, permanently blocking future auto-pins | Real correctness bug | **Fixed** — corrupt sidecar now treated as absent, safely re-pinned |
| 3 | `_persist_target_authority` used raw `write_text` instead of the module's own atomic `_write_json` helper, now invoked on every real push (not a rare manual call) | Real robustness gap, given this repo's documented concurrent-session hazards (ST-021) | **Fixed** |
| 4 | CLI's DIRTY loop double-printed an indeterminate product as `DIRTY family/platform: {}` right below its own dedicated INDETERMINATE line | Real UX/confusion bug | **Fixed** |
| 5 | `push()` discarded the auto-pin result entirely — even a clean no-op was invisible to callers | Real observability gap | **Fixed** — recorded onto the manifest, re-saved |
| 6 | **font/python's real push receipt records `target_authority: "mirror"` (2026-09-02, human-acknowledged), but a fresh `classify_target_authority()` call today reads `canonical`** — the PR that merged on top of the mirror's post-reset root gave HEAD a real parent, flipping one of the two AND-ed structural signals, even though `orphan_root_count` (still 12) proves the repo is still a periodically-resnapshotted mirror | **Most consequential finding** — discovered live, not synthetically, by running the mission's own new tool against real data; would have made font/python look safe to backfill | **Fixed** — new `_ever_receipted_as_mirror()` makes any historical mirror receipt sticky, never overridden by a later live re-read |
| 7 | Pinning is anchored at PUSH time only; a composed-but-not-yet-pushed ledger (AWAITING_REVIEW) has no equivalent protection if the clone cache is externally refreshed before `approve()` | Real, deeper structural finding — no confirmed live incident of this class yet (unlike #6) | **Deliberately deferred**, filed as backlog ST-183 rather than expanding this mission's scope reactively |
| 8 | Several duplication/reuse findings (a `git show <sha>:README.md` snippet appears 3x; active-product target-selection appears 4-5x across the file; `disposition_tracking`/`verification_status` store the same value twice; enum-like state groups handled inconsistently as constants vs. raw strings) | Code-quality, not correctness | **Deliberately not fixed** — pre-existing patterns in most cases, no confirmed defect, out of this mission's stated scope; noted here for a future cleanup pass, not silently dropped |

All 6 real findings (1-6) were fixed in this same execution cycle and re-verified (see below).
Finding 7 is tracked, not silently dropped. Finding 8 is disclosed, not silently dropped.

## Verification (after every fix, cumulative)

```
pytest scripts/pipeline/tests/test_readme_refresh_run.py -q
  → 209 passed (0 regressions) after the core RRABP-01..06 implementation
  → 214 passed (0 regressions) after the independent-review hardening fixes + 5 new regression tests
pytest scripts/pipeline/tests/test_readme_refresh_checks.py -q
  → 802 passed (untouched sibling suite, sanity-checked, unaffected)
```

New regression tests directly reproduce: the exact font/python historical-mirror-vs-live-reclassification
scenario (`test_a_historical_mirror_receipt_is_sticky_even_when_a_fresh_reclassification_says_canonical`),
corrupt-sidecar recovery, `OSError` non-propagation from the advisory pin step, the manifest-visibility
fix, and the CLI dedup fix. The original core regression test
(`test_pin_then_audit_content_units_extracted_against_pinned_commit_not_live_head`) reproduces the
exact ST-181/ST-182 mechanism end to end: push (auto-pins) → mutate `clone_cache/README.md`
afterward → `_resolve_old_readme_text` still returns the pinned, pre-mutation text.
`test_audit_portfolio_reruns_are_stable_after_drift_once_pinned` directly proves the original
"true→false flip across reruns" symptom is closed (byte-identical `verification_status` across two
consecutive calls, post-pin, despite live drift underneath).

## Real-world (not just fixture) validation

Ran the new `audit-baseline-coverage` survey against the real, live portfolio (32 active products):

```
counts: {'no_push_yet': 26, 'pinned': 3, 'recoverable_unpinned': 2, 'unrecoverable_unpinned': 1}
font/python:  unrecoverable_unpinned — "mirror-classified target (currently or at a past push)"
tex/python:   recoverable_unpinned  — pinned_clone_cache_head 2f4bfab3863e66ef32868f5464685eb4c2d36911
3d/python:    recoverable_unpinned  — pinned_clone_cache_head d9f3bfe50d47e8156266955dda52ec5abf2d9dec
```

Cross-checked tex/python's and 3d/python's real push receipts before backfilling: both genuinely
recorded `target_authority: "canonical"` at push time (no mirror risk) — reviewed, then backfilled
for real via `backfill-old-readme-baseline`:

```
tex/python -> baseline_commit 2f4bfab3863e66ef32868f5464685eb4c2d36911 (backfilled)
3d/python  -> baseline_commit d9f3bfe50d47e8156266955dda52ec5abf2d9dec (backfilled)
```

Post-backfill, real `audit-portfolio` runs:

```
tex/python: 1/1 ALL HARD GATES CLEAN, 1/1 REAL disposition-tracking verification
             (the ST-181-style flood does NOT reproduce once the reference frame is pinned)
3d/python:  1/1 ALL HARD GATES CLEAN, correctly skipped_published (unrelated, pre-existing
             MT053 mechanism firing normally — 3d/python's own candidate already matches live
             upstream)
```

font/python deliberately left `unrecoverable_unpinned` — no safe local commit to trust, per the
sticky-mirror fix. This is the correct outcome, not an unfinished one: font/python's disposition
ledger recomposition remains a separate, deferred mission (as scoped from the start), and this
mission's job — closing the wiring gap and correctly identifying which products are/aren't safe to
trust — is complete for it.

## Idempotency / rerun proof

`test_push_auto_pin_is_idempotent_on_retry` proves a second auto-pin attempt for the same commit
is a true no-op (byte-identical sidecar). `test_audit_portfolio_reruns_are_stable_after_drift_once_pinned`
proves two consecutive `audit_portfolio()` calls against an unchanged, pinned product report
byte-identical `verification_status`. Re-running `audit-baseline-coverage` a second time against
the real portfolio (not included verbatim above, but performed) returned identical counts to the
first, confirming no partial/duplicate state from the real backfill runs.

## What was explicitly NOT done (human_authority_boundaries, per the mission contract)

- **No git commit.** All changes are complete, tested, and verified but left uncommitted, matching
  this specific subsystem's own documented standing practice (readme-refresh pipeline-code changes
  have historically been left uncommitted pending an explicit, fresh go-ahead — see
  `docs/readme-refresh/plan-system-forensic-reconciliation.md`'s repeated observation of this norm
  across MT041–MT056). `scripts/ci/checks/check_skill_mirror_parity.py`'s pre-commit gate would
  otherwise have blocked a commit touching `skills/readme-refresh.md` without its mirrors — mirrors
  are already synced and verified clean in advance, so committing later requires no further prep
  beyond staging the exact changed paths and running `/commit` (S-76).
- **No push to any external product repository.** Nothing in this mission calls `push()` against a
  real product — the two real writes performed (`backfill-old-readme-baseline` for tex/python and
  3d/python) are local-only, gitignored, `reports/`-scoped sidecar files.
- **font/python's and tex/python's/3d/python's disposition-ledger content recomposition** — a
  separate, larger, already-known-scale mission, explicitly out of scope from the start. Notably,
  tex/python's real audit result above suggests it may need little or no recomposition once
  correctly pinned; 3d/python is unaffected (already correctly skip-handled). font/python's remains
  a live, unresolved gap requiring a human decision (mirror risk), not a code defect.
- **ST-183** (compose-time drift, a deeper/broader variant of the same defect class) — filed, not
  implemented, given no confirmed live incident of this specific variant exists yet.

## Changed files (working tree, uncommitted)

```
M  .agents/skills/readme-refresh/SKILL.md            (mirror sync)
M  .claude/commands/readme-refresh.md                (mirror sync)
M  .kilocode/skills/readme-refresh/SKILL.md           (mirror sync)
M  backlog/inbox.md                                   (ST-181 corrected, ST-182 + ST-183 filed)
M  scripts/pipeline/commands/foss/readme_refresh_run.py   (the fix)
M  scripts/pipeline/tests/test_readme_refresh_run.py      (19 new tests)
M  skills/readme-refresh.md                           (CLI contract + incident writeup)
```

Untracked, local-only (gitignored `reports/`, not part of any future commit):
`reports/plan_state/readme-refresh-audit-baseline-pinning-hardening-2026-09-03/` (this mission's
mission_authority.yaml, taskcards.jsonl, this EVIDENCE.md), plus the two real backfilled sidecar
files for tex/python and 3d/python under their respective `reports/<candidate_tree>/<family>/
<platform>/old-readme-baseline.json`.

Pre-existing, unrelated dirty files observed throughout (untouched, per "preserve unrelated work"):
`data/knowledge_state.json`, `data/seo_schema_a_migration_state.json`, `data/upstream_baselines.json`,
`keywords/*.json` (9 files), `knowledge/_index.json`, `knowledge/pdf/typescript/.pipeline_state.json`,
`scripts/pipeline/config/mission-ids.jsonl`, `content/blog.aspose.org/pdf/net/pdf-annotations-forms-net/index.de.md`,
plus 4 untracked files (SEO workflow YAMLs, a knowledge bundle manifest) — all present in the
working tree before this mission began, none touched by it.
