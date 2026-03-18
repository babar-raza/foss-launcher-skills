---
name: launch-product
id: S-38
description: >
  Orchestrate a full FOSS product launch: knowledge extraction pipeline followed
  by all required page types (docs, blog, KB, FAQ, reference) with validation gates.
args: "{family} {platform} {repo-path}"
---

# S-38: Launch Product — Full FOSS Product Launch Orchestrator

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} {repo-path}`
Example: `launch-product words python /repos/aspose-words-python`

## Purpose

Orchestrate an end-to-end FOSS product launch from a repository path to a full set of
published-ready content pages. This skill chains the knowledge extraction pipeline with
all five page generation skills and their validation gates, so a new product can be
launched with a single invocation rather than manually sequencing ~10 skills.

**Pages produced** (minimum viable launch set):
- 2 docs pages: `getting-started/installation`, `getting-started/quick-start`
- 1 blog post: launch announcement
- 1 KB how-to: getting started guide
- 1 KB FAQ page
- Up to 10 API reference pages (top public classes by method count)

## Pre-conditions

1. The FOSS repository at `{repo-path}` must be accessible and contain Python/source files
2. A content repo must be configured (via `$CONTENT_REPO_PATH` or `config.yaml`)
3. No existing `knowledge/{family}/{platform}/` directory is required — this skill creates it

## Phase 1 — Knowledge Extraction

Run the full knowledge pipeline in sequence. Each step must succeed before proceeding.

### Step 1.1 — Scout the repository (S-34)

```
python scripts/scout.py {family} {platform} {repo-path} knowledge/{family}/{platform}/scout/
```

Or invoke: `/repo-scout {family} {platform} {repo-path}`

Expected outputs:
- `knowledge/{family}/{platform}/scout/model.yaml`
- `knowledge/{family}/{platform}/scout/api_surface.json`
- `knowledge/{family}/{platform}/scout/claims.json`
- `knowledge/{family}/{platform}/scout/formats.json`
- `knowledge/{family}/{platform}/scout/class_graph.json`
- `knowledge/{family}/{platform}/scout/limitations.md`

If scout fails → **ABORT**. Report error details and repo path to user.

### Step 1.2 — Merge knowledge (S-35)

Invoke: `/truth-merge {family} {platform}`

Expected outputs in `knowledge/{family}/{platform}/merged/`:
- `model.yaml`, `claims.json`, `api_surface.json`, `formats.json`
- `claims.md`, `api_surface.md`, `merge_report.md`
- `snippets/` directory with pre-approved code examples

If merge fails → **ABORT**.

After merge completes, read `knowledge/{family}/{platform}/merged/merge_conflicts.md` and count
conflict entries:

| Conflict count | Action |
|----------------|--------|
| 0 | Proceed normally |
| 1–5 | **WARN**: list conflict pairs in the launch report; proceed |
| > 5 | **HALT**: too many contradictions to produce reliable content. Instruct user to resolve conflicts via `/truth-sync` with a reconciling external source, then retry. |

### Step 1.3 — Index knowledge (S-31)

Invoke: `/truth-index {family} {platform}`

Expected output: `knowledge/{family}/{platform}/merged/index.json`

### Step 1.4 — Embed knowledge (S-15, conditional)

Check if a vector store is configured (look for `knowledge/_vectors/{tier}/{family}/{platform}/` or vector config in `config.yaml`).
- If configured → invoke: `/embed-knowledge {family} {platform}`
- If not configured → **SKIP** (log: "Vector store not configured — embedding skipped")

### Step 1.5 — Scan corpus (S-37)

Invoke for each site type used in Phase 2:
```
/corpus-scan {family} {platform} docs
/corpus-scan {family} {platform} blog
/corpus-scan {family} {platform} kb
/corpus-scan {family} {platform} reference
```

If no existing content is found for a site type → WARN and proceed (generation skills will use default templates).

## Confidence Gate

After Phase 1, read `knowledge/{family}/{platform}/merged/index.json` and check `api_confidence`:

| api_confidence | Action |
|----------------|--------|
| `high` | Proceed to Phase 2 normally |
| `medium` | Proceed with WARN: flag all generated pages for human review |
| `low` | **HALT** — report: "API confidence is low; cannot generate reliable content. Run `/truth-sync` with an additional external source, then retry." |

Also check `forbidden_claims` from `index.json`. These must never appear in any generated page.

## Phase 2 — Page Generation

Run each page through its full generation chain:
**S-10 → S-18 → S-19 → S-22 → S-23 → S-24 → S-01 → write**

S-22 (`faq-generate`) applicability per page type:
- Docs installation/quick-start pages: **skip S-22** — no FAQ section on procedural setup pages
- Blog post: **run S-22** — adds a FAQ section to the announcement post
- KB how-to: **run S-22** — adds a FAQ section to the how-to guide
- KB FAQ page: S-22 is **already internal** to `/new-kb-faq` — do not invoke separately
- Reference pages: **skip S-22** — FAQ sections are not part of the reference format

For each page, if S-23 (ground-check) returns FAIL:
- Revise the page once to address failed claims
- Re-run S-23
- If FAIL persists → **SKIP** this page, log the failure, continue with remaining pages

### Step 2.1 — Docs: Installation page

Invoke: `/new-docs-page {family} {platform} getting-started installation`

Target: `content/docs.aspose.org/en/{family}/{platform}/getting-started/installation.md`

### Step 2.2 — Docs: Quick-start page

Invoke: `/new-docs-page {family} {platform} getting-started quick-start`

Target: `content/docs.aspose.org/en/{family}/{platform}/getting-started/quick-start.md`

### Step 2.3 — Blog: Launch announcement

Invoke: `/new-blog-post {family} {platform} {family}-{platform}-launch`

Target: `content/blog.aspose.org/{family}/{platform}/{family}-{platform}-launch.md`

Content focus: announce the product, highlight top 3–5 features from `claims.json`, include
install command from `knowledge/{family}/{platform}/merged/install.md`, list supported formats
from `formats.json`.

### Step 2.4 — KB: Getting-started how-to

Invoke: `/new-kb-howto {family} {platform} how-to-get-started-with-{family}-{platform}`

Target: `content/kb.aspose.org/en/{family}/{platform}/how-to-get-started-with-{family}-{platform}.md`

### Step 2.5 — KB: FAQ page

Invoke: `/new-kb-faq {family} {platform}`

Target: `content/kb.aspose.org/en/{family}/{platform}/faq.md`

### Step 2.6 — Reference: Public class pages

Read `knowledge/{family}/{platform}/merged/api_surface.json`. Sort classes by method count
(descending). Generate reference pages for the top 10 public classes.

For each class `{ClassName}`:

```
/new-reference-page {family} {platform} {ClassName}
```

Target: `content/reference.aspose.org/en/{family}/{platform}/{ClassName}.md`

If there are fewer than 10 public classes → generate all of them.

## Phase 2 Post-Check — Page Count Gate

After all steps in Phase 2 complete, count outcomes:
- `pages_written` = pages that passed S-23 and were committed via S-01
- `pages_skipped` = pages that failed S-23 after retry or were denied by S-01

| Outcome | Action |
|---------|--------|
| `pages_written == 0` | **HALT** — no content written. Write a FAILED launch report (no commit). Summarize every skip reason. Instruct user to resolve ground-check failures before retrying. |
| `pages_written > 0` and `pages_skipped > 0` | **WARN** — partial launch. Mark report title as `PARTIAL`. Continue to Phase 3. |
| `pages_written > 0` and `pages_skipped == 0` | Proceed normally. Mark report title as `COMPLETE`. |

## Phase 3 — Cross-Platform Consistency (conditional)

Check `knowledge/_index.json` for sibling platforms in the same family.
- If sibling platforms exist → invoke: `/cross-platform {family} {platform}`
- If this is the first platform in the family → **SKIP**

## Phase 4 — Launch Report

Write a launch report to `reports/launch/{family}-{platform}-{timestamp}.md`.
Title the report `COMPLETE`, `PARTIAL`, or `FAILED` based on the Phase 2 Post-Check result.

```markdown
# Launch Report [{COMPLETE|PARTIAL|FAILED}] — {family}/{platform}
Date: {ISO timestamp}

