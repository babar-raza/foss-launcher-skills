# Phase 08 — Rollback Notes

**Sprint:** 2026-06-11-recruitize-foss-launcher

---

## Rollback Procedure

If sprint changes need to be reverted, the following commits are involved:

| Commit | Content | Reversible? |
|--------|---------|-------------|
| 3511124 | Concurrency note in run_outcome_log.py | Yes — `git revert 3511124` |
| 73d2fc8 | ADRs, runbooks, input validation, coverage gate | Yes — `git revert 73d2fc8` |
| 303a7f2 | adaptive_retry.py, run_outcome_log.py, 4 test files | Yes — `git revert 303a7f2` |
| e37b4a3 | CODEOWNERS, CHANGELOG, CONTRIBUTING, SECURITY, governance docs | Yes — `git revert e37b4a3` |

**Note:** Each `git revert` creates a new commit that undoes the target commit's changes. This preserves history.

---

## Selective Rollback

If only specific changes need reverting:

### Revert input validation only
```bash
git revert 73d2fc8 --no-commit
# Then selectively unstage the non-validation files
git reset HEAD docs/adr/ docs/runbooks/ .github/workflows/pipeline-tests.yml
git checkout -- docs/adr/ docs/runbooks/ .github/workflows/pipeline-tests.yml
git commit -m "revert: remove input validation from adaptive_retry.py"
```

### Revert coverage threshold only
```bash
git checkout e7d8f68 -- .github/workflows/pipeline-tests.yml
git commit -m "revert: lower coverage threshold back to 11%"
```

---

## Post-Rollback State

After full rollback to pre-sprint state (before e37b4a3):
- CODEOWNERS, CHANGELOG.md, CONTRIBUTING.md, SECURITY.md: untracked
- adaptive_retry.py, run_outcome_log.py, test files: untracked or absent
- docs/adr/, docs/runbooks/: absent
- Coverage threshold: 11%
- Estimated S score: ~8-15 (R sigmoid gate fires)

---

## No Destructive Operations Required

All sprint changes are additive (new files, new content). No existing files were deleted.
Rollback is low-risk.
