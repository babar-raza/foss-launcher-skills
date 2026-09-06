# SEO Pipeline Secrets Rotation Policy

Status: Current
Audience: Operator, Contributor, Agent
Canonical reference: this page
Last code-backed audit: 2026-09-06

This page owns the rotation cadence and runbook for the 3 secrets the SEO pipeline
workflows depend on (all set in `Aspose/aspose.org-workflows`, never in this repo — see
[`scripts/seo/README.md` §6](../../scripts/seo/README.md#6-secrets-required) for what each
secret is used by).

## Why this exists

`GH_TOKEN`/`REPO_TOKEN` silently expired on 2026-03-23 and went undetected until
2026-08-09 — nearly 5 months — because nothing checked the token's validity independent
of whether a scheduled workflow happened to run and fail loudly. A pre-flight `gh api
user` liveness check was added to 3 of the 4 local SEO workflow templates in this repo
(`seo-analysis.yml`, `seo-apply.yml`, `seo-review.yml`) as a reactive fix — the 4th,
`seo-keyword-refresh.yml`, still carries the pre-fix `GH_TOKEN`-primary token order with
no liveness check in its local, git-tracked copy, a known, separately-tracked drift issue
(`SEO-WORKFLOW-DEPLOY-REFRESH-KEYWORD-REFRESH-TEMPLATE-RESOLVER-1`) between this repo's
template and its live deployed copy. Even where present, the liveness check still only
catches an expired token on the *next* scheduled run; a token that dies during a quiet
week with no scheduled runs would still go undetected for the whole quiet week. This
document is the proactive half of the fix: a fixed rotation cadence so no credential is
ever left unrotated long enough to expire silently in the first place. (The other half —
an independent daily liveness probe, decoupled from whether any pipeline workflow
actually runs that day — is a separate, dependent task: `SEO-TOKEN-LIVENESS-CHECK`.)

## Rotation cadence

| Secret | Cadence | Rationale |
|---|---|---|
| `GH_TOKEN` / `REPO_TOKEN` | 90 days | Highest blast radius — full `repo` scope on `Aspose/aspose.org` (checkout, commit, PR creation for all 3 workflows). The real 2026-03-23 outage was this exact secret. |
| `GOOGLE_API_KEY` | 180 days | Gemini-only access (Schema A keyword generation) — no repo write capability, lower urgency than a `repo`-scope PAT. |
| `LITELLM_KEY` | 180 days | `analyze.py`/`recommend.py` degrade gracefully to Track 1-only if this is absent or expired — the pipeline does not silently fail closed the way a dead `GH_TOKEN` does. |

**Owner**: whoever last set the secret via `gh secret set` for `Aspose/aspose.org-workflows`
is the de facto owner until reassigned; there is no dedicated on-call rotation for this
repo as of this writing. Check the workflow run history
(`gh run list --repo Aspose/aspose.org-workflows`) for who has been triggering/maintaining
these workflows if the current owner is unclear.

## Rotate → confirm → revoke runbook

**Never revoke the old credential before confirming the new one works** — that ordering
is what turns a routine rotation into the exact silent-outage failure mode this policy
exists to prevent.

### 1. Rotate — generate the new credential without touching the old one

- **`GH_TOKEN` / `REPO_TOKEN`**: generate a new PAT (classic, `repo` scope, or a
  fine-grained token with equivalent permissions on `Aspose/aspose.org`) at
  `https://github.com/settings/tokens`. Do not revoke the old PAT yet.
- **`GOOGLE_API_KEY`**: generate a new key in Google AI Studio
  (`https://aistudio.google.com/apikey`) or the Google Cloud Console, depending on which
  the current key was issued from. Do not revoke/delete the old key yet.
- **`LITELLM_KEY`**: obtain a new key from the `llm.professionalize.com` dashboard. Do not
  revoke the old key yet.

Set the new value:
```bash
gh secret set GH_TOKEN --repo Aspose/aspose.org-workflows
gh secret set GOOGLE_API_KEY --repo Aspose/aspose.org-workflows
gh secret set LITELLM_KEY --repo Aspose/aspose.org-workflows
```
(`gh secret set <NAME>` prompts for the value on stdin, or reads `--body <value>` /
`< file` — never pass the raw secret value as a bare CLI argument, since that would leave
it in shell history.)

### 2. Confirm — trigger a real run before revoking anything

Do not wait for the next scheduled cron fire. Trigger a real workflow run immediately so a
bad rotation is caught within minutes, not up to a week later:

```bash
# GH_TOKEN / GOOGLE_API_KEY
gh workflow run seo-keyword-refresh.yml --repo Aspose/aspose.org-workflows

# GH_TOKEN / LITELLM_KEY
gh workflow run seo-analysis.yml --repo Aspose/aspose.org-workflows

# Wait a few seconds, then check the result:
gh run list --workflow seo-keyword-refresh.yml --repo Aspose/aspose.org-workflows --limit 1
gh run list --workflow seo-analysis.yml --repo Aspose/aspose.org-workflows --limit 1
```

Confirm the triggered run's conclusion is `success` (or, for `seo-analysis.yml` without
`LITELLM_KEY` present at all, confirm it degrades to Track 1-only as designed rather than
failing outright) before proceeding to step 3.

### 3. Revoke — only after step 2 confirms success

- **`GH_TOKEN` / `REPO_TOKEN`**: revoke the old PAT at
  `https://github.com/settings/tokens`.
- **`GOOGLE_API_KEY`**: delete the old key from Google AI Studio / Cloud Console.
- **`LITELLM_KEY`**: revoke the old key from the `llm.professionalize.com` dashboard.

## Real, tracked incident this policy is written against

- **2026-03-23 → 2026-08-09**: `GH_TOKEN`/`REPO_TOKEN` expired silently, undetected for
  nearly 5 months. Fixed reactively with a pre-flight `gh api user` liveness check in each
  of the 4 SEO workflows. This rotation policy, plus the planned
  `SEO-TOKEN-LIVENESS-CHECK` independent daily probe, are the proactive follow-through so
  the same failure class cannot recur silently between scheduled runs.
