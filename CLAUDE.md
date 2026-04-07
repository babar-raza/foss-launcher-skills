# CLAUDE.md — Session Gate

This file contains **no operational rules**. All governance, skill chains,
write-path enforcement, evidence requirements, and task protocols live
exclusively in `AGENTS.md`.

## Mandatory First Action

You must read `AGENTS.md` in full before doing anything else in this session.
Use the Read tool now:

  Read: AGENTS.md

Do not begin any task, respond to any request, or invoke any skill until
`AGENTS.md` is in your active context. If you cannot read it (file missing,
path error), stop and report the failure — do not proceed with cached memory
of its contents.

## After Reading AGENTS.md

Follow §2 (Read Order) in AGENTS.md exactly. The session start checklist is
in AGENTS.md §3 (Mental Model Refresh Protocol).

## Sites & Content Paths (reference only — not rules)

| Site | Config | Content |
|------|--------|---------|
| docs.aspose.org | `configs/docs.aspose.org.toml` | `content/docs.aspose.org/en/{family}/{platform}/` |
| blog.aspose.org | `configs/blog.aspose.org.toml` | `content/blog.aspose.org/{family}/{platform}/` |
| kb.aspose.org | `configs/kb.aspose.org.toml` | `content/kb.aspose.org/en/{family}/{platform}/` |
| products.aspose.org | `configs/products.aspose.org.toml` | `content/products.aspose.org/en/{family}/` |
| reference.aspose.org | `configs/reference.aspose.org.toml` | `content/reference.aspose.org/en/{family}/{platform}/` |

This table is for orientation only. Path enforcement rules are in AGENTS.md §4.

## Available Commands (Quick Reference)

Skills are invoked as slash commands:

```
/skill-name {arguments}
```

| Category | Commands |
|----------|---------|
| Knowledge | `/knowledge-update`, `/repo-scout`, `/knowledge-enrich`, `/truth-merge`, `/stale-detect`, `/knowledge-diff` |
| Generation | `/page-plan`, `/page-draft`, `/faq-generate`, `/new-docs-page`, `/launch-product`, `/batch-reference` |
| Repair | `/page-update`, `/page-enhance`, `/heal-page`, `/batch-remediate`, `/gap-apply`, `/evidence-repair` |
| Validation | `/content-check`, `/eval-page`, `/content-eval`, `/gap-eval`, `/content-audit`, `/link-validate` |
| Operations | `/update-registry`, `/family-sync`, `/translate`, `/getting-started`, `/session-start`, `/commit` |

Full list and argument syntax: `.claude/commands/README.md`
Authoritative registry: `AGENTS.md §12`