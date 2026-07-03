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

## Translation (Single Page)

```
/ht-translate {src_path} {site} {locales}
  -> hugo-translator CLI (--site explicit, --validation-mode normal, --force-accept)
  -> dry-run pass
  -> live translation to OUTPUT_TMP
  -> manual review of output
  -> copy step to content/{site}/{lang}/
  -> /commit (S-76)
```

The `{site}` argument is mandatory. No site profile = no translation.
Valid site profiles: `docs.aspose.org`, `kb.aspose.org`, `products.aspose.org`,
`reference.aspose.org`, `blog.aspose.org`, `www.aspose.org`.

## Translation (Batch)

```
/ht-translate-batch {family} {platform} {site} {locales}
  -> scope estimation (warn if >500 jobs)
  -> hugo-translator CLI (--site explicit, --validation-mode normal, --force-accept)
  -> dry-run pass
  -> live batch translation to OUTPUT_TMP
  -> spot-check 3-5 output files
  -> copy step to content/{site}/{lang}/
  -> /commit (S-76)
```

www.aspose.org requires `--force-retranslate --force-restart`.
blog.aspose.org must use m2m100_418m model only (not m2m100_1.2b -- OOM).

## Locale Patch (Targeted Fix)

```
S-75 (locale-patch) -> patch discovery -> apply -> validate_frontmatter.py
```

## Post-Body-Refresh Re-Translation

```
S-105 (body-refresh) -> S-107 (locale-refresh-handoff)
  -> < 3 sentences changed: S-75 (locale-patch)
  -> >= 3 sentences changed: S-56 (new-docs-page) for full re-translation
```

## Production Localization Incident

```
S-109 (production-localization-incident)
  -> containment + forensics
  -> rectification via S-HT-01 / S-HT-02 (hugo-translator, explicit --site)
  -> hardening via S-99 (pipeline-harden)
```

## Retired Translation Paths (DO NOT USE)

The following are permanently retired and must not be recreated:
- `/translate` -> was dispatcher to S-52/S-53; now tombstone
- `S-52 translate-page` -> deleted; internal `python -m translator` package deleted
- `S-53 translate-batch` -> deleted; internal `python -m translator` package deleted
- `scripts/translator/` -> deleted; no fallback

## Archive

Pre-refactor version:
[docs/_archive/pre-refactor/workflows/skill-chains.md](../_archive/pre-refactor/workflows/skill-chains.md)
