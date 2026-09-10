## Mission: MT061-2026-09-01-TRACKB-FOLLOWON-2
> Investigation/plan file: `C:/Users/prora/.claude/plans/investigate-and-plan-the-gentle-stearns.md`
> Status: **CLOSED** (2026-09-01)
> Mission contract: not root-bound — hand-authored archive record, root
> `MISSION_AUTHORITY.yaml` held by `MT058-2026-08-31-STALE-GUARD-WINDOW-IDENTITY-ENCODING`
> (open) for this mission's entire duration.
> Durable taskcards: `reports/plan_state/MT061-2026-09-01-TRACKB-FOLLOWON-2/taskcards.jsonl`
> (12 records — TC-B-06, TC-41, TC-27, TC-17, TC-18, TC-14, all CLOSED)

### Context

Follow-on to the closed mission `readme-refresh-trackb-and-followon-2026-09-01`
(verdict ACCEPTED_VERIFIED), which left 5 taskcards PAUSED with real, disclosed,
non-blocking-bar evidence. This mission re-investigated each from live repo state
before binding and found TC-27's stated blocker no longer held — the "phase6b
production-hardening design" document it couldn't find actually exists
(`reports/plan_state/readme-refresh-forensic-trust-audit-2026-08-25/phase6b-production-hardening-design.md`)
and gives a concrete, code-verified corrected mechanism (S3.VII). TC-B-04 (pdf/python
upstream-drift remediation) was explicitly deferred to its own future mission per user
decision.

### What was built

- **TC-41 (new, shared infra)**: `publication_reconciler.py` extended to record
  `published_blob_sha256` + `merged_by_login` at reconciliation time. A live
  investigation before writing any identity-gate code found phase6b's literal
  "merging actor is not the pipeline's own bot identity" mechanism is **not
  exercisable** in this repo — `gh api user` for the live token resolves to the human
  maintainer's own personal account on every real sampled merge, including
  font/python's REVERTED case. `merged_by_login` was shipped as an audit-only field
  that never gates a state transition; `published_blob_sha256` (structurally sound,
  independent of the identity question) is the real, buildable value and feeds TC-17.
  A second real bug found live: `gh api -f ref=<sha>` silently defaults to POST
  instead of GET against a GET-only endpoint, producing 404s — fixed via the
  URL-query-string form.
- **TC-27 (resume)**: removed `push()`'s direct `_record_publication()` call —
  `data/readme_published_state.json`'s "published" status is now exclusively
  reconciler-derived, never a side effect of a successful PR-open.
- **TC-17 (resume)**: `check_live_published_regression` compares the current live
  README blob against the *recorded* `published_blob_sha256`, never the local
  candidate — the exact conflation that made a naive hard-gate promotion regress
  23/28 already-correctly-published products when tested live by the parent mission.
  Shipped advisory-only; a live `--all` run across the real 32-product portfolio found
  0/32 had a recorded fingerprint yet (the bulk backfill was deliberately left for a
  human-reviewed follow-on), so this pass reports "no data, no finding" honestly
  rather than a false positive.
- **TC-18 (resume)**: SUPPORT-tier disposition schema split (`literal_tokens` vs.
  `descriptive_tokens`). Live re-measurement found the schema split alone didn't fix
  cells/typescript's 60% false-positive rate; root-caused to 2 further polarity/scope
  bugs (absence-proof dispositions, self-referential filename citations) plus 3
  call-signature/Maven-coordinate punctuation variants. Final measured result:
  pdf/java 0/112, note/python 3/113, cells/typescript 0/7 (was 18/30) — meets the
  mission's own acceptance criterion.
- **TC-14 (resume)**: `resolve_manifest_version()` (per-language: .csproj, pom.xml,
  pyproject.toml/setup.py, package.json, Cargo.toml, CMakeLists.txt; Go explicitly
  out of scope) plus `check_installation_matches_manifest_version`. Two real bugs
  found building the Java resolver: pom.xml's XML encoding declaration breaks
  `ElementTree.fromstring()` on a decoded str (fixed via raw bytes); a naive
  first-`<version>`-tag scan would misread a `<parent>` block's version (fixed via
  root-element-scoped search). Canary-verified: reproduces pdf/net's
  already-manually-verified v26.8.0.

### Deliberately out of scope

ACCESSIBILITY tier of TC-18 (blocked on a different skill's C++ scout prerequisite);
live-registry (npm/PyPI/NuGet/Maven) half of TC-14; TC-B-04 (pdf/python upstream
drift, deferred to its own future mission); any push/approve/merge to an external
product repository without a fresh, explicit per-PR human go-ahead.

### Commits

`53f6d2fa16` (TC-41), `6467c4619c` (TC-27), `f078cbdb0e` (TC-17), `b304616206`
(TC-18), `338efbb6d3` (TC-14) — all pushed to `origin/main` via `git_plumb_commit.py`.
