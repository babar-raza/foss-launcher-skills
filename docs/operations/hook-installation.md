# Hook Installation

Status: Current
Audience: Operator, Contributor
Canonical reference: `docs/reference/governance-gates.md`
Last code-backed audit: 2026-07-04

The hook installer is `scripts/install-hooks.sh`.

## Initial Installation

Run after cloning:

```bash
bash scripts/install-hooks.sh
```

It installs four hooks into `.git/hooks/`:

| Hook | Source | Purpose |
|------|--------|---------|
| `pre-commit` | `scripts/pre-commit-audit.sh` | Path guard, deletion gate (Step 1), API audit |
| `commit-msg` | `scripts/commit-msg-skills.sh` | Skills invoked field, DGR token validation |
| `post-commit` | `scripts/post-commit-override.sh` | Override token consumption |
| `reference-transaction` | inline | Auto-unshallow shallow clones |

## Re-syncing After Governance Updates

`.git/hooks/` is not tracked by git. When governance hooks change upstream
(e.g., a commit adding the deletion gate Step 1), your local hook stays stale
and new gates will not run. Re-run the installer after any major hook update:

```bash
bash scripts/install-hooks.sh
```

**Signal:** if `git rm` of a tracked T-01 file commits without blocking, the
pre-commit hook is stale. Re-run the installer immediately.

## Verifying Current State

```bash
# Confirm installed hook matches source
diff .git/hooks/pre-commit scripts/pre-commit-audit.sh && echo "pre-commit: current"

# Confirm line count matches (current source is 808 lines as of 2026-07-04)
wc -l .git/hooks/pre-commit
```

If `diff` shows differences, re-run `bash scripts/install-hooks.sh`.

## Manual Fallback

If the installer fails, copy manually:

```bash
cp scripts/pre-commit-audit.sh   .git/hooks/pre-commit   && chmod +x .git/hooks/pre-commit
cp scripts/commit-msg-skills.sh  .git/hooks/commit-msg   && chmod +x .git/hooks/commit-msg
cp scripts/post-commit-override.sh .git/hooks/post-commit && chmod +x .git/hooks/post-commit
```

## Related

- [Governance gates reference](../reference/governance-gates.md) — what each hook enforces
- [Deletion governance](../DELETION_GOVERNANCE.md) — DGR protocol and deletion gate behavior
