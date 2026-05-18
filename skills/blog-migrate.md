<!-- CONTRACT: agent-executed
     purpose: governed folder slug migration for blog.aspose.org WEAK/BAD slugs
     preconditions: candidates JSON with MIGRATION_READY slugs from blog_slug_inventory.py; Hugo build passing
     postcondition: renamed folders with aliases + inbound-link rewrites; applied.json + rollback.json in reports/blog-slugs/; Hugo build still passing; S-23 clean
     idempotent: no — renames are one-way; rollback.json enables undo
     verified: 2026-05-13
     id: S-100
     depends_on: [S-23, S-76]
     backing_script: scripts/pipeline/commands/migration/blog_folder_migrate.py
-->

# S-100: Blog Migrate — Governed Blog Folder Slug Migration

**Arguments**: `$ARGUMENTS`
**Expected format**: `{candidates_json_path} [--dry-run | --apply]`

- `candidates_json_path` — Path to a JSON file with MIGRATION_READY candidates (from blog_slug_inventory.py or hand-crafted per §6f policy)
- `--dry-run` — Show what would happen; no files changed (default if neither flag given)
- `--apply` — Execute renames, alias writes, inbound-link rewrites, manifest writes

## Purpose

Migrate blog post folder slugs from WEAK or BAD quality to OK quality by:

1. Renaming the post directory (`old_slug/` → `new_slug/`)
2. Updating `source_file:` frontmatter in all 36 locale copies
3. Adding `aliases: [/old/url/]` to the English `index.md` (redirect preservation)
4. Rewriting inbound body references in other blog posts that link to the old URL
5. Updating `site_plan.yaml` if it references the old slug
6. Writing `applied.json` (manifest) and `rollback.json` (undo instructions)

**Not a content generation skill.** Never modifies post title, body prose, evidence, grade, or provenance.

## BSM-TC-07 WEAK Migration Policy Gate (14 criteria — ALL required)

Before adding any candidate to the candidates JSON, verify all 14:

**Pre-migration (9 criteria):**
1. Target slug passes `validate_folder_slug()` — 0 violations
2. Post is NOT draft (`draft: false` or absent)
3. `auto_updatable: true` in provenance
4. Source folder exists; target folder absent
5. Alias path confirmed (`aliases: [/{family}/{platform}/{old_slug}/]`)
6. All locale `source_file:` updates enumerated in candidates JSON
7. Inbound links fully inventoried (`inbound_link_count` from blog_slug_inventory.py)
8. Dry-run exit 0, counts match plan
9. Cross-subdomain risks documented (absolute URL refs treated as alias-safe if external)

**Post-apply (5 criteria):**
10. Hugo build exit 0; redirect HTML at old URL with correct canonical
11. S-23 (`/content-check`): 0 FAIL
12. Blog slug tests pass: `pytest scripts/pipeline/tests/test_blog_slug_policy.py -q`
13. Commit contains only expected renames + alias additions + locale source_file updates
14. IV: aliases, source_file, file counts confirmed from HEAD

**Explicit exclusions:** draft posts, target slug conflicts, `auto_updatable: false`, ambiguous platform posts.

## Execution Steps

### Step 1 — Pre-flight (always)

```bash
# Confirm no uncommitted changes in blog content
git status --short content/blog.aspose.org/

# Confirm candidates JSON is valid
PYTHONPATH=scripts/pipeline .venv/Scripts/python -m json.tool {candidates_json_path} > /dev/null

# Verify all 14 pre-migration criteria for each candidate (manual checklist)
```

### Step 2 — Dry-run (required before apply)

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python \
  scripts/pipeline/commands/migration/blog_folder_migrate.py \
  --candidates {candidates_json_path} \
  --dry-run
```

Verify output:
- Candidate count matches plan
- Alias URL shown for each post
- Inbound link count shown (0 is OK; >0 means rewrites will run)
- No SKIP entries unless expected

### Step 3 — Apply (after operator approval)

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python \
  scripts/pipeline/commands/migration/blog_folder_migrate.py \
  --candidates {candidates_json_path} \
  --apply
```

