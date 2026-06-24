# Skill Chains by Task

> Source: AGENTS.md §6
> Status: Current (restored from archive 2026-06-24)
> Override token: 20260624-113217-docs-workflows-mental-model-refresh-md

Skills are the **only sanctioned execution mechanism** for the task types listed below. When
your requirement matches a listed task type, follow the corresponding chain — invoking each skill
in order, passing outputs forward, and not substituting manual reasoning for any step that has a
registered skill. If your requirement does not match any listed task type, follow the protocol in
`docs/workflows/gap-escalation.md` before doing anything else.

## Initial Generation (New Page)

```
S-10 (project-phase-store) → S-18 (page-plan) → S-19 (page-draft) → S-22 (faq-generate)
→ S-23 (content-check / audit.py) → S-38 (truth-audit) → S-01 (path-guard) → write
```

## Knowledge Bootstrap

```
S-34 (repo-scout) → S-37 (knowledge-enrich) → S-35 (truth-merge) → S-31 (truth-index)
```

## Full-Product Launch (5-Subdomain)

```
S-54 (knowledge-bootstrap) → S-47 (site-plan) → S-49 (launch-product stages 1–8)
```

Every launch MUST run `/site-plan` after knowledge bootstrap and BEFORE any content generation.
The site plan output (`reports/plans/{family}/{platform}/site_plan.yaml`) is the authoritative
slug manifest. Stages that skip site-plan are in violation of this chain.

## Maintenance (Repo Changed)

Use S-84 (refresh-product) to run the full maintenance cycle:

```
/refresh-product {family} {platform}
```

S-84 orchestrates internally:
```
S-12 (knowledge-diff) → S-14 (knowledge-update) → S-82 (delta-site-plan)
→ S-20 (page-update) → S-62 (batch-reference) → S-48 (family-sync)
→ S-23 (content-check) → S-65 (link-validate) → S-76 (commit)
```

## Healing / Fix

```
S-73 (manual-edit) → S-23 (content-check) → S-90 (system-heal if multi-page)
```

## Archive

Pre-refactor version:
[docs/_archive/pre-refactor/workflows/skill-chains.md](../_archive/pre-refactor/workflows/skill-chains.md)
