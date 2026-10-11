# Public/Private Threat Assessment

**Mission:** MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE
**Taskcard:** MT069-TC-07-DESTINATION-DECISION-MATRIX
**Date:** 2026-09-17

Per the mission's mandatory acceptance criteria, every workflow recommended for public or
self-hosted execution must have its secret/credential/data exposure named explicitly.

## Self-hosted candidates

### `content-governance-checks.yml`
- **Secrets/credentials used**: none explicit in the workflow file (default `GITHUB_TOKEN`
  only, `permissions: contents: read`). No PAT, no external API key.
- **Data processed**: the full private repo checkout (content/, scripts/, knowledge/,
  data/) — this is expected and unchanged by self-hosting; the data never leaves a
  machine the maintainer already controls (their own dev machine), unlike a public-repo
  migration which would require exposing this data to a workflow whose logs are
  world-readable.
- **New exposure introduced by self-hosting**: the runner process itself gains
  filesystem access on the maintainer's own machine. Mitigation already specified in the
  design: runner workspace must live outside `D:\onedrive\Documents\GitHub\aspose.org`
  (the maintainer's actual working tree), on its own path, to prevent cross-contamination
  between CI runs and interactive work.
- **Verdict**: no new secret exposure; the operational risk is resource contention, not
  credential leakage (already covered in the self-hosted design's risk section).

### `skill-governance.yml` (Linux job)
- **Secrets/credentials used**: none explicit (default `GITHUB_TOKEN` only,
  `permissions:` absent/default).
- **Data processed**: same private-repo checkout scope as above, narrower path filter
  (skills/, `.agents/skills/`, `.claude/commands/`, `scripts/ci/*.py`).
- **Verdict**: same as `content-governance-checks.yml` — no new secret exposure from
  self-hosting.

## Public-migration candidates

### `aspose-com-targets-watch.yml` (this mission's designated canary)
- **Secrets/credentials used**: none explicit in the private original. The **deployed
  public copy** would need `REPO_TOKEN`/`GH_TOKEN` (the same token already present in
  `Aspose/aspose.org-workflows` for the SEO templates) to check out `Aspose/aspose.org`.
  This token already has `repo` scope (confirmed live this session) — broad enough to
  read and write the private repo. It is not new exposure (already sitting in that public
  repo for the SEO workflows) but this canary would be a second consumer of the same
  token.
- **Data processed**: reads `data/aspose_com_targets.json` and makes outbound HTTPS
  calls to aspose.com; writes only an issue (via `github-script`, default token) on the
  private repo. No content/source code is written to any public artifact or log beyond
  what the check itself prints (target URLs and drift status — already public-facing
  URLs, not sensitive).
- **Public-visibility risk**: this workflow's logs, once running in
  `Aspose/aspose.org-workflows`, are world-readable. Reviewed the script's own behavior:
  it does not print repo secrets, internal file contents beyond the target list (which
  describes public aspose.com URLs), or credentials. **Verdict: safe to migrate as
  designed.**

### `backlink-compliance-watch.yml`
- **Secrets/credentials used**: none explicit; same `REPO_TOKEN`/`GH_TOKEN` reuse as above
  for the deployed copy's checkout.
- **Data processed**: runs a full-site backlink audit against public content and writes
  `backlink-audit-results.json`; only opens an issue on regression, does not publish the
  raw audit file publicly. **Verdict: safe to migrate**, same reasoning as above.

### `seo-analysis.yml`
- **Secrets/credentials used**: none explicit; same token reuse pattern.
- **Data processed**: runs `scripts/seo/pipeline/weekly_analysis.py`, uploads
  `reports/seo/weekly_analysis_summary.json`/`.md` as a **workflow artifact**. Artifacts
  on a public-repo workflow are **publicly downloadable** — this is a real, distinct risk
  from the issue-only workflows above. **Action required before migration**: read
  `weekly_analysis.py`'s output to confirm the summary contains no unpublished
  keyword-strategy data, internal SEO tactics, or anything not already intended for
  public consumption, before deploying this one publicly. Not yet verified — flagging as
  an open item for whoever executes this specific migration (`MT069-PHB-06`), not
  resolved in this pass.

### Auto-commit bots pending the user's product decision (`upstream-monitor.yml`,
`maven-publish-watcher.yml`, `install-literal-sweep.yml`, `package-publish-watch.yml`)
- **Secrets/credentials used**: `upstream-monitor.yml` explicitly references
  `secrets.GITHUB_TOKEN` (documented as currently insufficient — a real PAT is needed,
  per HP-05); `install-literal-sweep.yml` also references `secrets.GITHUB_TOKEN`
  explicitly; the other two use the default token implicitly via `github-script`.
  `permissions: contents: write, issues: write` on all four (broader than the read-only
  canary candidates) — this is exactly the class of credential this mission's own hard
  rules flag: broader write scope needs the most scrutiny before any public exposure.
- **Verdict**: none of these four should move to public execution until (a) the user's
  auto-commit-to-PR-gated product decision is made, and (b) their `contents: write` scope
  is re-examined under the public-repo threat model — a public workflow with write access
  to the private repo is a materially different risk than a read-only one, even reusing
  the already-present `REPO_TOKEN`. Not resolved in this pass; explicitly deferred.

## Workflows requiring correctness fixes before any destination decision

`upstream-monitor.yml` and `launch-dashboard.yml` are `REQUIRES_REDESIGN` per the
destination matrix — their confirmed defects (HP-05, HP-11) must be resolved before a
threat assessment is even meaningful, since migrating a broken workflow to a new
destination doesn't fix or worsen its brokenness, it just relocates it.

## Summary

No new secret was found requiring rotation. No public-migration candidate in the
"clean" tier introduces a secret-exposure risk beyond what already exists (the same
`REPO_TOKEN` already deployed for the SEO workflows). The one real, unresolved risk
flagged is `seo-analysis.yml`'s public artifact upload, and the one class of risk
requiring a human decision before any action is the four `contents: write` auto-commit
bots.
