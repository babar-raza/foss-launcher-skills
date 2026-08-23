# S-124: Blog Release Check — Mandatory Per-Release Announcement Trigger

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} {run_id}`

## Purpose

Checks whether a refresh run's real, non-empty knowledge delta requires a mandatory
blog release-announcement post (mission-plan-the-end-to-end-vast-hejlsberg.md's own
S9.6, per direct user instruction: "there must also be a new blog announcement
targeting only the changes in the new release... a new blog post must also be
published as part of the release process"), and if so, directs the invoking agent to
draft one via `/new-blog-post` before the run is considered complete.

This skill never drafts blog content itself — release-announcement prose requires
genuine LLM/editorial judgment (what changed, why it matters, how to explain it), the
same reason `/new-blog-post` itself is `agent-executed`, not a deterministic script.
`refresh_run.py`'s `prepare_run()` computes the one part of this decision that is
genuinely mechanical — whether this run's `knowledge_delta.json` is non-empty at all
(a no-op sync produces no announcement) — and records it as
`manifest["blog_announcement_required"]`. This skill is the directive layer that acts
on that signal; `/new-blog-post` remains the sole governed content-generation path,
unchanged.

## Pre-conditions

1. A `refresh_run.py` run for `{family}/{platform}/{run_id}` has reached `prepare_run()`
   — i.e. `reports/refresh_runs/{family}/{platform}/{run_id}/manifest.json` exists.

## Steps

### Step 1: Read the deterministic signal

Read `reports/refresh_runs/{family}/{platform}/{run_id}/manifest.json` and check the
`blog_announcement_required` field:

- Missing (older, pre-Task-6 run) or `false` → no announcement is required. Report and
  stop — do not retroactively demand an announcement for a run whose knowledge delta
  was computed before this signal existed.
- `true` → continue to Step 2.

### Step 2: Check whether an announcement draft already exists in this run's scope

Read the same run's `scope.json` (`reports/refresh_runs/{family}/{platform}/{run_id}/scope.json`)
`paths` list. If any path already matches `content/blog.aspose.org/{family}/{platform}/**`
(e.g. a prior invocation of this skill already handled it, or the run resumed after a
partial completion), skip drafting — go to Step 4.

### Step 3: Draft the announcement via `/new-blog-post`

Invoke `/new-blog-post {family} {platform} {slug}` — choose `{slug}` as a fresh,
release-specific slug (e.g. `{version}-release` or a short descriptive title, never
reusing an existing post's slug). Give the invocation an explicit brief, scoping
content to **only this release's actual changes**:

- New, changed, deprecated, and removed APIs (source: this run's own
  `knowledge/{family}/{platform}/merged/knowledge_delta.json` and
  `reports/refresh_review/{family}/{platform}/semantic_changes.json`)
- Migration guidance for anything that changed behavior
- The end-user-facing benefit of what's new — never a general product rewrite or a
  restatement of features that existed before this release

The resulting post is **Tier 1** by AGENTS.md §7b (all blog posts are, unconditionally)
— it is generated automatically and unconditionally per this skill's own trigger, but
is **never auto-published**: mandatory generation does not mean bypassed review. A
human clears S-90 (`/publish-readiness-review`) before the post actually goes live,
exactly like any manually-authored post.

### Step 4: Fold the resulting page into the run's scope

Read the run's `scope.json`, append the new post's repo-relative path to `paths`
(sorted, no duplicates), and write it back — this is what makes the announcement flow
through the same validators (content-check, evidence, no-downgrade-guard, link
validation) as every other in-scope page for this run, rather than existing outside
the run's own evidence trail.

### Step 5: Report

State plainly: `{family}/{platform}` run `{run_id}` required a blog announcement;
drafted at `{path}` (or: an announcement already existed at `{path}`); added to the
run's scope; pending S-90 review before publish.

## Post-conditions

- If `blog_announcement_required` was `true`: exactly one `blog.aspose.org` page for
  `{family}/{platform}` exists in the run's scope, scoped to this release's changes
  only, Tier-1-classified, pending S-90 clearance before publication.
- If `blog_announcement_required` was `false` or absent: no action taken, nothing
  written.

## Refusal and halt conditions

| Condition | Response |
|-----------|----------|
| `manifest.json` not found for the given `{family}/{platform}/{run_id}` | REFUSE — "No such run" |
| `blog_announcement_required` missing (pre-Task-6 run) | Treat as `false` — do not retroactively require an announcement |
| A qualifying draft already exists in `scope.json` | Skip Step 3, proceed to Step 4/5 |
| `/new-blog-post` itself refuses or halts | Surface its refusal verbatim; do not retry with a different, ungoverned content path |

### What this skill will never do

- Generate blog content directly, bypassing `/new-blog-post`'s own governed path
  (knowledge bootstrap, evidence citation, no-downgrade-guard, provenance)
- Publish a post without a human clearing S-90
- Force an announcement for a no-op sync (an empty `knowledge_delta.json`)
- Retroactively require an announcement for a run created before this signal existed
