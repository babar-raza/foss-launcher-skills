# PHB-01/PHB-02: Lightweight migration tracking (decision record)

**Date**: 2026-09-17
**Decision**: build lightweight, per-migration JSON state records instead of the full
9-state CLI state machine the Phase A design sketched.

## Why

The Phase A design (`design/self_hosted_architecture.md`'s sibling section on Phase B,
and the plan's own "Migration-run state machine" section) explicitly flagged this exact
choice as unresolved: *"consider the lighter-weight alternative of reusing FileLock +
session-identity + git_plumb_commit/bind_commit-style verification as direct library
calls inside the existing taskcard system, without a dedicated 9-state CLI, if 11
one-time migrations don't justify the heavier build. This is a decision for the user,
not settled here."*

Given the scope is genuinely 11 one-time migration candidates (a `bounded-oneoff` gap
per the mission's own gap-escalation report, not a recurring deliverable), and given the
user's explicit direction to execute Phase B now, the lighter-weight path was chosen: a
small JSON record per migration (this directory) tracking the same state names the
heavier design specified, without a dedicated CLI, framework, or new library module. No
approval round-trip was used for this specific call since the plan's own tradeoff
analysis already reasoned it through and named the lighter path as the likely right fit
at this scale — flagged here, transparently, in case that judgment should be revisited.

## What is preserved from the heavier design

- The same state names: `CREATED → BASELINE_PINNED → TEMPLATE_BUILT → CANARY_DEPLOYED →
  CANARY_OBSERVING → CANARY_CONFIRMED → CUTOVER_STAGED → CUTOVER_LIVE → STABILIZED`
  (`BLOCKED`, `ABANDONED`, `ROLLED_BACK` as needed).
- Baseline hash-pinning of the private workflow file before any change (sha256, recorded
  per migration).
- A reconciliation step that asks GitHub what actually happened (a real `gh run watch` +
  `gh issue list` check) before advancing past `CANARY_DEPLOYED`, not trusting "the push
  succeeded" alone — the exact principle `publication_reconciler.py` established.
- `git_plumb_commit.py`-equivalent discipline for the one local commit this track makes
  (the private trigger flip): isolated temp index, exact file scope, no porcelain
  `git commit`.
- For the cross-repo push to `Aspose/aspose.org-workflows`: the same isolated-temp-index
  technique, hand-applied (that tool is scoped to this repo only; the sibling repo has no
  equivalent). See `migrations/aspose-com-targets-watch.json` for the exact commit SHAs.

## What is NOT built (the actual scope reduction)

- No dedicated CLI, no `refresh_run.py`-style resumable run-ID system.
- No generalized reconciler *component* — reconciliation is done manually per migration
  right now (a `gh run watch` + `gh issue list` check), not automated into a scheduled
  job. `PHB-03`'s cost-telemetry work is the closer analogue to an automated watcher, and
  remains separately scoped.
- No orphaned-lock detection or multi-session locking — each migration this session is
  performed by one session in one sitting; this is a real, disclosed limitation if a
  future migration is interrupted mid-flight by a session boundary.

## Honest risk of this choice

If migrations end up needing far more than the 11 originally estimated, or if
interruption-and-resume across sessions becomes common, this lighter approach will not
scale as gracefully as the full design would have. That tradeoff is accepted here as
appropriate to the mission's own stated scope, not because the risk doesn't exist.
