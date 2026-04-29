---
name: launch-rollback
description: >
  Revert one product's generated content files without touching system scripts
args: "{family} {platform}"
---

# S-79: Launch Rollback — Revert One Product's Generated Content

**Arguments**: $ARGUMENTS
**Expected format**: `{family} {platform}` — e.g. `cells net` or `slides python`

## Purpose

Revert all generated content files for a specific `{family}/{platform}` product back to their
last committed git state, without affecting system files (scripts/, .agents/, reports/, knowledge/).

Used after a flawed launch is detected to clean the working tree before a corrected relaunch.

## Pre-conditions

- Git working tree is clean for system files (no uncommitted changes to scripts/, .agents/).
  If system files are dirty, STOP and ask the operator to commit or stash them first.
- `reports/plans/{family}/{platform}/site_plan.yaml` must exist (created by `/site-plan`).
  The site plan is the authoritative list of generated content files.

## Execution Steps

### Step 1 — Read site plan

```
Read: reports/plans/{family}/{platform}/site_plan.yaml
```

Collect every `path:` value under `sections.products.pages`, `sections.blog.pages`,
`sections.docs.pages`, `sections.kb.pages`, and `sections.reference.pages`.

### Step 2 — Classify each file

For each path:
- If file exists in git history (`git ls-files {path}` returns the path): mark as **revert**
- If file is untracked (new, not in git): mark as **delete**
- If file does not exist at all: mark as **skip**

### Step 3 — Produce rollback manifest (dry run first)

Write `reports/rollback/{family}/{platform}/{date}.md` with three tables:
1. Files to revert (git checkout HEAD -- {path})
2. Files to delete (not in git, will be removed)
3. Files skipped (already absent)

Show the manifest to the operator. Do NOT execute until operator confirms.

### Step 4 — Execute rollback

On operator confirmation:

For **revert** files:
```bash
git checkout HEAD -- {path}
```

For **delete** files:
```bash
rm {path}
```

Also revert locale translation variants if present (e.g. `content/docs.aspose.org/ar/cells/net/`
through `zh`). These follow the same site plan slugs under locale prefixes.

### Step 5 — Verify

```bash
git status
```

Expected: no staged changes; all content files for the product should be absent from `git status`
modified list (either reverted to HEAD or deleted).

Report: `{N} files reverted, {M} files deleted, {K} files skipped.`

## Failure Modes

| Condition | Action |
|-----------|--------|
| site_plan.yaml not found | STOP — run `/site-plan {family} {platform}` first |
| System files have uncommitted changes | STOP — ask operator to commit system changes first |
| `git checkout HEAD -- {path}` fails for a file | Log as WARNING; continue with remaining files |
| File is in a subdirectory with mixed content | Do NOT rm -rf; only remove listed files individually |

## Acceptance Criteria

- All content files listed in site_plan.yaml are either reverted to HEAD or deleted
- `git status` shows no staged changes and no modified content files for this product
- Rollback manifest written to `reports/rollback/{family}/{platform}/{date}.md`
- System files (scripts/, .agents/, reports/plans/, knowledge/) are NOT touched

## Related Skills

- `/site-plan {family} {platform}` — generates the site_plan.yaml that this skill reads
- `/launch-product {family} {platform}` — re-runs the launch after rollback
- `/knowledge-coverage-audit {family} {platform}` — S-80, disposition all knowledge units

## Registry

**Skill code**: S-79
**Status**: REGISTERED — AGENTS.md §12 / [docs/registries/skills.md](../docs/registries/skills.md) entry added 2026-04-07
**Script**: `scripts/pipeline/commands/launch/launch_rollback.py`
**Test**: `scripts/pipeline/tests/test_launch_rollback.py` (to be created)
