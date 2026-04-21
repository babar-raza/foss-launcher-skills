# Skill Parity Program — Artifact Index

This directory contains all artifacts produced by the aspose.org → foss-launcher-skills-gitlab
skill parity and migration program. Treat these files as living documents; they are updated
as each taskcard completes.

## Program Goal

Ensure `foss-launcher-skills-gitlab` provides equivalent or better practical skill features
and behavior as the embedded skills system in `aspose.org`, while remaining cleaner,
better organized, and better governed.

## Reference Repositories

| Repo | Role | Path |
|------|------|------|
| `aspose.org` | Reference implementation (READ-ONLY) | `D:\onedrive\Documents\GitHub\aspose.org` |
| `foss-launcher-skills-gitlab` | Target (all work lands here) | `C:\Users\prora\OneDrive\Documents\GitHub\foss-launcher-skills-gitlab` |

## Artifacts

| File | Status | Description |
|------|--------|-------------|
| [inventory-aspose.md](inventory-aspose.md) | COMPLETE | Full normalized skill inventory for aspose.org (76 skills) |
| [inventory-foss.md](inventory-foss.md) | COMPLETE | Full normalized skill inventory for foss-launcher (42 skills) |
| [parity-matrix.md](parity-matrix.md) | COMPLETE | Cross-repo capability comparison with parity status |
| [gap-report.md](gap-report.md) | COMPLETE | All gaps classified with evidence and priority |
| [id-mapping.md](../../docs/id-mapping.md) | PENDING | Cross-reference of aspose.org S-XX IDs to foss-launcher IDs |
| [verification-log.md](verification-log.md) | PENDING | Non-destructive verification evidence |
| [closure-report.md](closure-report.md) | PENDING | Final parity closure summary |

## Key Findings (Summary)

- **aspose.org:** 76 skills, 8 internal, 68 user-callable; IDs S-01 to S-92
- **foss-launcher:** 42 skills (all user-callable); IDs S-01 to S-55
- **ID divergence:** S-XX numbers diverge after ~S-42. Same ID ≠ same skill. Compare by slug.
- **Missing from foss-launcher:** 43 skills (41 prompt-only + no-downgrade-guard + content-check status unclear)
- **Infrastructure gaps:** No CI workflows, no git hooks, sync only covers .claude/commands
- **foss-launcher advantages:** Evidence pipeline, 16-evaluator content_eval, schema validation, YAML registry, installer scripts

## Migration Decisions

| Decision | Choice |
|----------|--------|
| Translator system | Port fully (all scripts + skills) |
| Gap-eval vs evidence pipeline | Port gap-eval as parallel skills; both coexist |
| New skill IDs | Continue from S-56 in foss-launcher |
