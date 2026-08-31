# ADR-007: GitHub<->GitLab Main-Branch Sync Automation

**Date:** 2026-08-30
**Status:** Accepted
**Deciders:** @prora
**Mission:** GHGL-1 (`reports/plan_state/GHGL-1/`)

## Context

This repo is hosted on both GitHub (`github` remote, primary per ADR-003) and
a self-hosted GitLab instance (`origin` remote, gitlab.recruitize.ai, project
490). No automated mechanism kept the two `main` branches synchronized --
the only "sync" was a human or agent remembering to push to both remotes
after every commit. Live drift was found during GHGL-1's own assessment:
`origin/main` had two commits `github/main` lacked, confirmed by direct
`git rev-list` inspection, not inferred. Mid-implementation, a second,
independent divergence appeared on its own: GitHub's existing
`pipeline-tests.yml` release-receipt job pushed a commit to `github/main`
that `origin/main` did not have, while `origin/main` still carried its own
two unique commits -- proving the failure mode is real and recurring, not
hypothetical.

## Decision

Two symmetric, event-driven CI jobs mirror `main` only, fast-forward-only,
in both directions:

- `.github/workflows/sync-to-gitlab.yml` -- triggers on push to `main`,
  hourly schedule (safety net for missed webhook deliveries), and manual
  dispatch. Pushes into GitLab using a GitLab Project/Personal Access Token
  stored as the GitHub secret `gitlab_token` (GitHub Actions forces secret
  names to uppercase on storage -- confirmed via GitHub's own docs and a
  corroborating community report -- so it is visible in GitHub's UI as
  `GITLAB_TOKEN`; this is the one place the naming rule below cannot be
  honored literally).
- `.gitlab-ci.yml`'s new `sync-to-github` job (stage `sync`) -- triggers on
  push to `main`. Pushes into GitHub using a GitHub-authenticating credential
  stored as the GitLab CI/CD variable `github_token` (lowercase, no forced
  casing on GitLab).

Both invoke the same shared script, `scripts/ci/sync_remotes.py`, rather than
duplicating the logic per platform -- unlike ADR-003's accepted duplication
of *validation* logic (which independently re-derives the same pass/fail
from the same tree on both platforms), sync logic pushes to a foreign remote
with real consequences, and two independently-drifting copies of that logic
is the exact class of failure this ADR exists to close.

### Credential naming rule

Any credential used to perform a GitLab operation is named `gitlab_token`
(lowercase) everywhere technically possible: the pre-existing local Windows
Machine-level env var (unchanged), this script's own env-var contract,
`.env.example`, and all documentation. The one unavoidable exception is
GitHub's secret store itself (see above) -- documented here so it is never
mistaken for a bug. The GitHub-authenticating credential is named
`github_token` (lowercase) with no such exception.

### Safety mechanism

A pre-push SHA comparison is a no-op short-circuit only, never the
correctness gate -- a check-then-push sequence has no atomicity guarantee
across two independently-triggered CI systems. The actual gate is the push
itself: a plain fast-forward push (`git push <remote> HEAD:main`, never
`--force`), judged by its own exit code. A rejected (non-fast-forward) push
means a genuine divergence; the script never resolves one automatically --
it fails loudly and, on the GitHub leg only, files or updates a tracking
issue (title `[sync-conflict] main branch diverged`) for a human to
reconcile. No auto-merge, no force-push, ever, under any code path.

### Scope (v1)

`main` branch only. Feature branches are routinely force-pushed/rebased,
fundamentally incompatible with a fast-forward-only mirror. Tags and the
tag-triggered `release.yml` flow are explicitly deferred -- a conscious
choice, not a silent gap.

### Credential provenance (recorded honestly, not glossed over)

Rather than blocking this mission on minting brand-new, dedicated
project-scoped bot credentials -- GitHub provides no API for self-service
PAT/App creation (a platform security boundary, not a tooling gap), and the
GitLab token available during GHGL-1's execution lacked the `api` scope
needed to create a new GitLab Project Access Token via API -- this system
initially reuses the credentials already available: the existing personal
`gitlab_token` for the GitHub-side secret, and the existing GitHub CLI
credential for the GitLab-side variable (added by a human, since writing a
GitLab CI/CD variable also requires `api` scope this mission's token
lacked). This ties both sync legs to human accounts rather than dedicated
bot identities -- a real, accepted trade-off, tracked as a named follow-up
(not a taskcard, since it depends on a future human action) to migrate to
dedicated, minimally-scoped bot credentials when convenient.

## Alternatives Considered

- **GitLab's native push-mirror feature** (confirmed available on this
  instance via API) for the GitLab->GitHub leg: rejected because mixing a
  black-box native mirror for one direction with custom logic for the other
  makes the two directions behave asymmetrically under failure/divergence.
- **A `[skip-sync]` or bot-identity loop-prevention marker**: rejected as
  redundant. Mirroring is a pure, content-addressed ref update (same SHA
  both sides), so the second leg's own trigger finds tips already equal and
  no-ops by construction -- a marker would add a collision surface for no
  gap it actually closes.

## Consequences

- Convergence is bounded (<=1 hour via the scheduled safety net), not
  instantaneous -- webhook/event delivery on both platforms is best-effort.
- A genuine divergence (independent commits on both sides in the same
  window) always stops for human reconciliation rather than being resolved
  automatically -- by design, confirmed necessary by the real divergence
  GHGL-1 itself hit mid-implementation (see `reports/plan_state/GHGL-1/`).
- Branch protection on GitHub (`main`: no force-push, no deletion) was added
  to match GitLab's pre-existing Maintainer-gated, no-force-push posture.

## Implementation

- `scripts/ci/sync_remotes.py`, `tests/test_sync_remotes.py`
- `.github/workflows/sync-to-gitlab.yml`
- `.gitlab-ci.yml` (`sync` stage, `sync-to-github` job)
- Mission record: `reports/plan_state/GHGL-1/taskcards.jsonl`,
  `reports/plan_state/GHGL-1/evidence/`
