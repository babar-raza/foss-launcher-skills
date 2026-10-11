# Dossier: upstream-monitor.yml

## 1. Identity and purpose
Weekly upstream FOSS drift monitor: detects drift, sweeps drifted products, persists a
fleet freshness snapshot, bounded auto-regeneration, commits state, fails the job if
drift is found.

## 2. Trigger and execution path
`schedule(Monday 08:00 UTC)` + `workflow_dispatch`. 1 job, `ubuntu-latest`,
`timeout-minutes: 30`.

## 3. Consumers and business importance
`P1_HIGH` intended (content freshness matters) / degraded in practice — see §5.

## 4. Historical usage
2 min/0.1% of total (Sept), 1 run. Negligible cost.

## 5. Outcome and failure analysis
**93.3% historical failure (14/15), 100% in the 1-run Sept sample.** Originally
root-caused (`TC-05`/HP-05) to "a real, unresolved PAT gap, issue #94 —
`secrets.GITHUB_TOKEN` insufficient for this use case." **CORRECTED 2026-09-18**:
this was a misdiagnosis. An anonymous-request control test showed the
`aspose-*-foss` orgs are fully public (any token or none returns 200 — the earlier
"token works" signal was a false positive). Direct source read of
`repo_patrol.py`'s `cmd_sweep()` plus a live repro found the real cause:
`clone_exists()` is a pure filesystem check against the gitignored
`runs/.clone_cache/`, never present on a fresh checkout — every product failed
with "no local clone exists" before any git/API call was attempted, regardless of
any token. **Fixed** (`Aspose/aspose.org` commit `72821fbb4a`): `cmd_sweep()` now
calls the pre-existing `ensure_clone()` (a plain unauthenticated `git clone`) to
self-heal a cold cache. Verified live end-to-end (real empty cache dir, real
public-repo clone) plus 2 new DI-seam-based unit tests. No `continue-on-error`
was ever needed as a workaround — the defect is fixed at the source instead.

## 6. Secrets and permissions
`permissions: contents: write, issues: write`. `secrets.GITHUB_TOKEN` referenced
explicitly — **correction**: this token was never actually the problem; the sweep
step needs no elevated credential at all (it clones public FOSS mirror repos
unauthenticated).

## 7. Private/public data classification
Reads/writes repo-internal freshness state; no external secret needed at all (the
default token was already sufficient — the earlier "insufficient" framing was
itself part of the misdiagnosis).

## 8. Current runner dependencies
`ubuntu-latest`, GitHub-hosted.

## 9-11. Destination options
**Re-evaluable now that the fix is confirmed working.** Its low cost (0.1%) and
read+report shape make it a clean public-migration candidate, and it was in fact
already migrated (`PHB-06`, PR-gated) before this root cause was corrected — the
migration is unaffected by which diagnosis was right, since the fix lives in
`Aspose/aspose.org`'s `repo_patrol.py`, fetched fresh on every run regardless of
which repo triggers the workflow.

## 12. Optimization or retirement opportunity
Done — see §5. No `continue-on-error` masking was needed; the underlying defect
is fixed at the source (`cmd_sweep()`'s auto-clone self-heal).

## 13. Recommendation
`REQUIRES_REDESIGN` at the time of the original (mis)diagnosis; **superseded
2026-09-18** — the defect is fixed, not redesigned around. Recommend closing
issue #94 as a misdiagnosis and re-observing this workflow's real failure rate
after the fix (`ST-201`/`R-08`-style follow-up).

## 14. Rejected alternatives
Any migration destination — rejected as premature while the workflow was believed
broken; moot now that the actual defect is fixed rather than worked around.

## 15. Expected savings
Negligible (0.1% of total) — this workflow matters for correctness/reliability, not cost.

## 16. Migration complexity
N/A — already migrated (`PHB-06`); the code fix required no workflow-file change
at all beyond the corrected documentation comments.

## 17. Risks
The risk this dossier originally flagged (running broken with false confidence
that drift is being watched) is now closed by the real fix rather than mitigated
by disabling or masking. Residual risk: confirm the next real (or canary)
dispatch shows the sweep step actually succeeding, not just locally verified —
not yet observed live in an actual GitHub Actions run as of this writing.

## 18. Tests
2 new unit tests added (`test_no_clone_but_auto_clone_fails_is_fetch_failure`,
`test_no_clone_but_auto_clone_succeeds_proceeds_normally`), plus a live
end-to-end repro against a real empty cache dir and a real public FOSS repo
clone. Full `test_repo_patrol.py` suite (78 tests) passes. Monkeypatch-lint
clean (net -2 vs. baseline after a DI-seam refactor, not a workaround).

## 19. Rollback
`git revert` of `Aspose/aspose.org` commit `72821fbb4a` restores the old
fail-outright behavior; no workflow-file change is involved in the fix itself.

## 20. Evidence and confidence
HIGH confidence in the corrected diagnosis (direct source read + live repro,
not inference) and in the fix (tested, live-verified). Not yet confirmed via an
actual GitHub Actions dispatch of this specific workflow post-fix — the next
real run (scheduled or canary) is the remaining confirmation step.
