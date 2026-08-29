# Parity Documents

**Program:** Skill Parity Migration — aspose.org to foss-launcher-skills-gitlab
**Status:** See "Current State" immediately below — do not trust the historical "COMPLETE" status alone.

---

## Current State (2026-08-29)

The 2026-05-14 "84/84 FUNCTIONAL parity, 0 gaps" closure below was accurate when written but was never re-verified against aspose.org's actual git history — every comparison to date (this one included, historically) diffed live directories on a session date, never a pinned source commit SHA. 267 aspose.org commits landed between 2026-04-17 and 2026-08-29 with no mechanism that would ever have surfaced that drift.

This sync introduces `docs/parity/source-anchors.yaml` — a commit-SHA-pinned ledger, checked by `tools/capability_sync/detect_source_drift.py --check`, that makes future drift detectable with one command instead of a full manual re-audit.

**Scope of what is now anchored (updated same day):** 86 of 91 capabilities now have a `source-anchors.yaml` entry — 9 fully verified (the artifacts this sync actually ported/tested), 77 mechanically anchored by `scripts/pipeline/commands/ops/backfill_source_anchors.py` (source file confirmed to exist, pinned to its own current commit SHA — explicitly **not** a semantic content re-review of those 77; see TASK_BACKLOG.md SYNC-8, which stays open until that review happens). 2 (`translate-page`/`translate-batch`) could not be anchored — source has retired them from its canonical trees (SYNC-10). Building the backfill tool also caught and fixed an independent, real documentation bug: `docs/id-mapping.md` had mislabeled 4 foss-exclusive skills as having an aspose.org counterpart.

```bash
# Check whether anything anchored has drifted upstream (requires aspose.org
# checked out locally; SOURCE_REPO_PATH points at it):
export SOURCE_REPO_PATH=/path/to/aspose-org-checkout
.venv/bin/python tools/capability_sync/detect_source_drift.py --check
```

---

## Artifact Status

| Artifact | Status | Last Updated | Description |
|----------|--------|-------------|-------------|
| [inventory-aspose.md](inventory-aspose.md) | HISTORICAL | 2026-04-27 | Original 96-skill inventory of aspose.org |
| [inventory-foss.md](inventory-foss.md) | HISTORICAL | 2026-04-27 | Original 88-skill inventory of foss-launcher |
| [parity-matrix.md](parity-matrix.md) | HISTORICAL | 2026-04-27 Session 3 | Original parity comparison |
| [gap-report.md](gap-report.md) | HISTORICAL | 2026-04-27 Session 3 | Original gap report |
| [verification-log.md](verification-log.md) | CURRENT | 2026-05-14 | Includes resumed May 13 sprint verification |
| [closure-report.md](closure-report.md) | CURRENT | 2026-05-14 | Includes refreshed parity closure |
| [closure-report-2026-05-14.md](closure-report-2026-05-14.md) | CURRENT | 2026-05-14 | Resume-specific closure report |
| [review-package-2026-05-14.md](review-package-2026-05-14.md) | CURRENT | 2026-05-14 | Review and staging map for the resumed sprint |

---

## Summary

| Metric | Value |
|--------|-------|
| Current aspose capabilities compared | 84 |
| Current standalone skills | 92 |
| FUNCTIONAL parity | 84 |
| PARTIAL parity | 0 |
| UNVERIFIED | 0 |
| Open gaps | 0 |

---

## Key Outcomes

