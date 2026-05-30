# Git Integration

Status: Current
Audience: Operator, Contributor, Agent
Canonical reference: `docs/reference/governance-gates.md`
Last code-backed audit: 2026-05-30

Goal: integrate docs or pipeline changes without disturbing unrelated local work.

## Rules

- Inspect status before staging.
- Classify unrelated changes and leave them alone.
- Stage only the intended paths.
- Preserve history with moves when reorganizing docs.
- Do not use destructive git operations unless explicitly authorized.

## Verification

- `git status --short` shows only expected staged/unstaged files for the task.
- Renames are visible as moves where possible.
- Root docs hygiene passes after docs reorganization.

## References

- [Governance gates](../reference/governance-gates.md)
- [File contracts](../reference/file-contracts.md)
