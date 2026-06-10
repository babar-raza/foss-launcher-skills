# S-60: Launch Rollback — Revert One Product's Generated Content

**Arguments**: $ARGUMENTS
**Expected format**: `{family} {platform}` — e.g. `cells net` or `slides python`

## Purpose

Revert all generated content files for a specific `{family}/{platform}` product back to their
last committed git state, without affecting system files (scripts/, .agents/, reports/, knowledge/).

Used after a flawed launch is detected to clean the working tree before a corrected relaunch.

## Pre-conditions

1. Working tree has uncommitted content changes for the product
2. The last committed state is a valid rollback target (not itself flawed)
3. This skill must be invoked by a human operator — not invoked automatically

## Scope Boundaries

**Rolls back** (content only):
- `$CONTENT_REPO_PATH/content/products.aspose.org/en/{family}/{platform}/`
- `$CONTENT_REPO_PATH/content/docs.aspose.org/en/{family}/{platform}/`
- `$CONTENT_REPO_PATH/content/blog.aspose.org/{family}/{platform}/`
- `$CONTENT_REPO_PATH/content/kb.aspose.org/en/{family}/{platform}/`
- `$CONTENT_REPO_PATH/content/reference.aspose.org/en/{family}/{platform}/`

**Never rolls back** (system files):
- `scripts/`, `.agents/`, `.kilocode/`, `.claude/`
- `knowledge/`, `reports/`, `.github/`
- `skills/`, `AGENTS.md`, `CLAUDE.md`

## Steps

1. **Parse arguments**: Extract `{family}` and `{platform}`.

2. **Inventory dirty content files** for the product:
   ```bash
   git diff --name-only HEAD -- "content/**/{family}/{platform}/**"
   git ls-files -m -o --exclude-standard -- "content/**/{family}/{platform}/**"
   ```
   Print the list for operator review.

3. **Confirm rollback** with operator: Present the file count and ask for explicit confirmation before proceeding.

4. **Revert to last committed state**:
   ```bash
   git checkout HEAD -- content/products.aspose.org/en/{family}/{platform}/
   git checkout HEAD -- content/docs.aspose.org/en/{family}/{platform}/
   git checkout HEAD -- content/blog.aspose.org/{family}/{platform}/
   git checkout HEAD -- content/kb.aspose.org/en/{family}/{platform}/
   git checkout HEAD -- content/reference.aspose.org/en/{family}/{platform}/
   ```

5. **Remove untracked new files** (files not in git):
   ```bash
   # Dry-run first:
   git clean -n -- content/**/{family}/{platform}/

   # Execute (after operator confirms):
   git clean -f -- content/**/{family}/{platform}/
   ```

6. **Verify working tree is clean** for the product:
   ```bash
   git status -- content/**/{family}/{platform}/
   ```
   Must show no modified or untracked files in the product's content paths.

7. **Summary report**:
   ```
   LAUNCH ROLLBACK — {family}/{platform}
   Files reverted: N
   Untracked files removed: N
   Working tree: CLEAN
   Ready for relaunch: /launch-product {family} {platform}
   ```

## Post-conditions

- Content working tree clean for the product (no uncommitted changes)
- System files unchanged
- Ready for corrected relaunch via S-38 (launch-product)

## Hard rules

- Never roll back without explicit operator confirmation
- Never delete files outside content/ paths
- Never use `git reset --hard` — only `git checkout HEAD --` per-path