- **92 skills** in foss, including compatibility and governance surfaces added during the May 13 sprint
- **84/84 current aspose.org capabilities** classified as `functional parity proven through different implementation`
- **8 foss-exclusive innovations** preserved (evidence pipeline, corpus system, RBAC)
- **13 Python pipeline scripts** ported in session 3
- **22 AGENTS.md governance sections** (all P1+P2)
- **4 CI workflows** active
- **scripts/translator/** fully ported (37 Python files)
- **May 14 verification complete**: full suite `738 passed, 15 skipped`

---

## Quick Start

```bash
# Verify current state
cd foss-launcher-skills-gitlab
python scripts/validate_skills.py
grep "## 9a" AGENTS.md        # P2 governance present
ls scripts/pipeline/launch_gate.py  # Infrastructure present
```

## 2026-05-14 Resume Result

The May 13 parity sprint was resumed after an interruption. The last recorded slice was re-verified, remaining false-positive config and path gaps were converted into explicit compatibility evidence, prompt-orchestration skills were mapped, and the full standalone suite was run.

Final evidence:

- `docs/parity/evidence/phase7-resume-parity-run-final.json`
- `docs/parity/evidence/phase7-resume-parity-summary-final.txt`
- `docs/parity/evidence/suite-verification.json`
- `docs/parity/compatibility-path-map.json`
- `docs/parity/prompt-orchestration-map.json`

Final result:

```text
rows: 84
functional parity proven through different implementation: 84
gap_counts: {}
standalone_only: 8
```

## 2026-08-29 Delta Sync Result

Lean re-sync of the drift accumulated since the 2026-05-14 closure (267
aspose.org commits, ~44 new skills upstream). Full detail:
`docs/parity/sync-runs/2026-08-29-202e4a7b97.md`.

**Ported (7 artifacts, each anchored in `source-anchors.yaml` at aspose.org
commit `202e4a7b97f0e4963fedf598ac47ed22bce22181`):**

- `scripts/pipeline/lib/session_identity.py` (near-verbatim; zero Aspose coupling in source)
- `scripts/ci/checks/check_stale_file_regression.py` (adapted: session_ledger auto-resolve dropped)
- `scripts/ci/checks/check_module_consumption.py` (adapted: scan-root note only)
- `docs/reference/planning-execution-state-machine.md` (copied verbatim, confirmed generic)
- `skills/llms-generate.md` / `llms-coverage.md` / `llms-fidelity.md` (S-116/117/118; generalized to config.yaml `sites:` instead of 5 hardcoded subdomains)

**New system infrastructure built this sync (not a port -- new in this repo):**

- `docs/parity/source-anchors.yaml` -- commit-SHA-pinned provenance ledger
- `tools/capability_sync/detect_source_drift.py` -- upstream drift detector, sibling to `detect_adapter_drift.py`
- `scripts/ci/checks/check_hardcoded_external_coupling.py` -- structural-coupling linter (caught a real pre-existing bug, see below)
- `scripts/pipeline/commands/ops/compute_source_delta.py` -- repeatable `git log`-based delta tool
- `docs/governance/planning-methodology.md` -- this repo's own binding for the ported planning doc

**Bug found and fixed by the new linter, not silently left in place:**
`scripts/content_repo_adapter.py`'s write-safety boundary was hardcoded to
`D:/onedrive/Documents/GitHub/aspose.org/content` since this repo's very
first sync -- present through both prior "parity complete" closures,
undetected because nothing checked for that class of bug. Now config/env
driven (`FORBIDDEN_CONTENT_ROOT`), with the old constant preserved as the
documented backward-compatible default (existing tests unchanged, all pass).

**Deferred (see `TASK_BACKLOG.md`, Workstream SYNC-2026-08-29):**
concurrency-safety stack (taskcard_store.py/master_plan_index.py/git_plumb_commit.py),
readme-refresh (source's own forensic audit found 172 defects, do not port),
governance-audit cluster, content-maintenance cluster, Java/Maven cluster,
llms-verify + llms-stale (live-HTTP + provenance-manifest, out of scope this
pass), retroactive source-anchor backfill for the pre-2026-08-29 84
capabilities, behavioral-equivalence testing.

**Final readiness judgment: safe with noted limitations** -- see the sync
report for the full limitations list (heuristic linter/classifier, no CI
wiring for source-drift detection, only 7/91 capabilities anchored, no
behavioral-equivalence testing).
