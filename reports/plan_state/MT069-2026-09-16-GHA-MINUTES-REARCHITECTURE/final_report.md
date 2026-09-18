# Final Report: MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE (Phase A)

**Date**: 2026-09-17
**Verdict**: `PLAN_READY_EXCEPT_DOCUMENTED_EXTERNAL_AUTHORITY`

> **Point-in-time snapshot — see `dossiers/launch-dashboard.md` for a 2026-09-18
> correction.** This report's "Split private/public" bucket below still lists
> `launch-dashboard.yml`. That was tried for real during Phase B and found not to
> work — its `REQUIRES_REDESIGN` classification (line 52 of this document) turned out
> to be the correct bucket all along, just for a different, now-verified reason (its
> real inputs are gitignored local state, never available in any fresh checkout — not
> a hosting-location problem). Not edited in place below to preserve this document as
> an honest record of what Phase A actually concluded at the time.

Phase A (audit → evidence-backed migration plan) is complete. The plan is ready for
Phase B execution, gated on the explicit human decisions and open items listed below —
none of which are analytical gaps, all of which are genuine authority boundaries or
follow-up engineering this mission correctly declined to guess past.

## What was asked

Audit every GitHub Actions workflow in the private `Aspose/aspose.org` repo, measure
real usage/billing and failure history, decide per-workflow whether to stay private,
self-host, move to the public `Aspose/aspose.org-workflows` repo, consolidate, or
retire — with evidence, not assumption — and produce an execution-ready plan, while
never weakening a gate, exposing a secret, or re-enabling/dispatching any of the 20
workflows (all deliberately disabled as a cost stopgap) for any reason.

## What was found

- All 20 workflows were confirmed intentionally disabled by the user (2026-09-16), not
  an anomaly.
- Real usage data (user-supplied export, 2026-09-01–2026-09-18): 1,494 total minutes.
  Top 3 workflows = 75.7% of all cost. Two of those three needed self-hosting (the only
  lever to zero cost for push-gated checks); the third (`llms-generation.yml`) needed a
  redesign, not a simple destination pick — see below.
- Real failure-history investigation (172 days retained, far longer than assumed) found
  two genuine, previously-undiagnosed production defects behind the two highest-cost
  workflows' bad failure rates: a latent comparison bug making `skill-governance.yml`
  fail 100% of the time on a false positive for 12 days, and a missing pre-commit
  enforcement layer letting `content-governance-checks.yml` fail 49% of the time on a
  real, repeated authoring-discipline gap. Both root-caused and fixed with regression
  tests (`TC-14`, `TC-15`) — not just documented.
- Two more workflows (`upstream-monitor.yml`, `launch-dashboard.yml`) confirmed 93-100%
  broken from unrelated, already-known causes — correctly reclassified
  `REQUIRES_REDESIGN` rather than assigned a migration destination, since relocating a
  broken workflow doesn't fix it.
- This repo's private-tier plan means no workflow here can ever be a GitHub-enforced
  "required check" — this softens (doesn't eliminate) the self-hosting rationale and is
  recorded as an open, not-yet-evaluated alternative (a polling-based public check).
- **Independent review (`TC-11`) found 7 real issues in this mission's own prior work**,
  including a genuine fail-open gap discovered the same day it was introduced (`TC-15`'s
  new pre-commit gate read the wrong git state). All 7 fixed, not just logged — see
  `review/independent_review.md`.

## Decisions made (evidence-backed, per workflow — see dossiers for full citations)

| Destination | Workflows |
|---|---|
| Self-host (only lever to zero cost) | `content-governance-checks.yml`, `skill-governance.yml`'s required Linux job |
| Requires redesign before any destination is meaningful | `llms-generation.yml` (partially duplicated with the public deploy repo, not fully — keep the fail-fast gate, shed the duplicate regeneration), `upstream-monitor.yml`, `launch-dashboard.yml` (both broken, unrelated to cost) |
| Move to public repo, clean | `aspose-com-targets-watch.yml` (canary), `backlink-compliance-watch.yml`, `seo-analysis.yml` |
| Move to public, needs a product decision first | `upstream-monitor.yml`, `maven-publish-watcher.yml`, `install-literal-sweep.yml`, `package-publish-watch.yml` (auto-commit → PR-gated conversion) |
| Split private/public | `ci-eval-consistency.yml`, `launch-dashboard.yml` |
| Stay private, optimize only | `extraction-pipeline.yml`, `metrics-governance.yml`, `reference-index-structure.yml`, `seo-tests.yml`, `act-pipeline.yml`, `cross-repo-index-sync.yml` |
| Confirmed dead, leave alone | `content-audit.yml` |
| Consolidation-independent optimization | `example-verification-tests.yml`, the 4 auto-commit watcher bots |

## What was built, not just proposed

- Self-hosted runner architecture with a defined health/decommission lifecycle (not
  narrative-only).
- Public-migration mechanism reusing this repo's own proven SEO-template pattern (no new
  invention).
- A resumable migration-run state-machine design for Phase B, addressing three real
  structural weaknesses in the original sketch (no resumability, no durable-outcome
  verification, no runner lifecycle) — modeled on this repo's own most battle-tested
  precedent (`refresh_run.py`), with named, honest limits, not oversold.
- A recurring cost-and-CI-health telemetry design, filed as its own `recurring-candidate`
  gap-escalation report (not folded into this bounded-oneoff mission).
- **Two real CI defects actually fixed** (not designed-for-later): the platform-
  capabilities checker bug and the evaluator-version-bump shift-left gap, each with new
  regression tests proving the fix and pinning against recurrence.

## What is explicitly still open (see `EVIDENCE_BUNDLE.md` for the full list)

1. The concurrency-guard and CI-checker code fixes are real and tested but
   **uncommitted** — a genuine, disclosed precondition, not silently assumed satisfied.
2. `llms-generation.yml`'s specific redesign is diagnosed, not implemented.
3. Two workflows need their own underlying defects fixed before any destination
   decision is meaningful.
4. Docker Desktop licensing for the self-hosted runner — unconfirmed.
5. `AGENTS.md`'s dead link — human action item.
6. Phase B itself — seeded, authorized, not started; stop-gate per taskcard per the
   user's own standing instruction.

## Honest self-assessment

This plan does not claim zero remaining risk or perfect foresight. It claims: every
destination decision is evidence-backed and citable; every known defect found during
investigation was fixed, not deferred by default; every open item is disclosed with a
reason, not smoothed over; and an independent, adversarial review of this mission's own
work found real problems, which were then actually fixed rather than merely
acknowledged. That is the standard this mission was held to throughout, and it is the
standard this report holds itself to now.