## Knowledge Model
- Repository: {repo-path}
- SHA: {repo_sha from model.yaml}
- API confidence: {high | medium | low}
- Claims: {total count}
- Forbidden claims: {count}
- Merge conflicts: {count} {— see merge_conflicts.md | — none}

## Pages Generated
| Site | Path | Ground-check | Notes |
|------|------|-------------|-------|
| docs | getting-started/installation | {PASS|WARN|FAIL|SKIPPED} | |
| docs | getting-started/quick-start | {PASS|WARN|FAIL|SKIPPED} | |
| blog | {family}-{platform}-launch | {PASS|WARN|FAIL|SKIPPED} | |
| kb   | how-to-get-started | {PASS|WARN|FAIL|SKIPPED} | |
| kb   | faq | {PASS|WARN|FAIL|SKIPPED} | |
| ref  | {ClassName} × {n} | {PASS|WARN|FAIL|SKIPPED} | |

## Summary
- Pages written: {n} / {total attempted}
- Pages skipped (ground-check FAIL or S-01 DENY): {n}
- Cross-platform check: {RAN | SKIPPED}
- api_confidence flag: {none | WARN — medium confidence}
- Merge conflict flag: {none | WARN — {n} conflicts}

## Next Steps
- [ ] Human review of any WARN-flagged pages
- [ ] Resolve merge conflicts (if any): knowledge/{family}/{platform}/merged/merge_conflicts.md
- [ ] Run `/eval-page` on each written page to assign quality grades
- [ ] Commit: include knowledge SHA + ground-check PASS in commit message
```

## Output

```
LAUNCH {COMPLETE|PARTIAL|FAILED} — {family}/{platform}
Repository: {repo-path}
Knowledge SHA: {repo_sha}
API confidence: {high | medium | low}

Phase 1 — Knowledge:
  Scout:      OK
  Merge:      OK ({n} conflicts) | WARN ({n} conflicts — see merge_conflicts.md)
  Index:      OK
  Embed:      OK | SKIPPED
  Corpus:     OK (docs, blog, kb, reference)

Phase 2 — Pages:
  Written:    {n}
  Skipped:    {n}

Phase 3 — Cross-platform: OK | SKIPPED

Launch report: reports/launch/{family}-{platform}-{timestamp}.md
```

## Post-conditions

- Full knowledge model exists in `knowledge/{family}/{platform}/merged/`
- Minimum viable page set exists in content directories
- Every written page has passed S-23 (ground-check)
- Every written page has evidence citations from S-24
- Launch report exists at `reports/launch/{family}-{platform}-{timestamp}.md`

## Error handling

- Scout fails → ABORT entire launch; no content written
- Merge or index fails → ABORT; scout outputs are preserved for retry
- Individual page ground-check fails after retry → SKIP that page, continue
- Confidence gate = low → HALT before any page generation
- S-01 path-guard DENY on any page → SKIP that page, log the denial