### Step 4 — Post-apply verification

```bash
# 4a. Verify renames
git status --short content/blog.aspose.org/

# 4b. Verify alias added to English index.md
grep -A2 "^aliases:" content/blog.aspose.org/{family}/{platform}/{new_slug}/index.md

# 4c. Verify source_file updates in locale files
grep "source_file:" content/blog.aspose.org/{family}/{platform}/{new_slug}/index.*.md | head -5

# 4d. Verify old folder absent
ls content/blog.aspose.org/{family}/{platform}/{old_slug}/ 2>/dev/null && echo "ERROR: old folder still exists"

# 4e. Run S-23 on migrated post
PYTHONPATH=scripts/pipeline .venv/Scripts/python \
  scripts/pipeline/commands/content/audit.py \
  --files content/blog.aspose.org/{family}/{platform}/{new_slug}/index.md

# 4f. Run blog slug tests
PYTHONPATH=scripts/pipeline .venv/Scripts/python -m pytest \
  scripts/pipeline/tests/test_blog_slug_policy.py -q

# 4g. Verify new slug is OK quality
PYTHONPATH=scripts/pipeline .venv/Scripts/python -c "
from lib.blog_slug_policy import classify_folder_slug_quality
r = classify_folder_slug_quality('{new_slug}', '{family}', '{platform}')
print(r['quality'], r['violations'])
"
```

### Step 5 — Commit (using S-76)

Invoke `/commit` with:
- `Skills invoked: [S-100]`
- Scope: `fix(blog)` per Conventional Commits
- Body: list each rename as `{old_slug} → {new_slug} ({family}/{platform})`
- Include: applied manifest path, rollback manifest path
- Include: inbound link rewrite count (if >0)

**Do NOT use `git commit` directly.** Use `/commit` (S-76) for full governance trail.

## Governance

This skill is the **registered path** for blog slug migration. Commits made via S-100 do NOT
require `SKIP_SKILL_COMMIT_CHECK`. The pre-commit hook accepts `Skills invoked: [S-100]`.

If invoked before this skill was registered (BSM-TC-03, BSM-TC-04, BSM-TC-06):
the historical bypass was `GOV_BYPASS_TASKCARD=BSM-TC-0X SKIP_SKILL_COMMIT_CHECK=1`.

## Rollback

If post-apply validation fails, rollback using the generated `rollback.json`:

```bash
# Read rollback commands
cat reports/blog-slugs/migration-{timestamp}-rollback.json | .venv/Scripts/python -m json.tool

# Execute git mv commands from rollback_commands array
# Restore locale files: git checkout content/blog.aspose.org/{family}/{platform}/{old_slug}/

# Or full git revert:
git revert {commit_sha}
```

## Output Artifacts

| Artifact | Path | Contents |
|----------|------|---------|
| Applied manifest | `reports/blog-slugs/migration-{timestamp}-applied.json` | Per-candidate result: old_slug, new_slug, alias_update, inbound_link_updates, source_file_updates, site_plan_changes |
| Rollback manifest | `reports/blog-slugs/migration-{timestamp}-rollback.json` | `git mv` commands + undo_alias instructions to reverse the migration |

## Safety Rules (enforced by script)

- Never adds `slug:` to any frontmatter
- Only adds `aliases:` to the English `index.md` (never locale files)
- Never modifies title, date, evidence, grade, or provenance fields
- Never modifies post body content (other than inbound link URL rewrites)
- Fails if target folder already exists
- Fails if new slug still fails policy validation after rename
- Skips posts with `auto_updatable: false`
- Atomic writes via `os.replace()` — partial writes leave no corrupt files

## Related Skills

| Skill | Relationship |
|-------|-------------|
| S-23 (content-check) | Post-migration quality gate — 0 FAIL required |
| S-76 (commit) | Commit skill for migration commits |
| S-88 (backlog) | Tracks BSM taskcards and candidate batches |

## Backing Script

`scripts/pipeline/commands/migration/blog_folder_migrate.py`

Run `python scripts/pipeline/commands/migration/blog_folder_migrate.py --help` for full CLI reference.
