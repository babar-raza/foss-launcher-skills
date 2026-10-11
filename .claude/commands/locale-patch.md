<!-- CONTRACT: scripts/pipeline/commands/content/locale_patch.py
     purpose: propagate a targeted text fix from a fixed English source file to its locale copies
     preconditions: English source already fixed; a reconciliation_store.py record exists for it
     postcondition: matching locale files patched (byte-identical old_text match only), report written
     idempotent: yes -- re-running with the same patches is a no-op once applied (old_text is gone)
     verified: 2026-09-10
-->
# S-75: locale-patch — Propagate targeted text fixes to locale files

**PKGINSTALL-LOCALE-PATCH-MODULE (2026-09-10):** this skill is now backed by a
real, tested, committed module,
`scripts/pipeline/commands/content/locale_patch.py` — replacing the ad hoc,
write-once-delete-after-use script ST-054 TC-07 used to apply this same
algorithm at scale (250 real locale files across 3 products). The steps
below still describe the algorithm precisely (useful context for anyone
reading or extending the module), but invoke the module directly rather
than re-deriving the logic by hand:

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/content/locale_patch.py \
  {family} {platform} {site} {source_file} --patches-json {patches.json} --dry-run
```

The module adds one capability this skill's own steps below never had: it
refuses to run at all (`readiness_blocked: true`) unless
`reconciliation_store.py` shows the English source is no longer
`representation=literal` and carries no unresolved
`COLLISION_RISK_STRUCTURAL` classification — giving the "Pre-condition:
English source file already fixed" note below (previously just a
disclaimer) a real, enforced check. It also runs every proposed batch
through `install_change_budget.py`'s blast-radius check before writing
(mechanism `locale_propagation`) — see governing plan section R.3.5/R.3.6.

Propagate targeted text fixes from a fixed English source content file to all locale translation copies of that file, without re-translating the entire page.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{family} {platform} {site} {source_file}` plus patches specification

## When to use
After fixing a content bug in an English source file that has locale translations (e.g., `index.zh.md`, `index.de.md`, or locale directory variants), use this skill to apply the same fix to all locale copies.

## Inputs
- `family`: product family (e.g., `3d`, `slides`, `email`)
- `platform`: language platform (e.g., `python`, `net`, `java`)
- `site`: site name (e.g., `blog`, `kb`, `docs`)
- `source_file`: path to the fixed English source file (relative to content root)
- `patches`: list of patch objects, each with:
  - `old_text`: exact text to find and replace
  - `new_text`: replacement text
  - `context` (optional): a line of surrounding context to narrow the match
- `dry_run`: true/false (default: true for safety)

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-75 --scope "*"
> ```


1. **Parse arguments**: Extract family, platform, site, source_file from `$ARGUMENTS`. If patches are not in arguments, ask the user to provide them before proceeding.

2. **Discover locale files**: Find all locale variants of the source file:
   - Same directory: glob `{basename}.??.md` and `{basename}.??-??.md` patterns
   - Sibling locale directories (e.g., `../zh/`, `../de/`) containing the same filename
   - Search depth: up to 3 levels from source file directory

3. **For each locale file**:
   a. Read the file content
   b. For each patch:
      - If `context` is provided: check that `old_text` appears within 5 lines of a line containing `context`; if not, mark as `skipped`
      - If `old_text` is found: apply replacement of `old_text` → `new_text`, mark as `applied`
      - If `old_text` not found: mark as `not_found`
   c. If `dry_run: false` and at least one patch was `applied`: write the modified file

4. **Generate report**: Write patch report to `reports/agents/locale-patch/{family}-{platform}-{YYYYMMDD-HHMMSS}/patch_report.md`:

   ```markdown
   # Locale Patch Report
   **Source**: {source_file}
   **Dry run**: {true/false}
   **Date**: {timestamp}

   | Locale File | Patch # | old_text (first 50 chars) | Status |
   |-------------|---------|--------------------------|--------|
   | index.zh.md | 1       | mesh.control_points.appe | applied |
   | index.de.md | 1       | mesh.control_points.appe | not_found |

   ## Summary
   - Files scanned: N
   - Files modified: M
   - Patches applied: K
   - Patches not_found: J
   - Patches skipped: L
   ```

5. **Post-patch validation** (if dry_run: false and files modified):
   - Run: `.venv/Scripts/python scripts/pipeline/commands/content/validate_frontmatter.py --files {modified_files}`
   - Report any validation failures

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-75 --status completed
> ```

## Safety rules
- **Always run with `dry_run: true` first** and inspect the report before applying
- Never patch locale files that have diverged significantly from source (if context doesn't match, skip)
- Run `validate_frontmatter.py` on all modified files after patching
- Run `S-51 content-eval` on a sample of modified files to verify grades are not degraded

## Skill chain position
- Pre-condition: English source file already fixed (not this skill's responsibility)
- This skill only propagates changes — it does not create new content
- Post-condition: run `validate_frontmatter.py` + spot-check content-eval

## Example invocation
```
Apply S-75 locale-patch to propagate the mesh._control_points fix:
- family: 3d, platform: python, site: blog
- source_file: content/blog.aspose.org/3d/python/how-to-create-3d-mesh/index.md
- patches:
  - old_text: "mesh.control_points.append"
    new_text: "mesh._control_points.append"
    context: "control_points"
- dry_run: true
```
