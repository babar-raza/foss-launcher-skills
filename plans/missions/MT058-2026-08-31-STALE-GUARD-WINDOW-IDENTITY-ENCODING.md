## Mission: MT058-2026-08-31-STALE-GUARD-WINDOW-IDENTITY-ENCODING
> Investigation/plan file: `C:/Users/prora/.claude/plans/plan-based-on-above-foamy-hartmanis.md`
> Status: **OPEN** (soak-gated; not closed as of last check 2026-09-10)
> Mission contract: registered in `MISSION_AUTHORITY.yaml` (root-bound), commit
> `58adbdebe4` ("bind MT058 mission for stale-guard PSL retroactive convergence"),
> retroactively binding a redesign already fully executed via a parallel governance
> track before the bind. Superseded at the root by `MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION`.
> Durable taskcards: no `taskcards.jsonl` in `reports/plan_state/MT058-.../` — tracked
> via the governing plan's own `TC-SG-*` taskcard IDs instead.

### Context

Retroactive `.supervisor/` PSL registration (bound 2026-08-31) of a stale-file-guard /
`git_plumb_commit.py` / session-identity commit-path redesign that had already been
executed via a parallel governance track (S-67 CODE classification, S-88 backlog,
§6b gap escalation) — discovered only when explicitly asked to bind the
already-executed plan into the PSL loop. Original scope: two live defects (ST-095, an
`AmbiguousSessionError` at Tier-1 Step 34 under concurrency; ST-096, a Windows cp1252
subprocess-decode bug making the stale-file guard silently exit 0 on unmappable
bytes), traced through three deep-reassessment passes to five root causes and executed
as a 5-phase redesign across 12 pushed commits.

### What was built

- `session_ledger.resolve_context()` — single `CommitContext` resolved once and
  carried explicitly; ambiguity degrades the ledger cross-check to a loud WARN instead
  of raising, and never blocks or skips the stale-file check itself (ST-095 fix).
- `scripts/pipeline/lib/stale_file_regression.py` compares git blob OIDs
  (`hash-object`/`cat-file --batch-check`), never locale-decoded text — proven under
  `PYTHONUTF8=0, LC_ALL=C` (ST-096 fix at the root).
- Stale-guard lookback window widened to `oldest(lookback boundary, session base)` —
  a 14-day/5000-commit first-parent lookback instead of only commits-since-session-start
  — reproducing the previously-missed 2026-08-07 silent revert (`55586b637c`) as a
  caught finding.
- `scripts/pipeline/lib/checkout_sync.py`: scoped, clean-verified index/worktree sync
  after every ref advance `git_plumb_commit.py` performs, closing the source of the
  stale-index residue porcelain commits were sweeping into history (measured 42→0).
- Session lifecycle hooks (SessionStart/SessionEnd/Stop); `check_subprocess_encoding_parity.py`
  ratchet gate (baseline 135→127) wired into pre-commit Step 38 and CI; both governance
  CI workflows restored to green; repo Python re-pinned 3.12→3.13 across 18 sites.

### Deliberately out of scope / soak-gated, not closed

- `wide-findings=block` and the Windows-CI-leg `continue-on-error:false` flip —
  soak-gated to ~2026-09-13 (backlog R-04).
- `content/` lookback-window widening (TC-SG-08) — decision made (WIDEN) but not yet
  flipped; bundled into the R-04 flip commit by design.
- Strict-isolation default-on flip (TC-SG-10) — precondition met, flip not started.
- The advisory `.git/index` lock decision (TC-SG-13) — needs post-checkout_sync soak
  data not yet available.
- TC-SG-21 (final end-to-end closeout exercise) — sequenced after the R-04 flip.
- Subprocess-encoding baseline burn-down (TC-SG-15, ~116 sites remaining, ST-129) and
  hook stdout JSON/CRLF cleanup (TC-SG-16) — both P3, deliberately deferred.

### Incident note (recorded in the governing plan's own change log)

While building the full-script integration harness (TC-SG-11), an early design
linked a throwaway git-worktree fixture's `.venv` to the real repo's shared `.venv`
via an NTFS junction; `git worktree remove` followed the junction and deleted most of
the shared venv's installed packages. Recovered same-session (`python -m venv` +
reinstall from all 8 subsystem requirements files, full `scripts/ci/tests/` suite
green afterward); the shipped harness design never links to anything real.

### Related finding (not fixed here)

While minting this mission ID, a repo-wide mission-ID collision risk was found: two
independent, uncoordinated `MT0NN` numbering sequences exist (this repo's main track,
and `/readme-refresh`'s own private sequence, independently reaching MT057) — filed as
ST-157 and later fixed by `MT060-2026-09-01-MISSION-ID-LEDGER`.

### Commits

`f24e17bc96` (ST-095/ST-096 fixes, TC-SG-04) plus 11 further pushed commits across the
5-phase redesign (see the governing plan file for the full per-phase list).
