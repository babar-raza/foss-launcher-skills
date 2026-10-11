# Maintenance Workflow

> Source: AGENTS.md §9
> Status: Current (restored from archive 2026-06-24)
> Override token: 20260624-113217-docs-workflows-mental-model-refresh-md

**Trigger**: upstream FOSS repo has changed since last knowledge extraction — i.e.,
`stale_since` in `knowledge/{family}/{platform}/merged/model.yaml` is not null.

## Canonical Path — Use This

```bash
/refresh-product {family} {platform}
```

S-84 orchestrates the complete chain:
1. S-12 (knowledge-diff) — detect + fetch upstream
2. S-14 (knowledge-update) — re-scout + enrich + promote
3. S-82 (delta-site-plan) — plan page adds/removes/updates
4. S-20 (page-update) — update stale pages
5. S-62 (batch-reference) — regenerate modified reference pages
6. S-48 (family-sync) — update family landing pages
7. S-23 (content-check) — audit all changed files
8. S-65 (link-validate) — verify no broken cross-subdomain links
9. S-76 (commit) — commit with audit trail

**Exit early**: If S-12 reports SHAs match (no upstream change), the chain exits cleanly.

## Detect-Only (No Changes)

```bash
/knowledge-diff {family} {platform}
```

Reports impact level (HIGH/MEDIUM/LOW) and sets `stale_since` if HIGH/MEDIUM.

## Archive

Pre-refactor version:
[docs/_archive/pre-refactor/workflows/maintenance.md](../_archive/pre-refactor/workflows/maintenance.md)
